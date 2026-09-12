#!/bin/zsh

set -u

readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-code-preflight.XXXXXX)"
readonly REPO_ROOT="${0:A:h:h:h}"
readonly PREFLIGHT="${REPO_ROOT}/scripts/bridge/local-preflight.zsh"
typeset -i failures=0

cleanup() {
  if [[ -d "${TEST_ROOT}" && ! -L "${TEST_ROOT}" && "${TEST_ROOT}" == /tmp/chatgpt-code-preflight.* ]]; then
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
  {
    print -r -- '#!/bin/zsh'
    print -r -- 'case "$*" in'
    print -r -- '  "--version") print -r -- "codex-cli 9.9.9-test" ;;'
    print -r -- '  "mcp-server --help") print -r -- "Codex MCP test help" ;;'
    print -r -- '  *) exit 64 ;;'
    print -r -- 'esac'
  } > "${target}"
  chmod 755 "${target}"
}

make_fake_tunnel() {
  local target="$1"
  {
    print -r -- '#!/bin/zsh'
    print -r -- '[[ "$*" == "--version" ]] || exit 64'
    print -r -- 'print -r -- "tunnel-client 1.2.3-test"'
  } > "${target}"
  chmod 755 "${target}"
}

make_fake_id() {
  local target="$1"
  local groups="$2"
  {
    print -r -- '#!/bin/zsh'
    print -r -- '[[ "$*" == "-Gn" ]] || exit 64'
    print -r -- "print -r -- \"${groups}\""
  } > "${target}"
  chmod 755 "${target}"
}

value_for() {
  local key="$1"
  local file="$2"
  local line
  while IFS= read -r line; do
    if [[ "${line%%=*}" == "${key}" ]]; then
      print -r -- "${line#*=}"
      return 0
    fi
  done < "${file}"
  return 1
}

assert_allowed_keys_only() {
  local file="$1"
  local line key
  local allowed=' codex_path codex_version codex_mcp_server tunnel_client tunnel_client_version user_privilege sandbox_exists overall_status '
  while IFS= read -r line; do
    key="${line%%=*}"
    if [[ "${allowed}" != *" ${key} "* ]]; then
      fail "preflight output contains only approved keys (unexpected=${key:q})"
      return
    fi
  done < "${file}"
  pass "preflight output contains only approved keys"
}

bin_dir="${TEST_ROOT}/bin"
sandbox_dir="${TEST_ROOT}/approved-sandbox"
mkdir -p -- "${bin_dir}" "${sandbox_dir}"
codex_bin="${bin_dir}/codex-proof"
make_fake_codex "${codex_bin}"
make_fake_tunnel "${bin_dir}/tunnel-client"
make_fake_id "${bin_dir}/id" "staff admin"

stdout_file="${TEST_ROOT}/pass.stdout"
stderr_file="${TEST_ROOT}/pass.stderr"
CODEX_BRIDGE_BIN="${codex_bin}" \
PATH="${bin_dir}:/usr/bin:/bin" \
BRIDGE_TEST_SECRET="must-not-be-printed-a991" \
  /bin/zsh "${PREFLIGHT}" --sandbox "${sandbox_dir}" > "${stdout_file}" 2> "${stderr_file}"
pass_status=$?

assert_equal "0" "${pass_status}" "admin ready preflight exits successfully"
assert_equal "${codex_bin}" "$(value_for codex_path "${stdout_file}")" "preflight reports resolved Codex path"
assert_equal "codex-cli 9.9.9-test" "$(value_for codex_version "${stdout_file}")" "preflight reports Codex version"
assert_equal "AVAILABLE" "$(value_for codex_mcp_server "${stdout_file}")" "preflight reports MCP server availability"
assert_equal "AVAILABLE" "$(value_for tunnel_client "${stdout_file}")" "preflight reports tunnel availability"
assert_equal "tunnel-client 1.2.3-test" "$(value_for tunnel_client_version "${stdout_file}")" "preflight reports tunnel version"
assert_equal "admin" "$(value_for user_privilege "${stdout_file}")" "preflight reports admin user"
assert_equal "YES" "$(value_for sandbox_exists "${stdout_file}")" "preflight reports existing sandbox"
assert_equal "PASS" "$(value_for overall_status "${stdout_file}")" "ready preflight reports PASS"
assert_allowed_keys_only "${stdout_file}"
assert_equal "8" "$(wc -l < "${stdout_file}" | tr -d ' ')" "preflight emits exactly the approved report fields"
assert_not_contains "$(<"${stdout_file}")$(<"${stderr_file}")" "${sandbox_dir:A}" "preflight does not print the approved sandbox path"
assert_not_contains "$(<"${stdout_file}")$(<"${stderr_file}")" "must-not-be-printed-a991" "preflight does not print environment contents"

