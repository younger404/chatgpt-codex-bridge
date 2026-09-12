#!/bin/zsh
set -u

readonly REPO_ROOT="${0:A:h:h:h}"
readonly PLUGIN_ROOT="${REPO_ROOT}/plugins/chatgpt-codex-bridge"
readonly SERVICE="${PLUGIN_ROOT}/scripts/chatgpt-codex-bridge.zsh"
readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-codex-portable.XXXXXX)"
typeset -i failures=0

cleanup() {
  if [[ -d "${TEST_ROOT}" && ! -L "${TEST_ROOT}" && "${TEST_ROOT}" == /tmp/chatgpt-codex-portable.* ]]; then
    rm -rf -- "${TEST_ROOT}"
  fi
}
trap cleanup EXIT

pass() { print -r -- "PASS: $1"; }
fail() { print -u2 -r -- "FAIL: $1"; (( failures += 1 )); }
assert_equal() {
  [[ "$1" == "$2" ]] && pass "$3" || fail "$3 (expected=${1:q}, actual=${2:q})"
}

make_fake_codex() {
  mkdir -p -- "${1:h}"
  /usr/bin/printf '%s\n' '#!/bin/zsh' 'case "$*" in' '  "--version") print "codex-cli test" ;;' '  "mcp-server --help") print "MCP help" ;;' '  *) exit 64 ;;' 'esac' > "$1"
  chmod 755 "$1"
}

make_fake_tunnel() {
  local version="${2:-0.0.11-test}"
  mkdir -p -- "${1:h}"
  /usr/bin/printf '%s\n' '#!/bin/zsh' 'case "$*" in' "  \"--version\") print \"${version}\" ;;" '  "doctor --profile portable-profile") exit 0 ;;' '  *) exit 64 ;;' 'esac' > "$1"
  chmod 755 "$1"
}

[[ -x "${SERVICE}" ]] || {
  print -u2 -- "FAIL: portable service command is missing"
  exit 1
}

fake_home="${TEST_ROOT}/another-user"
workspace="${TEST_ROOT}/workspace with spaces"
codex_bin="${TEST_ROOT}/bin/codex"
tunnel_bin="${TEST_ROOT}/bin/tunnel-client"
mkdir -p -- "${fake_home}" "${workspace}"
make_fake_codex "${codex_bin}"
make_fake_tunnel "${tunnel_bin}"

HOME="${fake_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --label com.example.chatgpt-codex-test \
  --preset workspace-safe \
  --no-start >/dev/null
install_status=$?
assert_equal 0 "${install_status}" "isolated portable install succeeds"

state_dir="${fake_home}/Library/Application Support/chatgpt-codex-bridge"
runtime_dir="${fake_home}/.local/share/chatgpt-codex-bridge"
config="${state_dir}/config.plist"
plist="${fake_home}/Library/LaunchAgents/com.example.chatgpt-codex-test.plist"

[[ -f "${config}" ]] && pass "non-secret config is generated" || fail "non-secret config is generated"
[[ -f "${plist}" ]] && pass "LaunchAgent is generated" || fail "LaunchAgent is generated"
[[ -x "${runtime_dir}/run-guard.zsh" ]] && pass "runtime wrapper is staged" || fail "runtime wrapper is staged"
[[ -x "${runtime_dir}/codex-mcp-guard.py" ]] && pass "Guard is staged" || fail "Guard is staged"
staged_skill="${runtime_dir}/skills/workspace-new-project/SKILL.md"
staged_bootstrap="${runtime_dir}/skills/workspace-new-project/scripts/create_workspace_project.sh"
[[ -f "${staged_skill}" ]] && pass "portable new-project skill is staged" || fail "portable new-project skill is staged"
[[ -x "${staged_bootstrap}" ]] && pass "portable new-project bootstrap is staged" || fail "portable new-project bootstrap is staged"
bootstrap_root="${TEST_ROOT}/fresh-project"
mkdir -- "${bootstrap_root}"
(cd "${bootstrap_root}" && HOME="${fake_home}" /bin/zsh "${staged_bootstrap}" --here >/dev/null)
bootstrap_status=$?
assert_equal 0 "${bootstrap_status}" "staged new-project bootstrap runs in an empty HOME"
for marker in AGENTS.md README.md .gitignore docs/specs docs/adr src .project-memory; do
  [[ -e "${bootstrap_root}/${marker}" ]] \
    && pass "bootstrap creates ${marker}" || fail "bootstrap creates ${marker}"
