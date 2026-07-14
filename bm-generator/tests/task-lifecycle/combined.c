#include "common.h"

int main(void)
{
	return run_pthread() || run_fork() || run_vfork() || run_clone() ||
	       run_clone3();
}
