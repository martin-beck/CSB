#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -e

STRACE_LOG="ls_strace.log"
APP="ls -la /dev"
../scripts/plugins/collect_strace.sh ${STRACE_LOG} ${APP}
echo "STEP#0: Initializing ..."
./00_init.sh
echo "STEP#1: Building ..."
./01_build.sh
echo "STEP#2: Parsing ${STRACE_LOG} ..."
./02_parse.sh ${STRACE_LOG}
echo "STEP#3: Extracting ..."
./03_extract.sh
echo "STEP#4: Preparing ..."
./04_prepare.sh
echo "STEP#5: Generating ..."
./05_generate.sh

echo "STEP#6: Build and test ..."
cd ../build
# We only want to build related targets not everything.
find ../bench/targets/ -name "min_ls_*.h" | grep -v syz | sed 's/.*\/\(min_ls_.*\)\.h/\1/' | xargs make
# We run only related tests
ctest -R min_ls_* --output-on-failure
