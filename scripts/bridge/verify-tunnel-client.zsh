#!/bin/zsh

set -u

usage() {
  print -u2 -r -- "Usage: verify-tunnel-client.zsh --binary <absolute-path> [--archive <absolute-path> --checksums <absolute-path>]"
}

binary_input=""
archive_input=""
checksums_input=""

while (( $# > 0 )); do
  case "$1" in
    --binary)
      (( $# >= 2 )) || { usage; exit 64; }
      binary_input="$2"
      shift 2
      ;;
    --archive)
      (( $# >= 2 )) || { usage; exit 64; }
      archive_input="$2"
      shift 2
      ;;
    --checksums)
      (( $# >= 2 )) || { usage; exit 64; }
      checksums_input="$2"
      shift 2
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

if [[ -z "${binary_input}" ]]; then
  usage
  exit 64
fi

if [[ -n "${archive_input}" || -n "${checksums_input}" ]] \
  && [[ -z "${archive_input}" || -z "${checksums_input}" ]]; then
  usage
  exit 64
fi

binary_path="INVALID"
version="UNAVAILABLE"
capability_exit_code="NOT_RUN"
capability_status="FAIL"
runtime_capability_status="FAIL"
checksum_status="NOT_CHECKED"
archive_status="NOT_CHECKED"
payload_status="NOT_CHECKED"
release_version_status="NOT_CHECKED"
artifact_provenance_status="UNVERIFIED"
provenance_status="UNVERIFIED"
file_status="NOT_CHECKED"
codesign_verify_status="NOT_CHECKED"
codesign_detail_status="NOT_CHECKED"
xattr_status="NOT_CHECKED"
spctl_status="NOT_CHECKED"
gatekeeper_status="NOT_CHECKED"
overall_status="FAIL"
archive_version=""

is_canonical_regular_file() {
  local input="$1"
  [[ "${input}" == /* && "${input}" == "${input:A}" \
    && -f "${input}" && ! -L "${input}" ]]
}

probe_binary_capability() {
  local version_output version_exit version_first_line normalized_version
  [[ "${binary_path}" != "INVALID" && -f "${binary_path}" \
    && ! -L "${binary_path}" && -x "${binary_path}" ]] || return 1
  version_output="$("${binary_path}" --version 2>/dev/null)"
  version_exit=$?
  capability_exit_code="${version_exit}"
  if (( version_exit != 0 )); then
    return 1
  fi
  version_first_line="${version_output%%$'\n'*}"
  normalized_version="$(print -r -- "${version_first_line}" \
    | /usr/bin/grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
    | /usr/bin/head -n 1)"
  if [[ -n "${normalized_version}" ]]; then
    version="${normalized_version}"
    capability_status="PASS"
    runtime_capability_status="PASS"
    return 0
  fi
  version="UNPARSEABLE"
  return 1
}

run_macos_diagnostics() {
  if /usr/bin/file "${binary_path}" >/dev/null 2>&1; then
    file_status="PASS"
  else
    file_status="FAIL"
  fi
  if /usr/bin/codesign --verify --deep --strict "${binary_path}" >/dev/null 2>&1; then
    codesign_verify_status="PASS"
  else
    codesign_verify_status="FAIL"
  fi
  if /usr/bin/codesign -dv --verbose=4 "${binary_path}" >/dev/null 2>&1; then
    codesign_detail_status="PASS"
  else
    codesign_detail_status="FAIL"
  fi
  if /usr/bin/xattr -l "${binary_path}" >/dev/null 2>&1; then
    xattr_status="PASS"
  else
    xattr_status="FAIL"
  fi
  if /usr/sbin/spctl --assess --type execute "${binary_path}" >/dev/null 2>&1; then
    spctl_status="PASS"
  else
    spctl_status="REJECTED"
  fi
}

archive_shape_is_safe() {
  local archive_path="$1"
  local entries_output metadata_output entry expected_output actual_output
  local -a entries

  entries_output="$(/usr/bin/unzip -Z1 "${archive_path}" 2>/dev/null)" || return 1
  entries=(${(f)entries_output})
  (( ${#entries[@]} > 0 )) || return 1

  for entry in "${entries[@]}"; do
    [[ -n "${entry}" && "${entry}" != /* \
      && "${entry}" != *'\'* \
      && "${entry}" != '.' && "${entry}" != '..' \
      && "${entry}" != ./* && "${entry}" != */./* \
      && "${entry}" != ../* && "${entry}" != */../* \
      && "${entry}" != */.. ]] || return 1
  done

  metadata_output="$(/usr/bin/zipinfo -l "${archive_path}" 2>/dev/null)" || return 1
  print -r -- "${metadata_output}" | /usr/bin/grep -E '^l' >/dev/null 2>&1 \
    && return 1

  if (( ${#entries[@]} == 1 )) && [[ "${entries[1]}" == "tunnel-client" ]]; then
    return 0
  fi

  if [[ "${archive_version}" == "0.0.11" ]] && (( ${#entries[@]} == 4 )); then
    expected_output=$'LICENSE\ncloudflared\ncloudflared-manifest.json\ntunnel-client'
    actual_output="$(printf '%s\n' "${entries[@]}" \
      | /usr/bin/env LANG=C LC_ALL=C /usr/bin/sort)"
    [[ "${actual_output}" == "${expected_output}" ]] && return 0
  fi

  return 1
}

if [[ "${binary_input}" == /* && -f "${binary_input}" && ! -L "${binary_input}" ]]; then
  binary_path="${binary_input:A}"
fi

if [[ -n "${archive_input}" && -n "${checksums_input}" ]]; then
  artifact_provenance_status="FAIL"
  provenance_status="FAIL"
  checksum_status="FAIL"
  archive_status="FAIL"
  payload_status="FAIL"
  release_version_status="FAIL"

  if is_canonical_regular_file "${archive_input}" \
    && is_canonical_regular_file "${checksums_input}"; then
    archive_path="${archive_input:A}"
    checksums_path="${checksums_input:A}"
    archive_base="${archive_path:t}"

    if [[ "${archive_base}" == tunnel-client-v*-darwin-arm64.zip ]]; then
      archive_version="${archive_base#tunnel-client-v}"
      archive_version="${archive_version%-darwin-arm64.zip}"
    fi

    if [[ "${archive_version}" == <->.<->.<-> ]]; then
      expected_digest=""
      typeset -i matching_checksum_count=0
      while IFS= read -r checksum_line; do
        line_digest="${checksum_line%%[[:space:]]*}"
        line_name="${checksum_line#${line_digest}}"
        line_name="${line_name#"${line_name%%[![:space:]]*}"}"
        line_name="${line_name#\*}"
        if [[ "${line_name}" == "${archive_base}" \
          && "${(L)line_digest}" =~ '^[0-9a-f]{64}$' ]]; then
          expected_digest="${(L)line_digest}"
          (( matching_checksum_count += 1 ))
        fi
      done < "${checksums_path}"

      if (( matching_checksum_count == 1 )); then
        actual_digest_output="$(/usr/bin/env LANG=C LC_ALL=C \
          /usr/bin/shasum -a 256 "${archive_path}" 2>/dev/null)"
        digest_exit=$?
        actual_digest="${(L)actual_digest_output%%[[:space:]]*}"
        if (( digest_exit == 0 )) && [[ "${actual_digest}" == "${expected_digest}" ]]; then
          checksum_status="PASS"
        fi
      fi

      if archive_shape_is_safe "${archive_path}"; then
        archive_status="PASS"
        if [[ "${binary_path}" != "INVALID" && -f "${binary_path}" ]] \
          && /usr/bin/unzip -p "${archive_path}" tunnel-client 2>/dev/null \
            | /usr/bin/cmp -s "${binary_path}" -; then
          payload_status="PASS"
        fi
      fi
    fi
  fi
fi

if [[ -z "${archive_input}" ]]; then
  probe_binary_capability || true
elif [[ "${checksum_status}" == "PASS" \
  && "${archive_status}" == "PASS" \
  && "${payload_status}" == "PASS" ]]; then
  artifact_provenance_status="PASS"
  provenance_status="PASS"
  run_macos_diagnostics
  probe_binary_capability || true
  if [[ "${runtime_capability_status}" == "PASS" ]]; then
    if [[ "${version}" == "${archive_version}" ]]; then
      release_version_status="PASS"
    fi
    gatekeeper_status="NOT_BLOCKING"
  elif [[ "${spctl_status}" == "REJECTED" \
    && ( "${capability_exit_code}" == "137" || "${capability_exit_code}" == "9" ) ]]; then
    capability_status="BLOCKED_BY_OS_POLICY"
    runtime_capability_status="BLOCKED_BY_OS_POLICY"
    release_version_status="NOT_AVAILABLE_RUNTIME_BLOCKED"
    gatekeeper_status="BLOCKED"
  else
    gatekeeper_status="NOT_CONFIRMED"
  fi
fi

if [[ "${runtime_capability_status}" == "PASS" \
  && "${artifact_provenance_status}" == "PASS" \
  && "${release_version_status}" == "PASS" ]]; then
  overall_status="PASS"
elif [[ "${runtime_capability_status}" == "PASS" \
  && "${artifact_provenance_status}" == "UNVERIFIED" ]]; then
  overall_status="UNVERIFIED"
elif [[ "${runtime_capability_status}" == "BLOCKED_BY_OS_POLICY" \
  && "${artifact_provenance_status}" == "PASS" \
  && "${gatekeeper_status}" == "BLOCKED" ]]; then
  overall_status="RUNTIME_BLOCKED"
fi

print -r -- "binary_path=${binary_path}"
print -r -- "version=${version}"
print -r -- "capability_exit_code=${capability_exit_code}"
print -r -- "capability_status=${capability_status}"
print -r -- "runtime_capability_status=${runtime_capability_status}"
print -r -- "checksum_status=${checksum_status}"
print -r -- "archive_status=${archive_status}"
print -r -- "payload_status=${payload_status}"
print -r -- "release_version_status=${release_version_status}"
print -r -- "artifact_provenance_status=${artifact_provenance_status}"
print -r -- "provenance_status=${provenance_status}"
print -r -- "file_status=${file_status}"
print -r -- "codesign_verify_status=${codesign_verify_status}"
print -r -- "codesign_detail_status=${codesign_detail_status}"
print -r -- "xattr_status=${xattr_status}"
print -r -- "spctl_status=${spctl_status}"
print -r -- "gatekeeper_status=${gatekeeper_status}"
print -r -- "overall_status=${overall_status}"

case "${overall_status}" in
  PASS) exit 0 ;;
  UNVERIFIED) exit 2 ;;
  RUNTIME_BLOCKED) exit 3 ;;
  *) exit 1 ;;
esac
