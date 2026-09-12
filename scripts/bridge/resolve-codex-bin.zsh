#!/bin/zsh

set -u

validate_codex() {
  local candidate="$1"

  [[ "${candidate}" == /* ]] || return 1
  [[ -x "${candidate}" ]] || return 1
  "${candidate}" --version >/dev/null 2>&1 || return 1
  "${candidate}" mcp-server --help >/dev/null 2>&1 || return 1
}

explicit_candidate="${CODEX_BRIDGE_BIN-}"
if [[ -n "${explicit_candidate}" ]]; then
  if ! validate_codex "${explicit_candidate}"; then
    print -u2 -r -- "ERROR: explicit Codex executable is not usable"
    exit 1
  fi
  print -r -- "${explicit_candidate}"
  exit 0
fi

typeset -a candidates
candidates=()
if [[ -n "${HOME-}" ]]; then
  candidates+=("${HOME}/.local/bin/codex")
fi

if [[ -n "${PATH-}" ]]; then
  typeset -a path_directories
  path_directories=("${(s/:/)PATH}")
  for path_directory in "${path_directories[@]}"; do
    [[ "${path_directory}" == /* ]] || continue
    candidates+=("${path_directory%/}/codex")
  done
fi

candidates+=("/Applications/ChatGPT.app/Contents/Resources/codex")

typeset -A seen_candidates
for candidate in "${candidates[@]}"; do
  [[ -n "${seen_candidates[${candidate}]-}" ]] && continue
  seen_candidates[${candidate}]=1
  if validate_codex "${candidate}"; then
    print -r -- "${candidate}"
    exit 0
  fi
done

print -u2 -r -- "ERROR: no working Codex executable found; set CODEX_BRIDGE_BIN to an absolute working path"
exit 1
