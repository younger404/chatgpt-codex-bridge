#!/bin/zsh
set -euo pipefail

readonly STATE_DIR="${HOME}/Library/Application Support/chatgpt-codex-bridge"
readonly CONFIG_FILE="${STATE_DIR}/config.plist"
readonly RELAY_RUNTIME="${HOME}/.local/share/chatgpt-codex-bridge/github-relay"
readonly RELAY="${RELAY_RUNTIME}/github-issue-relay.py"
readonly PYTHON_BIN="$(/usr/bin/plutil -extract python_bin raw -o - "${CONFIG_FILE}")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

[[ -f "${CONFIG_FILE}" && ! -L "${CONFIG_FILE}" ]] || exit 64
[[ -x "${PYTHON_BIN}" && -f "${RELAY}" && ! -L "${RELAY}" ]] || exit 64
command -v gh >/dev/null 2>&1 || exit 69
gh auth status --hostname github.com >/dev/null 2>&1 || exit 78

export CHATGPT_CODEX_BRIDGE_CONFIG="${CONFIG_FILE}"
exec "${PYTHON_BIN}" "${RELAY}" --watch --config "${CONFIG_FILE}"
