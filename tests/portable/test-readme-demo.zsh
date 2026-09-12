#!/bin/zsh
set -u

readonly REPO_ROOT="${0:A:h:h:h}"
readonly README="${REPO_ROOT}/plugins/chatgpt-codex-bridge/README.md"
readonly SERVICE="${REPO_ROOT}/plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh"
readonly REGISTRY_CLI="${REPO_ROOT}/plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh"
typeset -i failures=0

check() {
  if "$@"; then
    print -r -- "PASS: $*"
  else
    print -u2 -r -- "FAIL: $*"
    (( failures += 1 ))
  fi
}

check test -f "${README}"
check test -x "${SERVICE}"
check test -x "${REGISTRY_CLI}"
check grep -q -- '--preset managed-repo' "${README}"
check grep -q -- 'codex-repo-start' "${README}"
check grep -q -- 'codex-repo-publish' "${README}"
check /bin/zsh -n "${SERVICE}"
check /bin/zsh -n "${REGISTRY_CLI}"
check /bin/zsh "${SERVICE}" --help
check /bin/zsh "${REGISTRY_CLI}" --help

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi
print -r -- "RESULT: PASS"
