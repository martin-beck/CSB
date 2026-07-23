#!/usr/bin/env bash
# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT
set -Eeuo pipefail

HARNESS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CSB_ROOT="$(cd -- "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/tools.tsv"
PREFIX="${PREFIX:-${TMPDIR:-/tmp}/csb-linux-tools}"
WORK_DIR="${WORK_DIR:-${TMPDIR:-/tmp}/csb-linux-tools-work}"
TRACE_DIR="${TRACE_DIR:-${HARNESS_DIR}/traces}"
COLLECT_STRACE="${COLLECT_STRACE:-${CSB_ROOT}/scripts/plugins/collect_strace.sh}"
export PATH="${PREFIX}/bin:${PREFIX}/usr/bin:${PREFIX}/usr/sbin:${PATH}"
PREFIX_LIBRARY_PATH="${PREFIX}/lib/$(uname -m)-linux-gnu:${PREFIX}/usr/lib/$(uname -m)-linux-gnu:${PREFIX}/lib:${PREFIX}/lib64:${PREFIX}/usr/lib:${PREFIX}/usr/lib64"
for rust_library_dir in "${PREFIX}"/usr/lib/rustlib/*/lib; do
  [[ -d "${rust_library_dir}" ]] && PREFIX_LIBRARY_PATH="${PREFIX_LIBRARY_PATH}:${rust_library_dir}"
done
export LD_LIBRARY_PATH="${PREFIX_LIBRARY_PATH}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${PREFIX}/usr/lib/python3/dist-packages${PYTHONPATH:+:${PYTHONPATH}}"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
note() { printf '==> %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }
host_arch() { case "$(uname -m)" in x86_64|amd64) echo amd64;; aarch64|arm64) echo arm64;; riscv64) echo riscv64;; *) uname -m;; esac; }
tool_row() { awk -F '\t' -v tool="$1" '$1 !~ /^#/ && $2 == tool { print; found=1; exit } END { exit !found }' "${MANIFEST}"; }
tool_field() { tool_row "$1" | cut -f "$2"; }
list_tools() { awk -F '\t' '$1 !~ /^#/ && NF >= 8 { print $1 "\t" $2 "\t" $7 "\t" $8 }' "${MANIFEST}"; }
prepare_case() {
  CASE_DIR="${WORK_DIR}/$1"
  [[ -n "${WORK_DIR}" && "${WORK_DIR}" != / && "${WORK_DIR}" != "${HOME}" ]] || die "unsafe WORK_DIR: ${WORK_DIR}"
  [[ "$1" =~ ^[a-zA-Z0-9+._/-]+$ && "$1" != /* && "$1" != *..* && "${CASE_DIR}" == "${WORK_DIR}/"* ]] || die "unsafe case path: ${CASE_DIR}"
  rm -rf -- "${CASE_DIR}"
  mkdir -p -- "${CASE_DIR}"
}

package_backend() {
  if have apt-get && have dpkg-deb; then echo apt
  elif have dnf && have rpm2cpio && have cpio; then echo dnf
  elif have zypper && have rpm2cpio && have cpio; then echo zypper
  elif have apk; then echo apk
  elif have pacman && have bsdtar; then echo pacman
  else return 1
  fi
}

prefix_command() {
  local tool="$1" candidate name
  local -a names=("${tool}")
  case "${tool}" in
    awk) names+=(gawk mawk) ;;
    vi) names+=(vim.tiny vim.basic vim) ;;
    which) names+=(which.debianutils) ;;
    nc) names+=(nc.openbsd ncat) ;;
    traceroute) names+=(traceroute.db) ;;
  esac
  for name in "${names[@]}"; do
    for candidate in "${PREFIX}/bin/${name}" "${PREFIX}/sbin/${name}" "${PREFIX}/usr/bin/${name}" "${PREFIX}/usr/sbin/${name}"; do
      [[ -x "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }
    done
    candidate="$(find "${PREFIX}" -type f -name "${name}" -perm /111 -print -quit 2>/dev/null || true)"
    [[ -n "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }
  done
  return 1
}

validate_prefix() {
  local resolved
  resolved="$(realpath -m -- "${PREFIX}")"
  case "${resolved}" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/srv|/sys|/usr|/var|"${HOME}"|"${HOME}"/*)
      die "unsafe PREFIX: ${PREFIX} resolves to ${resolved}" ;;
  esac
}

expose_prefix_command() {
  local tool="$1" target canonical="${PREFIX}/bin/${tool}"
  target="$(prefix_command "${tool}")" || return 1
  mkdir -p "${PREFIX}/bin"
  if [[ "${target}" != "${canonical}" ]]; then ln -sfn "${target}" "${canonical}"; fi
}

apt_extract() {
  local package="$1" cache="${PREFIX}/packages/apt" markers="${PREFIX}/.extracted-deb" deb dependency marker
  mkdir -p "${cache}" "${markers}"
  mapfile -t dependencies < <(apt-cache depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances "${package}" | \
    sed -n '/^[A-Za-z0-9][A-Za-z0-9+.-]*$/p' | sort -u)
  ((${#dependencies[@]})) || dependencies=("${package}")
  for dependency in "${dependencies[@]}"; do
    deb="$(find "${cache}" -maxdepth 1 -name "${dependency}_*.deb" -print -quit)"
    if [[ -n "${deb}" ]] && ! (dpkg-deb --fsys-tarfile "${deb}" 2>/dev/null | tar -tf - >/dev/null 2>&1); then
      note "discarding incomplete package archive: ${deb}"
      rm -f -- "${deb}"
      deb=''
    fi
    [[ -n "${deb}" ]] || (cd "${cache}" && apt-get download "${dependency}")
  done
  while IFS= read -r -d '' deb; do
    marker="${markers}/$(basename -- "${deb}")"
    [[ -e "${marker}" ]] && continue
    if ! (dpkg-deb --fsys-tarfile "${deb}" 2>/dev/null | tar -tf - >/dev/null 2>&1); then
      note "discarding incomplete package archive: ${deb}"
      rm -f -- "${deb}"
      continue
    fi
    dpkg-deb --fsys-tarfile "${deb}" | tar --skip-old-files --keep-directory-symlink --no-same-owner -x -C "${PREFIX}"
    : >"${marker}"
  done < <(find "${cache}" -name '*.deb' -print0)
}

dnf_extract() {
  local package="$1" cache="${PREFIX}/packages/rpm" markers rpm staging marker
  markers="${cache}/.extracted"
  mkdir -p "${cache}" "${markers}"
  dnf download --resolve --alldeps --destdir "${cache}" "${package}"
  while IFS= read -r -d '' rpm; do
    marker="${markers}/$(basename -- "${rpm}")"
    [[ -e "${marker}" ]] && continue
    staging="$(mktemp -d "${TMPDIR:-/tmp}/csb-linux-rpm.XXXXXX")"
    (cd "${staging}" && rpm2cpio "${rpm}" | cpio -idm --quiet --no-absolute-filenames --no-preserve-owner)
    chmod -R u+rwX -- "${staging}"
    tar -C "${staging}" -cf - . | tar -C "${PREFIX}" --skip-old-files --no-same-owner --keep-directory-symlink -xf -
    rm -rf -- "${staging}"
    : >"${marker}"
  done < <(find "${cache}" -name '*.rpm' -print0)
}

zypper_extract() {
  local package="$1" cache="${PREFIX}/packages/zypper" markers rpm staging marker
  markers="${cache}/.extracted"
  mkdir -p "${cache}" "${markers}"
  zypper --non-interactive download --all-matches --directory "${cache}" "${package}"
  while IFS= read -r -d '' rpm; do
    marker="${markers}/$(basename -- "${rpm}")"
    [[ -e "${marker}" ]] && continue
    staging="$(mktemp -d "${TMPDIR:-/tmp}/csb-linux-zypper.XXXXXX")"
    (cd "${staging}" && rpm2cpio "${rpm}" | cpio -idm --quiet --no-absolute-filenames --no-preserve-owner)
    chmod -R u+rwX -- "${staging}"
    tar -C "${staging}" -cf - . | tar -C "${PREFIX}" --skip-old-files --no-same-owner --keep-directory-symlink -xf -
    rm -rf -- "${staging}"
    : >"${marker}"
  done < <(find "${cache}" -name '*.rpm' -print0)
}

apk_extract() {
  local package="$1" cache="${PREFIX}/packages/apk" archive
  mkdir -p "${cache}"
  apk fetch --recursive --output "${cache}" "${package}"
  while IFS= read -r -d '' archive; do tar -xzf "${archive}" -C "${PREFIX}" 2>/dev/null || true; done < <(find "${cache}" -name '*.apk' -print0)
}

pacman_extract() {
  local package="$1" cache="${PREFIX}/packages/pacman" archive
  mkdir -p "${cache}"
  pacman -Sw --noconfirm --cachedir "${cache}" "${package}"
  while IFS= read -r -d '' archive; do bsdtar -xf "${archive}" -C "${PREFIX}"; done < <(find "${cache}" -name '*.pkg.tar.*' -print0)
}

install_kubectl_release() {
  local version arch url checksum
  arch="$(host_arch)"
  version="$(curl -fsSL --retry 5 https://dl.k8s.io/release/stable.txt)"
  url="https://dl.k8s.io/release/${version}/bin/linux/${arch}/kubectl"
  mkdir -p "${PREFIX}/bin" "${PREFIX}/packages/releases"
  curl -fL --retry 5 -o "${PREFIX}/packages/releases/kubectl" "${url}"
  checksum="$(curl -fsSL --retry 5 "${url}.sha256")"
  printf '%s  %s\n' "${checksum}" "${PREFIX}/packages/releases/kubectl" | sha256sum -c -
  install -m 0755 "${PREFIX}/packages/releases/kubectl" "${PREFIX}/bin/kubectl"
}

install_helm_release() {
  local arch tag archive url checksum
  arch="$(host_arch)"
  tag="$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/helm/helm/releases/latest)"
  tag="${tag##*/}"
  [[ "${tag}" == v* ]] || die "could not determine the latest Helm release"
  archive="${PREFIX}/packages/releases/helm-${tag}-linux-${arch}.tar.gz"
  url="https://get.helm.sh/helm-${tag}-linux-${arch}.tar.gz"
  mkdir -p "${PREFIX}/bin" "${PREFIX}/packages/releases"
  curl -fL --retry 5 -o "${archive}" "${url}"
  checksum="$(curl -fsSL --retry 5 "${url}.sha256sum" | awk '{print $1}')"
  printf '%s  %s\n' "${checksum}" "${archive}" | sha256sum -c -
  tar -xOf "${archive}" "linux-${arch}/helm" >"${PREFIX}/bin/helm"
  chmod 0755 "${PREFIX}/bin/helm"
}

