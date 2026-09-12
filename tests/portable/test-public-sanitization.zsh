#!/bin/zsh

set -euo pipefail

readonly REPO_ROOT="${0:A:h:h:h}"
readonly CHECKER="${REPO_ROOT}/scripts/release/check-public-sanitization.zsh"
readonly TEMP_PARENT="${TMPDIR:-/tmp}"
fixture_root="$(mktemp -d "${TEMP_PARENT%/}/chatgpt-code-public-sanitization.XXXXXX")"

cleanup() {
  [[ -n "${fixture_root:-}" ]] || return
  [[ ! -L "$fixture_root" ]] || return
  case "$fixture_root" in
    "${TEMP_PARENT%/}"/chatgpt-code-public-sanitization.*) ;;
    *) return ;;
  esac
  find "$fixture_root" -depth -mindepth 1 -delete
  rmdir "$fixture_root"
}
trap cleanup EXIT

[[ -x "$CHECKER" ]] || {
  print -u2 "missing executable privacy checker: $CHECKER"
  exit 1
}

if [[ -e "${REPO_ROOT}/.git" ]]; then
  "$CHECKER" --repo "$REPO_ROOT"
else
  "$CHECKER" --export "$REPO_ROOT"
fi

denylist_file="${fixture_root}/private-denylist.txt"
print -r -- "private-machine-sentinel" > "$denylist_file"

git -C "$fixture_root" init -q
print -r -- "safe synthetic content" > "$fixture_root/leak.txt"
git -C "$fixture_root" add leak.txt
"$CHECKER" --repo "$fixture_root" --denylist "$denylist_file" >/dev/null \
  || {
    print -u2 "privacy checker rejected supported untracked denylist input"
    exit 1
  }
typeset -a fixtures
fixtures=(
  '/Users/'"actual-person"'/workspace'
)

index=0
for fixture in "${fixtures[@]}"; do
  index=$(( index + 1 ))
  print -r -- "$fixture" > "$fixture_root/leak.txt"
  git -C "$fixture_root" add leak.txt
  if "$CHECKER" --repo "$fixture_root" >/dev/null 2>&1; then
    print -u2 "privacy checker accepted negative fixture ${index}"
    exit 1
  fi
done

print -r -- "private-machine-sentinel" > "$fixture_root/leak.txt"
git -C "$fixture_root" add leak.txt
if "$CHECKER" --repo "$fixture_root" --denylist "$denylist_file" >/dev/null 2>&1; then
  print -u2 "privacy checker accepted an untracked denylist fixture"
  exit 1
fi

export_fixture="${fixture_root}/export"
mkdir "$export_fixture"
print -r -- "safe synthetic content" > "$export_fixture/content.txt"
"$CHECKER" --export "$export_fixture" --denylist "$denylist_file" >/dev/null
print -r -- "private-machine-sentinel" > "$export_fixture/content.txt"
if "$CHECKER" --export "$export_fixture" --denylist "$denylist_file" >/dev/null 2>&1; then
  print -u2 "privacy checker accepted a clean-export denylist match"
  exit 1
fi
print "public sanitization tests: PASS"
