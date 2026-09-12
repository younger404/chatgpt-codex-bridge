#!/bin/zsh
set -u

readonly REPO_ROOT="${0:A:h:h:h}"
readonly PLUGIN_ROOT="${REPO_ROOT}/plugins/chatgpt-codex-bridge"
readonly MARKETPLACE="${REPO_ROOT}/.agents/plugins/marketplace.json"
typeset -i failures=0

pass() { print -r -- "PASS: $1"; }
fail() { print -u2 -r -- "FAIL: $1"; (( failures += 1 )); }

require_file() {
  [[ -f "$1" ]] && pass "$2" || fail "$2"
}

require_executable() {
  [[ -x "$1" ]] && pass "$2" || fail "$2"
}

require_file "${PLUGIN_ROOT}/.codex-plugin/plugin.json" "plugin manifest exists"
require_file "${PLUGIN_ROOT}/README.md" "standalone plugin README exists"
require_file "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/SKILL.md" "controller skill exists"
require_file "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/agents/openai.yaml" "controller UI metadata exists"
for reference in install-upgrade-macos controller-loop recovery-and-revocation mcp-contract; do
  require_file "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/references/${reference}.md" "controller reference ${reference} exists"
done
require_file "${PLUGIN_ROOT}/runtime/bootstrap/workspace-new-project/SKILL.md" "portable new-project skill exists"
require_executable "${PLUGIN_ROOT}/runtime/bootstrap/workspace-new-project/scripts/create_workspace_project.sh" "portable new-project bootstrap is executable"
require_file "${PLUGIN_ROOT}/bridge/codex-mcp-guard.py" "packaged Guard exists"
require_file "${PLUGIN_ROOT}/bridge/managed_repo.py" "packaged managed repository module exists"
require_executable "${PLUGIN_ROOT}/scripts/chatgpt-codex-bridge.zsh" "service command is executable"
require_file "${PLUGIN_ROOT}/scripts/process_observation.py" "shared observer is packaged"
require_file "${PLUGIN_ROOT}/scripts/bridge-doctor.py" "explicit doctor modes are packaged"
require_file "${PLUGIN_ROOT}/scripts/guard-store-config.py" "operator store validator is packaged"
require_executable "${PLUGIN_ROOT}/scripts/managed-repos.zsh" "managed repository CLI is executable"
require_executable "${PLUGIN_ROOT}/scripts/verify-tunnel-client.zsh" "tunnel-client verifier is executable"
require_executable "${PLUGIN_ROOT}/scripts/build-verified-tunnel-client.zsh" "tunnel-client source builder is executable"
require_executable "${PLUGIN_ROOT}/scripts/install-macos.zsh" "installer wrapper is executable"
require_executable "${PLUGIN_ROOT}/scripts/install-github-relay-v1-macos.zsh" "fresh GitHub Relay V1 installer is executable"
require_file "${PLUGIN_ROOT}/scripts/install-github-relay-v1.py" "fresh installer implementation is packaged"
for name in github-issue-relay.py run-github-relay.zsh; do
  require_file "${PLUGIN_ROOT}/relay/${name}" "packaged Relay ${name} exists"
  cmp -s "${REPO_ROOT}/scripts/relay/${name}" "${PLUGIN_ROOT}/relay/${name}" \
    && pass "Relay ${name} source/package identity" || fail "Relay ${name} source/package identity"
done
require_executable "${PLUGIN_ROOT}/scripts/doctor.zsh" "doctor wrapper is executable"
require_executable "${PLUGIN_ROOT}/scripts/uninstall-macos.zsh" "uninstaller wrapper is executable"
require_file "${MARKETPLACE}" "repo marketplace exists"
require_file "${REPO_ROOT}/LICENSE" "MIT license exists"

if [[ -x "${PLUGIN_ROOT}/scripts/chatgpt-codex-bridge.zsh" ]]; then
  help_output="$(/bin/zsh "${PLUGIN_ROOT}/scripts/chatgpt-codex-bridge.zsh" --help)"
  [[ "${help_output}" == *"chatgpt-codex-bridge.zsh {install|doctor|status|restart|stop|uninstall}"* ]] \
    && pass "service help names the executable" || fail "service help names the executable"
  [[ "${help_output}" != *"Usage: usage"* ]] \
    && pass "service help is not shadowed by the usage function" || fail "service help is not shadowed by the usage function"
fi

if [[ -f "${PLUGIN_ROOT}/.codex-plugin/plugin.json" ]]; then
  manifest_check="$(/usr/bin/python3 - "${PLUGIN_ROOT}/.codex-plugin/plugin.json" <<'PY'
import json
import pathlib
import re
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["name"] == "chatgpt-codex-bridge"
assert data["version"] == "1.0.0-beta.1"
assert data["skills"] == "./skills/"
assert data["interface"]["displayName"] == "ChatGPT Codex Bridge"
assert data["repository"] == "https://github.com/younger404/chatgpt-codex-bridge"
assert data["homepage"] == "https://github.com/younger404/chatgpt-codex-bridge"
assert data["interface"]["websiteURL"] == "https://github.com/younger404/chatgpt-codex-bridge"
assert data["author"]["name"] == "larryppgg"
assert data["license"] == "MIT"
print("ok")
PY
)"
  [[ "${manifest_check}" == "ok" ]] && pass "manifest fields are valid" || fail "manifest fields are valid"
fi

