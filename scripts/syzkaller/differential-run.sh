#!/bin/bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

set -u
set -o pipefail

usage() {
  cat <<EOF
Usage: $0 <pre-refactor-syzkaller> <post-refactor-syzkaller> <strace-directory>

Run bm-generator stages 02_parse through 06_prepare with both syzkaller trees
and stop at the first stage whose generated files differ.

Environment variables:
  TRACE_PATTERN   find(1) -name pattern for traces (default: *.log)
  DIFF_WORKDIR    use this new or empty directory instead of a temporary one
  KEEP_WORKDIR    keep the work directory after a successful run when set to 1
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

shell_quote() {
  printf '%q' "$1"
}

write_command() {
  output="$1"
  cwd="$2"
  shift 2

  {
    printf '(cd '
    shell_quote "${cwd}"
    printf ' &&'
    for arg in "$@"; do
      printf ' '
      shell_quote "${arg}"
    done
    printf ')\n'
  } > "${output}"
}

stage_label() {
  case "$1" in
    02) echo "02_parse" ;;
    03) echo "03_extract" ;;
    04) echo "04_reduce" ;;
    05) echo "05_multidiff" ;;
    06) echo "06_prepare (syz-prog2c)" ;;
    *) die "unknown stage $1" ;;
  esac
}

side_root() {
  side="$1"
  case_name="$2"
  echo "${WORKDIR}/${side}/${case_name}"
}

stage_output_dir() {
  side="$1"
  case_name="$2"
  stage="$3"
  root="$(side_root "${side}" "${case_name}")"

  case "${stage}" in
    02) echo "${root}/02_parse" ;;
    03) echo "${root}/03_extract" ;;
    04) echo "${root}/04_reduce" ;;
    05) echo "${root}/05_multidiff" ;;
    06) echo "${root}/bench/targets/gen-ws/syz" ;;
    *) die "unknown stage ${stage}" ;;
  esac
}

syzkaller_dir() {
  case "$1" in
    pre) echo "${PRE_SYZ}" ;;
    post) echo "${POST_SYZ}" ;;
    *) die "unknown side $1" ;;
  esac
}

prepare_case() {
  side="$1"
  case_name="$2"
  root="$(side_root "${side}" "${case_name}")"
  runner="${root}/bm-generator"

  mkdir -p "${runner}" "${root}/commands" "${root}/logs"
  ln -s "${GENERATOR_DIR}/helper" "${runner}/helper"
  for script in 02_parse.sh 03_extract.sh 04_reduce.sh 05_multidiff.sh 06_prepare.sh; do
    ln -s "${GENERATOR_DIR}/${script}" "${runner}/${script}"
  done
}

stage_command() {
  side="$1"
  case_name="$2"
  stage="$3"
  trace="$4"
  root="$(side_root "${side}" "${case_name}")"
  runner="${root}/bm-generator"
  syz="$(syzkaller_dir "${side}")"
  command_file="${root}/commands/${stage}.cmd"

  case "${stage}" in
    02)
      STAGE_CMD=(env "DIR_SYZ_SRC=${syz}" "DIR_PROG=$(stage_output_dir "${side}" "${case_name}" 02)" \
        ./02_parse.sh "${trace}")
      ;;
    03)
      STAGE_CMD=(env "DIR_SYZ_SRC=${syz}" \
        "DIR_PROG=$(stage_output_dir "${side}" "${case_name}" 02)" \
        "DIR_OUT=$(stage_output_dir "${side}" "${case_name}" 03)" ./03_extract.sh)
      ;;
    04)
      STAGE_CMD=(env "DIR_SYZ_SRC=${syz}" \
        "DIR_PROG=$(stage_output_dir "${side}" "${case_name}" 03)" \
        "DIR_OUT=$(stage_output_dir "${side}" "${case_name}" 04)" ./04_reduce.sh)
      ;;
    05)
      STAGE_CMD=(env "DIR_SYZ_SRC=${syz}" \
        "DIR_PROG=$(stage_output_dir "${side}" "${case_name}" 04)" \
        "DIR_OUT=$(stage_output_dir "${side}" "${case_name}" 05)" ./05_multidiff.sh)
      ;;
    06)
      STAGE_CMD=(env "DIR_SYZ_SRC=${syz}" \
        "DIR_PROG=$(stage_output_dir "${side}" "${case_name}" 05)" \
        CSB_RESULTS_GROUP=gen-ws ./06_prepare.sh)
      ;;
    *)
      die "unknown stage ${stage}"
      ;;
  esac

  write_command "${command_file}" "${runner}" "${STAGE_CMD[@]}"
}

