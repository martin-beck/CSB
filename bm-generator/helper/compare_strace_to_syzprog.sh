#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT


if [ $# -ne 2 ]; then
  echo "Usage: $0 <strace.log> </path/to/prog/dir>"
  exit 1
fi

export LC_ALL=C

# calculates the precentage like 100*$2/$1 with $3 number of digits (2 if $3 is empty)
calc_percent() {
  a=$1
  b=$2
  digits=$3
  if [ "x${digits}" == "x" ]; then
    digits=2
  fi
  echo "scale=${digits}; 100*${b}/${a}" | bc -l
}

TRACE="$1"
DIR_PROG="$2"

FILE_FREQ_IN="${DIR_PROG}/frequency_in.log"
FILE_FREQ_OUT="${DIR_PROG}/frequency_out.log"
FILE_FREQ_OUT_SUPPORTED="${DIR_PROG}/frequency_out_supported.log"
FILE_FREQ_OUT_HELPERS="${DIR_PROG}/frequency_out_helpers.log"

FILE_NAMES_IN="${DIR_PROG}/syscall_names_in.log"
FILE_NAMES_OUT="${DIR_PROG}/syscall_names_out.log"
FILE_NAMES_GENERATED="${DIR_PROG}/syscall_names_generated.log"

# Generate strace log input frequencies

cat "${TRACE}" | grep -vF '<...' | grep -vF -- '---' | grep -vF -- '+++' | sed 's/ \+/ /'  | cut -d ' ' -f 2 | cut -d '(' -f 1 | sort | uniq -c | sed 's/^ *//' | sed 's/^\(.*\) \(.*\)$/\2\t\1/' > "${FILE_FREQ_IN}"

# Generate prog output frequencies

cat "${DIR_PROG}/"*.prog | sed 's/^<[0-9]\+>//' | sed 's/^r.* = //' | grep -vE '^(#|$)' | cut -d '(' -f 1 | cut -d '$' -f 1 | sort | uniq -c | sed 's/^ *//' | sed 's/^\(.*\) \(.*\)$/\2\t\1/' > "${FILE_FREQ_OUT}"

# Expand generated replay helpers into the kernel syscalls they represent. The
# mapping is read from syzkaller so newly added helpers are included.
SCRIPT_SYZ_SRC="helper/find_syzkaller_src.sh"
: ${DIR_SYZ_SRC:=$(${SCRIPT_SYZ_SRC})}
FILE_SYZ_TARGETS="${DIR_SYZ_SRC}/sys/targets/targets.go"
if [ ! -f "${FILE_SYZ_TARGETS}" ]; then
  echo "syzkaller target metadata not found: ${FILE_SYZ_TARGETS}" >&2
  exit 1
fi

FILE_HELPER_DEPS=`mktemp`
trap 'rm -f "${FILE_HELPER_DEPS}"' EXIT
awk '
  /PseudoSyscallDeps: map\[string\]\[\]string{/ { in_map = 1; next }
  in_map && /^[[:space:]]*},/ { exit }
  in_map && /^[[:space:]]*"/ {
    line = $0
    sub(/^[[:space:]]*"/, "", line)
    helper = line
    sub(/".*/, "", helper)
    sub(/^[^:]*:[[:space:]]*{/, "", line)
    sub(/}.*/, "", line)
    count = split(line, deps, ",")
    for (i = 1; i <= count; i++) {
      gsub(/["[:space:]]/, "", deps[i])
      if (deps[i] != "")
        print helper "\t" deps[i]
    }
  }
' "${FILE_SYZ_TARGETS}" > "${FILE_HELPER_DEPS}"

: > "${FILE_FREQ_OUT_SUPPORTED}"
: > "${FILE_FREQ_OUT_HELPERS}"
awk -F '\t' '
  NR == FNR {
    helper_deps[$1] = helper_deps[$1] " " $2
    next
  }
  {
    if ($1 in helper_deps) {
      count = split(helper_deps[$1], deps, " ")
      for (i = 1; i <= count; i++) {
        if (deps[i] == "")
          continue
        represented[deps[i]] += $2
        helpers[deps[i]] += $2
      }
    } else if ($1 !~ /^syz_/) {
      represented[$1] += $2
    }
  }
  END {
    for (syscall in represented)
      print syscall "\t" represented[syscall] > supported_file
    for (syscall in helpers)
      print syscall "\t" helpers[syscall] > helpers_file
  }
' supported_file="${FILE_FREQ_OUT_SUPPORTED}" helpers_file="${FILE_FREQ_OUT_HELPERS}" "${FILE_HELPER_DEPS}" "${FILE_FREQ_OUT}"
sort -o "${FILE_FREQ_OUT_SUPPORTED}" "${FILE_FREQ_OUT_SUPPORTED}"
sort -o "${FILE_FREQ_OUT_HELPERS}" "${FILE_FREQ_OUT_HELPERS}"

num_hist_in=`cat ${FILE_FREQ_IN} | wc -l`
num_hist_out=`cat ${FILE_FREQ_OUT_SUPPORTED} | wc -l`

cat "${FILE_FREQ_IN}" | cut -f 1 | sort > "${FILE_NAMES_IN}"
cat "${FILE_FREQ_OUT_SUPPORTED}" | cut -f 1 > "${FILE_NAMES_OUT}"
cat "${FILE_FREQ_OUT}" | cut -f 1 | sort > "${FILE_NAMES_GENERATED}"

num_names_absent=`comm -23 "${FILE_NAMES_IN}" "${FILE_NAMES_OUT}" | wc -l`
num_names_represented=$((${num_hist_in}-${num_names_absent}))

echo "Unique syscall names (strace/generated support set): (${num_hist_in}/${num_hist_out})"
echo "Input syscall-name coverage: (${num_hist_in}/${num_names_represented}) - $(calc_percent ${num_hist_in} ${num_names_represented})% represented"

num_generated_helpers=`awk -F '\t' '$1 ~ /^syz_/ {count++} END {print count + 0}' "${FILE_FREQ_OUT}"`
if [ ${num_generated_helpers} -gt 0 ]; then
  echo "Generated syzlang helpers (${num_generated_helpers}):"
  awk -F '\t' '
    NR == FNR {
      dependencies[$1] = dependencies[$1] " " $2
      next
    }
    $1 ~ /^syz_/ {
      if ($1 in dependencies)
        print "  " $1 " (" $2 " calls):" dependencies[$1]
      else
        print "  " $1 " (" $2 " calls): no declared syscall dependencies"
    }
  ' "${FILE_HELPER_DEPS}" "${FILE_FREQ_OUT}"
fi

echo "${num_names_absent} unique strace syscall names are absent from the generated syzlang programs"
if [ ${num_names_absent} -gt 0 ]; then
  comm -23 "${FILE_NAMES_IN}" "${FILE_NAMES_OUT}" | sed 's/^/  /'
fi

num_names_generated_only=`comm -13 "${FILE_NAMES_IN}" "${FILE_NAMES_GENERATED}" | wc -l`
if [ ${num_names_generated_only} -gt 0 ]; then
  echo "${num_names_generated_only} generated syzlang call names, including helpers, are absent by direct name from the strace input"
  comm -13 "${FILE_NAMES_IN}" "${FILE_NAMES_GENERATED}" | sed 's/^/  /'
fi

# Total number of instances of syscalls
total_in=`awk -F '\t' '{sum += $2} END {print sum + 0}' "${FILE_FREQ_IN}"`
total_out=`awk -F '\t' '{sum += $2} END {print sum + 0}' "${FILE_FREQ_OUT}"`
total_supported=`awk -F '\t' '{sum += $2} END {print sum + 0}' "${FILE_FREQ_OUT_SUPPORTED}"`

echo "Raw syscall call counts (strace/generated syzlang): (${total_in}/${total_out}) - $(calc_percent ${total_in} ${total_out})% call-count ratio (not translation coverage)"
echo "Represented syscall call counts (strace/generated support set): (${total_in}/${total_supported}) - $(calc_percent ${total_in} ${total_supported})% call-count ratio"


# Compute Earth mover distance
EMD=0
if [ ${num_hist_in} -eq ${num_hist_out} ]; then
  i=0
  while [ $i -lt ${num_hist_in} ]; do
    cur_num_in=`head -n $(($i+1)) ${FILE_FREQ_IN} | tail -n 1 | cut -f 2`
    cur_num_out=`head -n $(($i+1)) ${FILE_FREQ_OUT_SUPPORTED} | tail -n 1 | cut -f 2`
    cur_diff=$((${cur_num_in}-${cur_num_out}))
    abs_diff=${cur_diff#-}
    EMD=$((${EMD} + ${abs_diff}))
    i=$(($i + 1))
  done
  echo "Earth movers distance: ${EMD}"
fi

# Info on visual meld diff
echo "Check Distribution differences"
echo "  meld ${FILE_FREQ_IN} ${FILE_FREQ_OUT_SUPPORTED}"
