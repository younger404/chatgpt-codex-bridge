#!/bin/zsh
set -euo pipefail
readonly SCRIPT_DIR="${0:A:h}"
exec /usr/bin/python3 -I "${SCRIPT_DIR}/install-github-relay-v1.py" "$@"
