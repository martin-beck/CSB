#ifndef CSB_TASK_LIFECYCLE_COMMON_H
#define CSB_TASK_LIFECYCLE_COMMON_H

#define _GNU_SOURCE
#include <errno.h>
#include <linux/sched.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define CHILD_STACK_SIZE (64 * 1024)

static inline int wait_for(pid_t pid)
{
	int status;

	while (waitpid(pid, &status, 0) < 0) {
		if (errno != EINTR)
			return 1;
	}
	return !WIFEXITED(status) || WEXITSTATUS(status) != 0;
}

static inline void *thread_main(void *unused)
{
	(void)unused;
	return NULL;
}

static inline int run_pthread(void)
{
	pthread_t thread;

	return pthread_create(&thread, NULL, thread_main, NULL) ||
	       pthread_join(thread, NULL);
}

static inline int run_fork(void)
{
	pid_t pid = fork();

	if (pid < 0)
		return 1;
	if (pid == 0)
		_exit(0);
	return wait_for(pid);
}

static inline int run_vfork(void)
{
	pid_t pid = vfork();

	if (pid < 0)
		return 1;
	if (pid == 0)
		_exit(0);
	return wait_for(pid);
}

static inline int clone_child(void *unused)
{
	(void)unused;
	return 0;
}

static inline int run_clone(void)
{
	void *stack = malloc(CHILD_STACK_SIZE);
	pid_t pid;

	if (!stack)
		return 1;
	pid = clone(clone_child, (char *)stack + CHILD_STACK_SIZE, SIGCHLD, NULL);
	if (pid < 0) {
		free(stack);
		return 1;
	}
	int ret = wait_for(pid);
	free(stack);
	return ret;
}

static inline int run_clone3(void)
{
#ifdef SYS_clone3
	struct clone_args args = { .exit_signal = SIGCHLD };
	pid_t pid = syscall(SYS_clone3, &args, sizeof(args));

	/* Seccomp commonly blocks clone3; ENOSYS still records the mapping input. */
	if (pid < 0)
		return errno == ENOSYS ? 0 : 1;
	if (pid == 0)
		_exit(0);
	return wait_for(pid);
#else
	return 0;
#endif
}

#endif
