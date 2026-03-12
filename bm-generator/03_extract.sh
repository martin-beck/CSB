#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT


 : ${DIR_PROG:="./deserialized"}
 : ${DIR_OUT:="./extracted"}
 : ${MINCALLS:=10}
 : ${JOBS:=10}

if [ ! -d "${DIR_PROG}" ]; then
  echo "Directory \"${DIR_PROG}\" with syz-lang programs does not exist."
  echo "Either run"
  echo "  ./`ls 02_*.sh`"
  echo "to generate it, or specify directory explicitly:"
  echo "  DIR_PROG=\"/path/to/prog/files/\" $0"

  exit 1
fi

DIR_PROG_ABS="`readlink -e ${DIR_PROG}`"

files=`find "${DIR_PROG_ABS}" -maxdepth 1 -name '*.prog'`

SCRIPT_SYZ_SRC="helper/find_syzkaller_src.sh"
 : ${DIR_SYZ_SRC:=$(${SCRIPT_SYZ_SRC})}

if [ ! -d "${DIR_SYZ_SRC}" ]; then
  echo "syzkaller source dir not found. Try to run:"
  echo "  ./`ls -1 01_*.sh`"
  echo ""
  echo "If the syzkaller source dir is not beneath $(pwd), then run this script as:"
  echo "  DIR_SYZ_SRC=\"</path/to/syzkaller/source>\" $0"
  exit 1
fi

if [ ! -d "${DIR_OUT}" ]; then
  mkdir -p "${DIR_OUT}"
fi
DIR_OUT_ABS="`readlink -e ${DIR_OUT}`"

cd "${DIR_SYZ_SRC}"

numRunning() {
  echo `pgrep 'syz-extraction' | wc -l`
}

# arg1 is number of total calls
# arg2 is number of total jobs
# arg3 is job index starting at 0
startIdx() {
  numCalls=$1
  numJobs=$2
  idxJob=$3
  sliceSize="$(($numCalls/$numJobs))"

  echo $((${sliceSize} * ${idxJob}))
}

# arg1 is number of total calls
# arg2 is number of total jobs
# arg3 is job index starting at 0
endIdx() {
  numCalls=$1
  numJobs=$2
  idxJob=$3
  sliceSize="$(($numCalls/$numJobs))"

  if [ $jobIdx -lt $(($numJobs - 1)) ]; then
    echo $(( (${sliceSize} * (${idxJob}+1))-1 ))
  else
    echo $(($numCalls - 1))
  fi
}

i=0
for file in $files; do
  echo $file
  dir="${DIR_OUT_ABS}/$i"
  mkdir -p "${dir}"
  numCalls="`cat ${file} | wc -l`"
  jobIdx=0
  while [ ${jobIdx} -lt ${JOBS} ]; do
    while [ $(numRunning) -ge ${JOBS} ]; do
      sleep 1
    done
    start=$(startIdx $numCalls ${JOBS} ${jobIdx})
    end=$(endIdx $numCalls ${JOBS} ${jobIdx})
    bin/syz-extraction -prog "${file}" -deserialize "${dir}" -minCalls ${MINCALLS} -syscallRangeStart ${start} -syscallRangeEnd ${end} &
    jobIdx=$(($jobIdx + 1))
  done
  i=$(($i + 1))
done

wait

# remove empty directories
i=0
for file in $files; do
  dir="${DIR_OUT_ABS}/$i"
  if [ -z "$( ls -A ${dir} )" ]; then
    rmdir "${dir}"
  fi
  i=$(($i + 1))
done
