#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -eu
source helper/bm-generator-lib.sh

 : ${DIR_PROG:="./multidiff"}
 : ${JOBS:=$(nproc)}

if [ ! -d "${DIR_PROG}" ]; then
    echo "Directory ${DIR_PROG} does not exist."
    echo "Run scripts with lower numbers first, or specify directory explicitly:"
    echo "  DIR_PROG=\"/path/to/prog/files/\" $0"
    exit 1
fi

if ! find "${DIR_PROG}" -type f -name '*.prog' -print -quit | grep -q .; then
    echo "No multidiff-selected syzkaller programs found in ${DIR_PROG}." >&2
    exit 1
fi

DIR_TARGETS="../bench/targets/$(get_workspace_dir)/syz"

if [ -d "${DIR_TARGETS}" ] && find "${DIR_TARGETS}" -mindepth 1 -print -quit | grep -q .; then
  echo "$(readlink -e "${DIR_TARGETS}") is not empty." >&2
  echo "Move it aside before header generation to avoid mixing stale and new headers." >&2
  exit 1
fi

mkdir -p "${DIR_TARGETS}"

declare -A basenames=()
while IFS= read -r -d '' prog; do
  basename=$(basename "${prog}" .prog)
  if [ "${basenames[${basename}]+present}" = present ]; then
    echo "Duplicate program basename '${basename}':" >&2
    echo "  ${basenames[${basename}]}" >&2
    echo "  ${prog}" >&2
    exit 1
  fi
  basenames[${basename}]="${prog}"
done < <(find "${DIR_PROG}" -type f -name '*.prog' -print0)

find "${DIR_PROG}" -type f -name '*.prog' -print0 | xargs -0 -r -n 1 -P "${JOBS}" ./helper/prog2bm.sh

if ! find "${DIR_TARGETS}" -type f -name '*.h' -print -quit | grep -q .; then
  echo "No benchmark headers were generated in ${DIR_TARGETS}." >&2
  exit 1
fi
