#!/bin/zsh

set -euo pipefail

readonly REPO_ROOT="${0:A:h:h:h}"
readonly EXAMPLES="${REPO_ROOT}/examples"

[[ -d "${EXAMPLES}" ]] || {
  print -u2 "missing examples directory: ${EXAMPLES}"
  exit 1
}

/usr/bin/python3 - "${REPO_ROOT}" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path(sys.argv[1])

bridge_src = root / "scripts" / "bridge"
sys.path.insert(0, str(bridge_src))

relay_path = root / "scripts" / "relay" / "github-issue-relay.py"
spec = importlib.util.spec_from_file_location("github_issue_relay", relay_path)
module = importlib.util.module_from_spec(spec)
sys.modules["github_issue_relay"] = module
spec.loader.exec_module(module)

config = module.OperatorConfig(
    "example/control-private",
    ["fixture-owner"],
    {"sample-repo": "codex/relay/sample-repo/"},
    "a" * 64,
)

examples = root / "examples"
expected = {
    "start.sample.json": "start",
    "query.sample.json": "query",
    "review.sample.json": "review",
    "reply.sample.json": "reply",
    "publish.sample.json": "publish",
}
found = {p.name for p in examples.glob("*.sample.json")}
assert found == set(expected), f"example set drifted: {sorted(found)}"

for name, operation in sorted(expected.items()):
    payload = json.loads((examples / name).read_text(encoding="utf-8"))
    assert payload["operation"] == operation, name
    validated = module.validate_job_payload(payload, config)
    assert validated == payload, name
    print(f"PASS: {name} validates as closed {operation}")

print("public examples: PASS")
PY