run_stage() {
  side="$1"
  case_name="$2"
  stage="$3"
  trace="$4"
  root="$(side_root "${side}" "${case_name}")"
  runner="${root}/bm-generator"
  log="${root}/logs/${stage}.log"

  stage_command "${side}" "${case_name}" "${stage}" "${trace}"
  (cd "${runner}" && "${STAGE_CMD[@]}") > "${log}" 2>&1
}

make_manifest() {
  directory="$1"
  output="$2"
  if [ -d "${directory}" ]; then
    LC_ALL=C find "${directory}" -type f -printf '%P\n' | LC_ALL=C sort > "${output}"
  else
    : > "${output}"
  fi
}

print_command_file() {
  label="$1"
  file="$2"
  echo "  ${label}:"
  sed 's/^/    /' "${file}"
}

report_file_differences() {
  side_pre_dir="$1"
  side_post_dir="$2"
  pre_command="$3"
  post_command="$4"
  pre_manifest="$5"
  post_manifest="$6"
  found=0

  mapfile -t missing_post < <(comm -23 "${pre_manifest}" "${post_manifest}")
  mapfile -t unexpected_post < <(comm -13 "${pre_manifest}" "${post_manifest}")

  if [ "${#missing_post[@]}" -gt 0 ] || [ "${#unexpected_post[@]}" -gt 0 ]; then
    found=1
    echo "File-set differences:"
    print_command_file "post-refactor command" "${post_command}"
    for rel in "${missing_post[@]}"; do
      echo "  missing after refactoring: ${side_post_dir}/${rel}"
      echo "    corresponding pre-refactor file: ${side_pre_dir}/${rel}"
    done
    for rel in "${unexpected_post[@]}"; do
      echo "  unexpectedly created after refactoring: ${side_post_dir}/${rel}"
    done
  fi

  while IFS= read -r rel; do
    pre_file="${side_pre_dir}/${rel}"
    post_file="${side_post_dir}/${rel}"
    if ! cmp -s -- "${pre_file}" "${post_file}"; then
      found=1
      echo "Content difference: ${rel}"
      printf '  diff command: diff -u -- '
      shell_quote "${pre_file}"
      printf ' '
      shell_quote "${post_file}"
      printf '\n'
      print_command_file "pre-refactor command" "${pre_command}"
      print_command_file "post-refactor command" "${post_command}"
    fi
  done < <(comm -12 "${pre_manifest}" "${post_manifest}")

  return "${found}"
}

compare_stage() {
  case_name="$1"
  trace_rel="$2"
  stage="$3"
  pre_dir="$(stage_output_dir pre "${case_name}" "${stage}")"
  post_dir="$(stage_output_dir post "${case_name}" "${stage}")"
  pre_root="$(side_root pre "${case_name}")"
  post_root="$(side_root post "${case_name}")"
  pre_manifest="${pre_root}/${stage}.manifest"
  post_manifest="${post_root}/${stage}.manifest"

  make_manifest "${pre_dir}" "${pre_manifest}"
  make_manifest "${post_dir}" "${post_manifest}"
  if report_file_differences "${pre_dir}" "${post_dir}" \
      "${pre_root}/commands/${stage}.cmd" "${post_root}/commands/${stage}.cmd" \
      "${pre_manifest}" "${post_manifest}"; then
    return 0
  fi

  echo >&2
  echo "ERROR: generated files differ at stage $(stage_label "${stage}")" >&2
  echo "Trace: ${trace_rel}" >&2
  echo "Work directory retained at: ${WORKDIR}" >&2
  return 1
}