done

if [[ -f "${config}" && -f "${plist}" ]]; then
  /usr/bin/plutil -lint "${config}" >/dev/null && pass "config plist validates" || fail "config plist validates"
  /usr/bin/plutil -lint "${plist}" >/dev/null && pass "LaunchAgent plist validates" || fail "LaunchAgent plist validates"
  assert_equal "${workspace:A}" "$(/usr/bin/plutil -extract workspace raw -o - "${config}")" "workspace with spaces is preserved"
  assert_equal "workspace-write" "$(/usr/bin/plutil -extract sandbox raw -o - "${config}")" "safe preset fixes workspace sandbox"
  assert_equal "on-request" "$(/usr/bin/plutil -extract approval_policy raw -o - "${config}")" "safe preset fixes approval policy"
  assert_equal "${staged_skill}" "$(/usr/bin/plutil -extract workspace_new_project_skill raw -o - "${config}")" "config pins the staged new-project skill"
  assert_equal "${runtime_dir}/run-guard.zsh" "$(/usr/bin/plutil -extract ProgramArguments.9 raw -o - "${plist}" | sed 's/^command=//')" "Tunnel command uses no-space runtime wrapper"
  assert_equal "true" "$(/usr/bin/plutil -extract RunAtLoad raw -o - "${plist}")" "LaunchAgent starts at login"
  assert_equal "true" "$(/usr/bin/plutil -extract KeepAlive raw -o - "${plist}")" "LaunchAgent restarts after exit"
fi

HOME="${fake_home}" /bin/zsh "${SERVICE}" doctor --runtime --no-start >/dev/null \
  && pass "doctor validates generated installation" || fail "doctor validates generated installation"

jobs_v2="${state_dir}/jobs-v2"
jobs_v3="${state_dir}/jobs-v3"
mkdir -p -- "${jobs_v2}" "${jobs_v3}"
print -r -- "legacy-key" > "${jobs_v2}/capability.key"
print -r -- "current-key" > "${jobs_v3}/capability.key"

outside_guard="${TEST_ROOT}/outside-guard.py"
/bin/cp "${PLUGIN_ROOT}/bridge/codex-mcp-guard.py" "${outside_guard}"
/bin/chmod 700 "${outside_guard}"
/usr/bin/plutil -replace runtime_guard -string "${outside_guard}" "${config}"
HOME="${fake_home}" /bin/zsh "${SERVICE}" doctor --runtime --no-start >/dev/null 2>&1
tampered_config_status=$?
(( tampered_config_status != 0 )) \
  && pass "doctor rejects runtime paths redirected outside generated state" \
  || fail "doctor rejects runtime paths redirected outside generated state"
/usr/bin/plutil -replace runtime_guard -string "${runtime_dir}/codex-mcp-guard.py" "${config}"

if /usr/bin/grep -R -E -q '(sk-[A-Za-z0-9_-]{12,}|tunnel_[A-Za-z0-9_-]{20,}|bearer[[:space:]]+[A-Za-z0-9._-]+)' "${state_dir}" "${runtime_dir}" "${plist}"; then
  fail "generated installation contains no credential-shaped values"
else
  pass "generated installation contains no credential-shaped values"
fi