make_fake_id "${bin_dir}/id" "staff"
stdout_file="${TEST_ROOT}/non-admin.stdout"
stderr_file="${TEST_ROOT}/non-admin.stderr"
CODEX_BRIDGE_BIN="${codex_bin}" \
PATH="${bin_dir}:/usr/bin:/bin" \
  /bin/zsh "${PREFLIGHT}" --sandbox "${sandbox_dir}" > "${stdout_file}" 2> "${stderr_file}"
non_admin_status=$?

if (( non_admin_status != 0 )); then
  pass "non-admin user fails the total gate"
else
  fail "non-admin user fails the total gate"
fi
assert_equal "non-admin" "$(value_for user_privilege "${stdout_file}")" "preflight reports non-admin user"
assert_equal "FAIL" "$(value_for overall_status "${stdout_file}")" "non-admin preflight reports FAIL"

make_fake_id "${bin_dir}/id" "staff admin"
missing_sandbox="${TEST_ROOT}/missing-sandbox"
stdout_file="${TEST_ROOT}/missing.stdout"
stderr_file="${TEST_ROOT}/missing.stderr"
CODEX_BRIDGE_BIN="${codex_bin}" \
PATH="${bin_dir}:/usr/bin:/bin" \
  /bin/zsh "${PREFLIGHT}" --sandbox "${missing_sandbox}" > "${stdout_file}" 2> "${stderr_file}"
missing_status=$?

if (( missing_status != 0 )); then
  pass "missing approved sandbox fails the total gate"
else
  fail "missing approved sandbox fails the total gate"
fi
assert_equal "NO" "$(value_for sandbox_exists "${stdout_file}")" "preflight reports missing sandbox"
assert_equal "FAIL" "$(value_for overall_status "${stdout_file}")" "missing-sandbox preflight reports FAIL"
assert_not_contains "$(<"${stdout_file}")$(<"${stderr_file}")" "${missing_sandbox:A}" "preflight does not print the missing sandbox path"

no_tunnel_bin="${TEST_ROOT}/no-tunnel-bin"
mkdir -p -- "${no_tunnel_bin}"
make_fake_id "${no_tunnel_bin}/id" "staff admin"
stdout_file="${TEST_ROOT}/no-tunnel.stdout"
stderr_file="${TEST_ROOT}/no-tunnel.stderr"
CODEX_BRIDGE_BIN="${codex_bin}" \
PATH="${no_tunnel_bin}:/usr/bin:/bin" \
  /bin/zsh "${PREFLIGHT}" --sandbox "${sandbox_dir}" > "${stdout_file}" 2> "${stderr_file}"
no_tunnel_status=$?

if (( no_tunnel_status != 0 )); then
  pass "unavailable tunnel-client fails the total gate"
else
  fail "unavailable tunnel-client fails the total gate"
fi
assert_equal "UNAVAILABLE" "$(value_for tunnel_client "${stdout_file}")" "preflight reports unavailable tunnel-client"
assert_equal "UNAVAILABLE" "$(value_for tunnel_client_version "${stdout_file}")" "preflight does not invent a tunnel version"
assert_equal "FAIL" "$(value_for overall_status "${stdout_file}")" "no-tunnel preflight reports FAIL"

unresolved_codex="${TEST_ROOT}/unresolved/codex"
stdout_file="${TEST_ROOT}/unresolved.stdout"
stderr_file="${TEST_ROOT}/unresolved.stderr"
CODEX_BRIDGE_BIN="${unresolved_codex}" \
PATH="${bin_dir}:/usr/bin:/bin" \
  /bin/zsh "${PREFLIGHT}" --sandbox "${sandbox_dir}" > "${stdout_file}" 2> "${stderr_file}"
unresolved_status=$?

if (( unresolved_status != 0 )); then
  pass "unresolved Codex executable fails the total gate"
else
  fail "unresolved Codex executable fails the total gate"
fi
assert_equal "UNRESOLVED" "$(value_for codex_path "${stdout_file}")" "preflight reports unresolved Codex without echoing its input"
assert_equal "UNAVAILABLE" "$(value_for codex_version "${stdout_file}")" "preflight reports unavailable Codex version"
assert_equal "UNAVAILABLE" "$(value_for codex_mcp_server "${stdout_file}")" "preflight reports unavailable MCP server"
assert_equal "FAIL" "$(value_for overall_status "${stdout_file}")" "unresolved-Codex preflight reports FAIL"
assert_not_contains "$(<"${stdout_file}")$(<"${stderr_file}")" "${unresolved_codex}" "preflight does not print the unresolved explicit path"

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi

print -r -- "RESULT: PASS"
