#!/bin/zsh

set -u

if (( $# != 2 )) || [[ "$1" != "--sandbox" ]] || [[ -z "$2" ]]; then
  print -u2 -r -- "Usage: local-preflight.zsh --sandbox <approved-path>"
  exit 64
fi

readonly resolver="${0:A:h}/resolve-codex-bin.zsh"
readonly sandbox_path="${2:A}"

first_line() {
  local value="$1"
  value="${value%%$'\n'*}"
  value="${value//$'\r'/}"
  print -r -- "${value}"
}

codex_path="$("${resolver}" 2>/dev/null)"
codex_resolve_status=$?
codex_version="UNAVAILABLE"
codex_mcp_server="UNAVAILABLE"

if (( codex_resolve_status == 0 )) && [[ -n "${codex_path}" ]]; then
  captured_codex_version="$("${codex_path}" --version 2>/dev/null)"
  codex_version_status=$?
  if (( codex_version_status == 0 )); then
    codex_version="$(first_line "${captured_codex_version}")"
    codex_mcp_server="AVAILABLE"
  fi
else
  codex_path="UNRESOLVED"
fi

tunnel_client="UNAVAILABLE"
tunnel_client_version="UNAVAILABLE"
tunnel_path="$(command -v tunnel-client 2>/dev/null)"
if [[ -n "${tunnel_path}" && -x "${tunnel_path}" ]]; then
  captured_tunnel_version="$("${tunnel_path}" --version 2>/dev/null)"
  tunnel_version_status=$?
  if (( tunnel_version_status == 0 )); then
    tunnel_client="AVAILABLE"
    tunnel_client_version="$(first_line "${captured_tunnel_version}")"
  fi
fi

user_groups="$(id -Gn 2>/dev/null)"
user_groups_status=$?
user_privilege="unknown"
if (( user_groups_status == 0 )); then
  typeset -a group_names
  group_names=(${=user_groups})
  if (( group_names[(I)admin] > 0 )); then
    user_privilege="admin"
  else
    user_privilege="non-admin"
  fi
fi

sandbox_exists="NO"
if [[ -d "${sandbox_path}" ]]; then
  sandbox_exists="YES"
fi

overall_status="FAIL"
if [[ "${codex_mcp_server}" == "AVAILABLE" \
   && "${tunnel_client}" == "AVAILABLE" \
   && "${user_privilege}" == "admin" \
   && "${sandbox_exists}" == "YES" ]]; then
  overall_status="PASS"
fi

print -r -- "codex_path=${codex_path}"
print -r -- "codex_version=${codex_version}"
print -r -- "codex_mcp_server=${codex_mcp_server}"
print -r -- "tunnel_client=${tunnel_client}"
print -r -- "tunnel_client_version=${tunnel_client_version}"
print -r -- "user_privilege=${user_privilege}"
print -r -- "sandbox_exists=${sandbox_exists}"
print -r -- "overall_status=${overall_status}"

[[ "${overall_status}" == "PASS" ]]
