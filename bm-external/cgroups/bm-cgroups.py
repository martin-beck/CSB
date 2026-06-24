#!/usr/bin/env python3
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

import time
import argparse
import sys
import subprocess


def quiet_shell(command):
    return subprocess.check_output(command)


def launch_container(config):
    index = config.index
    runtime = config.runtime
    n_units = config.units
    iters = config.iterations
    root = config.root
    container_name = f"cgroups_{index}"

    index_max = index + n_units * iters

    try:
        quiet_shell(["chmod", "666", "/dev/stderr"])

        total_start = time.perf_counter()

        create_start = time.perf_counter()
        for i in range(index, index_max + 1, n_units):
            create_out = quiet_shell([runtime, "run", "-d", "-b", root, f"{container_name}_{i}"])
            print(f"Container create output: {create_out}", file=sys.stderr)
        create_time = time.perf_counter() - create_start

        delete_start = time.perf_counter()
        for i in range(index, index_max + 1, n_units):
            delete_out = quiet_shell([runtime, "delete", "-f", f"{container_name}_{i}"])
            print(f"Container delete output: {delete_out}", file=sys.stderr)
        delete_time = time.perf_counter() - delete_start

        total_time = time.perf_counter() - total_start
        return container_name, create_time, delete_time, total_time

    except Exception as e:
        print("Error in container lifecycle:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Container Scalability Benchmark")
    parser.add_argument("--index", type=int, help="Index of the container", default=0)
    parser.add_argument("--units", type=int, help="Number of units spawned in a test", default=1)
    parser.add_argument("--iterations", type=int, help="Number of iterations", default=100)
    parser.add_argument("--runtime", type=str, help="Container runtime to use", default="runc")
    parser.add_argument("--root", type=str, help="OCI bundle root")
    args, _ = parser.parse_known_args()

    instance_name, create_time, delete_time, elapsed = launch_container(args)
    avg_create_time = create_time / args.iterations
    avg_delete_time = delete_time / args.iterations

    print(
        f"instance_name={instance_name};"
        f"create_time={create_time:.6f};"
        f"delete_time={delete_time:.6f};"
        f"avg_create_time={avg_create_time:.6f};"
        f"avg_delete_time={avg_delete_time:.6f};"
        f"time={elapsed:.6f}"
    )