# Compare only the new byte range common to both parse outputs. The final tree
# comparison remains authoritative; this watcher merely spots a large-file
# mismatch while syz-trace2syz is still writing.
watch_parse_outputs() {
  pre_dir="$1"
  post_dir="$2"
  done_file="$3"
  marker="$4"
  compared=0

  while [ ! -e "${done_file}" ]; do
    mapfile -t pre_files < <(find "${pre_dir}" -maxdepth 1 -type f -name '*.prog' -printf '%f\n' 2>/dev/null | LC_ALL=C sort)
    mapfile -t post_files < <(find "${post_dir}" -maxdepth 1 -type f -name '*.prog' -printf '%f\n' 2>/dev/null | LC_ALL=C sort)
    if [ "${#pre_files[@]}" -eq 1 ] && [ "${#post_files[@]}" -eq 1 ]; then
      if [ "${pre_files[0]}" != "${post_files[0]}" ]; then
        echo "parse output filenames differ" > "${marker}"
        echo "Detected a parse output difference while generators are running." >&2
        return
      fi
      pre_file="${pre_dir}/${pre_files[0]}"
      post_file="${post_dir}/${post_files[0]}"
      pre_size="$(stat -c %s "${pre_file}" 2>/dev/null || echo 0)"
      post_size="$(stat -c %s "${post_file}" 2>/dev/null || echo 0)"
      common_size="${pre_size}"
      if [ "${post_size}" -lt "${common_size}" ]; then
        common_size="${post_size}"
      fi
      if [ "${common_size}" -lt "${compared}" ]; then
        compared=0
      fi
      if [ "${common_size}" -gt "${compared}" ]; then
        count=$((common_size - compared))
        if ! cmp -s -i "${compared}:${compared}" -n "${count}" -- "${pre_file}" "${post_file}"; then
          echo "parse output content differs at or before byte ${common_size}" > "${marker}"
          echo "Detected a parse output difference while generators are running." >&2
          return
        fi
        compared="${common_size}"
      fi
    fi
    sleep 0.1
  done
}

report_stage_failure() {
  case_name="$1"
  trace_rel="$2"
  stage="$3"
  pre_status="$4"
  post_status="$5"
  pre_root="$(side_root pre "${case_name}")"
  post_root="$(side_root post "${case_name}")"

  echo >&2
  echo "ERROR: stage $(stage_label "${stage}") did not complete successfully" >&2
  echo "Trace: ${trace_rel}" >&2
  echo "Pre-refactor exit status: ${pre_status}" >&2
  echo "Post-refactor exit status: ${post_status}" >&2
  print_command_file "pre-refactor command" "${pre_root}/commands/${stage}.cmd" >&2
  echo "  pre-refactor log: ${pre_root}/logs/${stage}.log" >&2
  print_command_file "post-refactor command" "${post_root}/commands/${stage}.cmd" >&2
  echo "  post-refactor log: ${post_root}/logs/${stage}.log" >&2
  echo "Work directory retained at: ${WORKDIR}" >&2
}

run_case() {
  trace="$1"
  trace_rel="$2"
  case_name="$3"

  prepare_case pre "${case_name}"
  prepare_case post "${case_name}"
  echo "Trace: ${trace_rel}"

  for stage in 02 03 04 05 06; do
    echo "  Running and comparing $(stage_label "${stage}") ..."
    if [ "${stage}" = 02 ]; then
      done_file="${WORKDIR}/.${case_name}.parse.done"
      marker="${WORKDIR}/.${case_name}.parse.difference"
      watch_parse_outputs "$(stage_output_dir pre "${case_name}" 02)" \
        "$(stage_output_dir post "${case_name}" 02)" "${done_file}" "${marker}" &
      watcher_pid=$!
    fi

    run_stage pre "${case_name}" "${stage}" "${trace}" &
    pre_pid=$!
    run_stage post "${case_name}" "${stage}" "${trace}" &
    post_pid=$!

    if wait "${pre_pid}"; then pre_status=0; else pre_status=$?; fi
    if wait "${post_pid}"; then post_status=0; else post_status=$?; fi

    if [ "${stage}" = 02 ]; then
      touch "${done_file}"
      wait "${watcher_pid}" || true
    fi

    if [ "${pre_status}" -ne 0 ] || [ "${post_status}" -ne 0 ]; then
      report_stage_failure "${case_name}" "${trace_rel}" "${stage}" \
        "${pre_status}" "${post_status}"
      return 1
    fi
    if ! compare_stage "${case_name}" "${trace_rel}" "${stage}"; then
      return 1
    fi
  done
}

