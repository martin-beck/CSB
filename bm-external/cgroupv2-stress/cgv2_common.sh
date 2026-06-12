#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -u

CGV2_MOUNT="${CGV2_MOUNT:-/sys/fs/cgroup}"
BENCH_NAME="$(basename "$0")"
DURATION=3
THREADS=1
NOISE=0
INITIAL_SIZE=64
INDEX=0

usage() {
    cat <<EOF
Usage: ${BENCH_NAME} [-d seconds] [-t workers] [-s scale] [-n noise] [-i index]

  -d  benchmark duration in seconds
  -t  worker count inside this CSB execution unit
  -s  benchmark-specific scale parameter
  -n  optional no-op loop count between operations
  -i  CSB execution-unit index
EOF
}

parse_common_args() {
    while getopts ":d:t:s:n:i:h" opt; do
        case "${opt}" in
            d) DURATION="${OPTARG}" ;;
            t) THREADS="${OPTARG}" ;;
            s) INITIAL_SIZE="${OPTARG}" ;;
            n) NOISE="${OPTARG}" ;;
            i) INDEX="${OPTARG}" ;;
            h) usage; exit 0 ;;
            *) usage >&2; exit 2 ;;
        esac
    done

    case "${DURATION}${THREADS}${NOISE}${INITIAL_SIZE}${INDEX}" in
        *[!0-9]*)
            echo "all numeric arguments must be non-negative integers" >&2
            exit 2
            ;;
    esac

    if [ "${DURATION}" -lt 1 ] || [ "${THREADS}" -lt 1 ] || [ "${INITIAL_SIZE}" -lt 1 ]; then
        echo "duration, threads and initial_size must be >= 1" >&2
        exit 2
    fi
}

require_cgroup2() {
    if ! [ -f "${CGV2_MOUNT}/cgroup.controllers" ]; then
        echo "cgroup v2 mount not found at ${CGV2_MOUNT}" >&2
        exit 1
    fi
}

current_cgroup_dir() {
    local rel
    rel="$(awk -F: '$1 == "0" { print $3; exit }' /proc/self/cgroup)"
    rel="${rel#/}"
    if [ -n "${rel}" ]; then
        printf '%s/%s\n' "${CGV2_MOUNT}" "${rel}"
    else
        printf '%s\n' "${CGV2_MOUNT}"
    fi
}

create_bench_root() {
    local parent root
    parent="$(current_cgroup_dir)"
    root="${parent}/csb-${BENCH_NAME}-${$}-${INDEX}"

    if ! mkdir "${root}" 2>/dev/null; then
        root="${CGV2_MOUNT}/csb-${BENCH_NAME}-${$}-${INDEX}"
        if ! mkdir "${root}" 2>/dev/null; then
            echo "unable to create benchmark cgroup under ${parent} or ${CGV2_MOUNT}" >&2
            exit 1
        fi
    fi

    if ! grep -q '[^[:space:]]' "${root}/cgroup.controllers" 2>/dev/null &&
        [ "${parent}" != "${CGV2_MOUNT}" ] &&
        grep -q '[^[:space:]]' "${CGV2_MOUNT}/cgroup.controllers" 2>/dev/null; then
        rmdir "${root}" 2>/dev/null || true
        root="${CGV2_MOUNT}/csb-${BENCH_NAME}-${$}-${INDEX}"
        if ! mkdir "${root}" 2>/dev/null; then
            echo "unable to create benchmark cgroup under ${CGV2_MOUNT}" >&2
            exit 1
        fi
    fi

    printf '%s\n' "${root}"
}

enable_cgroup_controller() {
    local cg="$1"
    local controller="$2"

    if ! [ -f "${cg}/cgroup.controllers" ]; then
        echo "cgroup controllers file not found in ${cg}" >&2
        return 1
    fi

    if ! grep -qw "${controller}" "${cg}/cgroup.controllers"; then
        echo "${controller} controller is not available for children of ${cg}" >&2
        return 1
    fi

    if [ -f "${cg}/cgroup.subtree_control" ] && grep -qw "${controller}" "${cg}/cgroup.subtree_control"; then
        return 0
    fi

    if ! printf '+%s\n' "${controller}" > "${cg}/cgroup.subtree_control" 2>/dev/null; then
        echo "unable to enable ${controller} controller for children of ${cg}" >&2
        return 1
    fi
}

require_controller_file() {
    local cg="$1"
    local controller="$2"
    local file="$3"
    local parent

    if ! [ -f "${cg}/${file}" ]; then
        parent="$(dirname "${cg}")"
        enable_cgroup_controller "${parent}" "${controller}" || true
    fi

    if ! [ -f "${cg}/${file}" ]; then
        echo "${controller} controller is not available in ${cg}" >&2
        exit 1
    fi
}

cleanup_cgroups() {
    local root="$1"
    [ -n "${root}" ] || return 0
    if [ -d "${root}" ]; then
        find "${root}" -depth -type d -exec rmdir {} + 2>/dev/null || true
    fi
}

create_state_dir() {
    mktemp -d "/tmp/csb-${BENCH_NAME}-${$}-${INDEX}.XXXXXX"
}

cleanup_state() {
    local dir="$1"
    [ -n "${dir}" ] || return 0
    rm -rf "${dir}"
}

deadline_ns() {
    printf '%s\n' "$(($(date +%s%N) + DURATION * 1000000000))"
}

before_deadline() {
    [ "$(date +%s%N)" -lt "$1" ]
}

burn_noise() {
    local i=0
    while [ "${i}" -lt "${NOISE}" ]; do
        i=$((i + 1))
        :
    done
}

metric_line() {
    local ops="$1"
    local failures="$2"
    local elapsed_ns="$3"
    local extra="${4:-}"
    local throughput

    if [ "${elapsed_ns}" -gt 0 ]; then
        throughput="$(awk -v ops="${ops}" -v ns="${elapsed_ns}" 'BEGIN { printf "%.3f", ops * 1000000000 / ns }')"
    else
        throughput=0
    fi

    printf 'test=%s;ops=%s;failures=%s;elapsed_ns=%s;throughput=%s;threads=%s;initial_size=%s;noise=%s;%s\n' \
        "${BENCH_NAME}" "${ops}" "${failures}" "${elapsed_ns}" "${throughput}" \
        "${THREADS}" "${INITIAL_SIZE}" "${NOISE}" "${extra}"
}
