#!/bin/zsh

set -euo pipefail

usage() {
  print -u2 "usage: ${0:t} [--repo PATH | --export PATH] [--denylist ABSOLUTE_FILE]"
}

repo=""
denylist=""
export_mode=0
while (( $# > 0 )); do
  case "$1" in
    --repo)
      [[ -z "$repo" ]] || { usage; exit 2; }
      (( $# >= 2 )) || { usage; exit 2; }
      repo="$2"
      shift 2
      ;;
    --export)
      [[ -z "$repo" && $# -ge 2 ]] || { usage; exit 2; }
      repo="$2"
      export_mode=1
      shift 2
      ;;
    --denylist)
      (( $# >= 2 )) || { usage; exit 2; }
      denylist="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$repo" ]]; then
  script_dir="${0:A:h}"
  repo="${script_dir:h:h}"
fi

if (( export_mode )); then
  [[ -d "$repo" && ! -L "$repo" ]] || { usage; exit 2; }
  repo="${repo:A}"
  if [[ -n "$(find "$repo" -name .git -o -type l)" ]]; then
    print -u2 "public-sanitization: export must contain no Git metadata or symlinks"
    exit 2
  fi
else
  repo="$(git -C "$repo" rev-parse --show-toplevel)" || {
    print -u2 "public-sanitization: target is not a Git worktree"
    exit 2
  }
fi

scan_files() {
  if (( export_mode )); then
    (cd "$repo" && find . -type f -print0)
  else
    git -C "$repo" ls-files -z
  fi
}

typeset -a deny_values
deny_values=()
if [[ -n "$denylist" ]]; then
  [[ "$denylist" == /* && -f "$denylist" && ! -L "$denylist" && -r "$denylist" ]] || {
    print -u2 "public-sanitization: denylist must be a readable absolute regular file"
    exit 2
  }
  while IFS= read -r value || [[ -n "$value" ]]; do
    [[ -n "$value" ]] || continue
    (( ${#value} <= 1024 )) || {
      print -u2 "public-sanitization: denylist entry is too long"
      exit 2
    }
    deny_values+=("$value")
  done < "$denylist"
fi

failures=0

report_fixed_matches() {
  local relative="$1"
  local value="$2"
  local label="$3"
  local line

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    print -u2 "public-sanitization: ${label}: ${relative}:${line%%:*}"
    failures=$(( failures + 1 ))
  done < <(LC_ALL=C grep -I -i -n -F -- "$value" "$repo/$relative" || true)
}

while IFS= read -r -d '' relative; do
  [[ -f "$repo/$relative" ]] || continue

  for value in "${deny_values[@]}"; do
    report_fixed_matches "$relative" "$value" "private denylist match"
  done

  while IFS= read -r match; do
    [[ -n "$match" ]] || continue
    value="${match#*:}"
    case "$value" in
      /Users/example-user*|/Users/isolated-user*|/Users/test-user*)
        ;;
      *)
        print -u2 "public-sanitization: non-synthetic macOS home: ${relative}:${match%%:*}"
        failures=$(( failures + 1 ))
        ;;
    esac
  done < <(LC_ALL=C grep -I -n -o -E '/Users/[A-Za-z0-9._-]+' "$repo/$relative" || true)

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    print -u2 "public-sanitization: host-specific validation telemetry: ${relative}:${line%%:*}"
    failures=$(( failures + 1 ))
  done < <(LC_ALL=C grep -I -i -n -E \
    '(live|private|personal)[[:space:]-]+(account|host|machine|network)[[:space:]-]+(evidence|observation|telemetry|validation)' \
    "$repo/$relative" || true)
done < <(scan_files)

if (( failures > 0 )); then
  print -u2 "public-sanitization: FAIL (${failures} finding(s))"
  exit 1
fi

print "public-sanitization: PASS"