if [[ -f "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/agents/openai.yaml" ]]; then
  /usr/bin/grep -Fq '$chatgpt-codex-controller' "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/agents/openai.yaml" \
    && pass "controller default prompt explicitly invokes the skill" \
    || fail "controller default prompt explicitly invokes the skill"
fi

if [[ -f "${PLUGIN_ROOT}/runtime/bootstrap/workspace-new-project/SKILL.md" ]]; then
  /usr/bin/grep -Fq 'name: workspace-new-project' "${PLUGIN_ROOT}/runtime/bootstrap/workspace-new-project/SKILL.md" \
    && pass "portable new-project skill validates" || fail "portable new-project skill validates"
fi

skill_inventory_count="$(find "${PLUGIN_ROOT}/skills" -name SKILL.md -type f | wc -l | tr -d ' ')"
[[ "${skill_inventory_count}" == "1" ]] \
  && pass "controller is the only plugin-inventory Skill" \
  || fail "controller is the only plugin-inventory Skill"

if [[ -f "${MARKETPLACE}" ]]; then
  marketplace_check="$(/usr/bin/python3 - "${MARKETPLACE}" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["name"] == "chatgpt-codex-bridge"
assert data["interface"]["displayName"] == "ChatGPT Codex Bridge"
entry = next(item for item in data["plugins"] if item["name"] == "chatgpt-codex-bridge")
assert entry["source"] == {"source": "local", "path": "./plugins/chatgpt-codex-bridge"}
assert entry["policy"]["installation"] == "AVAILABLE"
assert entry["policy"]["authentication"] == "ON_INSTALL"
print("ok")
PY
)"
  [[ "${marketplace_check}" == "ok" ]] && pass "marketplace entry is valid" || fail "marketplace entry is valid"
fi

if [[ -f "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/SKILL.md" ]]; then
  skill_check="$(/usr/bin/python3 - "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/SKILL.md" <<'PY'
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
parts = text.split("---", 2)
assert len(parts) == 3 and not parts[0].strip()
frontmatter = parts[1]
assert "name: chatgpt-codex-controller" in frontmatter
assert "description:" in frontmatter
assert "TODO" not in text
print("ok")
PY
)"
  [[ "${skill_check}" == "ok" ]] \
    && pass "controller skill validates" || fail "controller skill validates"
  for phrase in "codex-start" "codex-reply-async" "codex-wait" "codex-job-open" "threadId" "click its return control" "per device" "install-macos.zsh"; do
    /usr/bin/grep -Fq "${phrase}" "${PLUGIN_ROOT}/skills/chatgpt-codex-controller/SKILL.md" \
      && pass "skill documents ${phrase}" || fail "skill documents ${phrase}"
  done
fi

if [[ -f "${PLUGIN_ROOT}/bridge/codex-mcp-guard.py" ]]; then
  /usr/bin/cmp -s "${REPO_ROOT}/scripts/bridge/codex-mcp-guard.py" "${PLUGIN_ROOT}/bridge/codex-mcp-guard.py" \
    && pass "packaged Guard matches reviewed source" || fail "packaged Guard matches reviewed source"
fi

if [[ -f "${PLUGIN_ROOT}/bridge/managed_repo.py" ]]; then
  /usr/bin/cmp -s "${REPO_ROOT}/scripts/bridge/managed_repo.py" "${PLUGIN_ROOT}/bridge/managed_repo.py" \
    && pass "packaged managed repository module matches reviewed source" \
    || fail "packaged managed repository module matches reviewed source"
fi

if [[ -f "${PLUGIN_ROOT}/scripts/verify-tunnel-client.zsh" ]]; then
  /usr/bin/cmp -s "${REPO_ROOT}/scripts/bridge/verify-tunnel-client.zsh" "${PLUGIN_ROOT}/scripts/verify-tunnel-client.zsh" \
    && pass "packaged tunnel-client verifier matches reviewed source" \
    || fail "packaged tunnel-client verifier matches reviewed source"
fi

if [[ -f "${PLUGIN_ROOT}/scripts/build-verified-tunnel-client.zsh" ]]; then
  /usr/bin/cmp -s "${REPO_ROOT}/scripts/bridge/build-verified-tunnel-client.zsh" "${PLUGIN_ROOT}/scripts/build-verified-tunnel-client.zsh" \
    && pass "packaged tunnel-client source builder matches reviewed source" \
    || fail "packaged tunnel-client source builder matches reviewed source"
fi

if [[ -d "${PLUGIN_ROOT}" ]]; then
  [[ ! -e "${PLUGIN_ROOT}/.mcp.json" ]] && pass "plugin avoids a local Codex-to-Codex MCP loop" || fail "plugin avoids a local Codex-to-Codex MCP loop"
  # Synthetic sentinels only. Real historical personal values belong to the
  # repository-external private denylist, never to tracked test sources.
  synthetic_home="/Users/example-user"
  synthetic_profile="example-tunnel-profile"
  forbidden_pattern="(${synthetic_home}|${synthetic_profile}|tunnel_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{12,})"
  if /usr/bin/grep -R -E -q "${forbidden_pattern}" "${PLUGIN_ROOT}"; then
    fail "portable package has no personal paths, profile, or credential-shaped values"
  else
    pass "portable package has no personal paths, profile, or credential-shaped values"
  fi
fi

if cmp -s "${REPO_ROOT}/scripts/bridge/supervision.py" "${PLUGIN_ROOT}/bridge/supervision.py"; then
  pass "supervision helper mirror matches"
else
  fail "supervision helper mirror matches"
fi

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi
print -r -- "RESULT: PASS"
