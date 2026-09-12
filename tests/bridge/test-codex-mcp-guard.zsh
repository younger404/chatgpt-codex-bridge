#!/bin/zsh

set -u

readonly REPO_ROOT="${0:A:h:h:h}"
readonly CONTRACT_TEST="${REPO_ROOT}/tests/bridge/test-codex-mcp-guard.py"

if PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -W error::ResourceWarning "${CONTRACT_TEST}"; then
  print -r -- "RESULT: PASS"
  exit 0
fi

print -u2 -r -- "RESULT: FAIL"
exit 1
