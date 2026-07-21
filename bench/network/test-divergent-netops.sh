#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -u

SERVER_SPEC="1w32"
CLIENT_SPEC="1w64"
CLIENT_TIMEOUT=8
SLOW_SERVER_SPEC="1r32"
SLOW_CLIENT_SPEC="1w32"
SLOW_DELAY=2
PORT=${PORT:-$((15000 + $$ % 10000))}

SERVER_PID=""
RESUME_PID=""

cleanup()
{
	if [ -n "$RESUME_PID" ] && kill -0 "$RESUME_PID" 2>/dev/null; then
		kill "$RESUME_PID" 2>/dev/null || true
		wait "$RESUME_PID" 2>/dev/null || true
	fi
	if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
		kill -CONT "$SERVER_PID" 2>/dev/null || true
		kill "$SERVER_PID" 2>/dev/null || true
		wait "$SERVER_PID" 2>/dev/null || true
	fi
}

trap cleanup EXIT

echo "Launching valid server with a ${SLOW_DELAY}s delay"
./server -p "$PORT" -P "$SLOW_SERVER_SPEC" &
SERVER_PID=$!

sleep 0.1
kill -STOP "$SERVER_PID"
(sleep "$SLOW_DELAY"; kill -CONT "$SERVER_PID" 2>/dev/null) &
RESUME_PID=$!

timeout "$CLIENT_TIMEOUT" ./client -O -R -h localhost -p "$PORT" \
	-P "$SLOW_CLIENT_SPEC"
client_ret=$?
wait "$RESUME_PID" 2>/dev/null || true
RESUME_PID=""
if [ "$client_ret" -ne 0 ]; then
	echo "Client failed while waiting for a slow valid peer: $client_ret"
	exit 1
fi
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

echo "Launching divergent server on port $PORT with $SERVER_SPEC"
./server -p "$PORT" -P "$SERVER_SPEC" &
SERVER_PID=$!

sleep 0.1
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    ret=$?
    echo "Server exited before the client could connect: $ret"
    exit 1
fi

echo "Launching divergent client with $CLIENT_SPEC"
timeout "$CLIENT_TIMEOUT" ./client -R -h localhost -p "$PORT" -P "$CLIENT_SPEC"
client_ret=$?
if [ "$client_ret" -eq 124 ]; then
    echo "Client did not exit within $CLIENT_TIMEOUT seconds"
    exit 1
fi
if [ "$client_ret" -ne 0 ]; then
    echo "Client exited with $client_ret"
    exit 1
fi

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    ret=$?
    echo "Server exited unexpectedly during divergent netops test: $ret"
    exit 1
fi

echo "Divergent netops client exited without hanging"
