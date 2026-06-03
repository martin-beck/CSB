/*
 * Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
 * SPDX-License-Identifier: MIT
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <netdb.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <signal.h>
#include <sys/epoll.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "helper.h"
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
    size_t n;
    size_t step;
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

static struct extracted_op eops[128];
static size_t eops_sz = 0;

static uint32_t
wait_event_for_step(size_t step)
{
    return eops[step].is_write ? EPOLLIN : EPOLLOUT;
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
    if (progressed && d->step == 0) {
        unregister(d, est);
    } else {
        config_wait(d, est);
    }
}

static void
usage(const char *argv0)
{
    fprintf(stderr,
            "Usage: %s [-6] [-p port] [-P operation_sequence | -F "
            "op_sequence_file]\n",
            argv0);
    fprintf(
        stderr,
        "Operation sequence: <NUM_TIME>[rw]<NUM_BYTES>[-operation_sequence]*, "
        "e.g. '2r1023-1w32'\n");
}

int
main(int argc, char *argv[])
{
    uint16_t port   = 10000;
    char *program   = NULL;
    bool use_ipv6   = false;
    int opt         = 0;
    char *prog_file = NULL;
    while ((opt = getopt(argc, argv, "6p:P:F:O")) != -1) {
        switch (opt) {
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
        fprintf(stderr, "No operation sequence specified\n");
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

    struct epoll_event ev;
    struct epoll_st est = {};
    est.fd = epoll_create1(0);
    if (est.fd == -1) {
        fprintf(stderr, "epoll_create1 failed!\n");
        return 1;
    }
    int lsock = socket(use_ipv6 ? AF_INET6 : AF_INET, SOCK_STREAM, 0);
    if (lsock == -1) {
        fprintf(stderr, "socket failed!\n");
        return 1;
    }

    struct sockaddr_in loopback = {
        .sin_family      = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_ANY),
        .sin_port        = htons(port),
    };

    struct sockaddr_in6 loopback6 = {
        .sin6_family = AF_INET6,
        .sin6_addr   = IN6ADDR_ANY_INIT,
        .sin6_port   = htons(port),
    };

    int opt_val = 1;
    setsockopt(lsock, SOL_SOCKET, SO_REUSEPORT, &opt_val, sizeof(opt_val));

    if (bind(lsock,
             use_ipv6 ? (struct sockaddr *)&loopback6 :
                        (struct sockaddr *)&loopback,
             use_ipv6 ? sizeof(loopback6) : sizeof(loopback)) == -1) {
        return 2;
    }
    if (listen(lsock, 50) == -1) {
        return 2;
    }

    ev.events   = EPOLLIN;
    ev.data.ptr = NULL;
    if (epoll_ctl(est.fd, EPOLL_CTL_ADD, lsock, &ev) == -1) {
        return -1;
    }
    signal(SIGPIPE, SIG_IGN);
    while (true) {
        struct epoll_event evs[MAX_EVS];
        int nfds =
            epoll_wait(est.fd, &evs[0], MAX_EVS, NETOPS_STALL_TIMEOUT_MS);
        if (nfds == -1) {
            perror("epoll_wait");
            continue;
        }
        if (nfds == 0) {
            handle_stalled_conns(&est);
            continue;
        }
        for (int i = 0; i < nfds; i++) {
            if (evs[i].data.ptr == NULL) {
                int cfd = accept(lsock, NULL, 0);
                if (cfd == -1) {
                    perror("accept");
                    continue;
                }
                setnonblocking(cfd);
                struct conn_data *d = malloc(sizeof(struct conn_data));
                if (!d) {
                    perror("malloc");
                    close(cfd);
                    continue;
                }
                d->fd            = cfd;
                d->last_epoll    = wait_event_for_step(0);
                d->step          = 0;
                d->n             = 0;
                d->stalled_waits = 0;
                d->next          = NULL;
                ev.events        = d->last_epoll | EPOLLRDHUP;
                ev.data.ptr      = d;
                if (epoll_ctl(est.fd, EPOLL_CTL_ADD, cfd, &ev) == -1) {
                    perror("epoll_ctl");
                    close(cfd);
                    free(d);
                    continue;
                }
                track_conn(d, &est);
            } else {
                readwrite(&evs[i], &est);
            }
        }
    }
    return 0;
}
