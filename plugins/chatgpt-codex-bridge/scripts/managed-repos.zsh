#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
STATE_DIR="${CHATGPT_CODEX_BRIDGE_STATE_DIR:-${HOME}/Library/Application Support/chatgpt-codex-bridge}"
REGISTRY_PATH="${CHATGPT_CODEX_BRIDGE_MANAGED_REGISTRY:-${STATE_DIR}/managed-repos.v1.json}"

exec /usr/bin/python3 "${SCRIPT_DIR:h}/bridge/managed_repo.py" \
  --registry "${REGISTRY_PATH}" "$@"
