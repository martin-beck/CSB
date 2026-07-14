// Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static const char* const modes[] = {
	"execl", "execle", "execlp", "execv", "execvp", "execvpe",
	"fexecve", "execve", "execveat", "execveat_empty",
};

static void run_exec(const char* mode)
{
	char* const argv[] = {(char*)"true", NULL};
	char* const envp[] = {(char*)"CSB_EXEC_FIXTURE=1", NULL};
	if (!strcmp(mode, "execl"))
		execl("/bin/true", "true", NULL);
	else if (!strcmp(mode, "execle"))
		execle("/bin/true", "true", NULL, envp);
	else if (!strcmp(mode, "execlp"))
		execlp("true", "true", NULL);
	else if (!strcmp(mode, "execv"))
		execv("/bin/true", argv);
	else if (!strcmp(mode, "execvp"))
		execvp("true", argv);
	else if (!strcmp(mode, "execvpe"))
		execvpe("true", argv, envp);
	else if (!strcmp(mode, "fexecve")) {
		int fd = open("/bin/true", O_RDONLY | O_CLOEXEC);
		if (fd >= 0)
			fexecve(fd, argv, envp);
	} else if (!strcmp(mode, "execve"))
		execve("/bin/true", argv, envp);
	else if (!strcmp(mode, "execveat"))
		syscall(SYS_execveat, AT_FDCWD, "/bin/true", argv, envp, 0);
	else if (!strcmp(mode, "execveat_empty")) {
		int fd = open("/bin/true", O_PATH | O_CLOEXEC);
		if (fd >= 0)
			syscall(SYS_execveat, fd, "", argv, envp, AT_EMPTY_PATH);
	}
	_exit(errno == ENOSYS ? 77 : 127);
}

static int run_one(const char* mode)
{
	pid_t pid = fork();
	if (pid < 0)
		return 1;
	if (pid == 0)
		run_exec(mode);
	int status;
	do {
		if (waitpid(pid, &status, 0) == pid)
			break;
	} while (errno == EINTR);
	return !WIFEXITED(status) || (WEXITSTATUS(status) != 0 && WEXITSTATUS(status) != 77);
}

int main(int argc, char** argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s <mode|all>\n", argv[0]);
		return 2;
	}
	if (strcmp(argv[1], "all"))
		return run_one(argv[1]);
	int failed = 0;
	for (size_t i = 0; i < sizeof(modes) / sizeof(modes[0]); i++)
		failed |= run_one(modes[i]);
	return failed;
}
