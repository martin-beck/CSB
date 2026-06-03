/*
 * Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
 * SPDX-License-Identifier: MIT
 */
#include <arpa/inet.h>
#include <assert.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <netdb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdbool.h>
#include <sys/epoll.h>
#include <getopt.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>

#include "helper.h"

static struct extracted_op eops[128];
static size_t eops_sz = 0;

#define MAX_EVS                 16
#define MAX_IO_OPS_PER_EVENT    64
#define NETOPS_STALL_TIMEOUT_MS 1000
#define MAX_STALLED_WAITS       4

#ifndef EPOLLRDHUP
#define EPOLLRDHUP 0
#endif

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

static uint8_t *sbuf;
static size_t sbuf_size = 0;

struct conn_data {
    size_t step;
    size_t n;
    unsigned int stalled_waits;
    int last_epoll;
    int fd;
    struct conn_data *next;
};

struct epoll_st {
    int fd;
    size_t nconn;
    struct conn_data *conns;
};

static uint32_t
wait_event_for_step(size_t step)
{
    return eops[step].is_write ? EPOLLIN : EPOLLOUT;
}

static void
config_wait(struct conn_data *d, struct epoll_st *est)
{
    size_t step    = d->step;
    int next_epoll = wait_event_for_step(step);
    if (d->last_epoll == next_epoll) {
        return;
    }
    struct epoll_event ev_n;
    ev_n.events   = next_epoll | EPOLLRDHUP;
    ev_n.data.ptr = d;
    d->last_epoll = next_epoll;
    if (epoll_ctl(est->fd, EPOLL_CTL_MOD, d->fd, &ev_n) == -1) {
        perror("epoll_ctl_mod");
    }
}

static void
advance_step(struct conn_data *d)
{
    d->n++;
    if (d->n >= eops[d->step].n) {
        d->n    = 0;
        d->step = (d->step + 1) % eops_sz;
    }
}

static bool
resync_step(struct conn_data *d)
{
    bool current_dir = eops[d->step].is_write;
    for (size_t i = 1; i < eops_sz; i++) {
        size_t next = (d->step + i) % eops_sz;
        if (eops[next].is_write != current_dir) {
            d->step = next;
            d->n    = 0;
            return true;
        }
    }
    return false;
}

static void
track_conn(struct conn_data *d, struct epoll_st *est)
{
    d->next    = est->conns;
    est->conns = d;
    est->nconn++;
}

static void
untrack_conn(struct conn_data *d, struct epoll_st *est)
{
    struct conn_data **cur = &est->conns;
    while (*cur && *cur != d) {
        cur = &(*cur)->next;
    }
    if (*cur) {
        *cur = d->next;
        est->nconn--;
    }
}

static void
unregister(struct conn_data *d, struct epoll_st *est)
{
    epoll_ctl(est->fd, EPOLL_CTL_DEL, d->fd, NULL);
    close(d->fd);
    untrack_conn(d, est);
    free(d);
}

static void
handle_stalled_conn(struct conn_data *d, struct epoll_st *est)
{
    d->stalled_waits++;
    if (d->stalled_waits > MAX_STALLED_WAITS || !resync_step(d)) {
        unregister(d, est);
        return;
    }
    config_wait(d, est);
}

static void
handle_stalled_conns(struct epoll_st *est)
{
    struct conn_data *d = est->conns;
    while (d) {
        struct conn_data *next = d->next;
        handle_stalled_conn(d, est);
        d = next;
    }
}

static bool
register_new(struct epoll_st *est, struct sockaddr *serv_addr, size_t addr_size,
             bool retry_on_fail)
{
    struct epoll_event ev;
    struct conn_data *d = malloc(sizeof(struct conn_data));
    if (!d) {
        return false;
    }

    d->step          = 0;
    d->n             = 0;
    d->stalled_waits = 0;
    d->last_epoll    = wait_event_for_step(0);
    d->next          = NULL;

    int csock = socket(serv_addr->sa_family, SOCK_STREAM, 0);
    if (csock == -1) {
        fprintf(stderr, "socket failed!\n");
        free(d);
        return false;
    }
    d->fd = csock;

    int connect_ret = 0;
    do {
        connect_ret = connect(csock, serv_addr, addr_size);
        if (retry_on_fail && connect_ret != 0) {
            usleep(1000);
        }
    } while (retry_on_fail && connect_ret != 0);

    if (connect_ret == -1) {
        fprintf(stderr, "connect failed!\n");
        close(csock);
        free(d);
        return false;
    }

    setnonblocking(csock);
    ev.events   = d->last_epoll | EPOLLRDHUP;
    ev.data.ptr = d;
    if (epoll_ctl(est->fd, EPOLL_CTL_ADD, csock, &ev) == -1) {
        fprintf(stderr, "epoll_ctl failed!\n");
        close(csock);
        free(d);
        return false;
    }
    track_conn(d, est);
    printf("[Client] %zu connections established.\n", est->nconn);
    return true;
}

static void
readwrite(struct epoll_event *ev, struct epoll_st *est)
{
    struct conn_data *d = ev->data.ptr;
    int fd              = d->fd;
    bool progressed     = false;
    if ((ev->events & EPOLLERR) ||
        ((ev->events & (EPOLLHUP | EPOLLRDHUP)) &&
         !(ev->events & wait_event_for_step(d->step)))) {
        unregister(d, est);
        return;
    }

    for (size_t i = 0; i < MAX_IO_OPS_PER_EVENT; i++) {
        if (!(ev->events & wait_event_for_step(d->step))) {
            break;
        }
        assert(eops[d->step].sz < sbuf_size);
        if (eops[d->step].sz == 0) {
            advance_step(d);
            progressed = true;
            continue;
        }
        ssize_t r = 0;
        if (eops[d->step].is_write) {
            r = recv(fd, &sbuf[0], eops[d->step].sz, 0);
        } else {
            r = send(fd, &sbuf[0], eops[d->step].sz, MSG_NOSIGNAL);
        }
        if (r > 0) {
            advance_step(d);
            progressed = true;
            continue;
        }
        if (r == 0) {
            if (eops[d->step].is_write) {
                unregister(d, est);
                return;
            }
            break;
        }
        if (errno == EINTR) {
            continue;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            break;
        }
        unregister(d, est);
        return;
    }
    if (progressed) {
        d->stalled_waits = 0;
    }
    if (0 && d->step == 0) {
        unregister(d, est);
        return;
    } else {
        config_wait(d, est);
    }
}

