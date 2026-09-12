"""Synthetic-only wrapper recovery tests. No model calls or live state inputs.

Set BRIDGE_TEST_CODEX_BIN to a reviewed executable for real metadata coverage.
It selects only the test executable, never the production store.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/chatgpt-codex-bridge/scripts"
WRAPPER = SCRIPTS / "run-guard.zsh"
SERVICE = SCRIPTS / "chatgpt-codex-bridge.zsh"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mode, p.stat().st_uid,
            hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


class StoreSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bridge-store-selector-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.state = self.home / "Library/Application Support/chatgpt-codex-bridge"
        self.state.mkdir(parents=True, mode=0o700)
        self.store = self.state / "recovery-store"
        self.store.mkdir(mode=0o700)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.config = self.state / "config.plist"
        self.spy = self.root / "spy.py"
        self.spy.write_text("import json,sys\nprint(json.dumps(sys.argv[1:]))\n")
        self.data = dict(preset="managed-repo", python_bin=sys.executable,
                         runtime_guard=str(self.spy), workspace=str(self.workspace),
                         codex_bin="/usr/bin/false", sandbox="workspace-write",
                         approval_policy="never", managed_registry="synthetic-registry",
                         workspace_new_project_skill="", job_state_dir=str(self.store))
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "TMPDIR": str(self.root), "LC_ALL": "C", "LANG": "C",
                    "CHATGPT_CODEX_BRIDGE_CONFIG": str(self.config)}
        for name in ("jobs-v2", "jobs-v3", "jobs-v4"):
            old = self.state / name
            old.mkdir(mode=0o700)
            (old / "unchanged.txt").write_text("synthetic historical record\n")
        (self.workspace / "unchanged.txt").write_text("synthetic retained worktree\n")
        self.save()

    def save(self):
        self.config.write_bytes(plistlib.dumps(self.data))
        self.config.chmod(0o600)

    def run_wrapper(self):
        return subprocess.run(["/bin/zsh", str(WRAPPER)], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def rejected(self):
        before = snapshot(self.root)
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout, "")  # spy Guard never executed
        self.assertRegex(result.stderr, r"^[A-Z_]+\n$")
        self.assertEqual(snapshot(self.root), before)

    def test_single_selector_and_environment_override_ignored(self):
        self.env.update(JOB_STATE_DIR=str(self.state / "jobs-v4"),
                        CHATGPT_CODEX_BRIDGE_JOB_STATE_DIR="/outside",
                        CHATGPT_CODEX_BRIDGE_STATE_DIR="/outside")
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(result.stdout)
        self.assertEqual(args.count("--job-state-dir"), 1)
        self.assertEqual(args[args.index("--job-state-dir") + 1], str(self.store))
        self.assertFalse((self.store / "capability.key").exists())

    def test_missing_empty_wrong_type_noncanonical_and_outside(self):
        for value in ("", 4, True, [], {}, "relative", "/outside",
                      str(self.state), str(self.workspace), str(self.store) + "/",
                      str(self.store) + "/../recovery-store", str(self.state / "missing"),
                      *(str(self.state / name) for name in ("jobs-v2", "jobs-v3", "jobs-v4")),
                      str(self.state / "jobs-v4/child")):
            with self.subTest(value_type=type(value).__name__):
                self.data["job_state_dir"] = value
                self.save()
                self.rejected()
        del self.data["job_state_dir"]
        self.save()
        self.rejected()

    def test_store_mode_symlink_and_workspace_intersection(self):
        newline = self.state / "store\n"
        newline.mkdir(mode=0o700)
        self.data["job_state_dir"] = str(newline)
        self.save()
        self.rejected()
        loop = self.state / "loop"
        loop.symlink_to(loop)
        self.data["job_state_dir"] = str(loop)
        self.save()
        self.rejected()
        self.data["job_state_dir"] = str(self.store)
        self.save()
        self.store.chmod(0o755)
        self.rejected()
        self.store.chmod(0o700)
        alias = self.state / "alias"
        alias.symlink_to(self.store, target_is_directory=True)
        self.data["job_state_dir"] = str(alias)
        self.save()
        self.rejected()
        self.data["job_state_dir"] = str(self.store)
        self.data["workspace"] = str(self.store)
        self.save()
        self.rejected()
        self.data["workspace"] = str(self.state)
        self.save()
        self.rejected()

    def test_config_private_canonical_and_policy(self):
        self.state.chmod(0o777)
        self.rejected()
        self.state.chmod(0o700)
        self.config.chmod(0o644)
        self.rejected()
        self.config.chmod(0o600)
        alias = self.state / "config-alias.plist"
        alias.symlink_to(self.config)
        self.env["CHATGPT_CODEX_BRIDGE_CONFIG"] = str(alias)
        self.rejected()
        self.env["CHATGPT_CODEX_BRIDGE_CONFIG"] = str(self.config)
        self.data["sandbox"] = "danger-full-access"
        self.save()
        self.rejected()
        self.data.update(sandbox="workspace-write", approval_policy="on-request")
        self.save()
        self.rejected()
        self.data["approval_policy"] = "never"
        self.save()
        linked = self.state / "hardlinked-config"
        os.link(self.config, linked)
        self.rejected()

    def test_key_symlink_hardlink_permissions_and_size(self):
        key = self.store / "capability.key"
        original = self.root / "synthetic-key"
        original.write_bytes(b"x" * 32)
        original.chmod(0o600)
        key.symlink_to(original)
        self.rejected()
        key.unlink()
        os.link(original, key)
        self.rejected()
        key.unlink()
        key.write_bytes(b"x" * 32)
        key.chmod(0o644)
        self.rejected()
        key.chmod(0o600)
        key.write_bytes(b"short")
        self.rejected()

    def test_wrong_owner_when_os_permits_chown(self):
        try:
            os.chown(self.store, 0 if os.getuid() != 0 else 1, -1)
        except PermissionError:
            self.skipTest("OS disallows changing owner; no simulated owner PASS claimed")
        try:
            self.rejected()
        finally:
            os.chown(self.store, os.getuid(), -1)

    def test_legacy_maintenance_stops_before_any_side_effect(self):
        for action in ("install", "restart", "stop", "uninstall"):
            with self.subTest(action=action):
                before = snapshot(self.root)
                result = subprocess.run(["/bin/zsh", str(SERVICE), action, "--no-start"],
                                        env=self.env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 64)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY\n")
                self.assertEqual(snapshot(self.root), before)
        # Explicit key remains protected even if preset is changed or value invalid.
        self.data.update(preset="workspace-safe", job_state_dir="")
        self.save()
        result = subprocess.run(["/bin/zsh", str(SERVICE), "stop", "--no-start"],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 64)

        self.env["CHATGPT_CODEX_BRIDGE_STATE_DIR"] = str(self.root / "empty-override")
        result = subprocess.run(["/bin/zsh", str(SERVICE), "stop", "--no-start"],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stderr, "EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY\n")

    def test_other_presets_keep_original_argv(self):
        del self.data["job_state_dir"]
        for preset in ("workspace-safe", "personal-full-control"):
            self.data["preset"] = preset
            self.save()
            result = self.run_wrapper()
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("--job-state-dir", json.loads(result.stdout))

    def metadata(self):
        process = subprocess.Popen(["/bin/zsh", str(WRAPPER)], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=0)
        pending = bytearray()
        def send(message):
            process.stdin.write(json.dumps(message).encode() + b"\n")
            process.stdin.flush()
        def receive(identifier):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                while b"\n" in pending:
                    line, _, tail = pending.partition(b"\n")
                    pending[:] = tail
                    item = json.loads(line)
                    if item.get("id") == identifier:
                        return item
                if select.select([process.stdout], [], [], max(0, deadline-time.monotonic()))[0]:
                    data = os.read(process.stdout.fileno(), 65536)
                    if not data:
                        self.fail("METADATA_EOF")
                    pending.extend(data)
            self.fail("METADATA_TIMEOUT")
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "synthetic-wrapper-test", "version": "1.0"}}})
            self.assertIn("result", receive(1))
            send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            names = {t["name"] for t in receive(2)["result"]["tools"]}
            self.assertTrue({"codex-repo-start", "codex-reply-async", "codex-wait",
                             "codex-job-status", "codex-repo-publish"}.issubset(names))
            self.assertNotIn("codex-start", names)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        self.assertEqual(process.returncode, 0)

    def test_real_wrapper_metadata_repeat_and_persisted_relay_journal(self):
        codex = os.environ.get("BRIDGE_TEST_CODEX_BIN")
        if not codex:
            self.skipTest("requires reviewed Codex executable for metadata only")
        source = self.root / "source"
        source.mkdir()
        def git(*args):
            return subprocess.run(["git", "-C", str(source), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-b", "main")
        git("config", "user.name", "Synthetic Test")
        git("config", "user.email", "test@example.invalid")
        (source / "README.md").write_text("Synthetic fixture\n")
        git("add", "README.md")
        git("commit", "-m", "fixture")
        git("remote", "add", "origin", "https://github.com/example/synthetic-bridge.git")
        git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
        registry = self.state / "managed-repos.v1.json"
        registry.write_text(json.dumps({"registryVersion": "managed_repo_registry_v1", "repos": [
            {"alias": alias, "repoPath": str(source),
             "repositoryFullName": "example/synthetic-bridge", "baseRemote": "origin",
             "baseBranch": "main", "protectedBranches": ["main"],
             "workBranchPrefix": "codex/relay/" + alias + "/",
             "deploymentTier": "none", "prePublishChecks": [], "localLoopbackTargets": []}
            for alias in ("sample-beta", "sample-alpha", "sample-gamma")]}))
        registry.chmod(0o600)
        self.data.update(runtime_guard=str(ROOT / "scripts/bridge/codex-mcp-guard.py"),
                         codex_bin=codex, managed_registry=str(registry))
        self.save()
        fixtures = load("relay_fixture", ROOT / "tests/relay/test-github-issue-relay.py")
        relay = fixtures.relay_module
        journal = self.state / "github-relay.sqlite3"
        database = relay.RelayDatabase(journal)
        github = fixtures.FakeGitHub()
        old_mcp = fixtures.FakeMcpClient()
        old = relay.GitHubIssueRelay(database, github, mcp_factory=lambda: old_mcp)
        payload = fixtures.valid_payload()
        issue = fixtures.valid_issue(payload=payload)
        old.process_issue(issue)
        old.supervise_active_jobs()
        old.deliver_pending_results()
        recorded = dict(database.get_by_issue(1))
        database.close()
        before = snapshot(self.state)
        worktree_before = snapshot(self.workspace)
        self.metadata()  # Only initialize/tools/list; no tools/call.
        own_key = (self.store / "capability.key").read_bytes()  # synthetic key only
        self.metadata()
        self.assertEqual((self.store / "capability.key").read_bytes(), own_key)
        after = snapshot(self.state)
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertEqual(snapshot(self.workspace), worktree_before)
        # Reopen the SAME journal after wrapper selection; MCP is a local fake.
        database = relay.RelayDatabase(journal)
        self.addCleanup(database.close)
        new_mcp = fixtures.FakeMcpClient()
        new_mcp.revoked_threads.add(fixtures.FakeMcpClient.THREAD_CAPABILITY)
        resumed = relay.GitHubIssueRelay(database, github, mcp_factory=lambda: new_mcp)
        resumed.process_issue(issue)
        resumed.process_issue(fixtures.valid_issue(2, payload))  # same request, other issue
        self.assertEqual(new_mcp.calls, [])
        self.assertEqual(dict(database.get_by_issue(1)), recorded)
        resumed.process_issue(fixtures.valid_issue(3, fixtures.valid_reply_payload(recorded["relayJobRef"])))
        self.assertEqual(database.get_by_issue(3)["status"], "failed")
        self.assertNotIn("codex-repo-start", [name for name, _ in new_mcp.calls])
        self.assertEqual(database.get_by_issue(1)["deliveryState"], "delivered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
