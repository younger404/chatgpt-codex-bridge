#!/bin/zsh
set -euo pipefail
readonly SCRIPT_DIR="${0:A:h}"
exec /bin/zsh "${SCRIPT_DIR}/chatgpt-codex-bridge.zsh" doctor "$@"
