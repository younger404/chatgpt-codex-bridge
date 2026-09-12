#!/bin/zsh
set -euo pipefail

readonly PROGRAM_PATH="${0:A}"
readonly SCRIPT_DIR="${PROGRAM_PATH:h}"
readonly SOURCE_RELAY="${SCRIPT_DIR}/github-issue-relay.py"
readonly SOURCE_MANAGED_REPO="${SCRIPT_DIR:h}/bridge/managed_repo.py"
readonly SOURCE_SUPERVISION="${SCRIPT_DIR:h}/bridge/supervision.py"
readonly SOURCE_RUNNER="${SCRIPT_DIR}/run-github-relay.zsh"
readonly STATE_DIR="${HOME}/Library/Application Support/chatgpt-codex-bridge"
readonly CONFIG_FILE="${STATE_DIR}/config.plist"
readonly BRIDGE_RUNTIME="${HOME}/.local/share/chatgpt-codex-bridge"
readonly GUARD_RUNNER="${BRIDGE_RUNTIME}/run-guard.zsh"
readonly RELAY_RUNTIME="${BRIDGE_RUNTIME}/github-relay"
readonly TARGET_RELAY="${RELAY_RUNTIME}/github-issue-relay.py"
readonly TARGET_RUNNER="${RELAY_RUNTIME}/run-github-relay.zsh"
readonly LOG_DIR="${HOME}/Library/Logs/chatgpt-codex-bridge"
readonly LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
readonly LABEL="com.chatgpt-codex-bridge.github-relay"
readonly TARGET_PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
readonly USER_UID="$(/usr/bin/id -u)"
readonly DOMAIN="gui/${USER_UID}"

typeset -i no_start=0
while (( $# > 0 )); do
  case "$1" in
    --no-start) no_start=1 ;;
    -h|--help)
      print -r -- "Usage: ${PROGRAM_PATH} [--no-start]"
      exit 0
      ;;
    *) print -u2 -r -- "github-relay: unsupported argument"; exit 64 ;;
  esac
  shift
done

die() {
  print -u2 -r -- "github-relay: $1"
  exit 1
}

regular_file() {
  [[ -f "$1" && ! -L "$1" ]]
}

regular_file "${CONFIG_FILE}" || die "existing Bridge config is unavailable"
regular_file "${GUARD_RUNNER}" || die "existing Guard runner is unavailable"
regular_file "${SOURCE_RELAY}" || die "relay source is unavailable"
regular_file "${SOURCE_RUNNER}" || die "relay runner source is unavailable"
regular_file "${SOURCE_MANAGED_REPO}" || die "registry helper source is unavailable"
regular_file "${SOURCE_SUPERVISION}" || die "supervision helper source is unavailable"

readonly TUNNEL_LABEL="$(/usr/bin/plutil -extract label raw -o - "${CONFIG_FILE}")"
readonly TUNNEL_JOB="${DOMAIN}/${TUNNEL_LABEL}"
if /bin/launchctl print "${TUNNEL_JOB}" >/dev/null 2>&1; then
  die "Secure Tunnel LaunchAgent must be stopped before relay installation"
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
command -v gh >/dev/null 2>&1 || die "GitHub CLI is unavailable"
gh auth status --hostname github.com >/dev/null 2>&1 \
  || die "GitHub authentication is unavailable; stopped"

for directory in "${RELAY_RUNTIME}" "${LOG_DIR}" "${LAUNCH_AGENTS_DIR}"; do
  if [[ -e "${directory}" ]]; then
    [[ -d "${directory}" && ! -L "${directory}" ]] || die "unsafe generated directory"
  else
    /bin/mkdir -p -- "${directory}"
  fi
  /bin/chmod 700 "${directory}"
done

for target in "${TARGET_RELAY}" "${TARGET_RUNNER}" "${TARGET_PLIST}" "${RELAY_RUNTIME}/managed_repo.py" "${RELAY_RUNTIME}/supervision.py"; do
  [[ ! -e "${target}" || ( -f "${target}" && ! -L "${target}" ) ]] \
    || die "unsafe generated file target"
done

/usr/bin/install -m 700 "${SOURCE_RELAY}" "${TARGET_RELAY}"
/usr/bin/install -m 700 "${SOURCE_RUNNER}" "${TARGET_RUNNER}"
/usr/bin/install -m 600 "${SOURCE_MANAGED_REPO}" "${RELAY_RUNTIME}/managed_repo.py"
/usr/bin/install -m 600 "${SOURCE_SUPERVISION}" "${RELAY_RUNTIME}/supervision.py"

readonly PLIST_TMP="$(/usr/bin/mktemp "${LAUNCH_AGENTS_DIR}/${LABEL}.plist.XXXXXX")"
cleanup() {
  if [[ -f "${PLIST_TMP}" && ! -L "${PLIST_TMP}" ]]; then
    /bin/rm -f -- "${PLIST_TMP}"
  fi
}
trap cleanup EXIT

LABEL_OUT="${LABEL}" \
RUNNER_OUT="${TARGET_RUNNER}" \
STDOUT_OUT="${LOG_DIR}/github-relay.stdout.log" \
STDERR_OUT="${LOG_DIR}/github-relay.stderr.log" \
PLIST_TMP_OUT="${PLIST_TMP}" \
/usr/bin/python3 -c '
import os
import plistlib
from pathlib import Path

payload = {
    "Label": os.environ["LABEL_OUT"],
    "ProgramArguments": ["/bin/zsh", os.environ["RUNNER_OUT"]],
    "RunAtLoad": True,
    "KeepAlive": {"SuccessfulExit": False},
    "ThrottleInterval": 15,
    "ProcessType": "Background",
    "StandardOutPath": os.environ["STDOUT_OUT"],
    "StandardErrorPath": os.environ["STDERR_OUT"],
}
with Path(os.environ["PLIST_TMP_OUT"]).open("wb") as output:
    plistlib.dump(payload, output, fmt=plistlib.FMT_XML, sort_keys=True)
'

/usr/bin/plutil -lint "${PLIST_TMP}" >/dev/null || die "generated LaunchAgent is invalid"
/bin/chmod 600 "${PLIST_TMP}"

readonly RELAY_JOB="${DOMAIN}/${LABEL}"
if /bin/launchctl print "${RELAY_JOB}" >/dev/null 2>&1; then
  /bin/launchctl bootout "${RELAY_JOB}"
fi
/bin/mv -f -- "${PLIST_TMP}" "${TARGET_PLIST}"
trap - EXIT

if (( no_start == 1 )); then
  print -r -- "github-relay: installed status=configured"
  exit 0
fi

/bin/launchctl enable "${RELAY_JOB}"
/bin/launchctl bootstrap "${DOMAIN}" "${TARGET_PLIST}"
/bin/launchctl kickstart -k "${RELAY_JOB}"
print -r -- "github-relay: installed status=started"
