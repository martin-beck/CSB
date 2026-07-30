#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT


if [ $# -ne 1 ]; then
  echo "Usage: $0 </path/to/prog/dir>"
  exit 1
fi

REPORT="$1/translation_report.txt"
if [ ! -f "${REPORT}" ]; then
  echo "Translation report not found: ${REPORT}" >&2
  exit 1
fi

cat "${REPORT}"