install_yq_release() {
  local arch tag asset base binary checksums order checksum_field checksum
  case "$(host_arch)" in amd64) arch=amd64;; arm64) arch=arm64;; *) return 1;; esac
  tag="$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/mikefarah/yq/releases/latest)"
  tag="${tag##*/}"
  [[ "${tag}" == v* ]] || die "could not determine the latest yq release"
  asset="yq_linux_${arch}"
  base="https://github.com/mikefarah/yq/releases/download/${tag}"
  binary="${PREFIX}/packages/releases/${asset}-${tag}"
  checksums="${PREFIX}/packages/releases/yq-checksums-${tag}"
  order="${PREFIX}/packages/releases/yq-checksums-order-${tag}"
  mkdir -p "${PREFIX}/bin" "${PREFIX}/packages/releases"
  curl -fL --retry 5 -o "${checksums}" "${base}/checksums"
  curl -fL --retry 5 -o "${order}" "${base}/checksums_hashes_order"
  checksum_field="$(awk '$0 == "SHA-256" { print NR + 1; exit }' "${order}")"
  [[ -n "${checksum_field}" ]] || die "yq checksum metadata has no SHA-256 field"
  checksum="$(awk -v asset="${asset}" -v field="${checksum_field}" '$1 == asset { print $field; exit }' "${checksums}")"
  [[ "${checksum}" =~ ^[0-9a-fA-F]{64}$ ]] || die "could not find the yq SHA-256 checksum for ${asset}"
  if [[ ! -f "${binary}" ]] || ! printf '%s  %s\n' "${checksum}" "${binary}" | sha256sum -c - >/dev/null 2>&1; then
    curl -fL --retry 5 -o "${binary}" "${base}/${asset}"
  fi
  printf '%s  %s\n' "${checksum}" "${binary}" | sha256sum -c -
  install -m 0755 "${binary}" "${PREFIX}/bin/yq"
}

