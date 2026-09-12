#!/bin/zsh

set -u

readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-code-resolver.XXXXXX)"
readonly REPO_ROOT="${0:A:h:h:h}"
readonly RESOLVER="${REPO_ROOT}/scripts/bridge/resolve-codex-bin.zsh"
typeset -i failures=0

cleanup() {
  if [[ -d "${TEST_ROOT}" && ! -L "${TEST_ROOT}" && "${TEST_ROOT}" == /tmp/chatgpt-code-resolver.* ]]; then
    rm -rf -- "${TEST_ROOT}"
  fi
}
trap cleanup EXIT

pass() {
  print -r -- "PASS: $1"
}

fail() {
  print -u2 -r -- "FAIL: $1"
  (( failures += 1 ))
}

assert_equal() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    pass "${label}"
  else
    fail "${label} (expected=${expected:q}, actual=${actual:q})"
  fi
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    pass "${label}"
  else
    fail "${label} (missing=${needle:q})"
  fi
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    fail "${label} (unexpected=${needle:q})"
  else
    pass "${label}"
  fi
}

make_fake_codex() {
  local target="$1"
  mkdir -p -- "${target:h}"
  {
    print -r -- '#!/bin/zsh'
    print -r -- 'print -r -- "$*" >> "${FAKE_CODEX_LOG:?}"'
    print -r -- 'case "$*" in'
    print -r -- '  "--version") print -r -- "codex-cli 9.9.9-test" ;;'
    print -r -- '  "mcp-server --help") print -r -- "Codex MCP test help" ;;'
    print -r -- '  *) exit 64 ;;'
    print -r -- 'esac'
  } > "${target}"
  chmod 755 "${target}"
}

make_broken_codex() {
  local target="$1"
  mkdir -p -- "${target:h}"
  {
    print -r -- '#!/bin/zsh'
    print -r -- 'print -r -- "$*" >> "${FAKE_BROKEN_CODEX_LOG:?}"'
    print -r -- 'exit 1'
  } > "${target}"
  chmod 755 "${target}"
}

run_resolver() {
  local stdout_file="$1"
  local stderr_file="$2"
  shift 2
  "$@" > "${stdout_file}" 2> "${stderr_file}"
}

explicit_bin="${TEST_ROOT}/explicit/codex"
default_bin="${TEST_ROOT}/home/.local/bin/codex"
explicit_log="${TEST_ROOT}/explicit.log"
default_log="${TEST_ROOT}/default.log"
make_fake_codex "${explicit_bin}"
make_fake_codex "${default_bin}"
: > "${explicit_log}"
: > "${default_log}"

stdout_file="${TEST_ROOT}/explicit.stdout"
stderr_file="${TEST_ROOT}/explicit.stderr"
FAKE_CODEX_LOG="${explicit_log}" \
CODEX_BRIDGE_BIN="${explicit_bin}" \
HOME="${TEST_ROOT}/home" \
PATH="/usr/bin:/bin" \
BRIDGE_TEST_SECRET="must-not-be-printed-7f4e" \
  run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
explicit_status=$?

assert_equal "0" "${explicit_status}" "explicit executable succeeds"
assert_equal "${explicit_bin}" "$(<"${stdout_file}")" "explicit executable wins"
assert_equal $'--version\nmcp-server --help' "$(<"${explicit_log}")" "resolver validates only version and MCP help"
assert_equal "" "$(<"${default_log}")" "fallback executable is not invoked after explicit success"
assert_not_contains "$(<"${stdout_file}")$(<"${stderr_file}")" "must-not-be-printed-7f4e" "environment contents are not printed"

stdout_file="${TEST_ROOT}/missing.stdout"
stderr_file="${TEST_ROOT}/missing.stderr"
CODEX_BRIDGE_BIN="${TEST_ROOT}/missing/codex" \
HOME="${TEST_ROOT}/home" \
PATH="/usr/bin:/bin" \
  run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
missing_status=$?

if (( missing_status != 0 )); then
  pass "missing explicit executable fails closed"
else
  fail "missing explicit executable fails closed"
fi
assert_contains "$(<"${stderr_file}")" "explicit Codex executable is not usable" "missing explicit failure is diagnostic"
assert_not_contains "$(<"${stderr_file}")" "${TEST_ROOT}/missing/codex" "failure does not echo the explicit environment value"