HOME="${fake_home}" /bin/zsh "${SERVICE}" uninstall --no-start >/dev/null
uninstall_status=$?
assert_equal 0 "${uninstall_status}" "isolated uninstall succeeds"
[[ ! -e "${plist}" ]] && pass "uninstall removes generated LaunchAgent" || fail "uninstall removes generated LaunchAgent"
[[ ! -e "${runtime_dir}/run-guard.zsh" ]] && pass "uninstall removes generated runtime wrapper" || fail "uninstall removes generated runtime wrapper"
[[ ! -e "${runtime_dir}/skills/workspace-new-project" ]] && pass "uninstall removes staged new-project skill" || fail "uninstall removes staged new-project skill"
[[ ! -e "${jobs_v2}" && ! -e "${jobs_v3}" ]] \
  && pass "uninstall purges bridge-owned capability and job state" \
  || fail "uninstall purges bridge-owned capability and job state"

personal_home="${TEST_ROOT}/personal-home"
personal_workspace="${TEST_ROOT}/personal-workspace"
mkdir -p -- "${personal_home}" "${personal_workspace}"
HOME="${personal_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${personal_workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --label com.example.chatgpt-codex-personal \
  --preset personal-full-control \
  --no-start >/dev/null
personal_status=$?
personal_config="${personal_home}/Library/Application Support/chatgpt-codex-bridge/config.plist"
assert_equal 0 "${personal_status}" "personal preset install succeeds"
assert_equal "danger-full-access" "$(/usr/bin/plutil -extract sandbox raw -o - "${personal_config}")" "personal preset selects danger-full-access"
assert_equal "never" "$(/usr/bin/plutil -extract approval_policy raw -o - "${personal_config}")" "personal preset selects never"
personal_old_plist="${personal_home}/Library/LaunchAgents/com.example.chatgpt-codex-personal.plist"
personal_new_plist="${personal_home}/Library/LaunchAgents/com.example.chatgpt-codex-renamed.plist"
HOME="${personal_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${personal_workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --label com.example.chatgpt-codex-renamed \
  --preset personal-full-control \
  --no-start >/dev/null
[[ ! -e "${personal_old_plist}" ]] \
  && pass "reinstall removes the previous generated label" \
  || fail "reinstall removes the previous generated label"
[[ -f "${personal_new_plist}" ]] \
  && pass "reinstall writes the replacement label" \
  || fail "reinstall writes the replacement label"
/usr/bin/plutil -remove workspace_new_project_skill "${personal_config}"
HOME="${personal_home}" /bin/zsh "${SERVICE}" uninstall --no-start >/dev/null
legacy_uninstall_status=$?
assert_equal 0 "${legacy_uninstall_status}" "uninstall accepts pre-0.5 config without staged-skill key"

invalid_output="${TEST_ROOT}/invalid.out"
HOME="${fake_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --label ../bad-label \
  --preset workspace-safe \
  --no-start >"${invalid_output}" 2>&1
invalid_status=$?
(( invalid_status != 0 )) && pass "invalid label fails closed" || fail "invalid label fails closed"

HOME="${fake_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --no-start >"${invalid_output}" 2>&1
missing_preset_status=$?
(( missing_preset_status != 0 )) \
  && pass "install without explicit preset fails closed" \
  || fail "install without explicit preset fails closed"

wrong_version_home="${TEST_ROOT}/wrong-version-home"
wrong_version_tunnel="${TEST_ROOT}/bin/tunnel-client-wrong-version"
mkdir -p -- "${wrong_version_home}"
make_fake_tunnel "${wrong_version_tunnel}" "0.0.10-test"
HOME="${wrong_version_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${wrong_version_tunnel}" \
  --preset workspace-safe \
  --no-start >"${invalid_output}" 2>&1
wrong_version_status=$?
(( wrong_version_status != 0 )) \
  && pass "installer rejects a tunnel-client version other than 0.0.11" \
  || fail "installer rejects a tunnel-client version other than 0.0.11"

HOME="${fake_home}" /bin/zsh "${SERVICE}" install \
  --profile portable-profile \
  --workspace "${workspace}" \
  --codex-bin "${codex_bin}" \
  --tunnel-client-bin "${tunnel_bin}" \
  --preset unsupported-preset \
  --no-start >"${invalid_output}" 2>&1
invalid_preset_status=$?
(( invalid_preset_status != 0 )) && pass "invalid preset fails closed" || fail "invalid preset fails closed"

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi
print -r -- "RESULT: PASS"