if [ "$#" -ne 3 ]; then
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GENERATOR_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PRE_SYZ="$(readlink -e "$1")" || die "pre-refactor syzkaller directory does not exist: $1"
POST_SYZ="$(readlink -e "$2")" || die "post-refactor syzkaller directory does not exist: $2"
TRACE_DIR="$(readlink -e "$3")" || die "strace directory does not exist: $3"
TRACE_PATTERN="${TRACE_PATTERN:-*.log}"

[ -d "${PRE_SYZ}" ] || die "pre-refactor syzkaller path is not a directory: ${PRE_SYZ}"
[ -d "${POST_SYZ}" ] || die "post-refactor syzkaller path is not a directory: ${POST_SYZ}"
[ -d "${TRACE_DIR}" ] || die "strace path is not a directory: ${TRACE_DIR}"

for syz in "${PRE_SYZ}" "${POST_SYZ}"; do
  for tool in syz-trace2syz syz-extraction syz-prog-reduce syz-multidiff syz-prog2c; do
    [ -x "${syz}/bin/${tool}" ] || die "missing executable ${syz}/bin/${tool}; build both syzkaller trees first"
  done
done

mapfile -d '' traces < <(find "${TRACE_DIR}" -type f -name "${TRACE_PATTERN}" -print0 | LC_ALL=C sort -z)
[ "${#traces[@]}" -gt 0 ] || die "no traces matching ${TRACE_PATTERN} under ${TRACE_DIR}"

if [ -n "${DIFF_WORKDIR:-}" ]; then
  mkdir -p "${DIFF_WORKDIR}" || die "cannot create work directory: ${DIFF_WORKDIR}"
  WORKDIR="$(readlink -e "${DIFF_WORKDIR}")"
  [ -n "$(find "${WORKDIR}" -mindepth 1 -print -quit)" ] && die "DIFF_WORKDIR must be empty: ${WORKDIR}"
else
  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/csb-syzkaller-differential.XXXXXX")" || die "cannot create work directory"
fi

completed=0
cleanup() {
  status=$?
  if [ "${status}" -eq 0 ] && [ "${KEEP_WORKDIR:-0}" != 1 ]; then
    rm -rf -- "${WORKDIR}"
  elif [ "${status}" -eq 0 ]; then
    echo "Work directory retained at: ${WORKDIR}"
  elif [ "${completed}" -eq 0 ]; then
    echo "Work directory retained at: ${WORKDIR}" >&2
  fi
}
trap cleanup EXIT

echo "Pre-refactor syzkaller:  ${PRE_SYZ}"
echo "Post-refactor syzkaller: ${POST_SYZ}"
echo "Traces:                  ${TRACE_DIR}/${TRACE_PATTERN} (${#traces[@]} files)"
echo "Work directory:          ${WORKDIR}"

index=0
for trace in "${traces[@]}"; do
  trace_rel="${trace#${TRACE_DIR}/}"
  safe_name="$(printf '%s' "${trace_rel}" | sed 's/[^A-Za-z0-9_.-]/_/g')"
  case_name="$(printf '%04d_%s' "${index}" "${safe_name}")"
  if ! run_case "${trace}" "${trace_rel}" "${case_name}"; then
    completed=1
    exit 1
  fi
  index=$((index + 1))
done

completed=1
echo "All stages produced identical files for ${#traces[@]} trace(s)."