stdout_file="${TEST_ROOT}/relative.stdout"
stderr_file="${TEST_ROOT}/relative.stderr"
CODEX_BRIDGE_BIN="relative/codex" \
HOME="${TEST_ROOT}/home" \
PATH="/usr/bin:/bin" \
  run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
relative_status=$?

if (( relative_status != 0 )); then
  pass "non-absolute explicit executable fails closed"
else
  fail "non-absolute explicit executable fails closed"
fi
assert_contains "$(<"${stderr_file}")" "explicit Codex executable is not usable" "non-absolute explicit failure is diagnostic"

bad_path_dir="${TEST_ROOT}/path-bad"
good_path_dir="${TEST_ROOT}/path-good"
bad_path_bin="${bad_path_dir}/codex"
good_path_bin="${good_path_dir}/codex"
bad_path_log="${TEST_ROOT}/path-bad.log"
good_path_log="${TEST_ROOT}/path-good.log"
make_broken_codex "${bad_path_bin}"
make_fake_codex "${good_path_bin}"
: > "${bad_path_log}"
: > "${good_path_log}"
empty_path_home="${TEST_ROOT}/path-home"
mkdir -p -- "${empty_path_home}"
stdout_file="${TEST_ROOT}/path.stdout"
stderr_file="${TEST_ROOT}/path.stderr"
FAKE_BROKEN_CODEX_LOG="${bad_path_log}" \
FAKE_CODEX_LOG="${good_path_log}" \
CODEX_BRIDGE_BIN="" \
HOME="${empty_path_home}" \
PATH="${bad_path_dir}:${good_path_dir}:/usr/bin:/bin" \
  run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
path_status=$?

assert_equal "0" "${path_status}" "resolver continues after a broken PATH candidate"
assert_equal "${good_path_bin}" "$(<"${stdout_file}")" "resolver selects the next capable PATH candidate"
assert_equal "--version" "$(<"${bad_path_log}")" "broken PATH candidate stops after failed version check"
assert_equal $'--version\nmcp-server --help' "$(<"${good_path_log}")" "working PATH candidate passes both capability checks"

readonly HOMEBREW_CODEX="/opt/homebrew/bin/codex"
if [[ -x "${HOMEBREW_CODEX}" ]] \
   && ! { "${HOMEBREW_CODEX}" --version >/dev/null 2>&1 \
          && "${HOMEBREW_CODEX}" mcp-server --help >/dev/null 2>&1; }; then
  stdout_file="${TEST_ROOT}/homebrew.stdout"
  stderr_file="${TEST_ROOT}/homebrew.stderr"
  CODEX_BRIDGE_BIN="${HOMEBREW_CODEX}" \
  HOME="${TEST_ROOT}/home" \
  PATH="/usr/bin:/bin" \
    run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
  homebrew_status=$?

  if (( homebrew_status != 0 )); then
    pass "currently broken Homebrew executable fails capability validation"
  else
    fail "currently broken Homebrew executable fails capability validation"
  fi
  assert_contains "$(<"${stderr_file}")" "explicit Codex executable is not usable" "Homebrew failure uses the capability diagnostic"
else
  print -r -- "SKIP: Homebrew Codex is absent or now passes capability validation"
fi

readonly APP_CODEX="/Applications/ChatGPT.app/Contents/Resources/codex"
if [[ -x "${APP_CODEX}" ]]; then
  empty_home="${TEST_ROOT}/empty-home"
  mkdir -p -- "${empty_home}"
  app_log="${TEST_ROOT}/app.log"
  : > "${app_log}"
  stdout_file="${TEST_ROOT}/app.stdout"
  stderr_file="${TEST_ROOT}/app.stderr"
  FAKE_CODEX_LOG="${app_log}" \
  CODEX_BRIDGE_BIN="" \
  HOME="${empty_home}" \
  PATH="/usr/bin:/bin" \
    run_resolver "${stdout_file}" "${stderr_file}" /bin/zsh "${RESOLVER}"
  app_status=$?
  assert_equal "0" "${app_status}" "ChatGPT App bundled executable passes validation"
  assert_equal "${APP_CODEX}" "$(<"${stdout_file}")" "ChatGPT App bundled executable is selected"
else
  print -r -- "SKIP: ChatGPT App bundled executable is not installed on this host"
fi

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi

print -r -- "RESULT: PASS"