install_node_release() {
  local arch base checksums filename checksum archive version release_dir
  case "$(host_arch)" in amd64) arch=x64;; arm64) arch=arm64;; *) die "Node release is unavailable for $(host_arch)";; esac
  base='https://nodejs.org/dist/latest-v22.x'
  checksums="$(curl -fsSL --retry 5 "${base}/SHASUMS256.txt")"
  filename="$(awk -v arch="${arch}" '$2 ~ ("^node-v[0-9.]+-linux-" arch "[.]tar[.]xz$") {print $2; exit}' <<<"${checksums}")"
  [[ -n "${filename}" ]] || die "could not find a native Node release for ${arch}"
  checksum="$(awk -v file="${filename}" '$2 == file {print $1}' <<<"${checksums}")"
  version="${filename#node-}"; version="${version%-linux-${arch}.tar.xz}"
  archive="${PREFIX}/packages/releases/${filename}"
  release_dir="${PREFIX}/opt/node-${version}"
  mkdir -p "${PREFIX}/bin" "${PREFIX}/opt" "${PREFIX}/packages/releases" "${release_dir}"
  if [[ ! -x "${release_dir}/bin/node" ]]; then
    curl -fL --retry 5 -o "${archive}" "${base}/${filename}"
    printf '%s  %s\n' "${checksum}" "${archive}" | sha256sum -c -
    tar -xJf "${archive}" --strip-components=1 -C "${release_dir}"
  fi
  ln -sfn "${release_dir}/bin/node" "${PREFIX}/bin/node"
  ln -sfn "${release_dir}/bin/npm" "${PREFIX}/bin/npm"
  ln -sfn "${release_dir}/bin/npx" "${PREFIX}/bin/npx"
}