static void
usage(const char *argv0)
{
    fprintf(stderr,
            "Usage: %s [-h host] [-p port] [-P operation_sequence | -F "
            "op_sequence_file]\n",
            argv0);
    fprintf(
        stderr,
        "Operation sequence: <NUM_TIME>[rw]<NUM_BYTES>[-operation_sequence]*, "
        "e.g. '2r1024-1w32'\n");
}

int
main(int argc, char *argv[])
{
    size_t num_conn = 1;
    uint16_t port   = 10000;
    char *host      = NULL;
    char *program   = NULL;
    char *prog_file = NULL;
    bool use_ipv6   = false;
    int opt         = 0;
    bool retry_on_fail =
        false; /* retry if the connection fails till it succeeds*/
    bool only_once = false;
    prog_file      = NULL;
    while ((opt = getopt(argc, argv, "6h:p:P:F:RO")) != -1) {
        switch (opt) {
            case 'h':
                host = optarg;
                break;
            case 'p':
                port = strtoul(optarg, NULL, 0);
                if (errno == ERANGE) {
                    perror("strtoul");
                    return -1;
                }
                break;
            case '6':
                use_ipv6 = true;
                break;
            case 'P':
                program = optarg;
                break;
            case 'R':
                retry_on_fail = true;
                break;
            case 'O':
                only_once = true;
                break;
            case 'F':
                prog_file = optarg;
                break;
            default: /* '?' */
                usage(argv[0]);
                return -1;
        }
    }

    if (program && prog_file) {
        fprintf(stderr, "Please specify the operation sequence once.\n");
        return 1;
    }

    if (prog_file) {
        program = load_prog_file(prog_file);
        if (!program) {
            fprintf(stderr,
                    "Failed to load the operation sequence from file %s\n",
                    prog_file);
        }
    }

    if (!program) {
        fprintf(stderr, "No operation sequence specified.\n");
        usage(argv[0]);
        return 'P';
    }
    long parsed_ops =
        parse_ops(program, &eops[0], sizeof(eops) / sizeof(eops[0]));
    if (parsed_ops <= 0) {
        fprintf(stderr, "Failed to parse operation sequence.\n");
        usage(argv[0]);
        return 'P';
    }
    eops_sz = (size_t)parsed_ops;

    // allocate buffer large enough
    sbuf_size = get_max_buffer_size(&eops[0], eops_sz) + 1;
    sbuf      = calloc(1, sbuf_size);
    assert(sbuf != NULL);

    if (!host) {
        fprintf(stderr, "No host specified\n");
        return 1;
    }

    struct addrinfo *result = NULL;
    struct addrinfo hints   = {
          .ai_family   = PF_UNSPEC,
          .ai_socktype = SOCK_STREAM,
          .ai_flags    = AI_CANONNAME,
    };
    int r = getaddrinfo(host, NULL, &hints, &result);
    if (r != 0) {
        fprintf(stderr, "getaddrinfo: %s", gai_strerror(r));
        return 1;
    }

    struct sockaddr *serv_addr = NULL;
    size_t addr_size           = 0;
    for (struct addrinfo *res = result; res != NULL; res = res->ai_next) {
        switch (res->ai_family) {
            case AF_INET:
                if (use_ipv6) {
                    continue;
                }
                serv_addr                                   = res->ai_addr;
                addr_size                                   = res->ai_addrlen;
                ((struct sockaddr_in *)serv_addr)->sin_port = htons(port);
                break;
            case AF_INET6:
                if (!use_ipv6) {
                    continue;
                }
                serv_addr                                     = res->ai_addr;
                addr_size                                     = res->ai_addrlen;
                ((struct sockaddr_in6 *)serv_addr)->sin6_port = htons(port);
                break;
            default:
                continue;
        }
        break;
    }
    if (!serv_addr) {
        fprintf(stderr, "No address found for host %s\n", host);
        return 1;
    }

    struct epoll_st est = {};
    est.fd              = epoll_create1(0);
    if (est.fd == -1) {
        fprintf(stderr, "epoll_create1 failed!\n");
        return 1;
    }

    for (size_t i = 0; i < num_conn; i++) {
        if (!register_new(&est, serv_addr, addr_size, retry_on_fail)) {
            return -1;
        }
    }

    signal(SIGPIPE, SIG_IGN);

    while (est.nconn) {
        struct epoll_event evs[MAX_EVS];
        int nfds =
            epoll_wait(est.fd, &evs[0], MAX_EVS, NETOPS_STALL_TIMEOUT_MS);
        if (nfds == -1) {
            continue;
        }
        if (nfds == 0) {
            handle_stalled_conns(&est);
            continue;
        }
        for (int i = 0; i < nfds; i++) {
            readwrite(&evs[i], &est);
        }
        while (est.nconn < num_conn) {
            if (!register_new(&est, serv_addr, addr_size, false)) {
                break;
            }
        }
        if (only_once) {
            break;
        }
    }
    printf("[Client] exited!\n");
    return 0;
}
