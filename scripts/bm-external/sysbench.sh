#!/bin/bash -e
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

SCRIPT_DIR="$(readlink -f $(dirname "$0")/../..)"

if [ -x "$SCRIPT_DIR/bm-external/sysbench/bin/sysbench" ]; then
	cd "$SCRIPT_DIR/bm-external/sysbench/share/sysbench/"
	exec "$SCRIPT_DIR/bm-external/sysbench/bin/sysbench" "$@"
fi

if command -v sysbench >/dev/null 2>&1; then
	cd /usr/share/sysbench
	exec sysbench "$@"
fi

echo "sysbench not found: install sysbench or run scripts/bm-external/sysbench/configure.sh" >&2
exit 127
