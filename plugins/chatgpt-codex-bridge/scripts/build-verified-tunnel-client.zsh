#!/bin/zsh

set -euo pipefail

readonly APPROVED_VERSION="0.0.11"

usage() {
  print -u2 -r -- "Usage: build-verified-tunnel-client.zsh --source <absolute-checkout> --output <absolute-file> --expected-version 0.0.11 --expected-commit <40-hex>"
}

die() {
  print -u2 -r -- "build-verified-tunnel-client: $1"
  exit 1
}

source_input=""
output_input=""
expected_version=""
expected_commit=""

while (( $# > 0 )); do
  case "$1" in
    --source)
      (( $# >= 2 )) || { usage; exit 64; }
      source_input="$2"
      shift 2
      ;;
    --output)
      (( $# >= 2 )) || { usage; exit 64; }
      output_input="$2"
      shift 2
      ;;
    --expected-version)
      (( $# >= 2 )) || { usage; exit 64; }
      expected_version="$2"
      shift 2
      ;;
    --expected-commit)
      (( $# >= 2 )) || { usage; exit 64; }
      expected_commit="$2"
      shift 2
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

[[ -n "${source_input}" && -n "${output_input}" \
  && -n "${expected_version}" && -n "${expected_commit}" ]] \
  || { usage; exit 64; }
[[ "${expected_version}" == "${APPROVED_VERSION}" ]] \
  || die "expected version is not approved"
[[ "${expected_commit}" =~ '^[0-9a-f]{40}$' ]] \
  || die "expected commit must be a lowercase full SHA"
[[ "${source_input}" == /* && -d "${source_input}" && ! -L "${source_input}" ]] \
  || die "source must be an existing absolute non-symlink directory"
[[ "${output_input}" == /* ]] || die "output must be an absolute path"
[[ "${source_input}" == "${source_input:A}" ]] || die "source path must be canonical"
[[ "${output_input}" == "${output_input:A}" ]] || die "output path must be canonical"

readonly source_path="${source_input:A}"
readonly output_path="${output_input:A}"
readonly output_dir="${output_path:h}"
readonly receipt_path="${output_path}.provenance.json"

[[ -d "${output_dir}" && ! -L "${output_dir}" ]] \
  || die "output directory must exist and must not be a symlink"
[[ ! -e "${output_path}" && ! -L "${output_path}" ]] \
  || die "output already exists"
[[ ! -e "${receipt_path}" && ! -L "${receipt_path}" ]] \
  || die "provenance receipt already exists"

readonly source_top="$(/usr/bin/git -C "${source_path}" rev-parse --show-toplevel 2>/dev/null)"
[[ "${source_top:A}" == "${source_path}" ]] || die "source is not the checkout root"

origin_url="$(/usr/bin/git -C "${source_path}" remote get-url origin 2>/dev/null)" \
  || die "source origin is unavailable"
case "${origin_url}" in
  https://github.com/openai/tunnel-client|https://github.com/openai/tunnel-client.git|git@github.com:openai/tunnel-client.git)
    ;;
  *) die "source origin is not the official repository" ;;
esac

head_commit="$(/usr/bin/git -C "${source_path}" rev-parse HEAD 2>/dev/null)" \
  || die "source HEAD cannot be resolved"
[[ "${head_commit}" == "${expected_commit}" ]] || die "source HEAD does not match expected commit"
tag_commit="$(/usr/bin/git -C "${source_path}" rev-parse "refs/tags/v${expected_version}^{commit}" 2>/dev/null)" \
  || die "release tag cannot be resolved"
[[ "${tag_commit}" == "${expected_commit}" ]] || die "release tag does not resolve to expected commit"
[[ -z "$(/usr/bin/git -C "${source_path}" status --porcelain=v1 --untracked-files=all)" ]] \
  || die "source tree is not clean"

version_file="${source_path}/pkg/version/VERSION"
[[ -f "${version_file}" && ! -L "${version_file}" ]] || die "version file is unavailable"
version_file_value="$(<"${version_file}")"
[[ "${version_file_value}" == "${expected_version}" ]] || die "version file does not match expected version"

go_bin=""
for candidate in \
  /opt/homebrew/bin/go \
  /opt/homebrew/opt/go/bin/go \
  /usr/local/bin/go \
  /usr/local/go/bin/go \
  /usr/bin/go; do
  if [[ -x "${candidate}" ]]; then
    go_bin="${candidate}"
    break
  fi
done
[[ -n "${go_bin}" ]] || die "Go toolchain is unavailable"

go_path="${go_bin:h}:/usr/bin:/bin:/usr/sbin:/sbin"
go_version="$(/usr/bin/env -i \
  HOME="${HOME}" LANG=C LC_ALL=C PATH="${go_path}" \
  "${go_bin}" version)" || die "go version failed"

temp_output="$(/usr/bin/mktemp "${output_dir}/.tunnel-client-build.XXXXXX")"
temp_receipt="$(/usr/bin/mktemp "${output_dir}/.tunnel-client-provenance.XXXXXX")"
cleanup() {
  [[ -n "${temp_output:-}" && -f "${temp_output}" && ! -L "${temp_output}" ]] \
    && /bin/rm -f -- "${temp_output}"
  [[ -n "${temp_receipt:-}" && -f "${temp_receipt}" && ! -L "${temp_receipt}" ]] \
    && /bin/rm -f -- "${temp_receipt}"
}
trap cleanup EXIT

(
  cd "${source_path}"
  /usr/bin/env -i \
    HOME="${HOME}" LANG=C LC_ALL=C PATH="${go_path}" \
    "${go_bin}" mod verify
) >/dev/null || die "go mod verify failed"

(
  cd "${source_path}"
  /usr/bin/env -i \
    HOME="${HOME}" LANG=C LC_ALL=C PATH="${go_path}" \
    "${go_bin}" build -trimpath -o "${temp_output}" ./cmd/client
) >/dev/null || die "fixed Go build failed"

/bin/chmod 0755 "${temp_output}"
file_output="$(/usr/bin/file "${temp_output}")" || die "file inspection failed"
[[ "${file_output}" == *"Mach-O 64-bit executable arm64"* ]] \
  || die "built binary is not Mach-O arm64"

binary_version_output="$("${temp_output}" --version 2>/dev/null)" \
  || die "built binary --version failed"
binary_version="$(print -r -- "${binary_version_output%%$'\n'*}" \
  | /usr/bin/grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
  | /usr/bin/head -n 1)"
[[ "${binary_version}" == "${expected_version}" ]] \
  || die "built binary version does not match expected version"
"${temp_output}" help quickstart >/dev/null 2>&1 \
  || die "built binary quickstart help failed"

if /usr/bin/xattr -p com.apple.quarantine "${temp_output}" >/dev/null 2>&1; then
  die "built binary has a quarantine attribute"
fi
[[ -z "$(/usr/bin/git -C "${source_path}" status --porcelain=v1 --untracked-files=all)" ]] \
  || die "source tree changed during build"

binary_digest_output="$(/usr/bin/env LANG=C LC_ALL=C \
  /usr/bin/shasum -a 256 "${temp_output}")"
binary_digest="${binary_digest_output%%[[:space:]]*}"
[[ "${binary_digest}" =~ '^[0-9a-f]{64}$' ]] || die "built binary digest failed"

/usr/bin/python3 - \
  "${temp_receipt}" "${expected_commit}" "${go_version}" \
  "${binary_digest}" "${binary_version}" <<'PY'
import json
import pathlib
import sys

receipt_path, commit, go_version, digest, binary_version = sys.argv[1:]
receipt = {
    "binarySHA256": digest,
    "binaryVersion": binary_version,
    "goModVerify": "PASS",
    "goVersion": go_version,
    "provenanceMode": "official_source_build_v1",
    "release": "v0.0.11",
    "repository": "openai/tunnel-client",
    "runtimeCapability": "PASS",
    "sourceCommit": commit,
    "sourceTreeClean": True,
    "versionFile": "0.0.11",
}
pathlib.Path(receipt_path).write_text(
    json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
/bin/chmod 0644 "${temp_receipt}"
/bin/mv -- "${temp_output}" "${output_path}"
/bin/mv -- "${temp_receipt}" "${receipt_path}"
trap - EXIT

print -r -- "source_build_status=PASS"
print -r -- "binary_version=${binary_version}"
print -r -- "binary_sha256=${binary_digest}"
print -r -- "runtime_capability=PASS"