repair_java_prefix() {
  local link target
  while IFS= read -r -d '' link; do
    target="$(readlink -- "${link}")"
    [[ "${target}" == /etc/* && -e "${PREFIX}${target}" ]] || continue
    ln -sfn "${PREFIX}${target}" "${link}"
  done < <(find "${PREFIX}/usr/lib/jvm" \( -name conf -o -path '*/conf/*' \) -type l -print0 2>/dev/null)
}

repair_perf_prefix() {
  local perf_binary
  perf_binary="${PREFIX}/usr/bin/perf"
  if [[ ! -x "${perf_binary}" || "$(od -An -tx1 -N4 "${perf_binary}" 2>/dev/null)" != *'7f 45 4c 46'* ]]; then
    perf_binary="$(find "${PREFIX}/usr/lib" -path '*/linux-tools-*/perf' -type f -perm /111 -print -quit 2>/dev/null || true)"
  fi
  [[ -n "${perf_binary}" ]] || return 1
  ln -sfn "${perf_binary}" "${PREFIX}/bin/perf"
}

install_tool() {
  local tool="$1" backend package
  validate_prefix
  tool_row "${tool}" >/dev/null || die "unknown tool: ${tool}"
  if [[ "${tool}" =~ ^(node|npm)$ ]]; then
    note "${tool}: installing verified native Node release below ${PREFIX}"
    install_node_release
    expose_prefix_command "${tool}"
    return
  fi
  if prefix_command "${tool}" >/dev/null; then
    [[ "${tool}" =~ ^(java|javac)$ ]] && repair_java_prefix
    if [[ "${tool}" == perf ]]; then repair_perf_prefix || true; fi
    expose_prefix_command "${tool}"; note "${tool}: already installed below ${PREFIX}"; return
  fi
  backend="$(package_backend)" || die 'no supported package backend (apt, dnf, zypper, apk, or pacman)'
  case "${tool}" in
    kubectl)
      if [[ "${backend}" != dnf && "${backend}" != zypper ]]; then
        note "${tool}: installing verified native release below ${PREFIX}"
        install_kubectl_release
        expose_prefix_command "${tool}"
        return
      fi
      ;;
    helm) note "${tool}: installing verified native release below ${PREFIX}"; install_helm_release; expose_prefix_command "${tool}"; return ;;
    yq)
      if install_yq_release; then
        note "${tool}: installed verified native release below ${PREFIX}"
        expose_prefix_command "${tool}"
        return
      fi
      ;;
  esac
  case "${backend}" in apt) package="$(tool_field "${tool}" 3)";; dnf|zypper) package="$(tool_field "${tool}" 4)";; apk) package="$(tool_field "${tool}" 5)";; pacman) package="$(tool_field "${tool}" 6)";; esac
  if [[ "${tool}" == docker && "${backend}" =~ ^(dnf|zypper)$ ]]; then
    local candidate
    for candidate in moby-client "${package}" docker-cli docker-engine; do
      if { [[ "${backend}" == dnf ]] && dnf -q repoquery --qf '%{name}' "${candidate}" 2>/dev/null | grep -Fxq "${candidate}"; } ||
         { [[ "${backend}" == zypper ]] && zypper --non-interactive search --match-exact --type package "${candidate}" 2>/dev/null |
           grep -Eq "[|][[:space:]]*${candidate}[[:space:]]*[|]"; }; then
        package="${candidate}"
        break
      fi
    done
  fi
  if [[ "${backend}" == apt && "${tool}" == perf ]]; then
    local candidate
    for candidate in "linux-tools-$(uname -r)" linux-tools-generic linux-tools-common "${package}"; do
      if apt-cache show "${candidate}" >/dev/null 2>&1; then
        package="${candidate}"
        break
      fi
    done
  fi
  [[ -n "${package// /}" ]] || die "${tool} has no ${backend} package mapping"
  note "${tool}: extracting ${package} for ${backend} below ${PREFIX}"
  "${backend}_extract" "${package}"
  if [[ "${tool}" == perf ]]; then
    repair_perf_prefix || die "${package} did not provide a real perf executable below ${PREFIX}"
  fi
  prefix_command "${tool}" >/dev/null || die "${package} did not provide a runnable ${tool} below ${PREFIX}"
  [[ "${tool}" =~ ^(java|javac)$ ]] && repair_java_prefix
  expose_prefix_command "${tool}"
}
