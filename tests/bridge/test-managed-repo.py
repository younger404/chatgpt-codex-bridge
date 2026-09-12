#!/usr/bin/python3

import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "scripts" / "bridge"
sys.path.insert(0, str(BRIDGE))

import managed_repo


def load_guard():
    spec = importlib.util.spec_from_file_location("managed_guard", BRIDGE / "codex-mcp-guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load_guard()


def run(*command, cwd=None):
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


class ManagedRepoTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "source"
        self.remote = self.root / "remote.git"
        self.workspace = self.root / "workspace"
        self.repo.mkdir()
        self.workspace.mkdir()
        run("git", "init", "--bare", str(self.remote))
        run("git", "init", "-b", "main", str(self.repo))
        run("git", "config", "user.name", "Bridge Test", cwd=self.repo)
        run("git", "config", "user.email", "bridge@example.invalid", cwd=self.repo)
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".project-memory/\n", encoding="utf-8")
        run("git", "add", "README.md", ".gitignore", cwd=self.repo)
        run("git", "commit", "-m", "base", cwd=self.repo)
        run("git", "remote", "add", "origin", str(self.remote), cwd=self.repo)
        run("git", "push", "-u", "origin", "main", cwd=self.repo)
        self.entry = {
            "alias": "sample-repo",
            "repoPath": str(self.repo),
            "repositoryFullName": "example/sample-repo",
            "baseRemote": "origin",
            "baseBranch": "main",
            "protectedBranches": ["main"],
            "workBranchPrefix": "codex/bridge/",
            "deploymentTier": "none",
            "prePublishChecks": [],
            "localLoopbackTargets": [],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def allocate_gc_candidate(self, status="completed"):
        internal_job_id = str(uuid.uuid4())
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            allocation = managed_repo.allocate_worktree(
                str(self.workspace), self.entry, internal_job_id
            )
        document = {
            "registryVersion": managed_repo.REGISTRY_VERSION,
            "repos": [self.entry],
        }
        digest = managed_repo.canonical_hash(document)
        request = {
            **allocation,
            "jobId": "private-job-capability",
            "internalJobId": internal_job_id,
            "threadId": "private-thread-capability",
            "internalThreadId": "thread-" + internal_job_id,
            "repoAlias": self.entry["alias"],
            "repositoryFullName": self.entry["repositoryFullName"],
            "repoPath": self.entry["repoPath"],
            "baseRemote": self.entry["baseRemote"],
            "baseBranch": self.entry["baseBranch"],
            "registryCanonicalHash": digest,
            "preset": "managed-repo",
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
        }
        state = {
            "jobId": request["jobId"],
            "internalJobId": internal_job_id,
            "threadId": request["threadId"],
            "internalThreadId": request["internalThreadId"],
            "status": status,
        }
        candidate = [{
            "request": request,
            "state": state,
            "workerState": "inactive",
            "localProcessState": "inactive",
        }]
        return allocation, request, candidate, digest

    def allocate_grouped_gc_candidate(self):
        allocation, owner_request, candidate, digest = self.allocate_gc_candidate()
        continuation_id = str(uuid.uuid4())
        continuation_request = dict(owner_request)
        continuation_request.update({
            "jobId": "continuation-job-capability",
            "internalJobId": continuation_id,
        })
        continuation = {
            "request": continuation_request,
            "state": {
                "jobId": continuation_request["jobId"],
                "internalJobId": continuation_id,
                "threadId": continuation_request["threadId"],
                "internalThreadId": continuation_request["internalThreadId"],
                "status": "completed",
            },
            "workerState": "inactive",
            "localProcessState": "inactive",
        }
        return allocation, owner_request, candidate[0], continuation, digest

    def managed_registry(self, entry=None, suffix=""):
        registry_path = self.root / ("managed-repos" + suffix + ".v1.json")
        document = {
            "registryVersion": managed_repo.REGISTRY_VERSION,
            "repos": [entry or self.entry],
        }
        registry_path.write_text(json.dumps(document), encoding="utf-8")
        registry_path.chmod(0o600)
        normalized = managed_repo.Registry(str(registry_path)).load(verify_live=False)
        return registry_path, managed_repo.canonical_hash(normalized)

    def managed_store(self, usage_provider=None, root_name="jobs-v4", entry=None):
        registry_path, digest = self.managed_registry(entry, "-" + root_name)
        store = guard.JobStore(
            str(self.root / root_name),
            "/usr/bin/false",
            str(self.workspace),
            "workspace-write",
            "never",
            "/usr/bin/open",
            preset="managed-repo",
            managed_registry_path=str(registry_path),
            managed_registry_hash=digest,
            disk_usage_provider=usage_provider,
        )
        return store, digest

    def write_store_candidate(self, store, request, status="completed"):
        internal_job_id = request["internalJobId"]
        public_job_id = store.capabilities.encode("job", internal_job_id)
        internal_thread_id = "thread-" + internal_job_id
        public_thread_id = store.capabilities.encode("thread", internal_thread_id)
        job_dir = store.root / internal_job_id
        job_dir.mkdir(mode=0o700)
        request.update({
            "jobId": public_job_id,
            "threadId": public_thread_id,
            "internalThreadId": internal_thread_id,
            "createdAt": 1,
        })
        state = {
            "jobId": public_job_id,
            "internalJobId": internal_job_id,
            "status": status,
            "threadId": public_thread_id,
            "internalThreadId": internal_thread_id,
            "content": "fixture",
            "contentTruncated": False,
            "workerLaunchState": "not_attempted",
            "localProcessLaunchState": "not_attempted",
            "updatedAt": 1,
        }
        guard.atomic_write_json(job_dir / "request.json", request)
        guard.atomic_write_json(job_dir / "status.json", state)
        return public_thread_id, public_job_id, job_dir

    def write_store_continuation(self, store, owner_request, created_at=2):
        internal_job_id = str(uuid.uuid4())
        public_job_id = store.capabilities.encode("job", internal_job_id)
        job_dir = store.root / internal_job_id
        job_dir.mkdir(mode=0o700)
        request = dict(owner_request)
        request.update({
            "jobId": public_job_id,
            "internalJobId": internal_job_id,
            "createdAt": created_at,
        })
        state = {
            "jobId": public_job_id,
            "internalJobId": internal_job_id,
            "status": "completed",
            "threadId": request["threadId"],
            "internalThreadId": request["internalThreadId"],
            "content": "fixture",
            "contentTruncated": False,
            "workerLaunchState": "not_attempted",
            "localProcessLaunchState": "not_attempted",
            "updatedAt": created_at,
        }
        guard.atomic_write_json(job_dir / "request.json", request)
        guard.atomic_write_json(job_dir / "status.json", state)
        return request, job_dir

    def local_loopback_entry(self):
        return dict(
            self.entry,
            deploymentTier="local-loopback",
            localLoopbackTargets=[{
                "name": "preview",
                "executable": os.path.realpath(sys.executable),
                "argv": ["-c", "import time; time.sleep(30)", "{host}"],
                "host": "127.0.0.1",
            }],
        )

    def disk_usage_sequence(self, *free_values):
        values = list(free_values)
        total = 100 * managed_repo.GIB

        def provider(_path):
            free = values.pop(0) if len(values) > 1 else values[0]
            return SimpleNamespace(total=total, used=total - free, free=free)

        return provider

    def test_normalizes_only_supported_github_remotes(self):
        self.assertEqual(
            managed_repo.normalize_github_remote("git@github.com:Example/Sample.git"),
            "github:example/sample",
        )
        self.assertEqual(
            managed_repo.normalize_github_remote("https://github.com/Example/Sample.git"),
            "github:example/sample",
        )
        with self.assertRaises(managed_repo.ManagedRepoError):
            managed_repo.normalize_github_remote(str(self.remote))

    def test_registry_is_atomic_0600_and_hash_changes_invalidate_context(self):
        registry_path = self.root / "state" / "managed-repos.v1.json"
        registry = managed_repo.Registry(str(registry_path))
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            first = registry.write({
                "registryVersion": managed_repo.REGISTRY_VERSION,
                "repos": [self.entry],
            })
            first_hash = managed_repo.canonical_hash(first)
            self.assertEqual(stat.S_IMODE(registry_path.stat().st_mode), 0o600)
            loaded = registry.load()
            self.assertEqual(loaded["repos"][0]["alias"], "sample-repo")
            changed = dict(self.entry, deploymentTier="staging")
            second = registry.write({
                "registryVersion": managed_repo.REGISTRY_VERSION,
                "repos": [changed],
            })
            self.assertNotEqual(first_hash, managed_repo.canonical_hash(second))
            with self.assertRaisesRegex(managed_repo.ManagedRepoError, "restart"):
                registry.resolve("sample-repo", first_hash)
        os.chmod(registry_path, 0o644)
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "0600"):
            registry.load()

    def test_registry_rejects_symlink_wrong_remote_and_duplicate_alias(self):
        link = self.root / "source-link"
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "symlink"):
            managed_repo.validate_entry(dict(self.entry, repoPath=str(link)), verify_live=False)
        run("git", "remote", "set-url", "origin", "https://github.com/example/other.git", cwd=self.repo)
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "identity"):
            managed_repo.verify_entry(self.entry)
        registry_path = self.root / "duplicate.json"
        registry_path.write_text(json.dumps({
            "registryVersion": managed_repo.REGISTRY_VERSION,
            "repos": [self.entry, self.entry],
        }), encoding="utf-8")
        os.chmod(registry_path, 0o600)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            with self.assertRaisesRegex(managed_repo.ManagedRepoError, "unique"):
                managed_repo.Registry(str(registry_path)).load()

    def test_worktree_uses_fetched_revision_and_publish_only_generated_branch(self):
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            allocation = managed_repo.allocate_worktree(
                str(self.workspace), self.entry, "12345678-1234-1234-1234-123456789abc"
            )
        base_revision = run("git", "rev-parse", "origin/main", cwd=self.repo)
        self.assertEqual(allocation["baseRevision"], base_revision)
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=allocation["workspace"]), base_revision)
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.repo), "main")
        (self.repo / "README.md").write_text("base\nadvanced\n", encoding="utf-8")
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "-m", "advance base", cwd=self.repo)
        run("git", "push", "origin", "main", cwd=self.repo)
        advanced_revision = run("git", "rev-parse", "HEAD", cwd=self.repo)
        (Path(allocation["workspace"]) / "managed.txt").write_text("managed\n", encoding="utf-8")
        document = {"registryVersion": managed_repo.REGISTRY_VERSION, "repos": [self.entry]}
        digest = managed_repo.canonical_hash(document)
        record = {
            **allocation,
            "repoAlias": self.entry["alias"],
            "repositoryFullName": self.entry["repositoryFullName"],
            "repoPath": self.entry["repoPath"],
            "baseRemote": "origin",
            "baseBranch": "main",
            "registryCanonicalHash": digest,
            "preset": "managed-repo",
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
        }
        result = managed_repo.publish(record, self.entry, digest, "managed change")
        self.assertTrue(result["pushed"])
        self.assertTrue(result["base_stale"])
        remote_branches = run("git", "for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=self.remote)
        self.assertIn(allocation["workBranch"], remote_branches.splitlines())
        self.assertEqual(run("git", "rev-parse", "main", cwd=self.remote), advanced_revision)

    def test_gc_collects_unchanged_clean_terminal_worktree_and_prunes_metadata(self):
        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        workspace = allocation["workspace"]
        outcome = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(outcome["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertTrue(outcome["removed"])
        self.assertFalse(Path(workspace).exists())
        metadata = run("git", "worktree", "list", "--porcelain", cwd=self.repo)
        self.assertNotIn(workspace, metadata)

    def test_gc_collects_published_clean_worktree(self):
        allocation, request, candidate, digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "published.txt").write_text("published\n", encoding="utf-8")
        result = managed_repo.publish(request, self.entry, digest, "published")
        self.assertTrue(result["pushed"])
        outcome = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(outcome["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertFalse(workspace.exists())

    def test_gc_retains_active_dirty_and_unpublished_worktrees(self):
        allocation, _request, candidate, digest = self.allocate_gc_candidate("running")
        candidate[0]["workerState"] = "active"
        active = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(active["lifecycleState"], managed_repo.LIFECYCLE_ACTIVE)
        self.assertEqual(active["retainedReason"], managed_repo.RETAINED_ACTIVE_WORKER)
        self.assertTrue(Path(allocation["workspace"]).is_dir())

        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        (Path(allocation["workspace"]) / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        dirty = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(dirty["retainedReason"], managed_repo.RETAINED_DIRTY)
        self.assertTrue(Path(allocation["workspace"]).is_dir())

        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        unpublished_workspace = Path(allocation["workspace"])
        (unpublished_workspace / "local.txt").write_text("local\n", encoding="utf-8")
        run("git", "add", "local.txt", cwd=unpublished_workspace)
        run("git", "commit", "-m", "local only", cwd=unpublished_workspace)
        unpublished = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(
            unpublished["retainedReason"], managed_repo.RETAINED_UNPUBLISHED
        )
        self.assertTrue(unpublished_workspace.is_dir())

    def test_gc_retains_active_local_loopback_process(self):
        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        candidate[0]["localProcessState"] = "active"
        outcome = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(outcome["lifecycleState"], managed_repo.LIFECYCLE_ACTIVE)
        self.assertEqual(
            outcome["retainedReason"], managed_repo.RETAINED_ACTIVE_LOCAL_PROCESS
        )
        self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_gc_protects_ignored_only_work_at_normal_soft_and_hard_pressure(self):
        pressures = (
            ("normal", 30 * managed_repo.GIB),
            ("soft", 20 * managed_repo.GIB),
            ("hard", 12 * managed_repo.GIB),
        )
        for index, (label, free_bytes) in enumerate(pressures):
            with self.subTest(label=label):
                allocation, request, _candidate, _digest = self.allocate_gc_candidate()
                ignored = Path(allocation["workspace"]) / ".project-memory" / "note.md"
                ignored.parent.mkdir()
                ignored.write_text("retain\n", encoding="utf-8")
                provider = self.disk_usage_sequence(free_bytes, free_bytes)
                store, digest = self.managed_store(
                    provider, root_name="ignored-" + str(index)
                )
                request["registryCanonicalHash"] = digest
                self.write_store_candidate(store, request)
                with mock.patch.object(
                    managed_repo, "verify_entry", return_value=True
                ):
                    store.gc_sweep()
                self.assertTrue(ignored.is_file())
                self.assertEqual(
                    store.last_gc_metrics["retainedReasons"],
                    {managed_repo.RETAINED_IGNORED: 1},
                )

    def test_gc_group_owner_is_uuid_bound_not_list_position(self):
        allocation, owner_request, owner, continuation, digest = (
            self.allocate_grouped_gc_candidate()
        )
        records = [continuation, owner]
        self.assertNotEqual(
            records[0]["request"]["internalJobId"], Path(allocation["workspace"]).name
        )
        resolved_owner, resolved_workspace, reason = managed_repo._managed_candidate_group(
            str(self.workspace), records, self.entry, digest
        )
        self.assertIs(resolved_owner, owner_request)
        self.assertEqual(resolved_owner["internalJobId"], Path(resolved_workspace).name)
        self.assertEqual(reason, "")

    def test_gc_group_eligibility_is_identical_in_both_record_orders(self):
        _allocation, _owner_request, owner, continuation, digest = (
            self.allocate_grouped_gc_candidate()
        )
        outcomes = []
        for label, records in (
            ("owner-first", [owner, continuation]),
            ("owner-second", [continuation, owner]),
        ):
            with self.subTest(order=label):
                outcome = managed_repo.evaluate_managed_workspace(
                    str(self.workspace), records, self.entry, digest, remove=False
                )
                self.assertEqual(
                    outcome["lifecycleState"], managed_repo.LIFECYCLE_ELIGIBLE
                )
                outcomes.append(outcome)
        self.assertEqual(outcomes[0], outcomes[1])

    def test_gc_group_request_status_identity_mismatch_retains(self):
        allocation, _owner_request, owner, continuation, digest = (
            self.allocate_grouped_gc_candidate()
        )
        mismatches = (
            ("internalJobId", str(uuid.uuid4())),
            ("jobId", "mismatched-job-capability"),
            ("internalThreadId", "mismatched-internal-thread"),
            ("threadId", "mismatched-thread-capability"),
        )
        for record_name, record_index in (("owner", 0), ("continuation", 1)):
            for field, value in mismatches:
                with self.subTest(record=record_name, field=field):
                    records = [
                        dict(owner, state=dict(owner["state"])),
                        dict(continuation, state=dict(continuation["state"])),
                    ]
                    records[record_index]["state"][field] = value
                    outcome = managed_repo.evaluate_managed_workspace(
                        str(self.workspace), records, self.entry, digest, remove=True
                    )
                    self.assertEqual(
                        outcome["retainedReason"], managed_repo.RETAINED_IDENTITY
                    )
                    self.assertFalse(outcome["removed"])
                    self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_gc_group_context_drift_retains(self):
        allocation, _owner_request, owner, continuation, digest = (
            self.allocate_grouped_gc_candidate()
        )
        continuation_request = continuation["request"]
        for field, value in (
            ("baseRevision", "f" * 40),
            ("workBranch", "codex/bridge/drifted-branch"),
        ):
            with self.subTest(field=field):
                drifted = dict(continuation_request, **{field: value})
                outcome = managed_repo.evaluate_managed_workspace(
                    str(self.workspace),
                    [owner, dict(continuation, request=drifted)],
                    self.entry,
                    digest,
                    remove=True,
                )
                self.assertEqual(
                    outcome["retainedReason"], managed_repo.RETAINED_IDENTITY
                )
                self.assertFalse(outcome["removed"])
                self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_same_internal_thread_cannot_span_two_allocations(self):
        first, first_request, _candidate, _digest = self.allocate_gc_candidate()
        second, second_request, _candidate, _digest = self.allocate_gc_candidate()
        store, digest = self.managed_store(root_name="cross-workspace-thread")
        first_request["registryCanonicalHash"] = digest
        first_thread, _job_id, _job_dir = self.write_store_candidate(
            store, first_request
        )
        second_request["registryCanonicalHash"] = digest
        _second_thread, _job_id, second_dir = self.write_store_candidate(
            store, second_request
        )
        first_internal_thread = store.capabilities.decode("thread", first_thread)
        second_request_path = second_dir / "request.json"
        durable_request = json.loads(
            second_request_path.read_text(encoding="utf-8")
        )
        durable_request.update({
            "threadId": first_thread,
            "internalThreadId": first_internal_thread,
        })
        guard.atomic_write_json(second_request_path, durable_request)
        second_state_path = second_dir / "status.json"
        durable_state = json.loads(second_state_path.read_text(encoding="utf-8"))
        durable_state.update({
            "threadId": first_thread,
            "internalThreadId": first_internal_thread,
        })
        guard.atomic_write_json(second_state_path, durable_state)
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), self.assertRaises(guard.GuardProtocolError):
            store.gc_sweep()
        self.assertTrue(Path(first["workspace"]).is_dir())
        self.assertTrue(Path(second["workspace"]).is_dir())

    def test_gc_remote_movement_network_and_parse_failure_retain_unpublished(self):
        allocation, request, candidate, digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "published.txt").write_text("published\n", encoding="utf-8")
        managed_repo.publish(request, self.entry, digest, "published head")
        mover = self.root / "remote-mover"
        run("git", "clone", str(self.remote), str(mover))
        run("git", "config", "user.name", "Bridge Test", cwd=mover)
        run("git", "config", "user.email", "bridge@example.invalid", cwd=mover)
        run("git", "checkout", allocation["workBranch"], cwd=mover)
        (mover / "moved.txt").write_text("moved\n", encoding="utf-8")
        run("git", "add", "moved.txt", cwd=mover)
        run("git", "commit", "-m", "move generated branch", cwd=mover)
        run("git", "push", "origin", allocation["workBranch"], cwd=mover)
        moved = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(moved["retainedReason"], managed_repo.RETAINED_UNPUBLISHED)
        self.assertTrue(workspace.is_dir())

        original_git = managed_repo._git
        for label, result in (
            ("network", SimpleNamespace(returncode=2, stdout="", stderr="offline")),
            ("parse", SimpleNamespace(returncode=0, stdout="malformed\n", stderr="")),
        ):
            with self.subTest(label=label):
                def failing_remote(repo_path, *arguments, **kwargs):
                    if arguments and arguments[0] == "ls-remote":
                        return result
                    return original_git(repo_path, *arguments, **kwargs)

                with mock.patch.object(managed_repo, "_git", side_effect=failing_remote):
                    outcome = managed_repo.evaluate_managed_workspace(
                        str(self.workspace), candidate, self.entry, digest, remove=True
                    )
                self.assertEqual(
                    outcome["retainedReason"], managed_repo.RETAINED_UNPUBLISHED
                )
                self.assertTrue(workspace.is_dir())

    def test_gc_rejects_foreign_traversal_symlink_and_wrong_identity(self):
        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        candidate[0]["request"] = dict(candidate[0]["request"], workspace=str(self.repo))
        foreign = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(foreign["retainedReason"], managed_repo.RETAINED_OUTSIDE_ROOT)
        self.assertTrue(self.repo.is_dir())

        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        traversal = str(
            Path(allocation["workspace"]).parent / ".." / "escape" / Path(allocation["workspace"]).name
        )
        candidate[0]["request"] = dict(candidate[0]["request"], workspace=traversal)
        traversed = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(traversed["retainedReason"], managed_repo.RETAINED_OUTSIDE_ROOT)
        self.assertTrue(Path(allocation["workspace"]).is_dir())

        symlink_id = str(uuid.uuid4())
        symlink_path = self.workspace / "managed" / self.entry["alias"] / symlink_id
        symlink_path.symlink_to(self.repo, target_is_directory=True)
        symlink_request = dict(
            candidate[0]["request"],
            workspace=str(symlink_path),
            internalJobId=symlink_id,
        )
        symlink_candidate = [{
            "request": symlink_request,
            "state": {"internalJobId": symlink_id, "status": "completed"},
            "workerState": "inactive",
            "localProcessState": "inactive",
        }]
        symlinked = managed_repo.evaluate_managed_workspace(
            str(self.workspace), symlink_candidate, self.entry, digest, remove=True
        )
        self.assertEqual(symlinked["retainedReason"], managed_repo.RETAINED_UNSAFE_PATH)
        self.assertTrue(self.repo.is_dir())

        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        candidate[0]["request"] = dict(
            candidate[0]["request"], repositoryFullName="example/foreign"
        )
        mismatched = managed_repo.evaluate_managed_workspace(
            str(self.workspace), candidate, self.entry, digest, remove=True
        )
        self.assertEqual(mismatched["retainedReason"], managed_repo.RETAINED_IDENTITY)
        self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_gc_retains_wrong_registry_canonical_hash(self):
        allocation, _request, candidate, digest = self.allocate_gc_candidate()
        candidate[0]["request"] = dict(
            candidate[0]["request"], registryCanonicalHash="0" * 64
        )
        with mock.patch.object(
            managed_repo, "remove_managed_worktree"
        ) as remove_worktree:
            outcome = managed_repo.evaluate_managed_workspace(
                str(self.workspace), candidate, self.entry, digest, remove=True
            )
        self.assertEqual(outcome["retainedReason"], managed_repo.RETAINED_IDENTITY)
        self.assertFalse(outcome["removed"])
        remove_worktree.assert_not_called()
        self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_gc_metrics_are_sanitized_and_deterministic(self):
        total = 100 * managed_repo.GIB
        before = {"total": total, "used": 80 * managed_repo.GIB, "free": 20 * managed_repo.GIB}
        after = {"total": total, "used": 70 * managed_repo.GIB, "free": 30 * managed_repo.GIB}
        metrics = managed_repo.gc_metrics(before, after, [
            {"lifecycleState": managed_repo.LIFECYCLE_REMOVED, "retainedReason": ""},
            {"lifecycleState": managed_repo.LIFECYCLE_RETAINED, "retainedReason": managed_repo.RETAINED_DIRTY},
        ])
        self.assertEqual(set(metrics), {
            "bytesBefore", "bytesAfter", "reclaimedBytes", "consideredJobCount",
            "removedJobCount", "retainedJobCount", "retainedReasons",
            "watermarkState", "freeBytesBefore", "freeBytesAfter",
        })
        self.assertEqual(metrics["watermarkState"], managed_repo.WATERMARK_SOFT)
        self.assertEqual(metrics["removedJobCount"], 1)
        self.assertEqual(metrics["retainedReasons"], {managed_repo.RETAINED_DIRTY: 1})
        self.assertNotIn(str(self.root), json.dumps(metrics, sort_keys=True))

    def test_percentage_dominant_watermark_boundaries(self):
        total = 1000 * managed_repo.GIB
        cases = (
            (150, managed_repo.WATERMARK_NORMAL),
            (149, managed_repo.WATERMARK_SOFT),
            (100, managed_repo.WATERMARK_SOFT),
            (99, managed_repo.WATERMARK_HARD),
            (50, managed_repo.WATERMARK_HARD),
            (49, managed_repo.WATERMARK_EMERGENCY),
        )
        for free_gib, expected in cases:
            with self.subTest(free_gib=free_gib):
                free = free_gib * managed_repo.GIB
                self.assertEqual(
                    managed_repo.disk_watermark({
                        "total": total,
                        "used": total - free,
                        "free": free,
                    }),
                    expected,
                )

    def test_absolute_dominant_watermark_boundaries(self):
        total = 100 * managed_repo.GIB
        cases = (
            (24 * managed_repo.GIB, managed_repo.WATERMARK_NORMAL),
            (24 * managed_repo.GIB - 1, managed_repo.WATERMARK_SOFT),
            (16 * managed_repo.GIB, managed_repo.WATERMARK_SOFT),
            (16 * managed_repo.GIB - 1, managed_repo.WATERMARK_HARD),
            (8 * managed_repo.GIB, managed_repo.WATERMARK_HARD),
            (8 * managed_repo.GIB - 1, managed_repo.WATERMARK_EMERGENCY),
        )
        for free, expected in cases:
            with self.subTest(free=free, expected=expected):
                self.assertEqual(
                    managed_repo.disk_watermark({
                        "total": total,
                        "used": total - free,
                        "free": free,
                    }),
                    expected,
                )

    def test_close_is_capability_bound_sanitized_and_idempotent(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        store, digest = self.managed_store()
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, job_dir = self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            first = store.close_managed(thread_id)
            second = store.close_managed(thread_id)
        self.assertEqual(first, {
            "status": managed_repo.LIFECYCLE_REMOVED,
            "lifecycleState": managed_repo.LIFECYCLE_REMOVED,
            "removed": True,
            "retainedReason": "",
        })
        self.assertEqual(second["status"], managed_repo.LIFECYCLE_REMOVED)
        self.assertFalse(second["removed"])
        self.assertFalse(Path(allocation["workspace"]).exists())
        self.assertNotIn(str(self.root), json.dumps(first, sort_keys=True))
        receipt = json.loads(
            (job_dir / guard.GC_RECEIPT_FILENAME).read_text(encoding="utf-8")
        )
        metrics = json.loads(
            (store.root / "gc-status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["phase"], "removed")
        self.assertEqual(receipt["trigger"], "close")
        self.assertEqual(metrics["removedJobCount"], 1)
        self.assertNotIn(str(self.root), json.dumps(receipt, sort_keys=True))
        with self.assertRaises(guard.GuardProtocolError):
            store.close_managed("caller-selected-path")

    def test_close_retains_dirty_workspace_with_stable_result(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        store, digest = self.managed_store()
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, _job_dir = self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            result = store.close_managed(thread_id)
        self.assertEqual(result["status"], managed_repo.WORKSPACE_NOT_SAFE_TO_GC)
        self.assertEqual(result["retainedReason"], managed_repo.RETAINED_DIRTY)
        self.assertTrue(workspace.is_dir())

    def test_gc_status_write_failure_before_removal_deletes_nothing(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        store, digest = self.managed_store(root_name="preflight-status-failure")
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, _job_dir = self.write_store_candidate(store, request)
        original_atomic = guard.atomic_write_json

        def fail_eligible_status(path, payload):
            if (
                path.name == "status.json"
                and payload.get("lifecycleState") == managed_repo.LIFECYCLE_ELIGIBLE
            ):
                raise OSError("simulated lifecycle preflight failure")
            return original_atomic(path, payload)

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "atomic_write_json", side_effect=fail_eligible_status
        ), self.assertRaises(OSError):
            store.close_managed(thread_id)
        self.assertTrue(workspace.is_dir())
        self.assertIn(
            str(workspace),
            run("git", "worktree", "list", "--porcelain", cwd=self.repo),
        )

    def test_post_remove_failure_recovers_without_second_delete(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        store, digest = self.managed_store(root_name="post-remove-recovery")
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, job_dir = self.write_store_candidate(store, request)
        original_atomic = guard.atomic_write_json

        def fail_removed_receipt(path, payload):
            if (
                path.name == guard.GC_RECEIPT_FILENAME
                and payload.get("phase") == "removed"
            ):
                raise OSError("simulated death after remove")
            return original_atomic(path, payload)

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "atomic_write_json", side_effect=fail_removed_receipt
        ), self.assertRaises(OSError):
            store.close_managed(thread_id)
        self.assertFalse(workspace.exists())
        prepared = json.loads(
            (job_dir / guard.GC_RECEIPT_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(prepared["phase"], "prepared")

        restarted, _digest = self.managed_store(root_name="post-remove-recovery")
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            managed_repo, "remove_managed_worktree"
        ) as remove_again:
            recovered = restarted.close_managed(thread_id)
        remove_again.assert_not_called()
        self.assertEqual(recovered["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertFalse(recovered["removed"])

    def test_prune_failure_preserves_removed_state_and_followup(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        store, digest = self.managed_store(root_name="prune-failure")
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, job_dir = self.write_store_candidate(store, request)
        original_git = managed_repo._git

        def fail_prune(repo_path, *arguments, **kwargs):
            if arguments[:2] == ("worktree", "prune"):
                return SimpleNamespace(returncode=1, stdout="", stderr="failure")
            return original_git(repo_path, *arguments, **kwargs)

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            managed_repo, "_git", side_effect=fail_prune
        ):
            result = store.close_managed(thread_id)
        self.assertFalse(workspace.exists())
        self.assertEqual(result["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertEqual(
            result["retainedReason"], managed_repo.RETAINED_PRUNE_FAILED
        )
        receipt = json.loads(
            (job_dir / guard.GC_RECEIPT_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(
            receipt["followupReason"], managed_repo.RETAINED_PRUNE_FAILED
        )

    def test_multi_record_partial_finalize_and_metric_failure_recover(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        store, digest = self.managed_store(root_name="partial-finalize")
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, owner_dir = self.write_store_candidate(store, request)
        _continuation, continuation_dir = self.write_store_continuation(
            store, request
        )
        original_atomic = guard.atomic_write_json
        removed_status_writes = 0

        def fail_second_removed_status(path, payload):
            nonlocal removed_status_writes
            if (
                path.name == "status.json"
                and payload.get("lifecycleState") == managed_repo.LIFECYCLE_REMOVED
            ):
                removed_status_writes += 1
                if removed_status_writes == 2:
                    raise OSError("simulated partial group finalize")
            return original_atomic(path, payload)

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "atomic_write_json", side_effect=fail_second_removed_status
        ), self.assertRaises(OSError):
            store.close_managed(thread_id)
        self.assertFalse(workspace.exists())
        restarted, _digest = self.managed_store(root_name="partial-finalize")
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            recovered = restarted.close_managed(thread_id)
        self.assertEqual(recovered["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        for job_dir in (owner_dir, continuation_dir):
            state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(state["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)

        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        metric_store, digest = self.managed_store(root_name="metric-recovery")
        request["registryCanonicalHash"] = digest
        metric_thread, _job_id, _job_dir = self.write_store_candidate(
            metric_store, request
        )

        def fail_final_metric(path, payload):
            if path.name == "gc-status.json" and payload.get("removedJobCount") == 1:
                raise OSError("simulated final metric failure")
            return original_atomic(path, payload)

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "atomic_write_json", side_effect=fail_final_metric
        ), self.assertRaises(OSError):
            metric_store.close_managed(metric_thread)
        self.assertFalse(workspace.exists())
        metric_restart, _digest = self.managed_store(root_name="metric-recovery")
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            recovered = metric_restart.close_managed(metric_thread)
        self.assertEqual(recovered["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertTrue((metric_restart.root / "gc-status.json").is_file())

    def test_publish_marks_workspace_gc_eligible_without_immediate_removal(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "published.txt").write_text("published\n", encoding="utf-8")
        provider = self.disk_usage_sequence(6 * managed_repo.GIB)
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        thread_id, job_id, _job_dir = self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            result = store.publish_managed(thread_id, "publish for recovery")
        self.assertTrue(result["pushed"])
        self.assertTrue(workspace.is_dir())
        state = store.read(job_id)
        self.assertEqual(state["lifecycleState"], managed_repo.LIFECYCLE_ELIGIBLE)

    def test_guard_startup_runs_managed_sweep_and_exposes_closed_close_schema(self):
        registry_path, _digest = self.managed_registry()
        provider = self.disk_usage_sequence(
            30 * managed_repo.GIB,
            30 * managed_repo.GIB,
        )
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            managed_guard = guard.CodexMcpGuard(
                str(self.workspace),
                "/usr/bin/false",
                "workspace-write",
                "never",
                job_state_dir=str(self.root / "guard-jobs-v4"),
                preset="managed-repo",
                managed_registry_path=str(registry_path),
                disk_usage_provider=provider,
            )
        self.assertIsNotNone(managed_guard.job_store.last_gc_metrics)
        self.assertTrue((managed_guard.job_store.root / "gc-status.json").is_file())
        close = next(
            tool for tool in managed_guard.public_tools
            if tool["name"] == "codex-repo-close"
        )
        self.assertEqual(
            set(close["inputSchema"]["properties"]), {"threadId"}
        )
        self.assertEqual(close["inputSchema"]["additionalProperties"], False)
        self.assertNotIn("cwd", json.dumps(close, sort_keys=True))
        self.assertNotIn("repoPath", json.dumps(close, sort_keys=True))
        self.assertGreater(
            guard.purge_job_state(str(managed_guard.job_store.root)), 0
        )
        self.assertFalse(managed_guard.job_store.root.exists())

    def test_soft_watermark_runs_safe_pre_start_gc(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        provider = self.disk_usage_sequence(
            20 * managed_repo.GIB,
            20 * managed_repo.GIB,
        )
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            store, "_start_worker", return_value=SimpleNamespace(pid=999999)
        ):
            state = store.enqueue("soft watermark start", repo_alias=self.entry["alias"])
        self.assertEqual(state["status"], "queued")
        self.assertFalse(Path(allocation["workspace"]).exists())
        self.assertEqual(
            store.last_gc_metrics["watermarkState"], managed_repo.WATERMARK_SOFT
        )
        self.assertEqual(store.last_gc_metrics["removedJobCount"], 1)

    def test_gc_active_receipt_round_trip_then_terminal_dirty(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        store, digest = self.managed_store(self.disk_usage_sequence(30 * managed_repo.GIB))
        request["registryCanonicalHash"] = digest
        _thread, _job, job_dir = self.write_store_candidate(store, request, status="running")
        state_path = job_dir / "status.json"
        state = json.loads(state_path.read_text())
        state["pid"] = os.getpid()
        guard.atomic_write_json(state_path, state)
        receipt_path = job_dir / guard.GC_RECEIPT_FILENAME

        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(guard, "remove_managed_worktree") as remove_worktree:
            first = store.gc_sweep()
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["phase"], "retained")
            self.assertEqual(receipt["lifecycleState"], managed_repo.LIFECYCLE_ACTIVE)
            second = store.gc_sweep()
            for metrics in (first, second):
                self.assertEqual(metrics["removedJobCount"], 0)
                self.assertEqual(metrics["retainedReasons"], {managed_repo.RETAINED_ACTIVE_WORKER: 1})
            self.assertTrue(workspace.is_dir())

            state = json.loads(state_path.read_text())
            state["status"] = "completed"
            guard.atomic_write_json(state_path, state)
            (workspace / "dirty.txt").write_text("keep this work\n", encoding="utf-8")
            terminal = store.gc_sweep()
            self.assertEqual(terminal["removedJobCount"], 0)
            self.assertEqual(terminal["retainedReasons"], {managed_repo.RETAINED_DIRTY: 1})
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["lifecycleState"], managed_repo.LIFECYCLE_RETAINED)
            self.assertTrue((workspace / "dirty.txt").is_file())
            remove_worktree.assert_not_called()

    def test_gc_active_receipt_rejects_prepared_and_removed(self):
        for phase in ("prepared", "removed"):
            with self.subTest(phase=phase):
                allocation, request, _candidate, _digest = self.allocate_gc_candidate()
                store, digest = self.managed_store(
                    self.disk_usage_sequence(30 * managed_repo.GIB), root_name="active-" + phase
                )
                request["registryCanonicalHash"] = digest
                _thread, _job, job_dir = self.write_store_candidate(store, request, status="running")
                state_path = job_dir / "status.json"
                state = json.loads(state_path.read_text())
                state["pid"] = os.getpid()
                guard.atomic_write_json(state_path, state)
                with mock.patch.object(
                    managed_repo, "verify_entry", return_value=True
                ), mock.patch.object(guard, "remove_managed_worktree") as remove_worktree:
                    store.gc_sweep()
                    receipt_path = job_dir / guard.GC_RECEIPT_FILENAME
                    receipt = json.loads(receipt_path.read_text())
                    self.assertEqual(receipt["lifecycleState"], managed_repo.LIFECYCLE_ACTIVE)
                    receipt["phase"] = phase
                    guard.atomic_write_json(receipt_path, receipt)
                    with self.assertRaisesRegex(guard.GuardProtocolError, "invalid GC receipt"):
                        store.gc_sweep()
                    remove_worktree.assert_not_called()
                self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_gc_sweep_is_idempotent_after_removal(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        provider = self.disk_usage_sequence(30 * managed_repo.GIB)
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            first = store.gc_sweep()
            second = store.gc_sweep()
        self.assertEqual(first["removedJobCount"], 1)
        self.assertEqual(second["consideredJobCount"], 0)
        self.assertEqual(second["removedJobCount"], 0)
        self.assertFalse(Path(allocation["workspace"]).exists())

    def test_strict_durable_enumeration_blocks_uuid_symlink_and_non_directory(self):
        for index, unsafe_type in enumerate((
            "symlink", "file", "noncanonical_uuid"
        )):
            with self.subTest(unsafe_type=unsafe_type):
                allocation, request, _candidate, _digest = self.allocate_gc_candidate()
                store, digest = self.managed_store(root_name="unsafe-" + str(index))
                request["registryCanonicalHash"] = digest
                self.write_store_candidate(store, request)
                unsafe = store.root / str(uuid.uuid4())
                if unsafe_type == "symlink":
                    unsafe.symlink_to(self.repo, target_is_directory=True)
                elif unsafe_type == "file":
                    unsafe.write_text("unsafe\n", encoding="utf-8")
                else:
                    unsafe = store.root / str(uuid.uuid4()).upper()
                    unsafe.write_text("unsafe\n", encoding="utf-8")
                with mock.patch.object(
                    managed_repo, "verify_entry", return_value=True
                ), self.assertRaises(guard.GuardProtocolError):
                    store.gc_sweep()
                self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_strict_durable_enumeration_blocks_malformed_managed_record(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        store, digest = self.managed_store(root_name="malformed-snapshot")
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        malformed_id = str(uuid.uuid4())
        malformed = store.root / malformed_id
        malformed.mkdir()
        guard.atomic_write_json(malformed / "request.json", {"preset": "managed-repo"})
        guard.atomic_write_json(malformed / "status.json", {
            "jobId": store.capabilities.encode("job", malformed_id),
            "internalJobId": malformed_id,
            "status": "completed",
        })
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), self.assertRaises(guard.GuardProtocolError):
            store.gc_sweep()
        self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_malformed_later_status_blocks_earlier_eligible_candidate(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        store, digest = self.managed_store(root_name="ordered-malformed-status")
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        eligible_id = request["internalJobId"]
        malformed_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        self.assertLess(eligible_id, malformed_id)

        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            candidates = store._managed_gc_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(
                store._evaluate_candidate(candidates[0])["lifecycleState"],
                managed_repo.LIFECYCLE_ELIGIBLE,
            )

        malformed = store.root / malformed_id
        malformed.mkdir()
        guard.atomic_write_json(malformed / "request.json", {"preset": "managed-repo"})
        (malformed / "status.json").write_text("{", encoding="utf-8")
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            managed_repo, "remove_managed_worktree"
        ) as remove_worktree, self.assertRaises(guard.GuardProtocolError):
            store.gc_sweep()
        remove_worktree.assert_not_called()
        self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_incomplete_and_unsafe_managed_records_block_whole_sweep(self):
        for index, unsafe_type in enumerate((
            "missing_request", "missing_status", "symlink_request", "symlink_status"
        )):
            with self.subTest(unsafe_type=unsafe_type):
                allocation, request, _candidate, _digest = self.allocate_gc_candidate()
                store, digest = self.managed_store(
                    root_name="unsafe-record-" + str(index)
                )
                request["registryCanonicalHash"] = digest
                self.write_store_candidate(store, request)
                unsafe = store.root / "ffffffff-ffff-ffff-ffff-ffffffffffff"
                unsafe.mkdir()
                target = store.root / (unsafe_type + "-target.json")
                guard.atomic_write_json(target, {})
                if unsafe_type != "missing_request":
                    if unsafe_type == "symlink_request":
                        (unsafe / "request.json").symlink_to(target)
                    else:
                        guard.atomic_write_json(unsafe / "request.json", {})
                if unsafe_type != "missing_status":
                    if unsafe_type == "symlink_status":
                        (unsafe / "status.json").symlink_to(target)
                    else:
                        guard.atomic_write_json(unsafe / "status.json", {})
                with mock.patch.object(
                    managed_repo, "verify_entry", return_value=True
                ), mock.patch.object(
                    managed_repo, "remove_managed_worktree"
                ) as remove_worktree, self.assertRaises(guard.GuardProtocolError):
                    store.gc_sweep()
                remove_worktree.assert_not_called()
                self.assertTrue(Path(allocation["workspace"]).is_dir())

    def test_remove_uses_registered_source_repo_and_exact_worktree_path(self):
        allocation, _request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = allocation["workspace"]
        success = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(
            managed_repo, "_git", side_effect=(success, success)
        ) as git_call, mock.patch.object(
            managed_repo.shutil, "rmtree"
        ) as recursive_delete:
            outcome = managed_repo.remove_managed_worktree(self.entry, workspace)
        self.assertEqual(outcome["lifecycleState"], managed_repo.LIFECYCLE_REMOVED)
        self.assertEqual(git_call.call_args_list, [
            mock.call(
                self.entry["repoPath"], "worktree", "remove", "--", workspace,
                timeout=300, check=False,
            ),
            mock.call(
                self.entry["repoPath"], "worktree", "prune",
                timeout=300, check=False,
            ),
        ])
        recursive_delete.assert_not_called()

    def test_sweep_retains_exactly_owned_active_local_process(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        provider = self.disk_usage_sequence(
            30 * managed_repo.GIB,
            30 * managed_repo.GIB,
        )
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        _thread_id, _job_id, job_dir = self.write_store_candidate(store, request)
        fake_pid = 424242
        guard.atomic_write_json(job_dir / "local-process.json", {
            "pid": fake_pid,
            "processGroupId": fake_pid,
            "command": ["/usr/bin/true"],
            "jobDir": str(job_dir),
            "workspace": allocation["workspace"],
            "status": "running",
        })
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "process_exists", return_value=True
        ), mock.patch.object(
            guard.os, "getpgid", return_value=fake_pid
        ), mock.patch.object(
            guard, "_local_process_command_matches", return_value=True
        ):
            store.gc_sweep()
        self.assertTrue(Path(allocation["workspace"]).is_dir())
        self.assertEqual(
            store.last_gc_metrics["retainedReasons"],
            {managed_repo.RETAINED_ACTIVE_LOCAL_PROCESS: 1},
        )

    def test_worker_launch_failure_and_post_popen_crash_remain_fail_closed(self):
        store, _digest = self.managed_store(root_name="worker-launch-failure")
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            store, "_start_worker", side_effect=OSError("launch failed")
        ):
            state = store.enqueue("worker failure", repo_alias=self.entry["alias"])
        job_dir = store.job_dir(state["jobId"])
        worker = json.loads((job_dir / "worker.json").read_text(encoding="utf-8"))
        durable_state = store._state_for_path(job_dir)
        self.assertEqual(worker["status"], "launch_failed")
        self.assertEqual(durable_state["workerLaunchState"], "launch_failed")
        self.assertEqual(store._worker_activity(job_dir, durable_state), "inactive")

        prelaunch_store, _digest = self.managed_store(
            root_name="worker-pre-popen-crash"
        )
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            prelaunch_store,
            "_start_worker",
            side_effect=guard.GuardProtocolError("simulated pre-popen crash"),
        ), self.assertRaises(guard.GuardProtocolError):
            prelaunch_store.enqueue(
                "worker pre-popen crash", repo_alias=self.entry["alias"]
            )
        prelaunch_job = prelaunch_store._job_directories(strict=True)[0]
        prelaunch_worker = json.loads(
            (prelaunch_job / "worker.json").read_text(encoding="utf-8")
        )
        self.assertEqual(prelaunch_worker["status"], "launching")
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            prelaunch_store.gc_sweep()
        prelaunch_request = json.loads(
            (prelaunch_job / "request.json").read_text(encoding="utf-8")
        )
        self.assertTrue(Path(prelaunch_request["workspace"]).is_dir())

        crash_store, _digest = self.managed_store(root_name="worker-post-popen")
        launched = []
        original_atomic = guard.atomic_write_json

        def start_sleep(_command):
            process = subprocess.Popen(
                [os.path.realpath(sys.executable), "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            launched.append(process)
            return process

        def fail_running_worker(path, payload):
            if path.name == "worker.json" and payload.get("status") == "running":
                raise guard.GuardProtocolError("simulated post-popen crash")
            return original_atomic(path, payload)

        try:
            with mock.patch.object(
                managed_repo, "verify_entry", return_value=True
            ), mock.patch.object(
                crash_store, "_start_worker", side_effect=start_sleep
            ), mock.patch.object(
                guard, "atomic_write_json", side_effect=fail_running_worker
            ), self.assertRaises(guard.GuardProtocolError):
                crash_store.enqueue("worker crash", repo_alias=self.entry["alias"])
            crash_job = crash_store._job_directories(strict=True)[0]
            crash_state = crash_store._state_for_path(crash_job)
            crash_worker = json.loads(
                (crash_job / "worker.json").read_text(encoding="utf-8")
            )
            self.assertEqual(crash_worker["status"], "launching")
            self.assertEqual(crash_state["workerLaunchState"], "launching")
            with mock.patch.object(managed_repo, "verify_entry", return_value=True):
                crash_store.gc_sweep()
            request = json.loads(
                (crash_job / "request.json").read_text(encoding="utf-8")
            )
            self.assertTrue(Path(request["workspace"]).is_dir())
        finally:
            for process in launched:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)

    def test_missing_worker_or_local_launch_evidence_retains(self):
        for index, missing_field in enumerate((
            "workerLaunchState", "localProcessLaunchState"
        )):
            with self.subTest(missing_field=missing_field):
                allocation, request, _candidate, _digest = self.allocate_gc_candidate()
                store, digest = self.managed_store(
                    root_name="missing-launch-evidence-" + str(index)
                )
                request["registryCanonicalHash"] = digest
                _thread_id, _job_id, job_dir = self.write_store_candidate(
                    store, request
                )
                state_path = job_dir / "status.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state.pop(missing_field)
                guard.atomic_write_json(state_path, state)
                with mock.patch.object(
                    managed_repo, "verify_entry", return_value=True
                ):
                    store.gc_sweep()
                self.assertTrue(Path(allocation["workspace"]).is_dir())
                self.assertEqual(
                    store.last_gc_metrics["retainedReasons"],
                    {managed_repo.RETAINED_UNKNOWN: 1},
                )

    def test_local_launch_failure_and_post_popen_crash_remain_fail_closed(self):
        entry = self.local_loopback_entry()
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        store, digest = self.managed_store(
            root_name="local-launch-failure", entry=entry
        )
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, job_dir = self.write_store_candidate(store, request)
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            store, "_start_local_process", side_effect=OSError("launch failed")
        ), self.assertRaises(guard.GuardProtocolError):
            store.start_local_target(thread_id, "preview")
        local = json.loads(
            (job_dir / "local-process.json").read_text(encoding="utf-8")
        )
        state = store._state_for_path(job_dir)
        self.assertEqual(local["status"], "launch_failed")
        self.assertEqual(state["localProcessLaunchState"], "launch_failed")
        self.assertEqual(
            store._local_process_activity(job_dir, allocation["workspace"], state),
            "inactive",
        )

        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        prelaunch_store, digest = self.managed_store(
            root_name="local-pre-popen-crash", entry=entry
        )
        request["registryCanonicalHash"] = digest
        prelaunch_thread, _job_id, prelaunch_job = self.write_store_candidate(
            prelaunch_store, request
        )
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            prelaunch_store,
            "_start_local_process",
            side_effect=guard.GuardProtocolError("simulated pre-popen crash"),
        ), self.assertRaises(guard.GuardProtocolError):
            prelaunch_store.start_local_target(prelaunch_thread, "preview")
        prelaunch_record = json.loads(
            (prelaunch_job / "local-process.json").read_text(encoding="utf-8")
        )
        self.assertEqual(prelaunch_record["status"], "launching")
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            prelaunch_store.gc_sweep()
        self.assertTrue(Path(allocation["workspace"]).is_dir())

        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        crash_store, digest = self.managed_store(
            root_name="local-post-popen", entry=entry
        )
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, crash_job = self.write_store_candidate(
            crash_store, request
        )
        launched = []
        original_atomic = guard.atomic_write_json

        def start_sleep(_command, _workspace, _stdout_fd, _stderr_fd):
            process = subprocess.Popen(
                [os.path.realpath(sys.executable), "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            launched.append(process)
            return process

        def fail_running_local(path, payload):
            if path.name == "local-process.json" and payload.get("status") == "running":
                raise guard.GuardProtocolError("simulated post-popen crash")
            return original_atomic(path, payload)

        try:
            with mock.patch.object(
                managed_repo, "verify_entry", return_value=True
            ), mock.patch.object(
                crash_store, "_start_local_process", side_effect=start_sleep
            ), mock.patch.object(
                guard, "atomic_write_json", side_effect=fail_running_local
            ), self.assertRaises(guard.GuardProtocolError):
                crash_store.start_local_target(thread_id, "preview")
            crash_state = crash_store._state_for_path(crash_job)
            crash_record = json.loads(
                (crash_job / "local-process.json").read_text(encoding="utf-8")
            )
            self.assertEqual(crash_record["status"], "launching")
            self.assertEqual(crash_state["localProcessLaunchState"], "launching")
            with mock.patch.object(managed_repo, "verify_entry", return_value=True):
                crash_store.gc_sweep()
            self.assertTrue(Path(allocation["workspace"]).is_dir())
        finally:
            for process in launched:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)

    def test_real_local_process_pid_and_group_are_verified(self):
        store, _digest = self.managed_store(root_name="real-process")
        job_id = str(uuid.uuid4())
        job_dir = store.root / job_id
        job_dir.mkdir()
        command = [
            os.path.realpath(sys.executable),
            "-c",
            "import time; time.sleep(30)",
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            guard.atomic_write_json(job_dir / "local-process.json", {
                "pid": process.pid,
                "processGroupId": process.pid,
                "command": command,
                "jobDir": str(job_dir),
                "workspace": str(self.workspace),
                "status": "running",
            })
            state = {"localProcessLaunchState": "running"}
            with mock.patch.object(
                guard, "_local_process_command_matches", return_value=True
            ):
                self.assertEqual(
                    store._local_process_activity(
                        job_dir, str(self.workspace), state
                    ),
                    "active",
                )
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

    def test_hard_watermark_blocks_start_when_reclamation_is_insufficient(self):
        provider = self.disk_usage_sequence(
            12 * managed_repo.GIB,
            12 * managed_repo.GIB,
        )
        store, _digest = self.managed_store(provider)
        with self.assertRaisesRegex(
            guard.GuardAdmissionError, managed_repo.DISK_PRESSURE_ERROR
        ):
            store.enqueue("new managed task", repo_alias=self.entry["alias"])
        self.assertEqual(store.last_gc_metrics["watermarkState"], managed_repo.WATERMARK_HARD)

    def test_reclaiming_above_hard_allows_new_start(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        provider = self.disk_usage_sequence(
            12 * managed_repo.GIB,
            30 * managed_repo.GIB,
        )
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True), mock.patch.object(
            store, "_start_worker", return_value=SimpleNamespace(pid=999999)
        ):
            state = store.enqueue("new managed task", repo_alias=self.entry["alias"])
        self.assertIn(state["status"], ("queued", "failed"))
        self.assertFalse(Path(allocation["workspace"]).exists())
        self.assertEqual(store.last_gc_metrics["removedJobCount"], 1)
        self.assertEqual(
            managed_repo.disk_watermark(store.last_disk_snapshot),
            managed_repo.WATERMARK_NORMAL,
        )

    def test_emergency_blocks_start_continuation_and_local_execution(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        provider = self.disk_usage_sequence(6 * managed_repo.GIB)
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        thread_id, _job_id, _job_dir = self.write_store_candidate(store, request)
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "allocate_worktree"
        ) as allocate, mock.patch.object(
            store, "_start_worker"
        ) as start_worker, mock.patch.object(
            store, "_start_local_process"
        ) as start_local, mock.patch.object(
            guard, "remove_managed_worktree"
        ) as remove_worktree:
            for label, operation in (
                ("start", lambda: store.enqueue(
                    "new managed task", repo_alias=self.entry["alias"]
                )),
                ("continuation", lambda: store.enqueue(
                    "continuation", thread_id=thread_id
                )),
                ("local", lambda: store.start_local_target(thread_id, "preview")),
            ):
                with self.subTest(surface=label), self.assertRaisesRegex(
                    guard.GuardAdmissionError, managed_repo.DISK_PRESSURE_ERROR
                ):
                    operation()
        allocate.assert_not_called()
        start_worker.assert_not_called()
        start_local.assert_not_called()
        remove_worktree.assert_not_called()
        self.assertTrue(workspace.is_dir())

    def test_emergency_keeps_status_wait_publish_stop_and_close_usable(self):
        entry = self.local_loopback_entry()
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        provider = self.disk_usage_sequence(6 * managed_repo.GIB)
        store, digest = self.managed_store(
            provider, root_name="emergency-recovery", entry=entry
        )
        request["registryCanonicalHash"] = digest
        thread_id, job_id, job_dir = self.write_store_candidate(store, request)
        target = entry["localLoopbackTargets"][0]
        guard.atomic_write_json(job_dir / "local-process.json", {
            "targetName": target["name"],
            "command": managed_repo.local_target_command(
                target, allocation["workspace"]
            ),
            "jobDir": str(job_dir),
            "workspace": allocation["workspace"],
            "status": "stopped",
            "updatedAt": 1,
        })
        publish_result = {"pushed": False, "surface": "available"}
        with mock.patch.object(
            managed_repo, "verify_entry", return_value=True
        ), mock.patch.object(
            guard, "publish_managed_repo", return_value=publish_result
        ) as publish, mock.patch.object(
            guard, "remove_managed_worktree"
        ) as remove_worktree:
            self.assertEqual(store.read(job_id)["status"], "completed")
            self.assertEqual(store.wait(job_id, 0)["status"], "completed")
            self.assertEqual(
                store.publish_managed(thread_id, "recovery publish"),
                publish_result,
            )
            self.assertEqual(
                store.stop_local_target(thread_id, target["name"]),
                {"targetName": target["name"], "status": "stopped"},
            )
            close = store.close_managed(thread_id)
        publish.assert_called_once()
        remove_worktree.assert_not_called()
        self.assertEqual(close["status"], managed_repo.WORKSPACE_NOT_SAFE_TO_GC)
        self.assertEqual(close["retainedReason"], managed_repo.RETAINED_DIRTY)
        self.assertTrue(workspace.is_dir())

    def test_admission_lock_serializes_gc_and_start_pressure_decision(self):
        total = 100 * managed_repo.GIB
        hard_usage = SimpleNamespace(
            total=total,
            used=total - 12 * managed_repo.GIB,
            free=12 * managed_repo.GIB,
        )
        gc_evaluating = threading.Event()
        release_gc = threading.Event()

        def synchronized_usage(_path):
            if (
                threading.current_thread().name == "gc-holder"
                and not gc_evaluating.is_set()
            ):
                gc_evaluating.set()
                if not release_gc.wait(5):
                    raise AssertionError("GC synchronization timed out")
            return hard_usage

        gc_store, _digest = self.managed_store(
            synchronized_usage, root_name="concurrent-admission"
        )
        admission_store, _digest = self.managed_store(
            synchronized_usage, root_name="concurrent-admission"
        )
        admission_attempted = threading.Event()
        capacity_checked = threading.Event()
        original_lock = admission_store._locked_admission
        original_capacity = admission_store._require_start_capacity_locked

        def observed_lock():
            inner = original_lock()

            class ObservedLock:
                def __enter__(self):
                    admission_attempted.set()
                    return inner.__enter__()

                def __exit__(self, error_type, value, traceback):
                    return inner.__exit__(error_type, value, traceback)

            return ObservedLock()

        def observed_capacity():
            capacity_checked.set()
            return original_capacity()

        gc_errors = []
        admission_errors = []

        def run_gc():
            try:
                gc_store.gc_sweep()
            except Exception as error:
                gc_errors.append(error)

        def run_admission():
            try:
                admission_store.enqueue(
                    "concurrent start", repo_alias=self.entry["alias"]
                )
            except Exception as error:
                admission_errors.append(error)

        gc_thread = threading.Thread(target=run_gc, name="gc-holder")
        admission_thread = threading.Thread(
            target=run_admission, name="admission-contender"
        )
        with mock.patch.object(
            admission_store, "_locked_admission", side_effect=observed_lock
        ), mock.patch.object(
            admission_store, "_require_start_capacity_locked",
            side_effect=observed_capacity,
        ):
            gc_thread.start()
            try:
                self.assertTrue(gc_evaluating.wait(5))
                probe = os.open(str(gc_store.lock_path), os.O_RDWR)
                try:
                    with self.assertRaises(OSError):
                        guard.fcntl.flock(
                            probe, guard.fcntl.LOCK_EX | guard.fcntl.LOCK_NB
                        )
                finally:
                    os.close(probe)
                admission_thread.start()
                self.assertTrue(admission_attempted.wait(5))
                self.assertFalse(capacity_checked.is_set())
            finally:
                release_gc.set()
                gc_thread.join(5)
                if admission_thread.ident is not None:
                    admission_thread.join(5)
        self.assertFalse(gc_thread.is_alive())
        self.assertFalse(admission_thread.is_alive())
        self.assertEqual(gc_errors, [])
        self.assertTrue(capacity_checked.is_set())
        self.assertEqual(len(admission_errors), 1)
        self.assertIsInstance(admission_errors[0], guard.GuardAdmissionError)
        self.assertEqual(str(admission_errors[0]), managed_repo.DISK_PRESSURE_ERROR)

    def test_emergency_recovery_tools_remain_on_public_surface(self):
        names = {
            tool["name"] for tool in guard.build_public_tools(
                "workspace-write", "never", "managed-repo",
                allow_local_loopback=True,
            )
        }
        self.assertTrue({
            "codex-job-status", "codex-wait", "codex-repo-publish",
            "codex-repo-close", "codex-repo-stop-local",
        }.issubset(names))

    def test_disk_pressure_never_deletes_dirty_unpublished_workspace(self):
        allocation, request, _candidate, _digest = self.allocate_gc_candidate()
        workspace = Path(allocation["workspace"])
        (workspace / "protected.txt").write_text("protected\n", encoding="utf-8")
        provider = self.disk_usage_sequence(
            12 * managed_repo.GIB,
            12 * managed_repo.GIB,
        )
        store, digest = self.managed_store(provider)
        request["registryCanonicalHash"] = digest
        self.write_store_candidate(store, request)
        with mock.patch.object(managed_repo, "verify_entry", return_value=True):
            with self.assertRaisesRegex(
                guard.GuardAdmissionError, managed_repo.DISK_PRESSURE_ERROR
            ):
                store.enqueue("new managed task", repo_alias=self.entry["alias"])
        self.assertTrue(workspace.is_dir())
        self.assertEqual(
            store.last_gc_metrics["retainedReasons"],
            {managed_repo.RETAINED_DIRTY: 1},
        )

    def test_capabilities_bind_preset_and_registry_hash(self):
        key = self.root / "capability.key"
        first = guard.CapabilityCodec(
            str(key),
            guard.capability_context(str(self.workspace), "workspace-write", "never", "managed-repo", "a" * 64),
        )
        capability = first.encode("thread", "thread-one")
        second = guard.CapabilityCodec(
            str(key),
            guard.capability_context(str(self.workspace), "workspace-write", "never", "managed-repo", "b" * 64),
        )
        with self.assertRaises(guard.GuardProtocolError):
            second.decode("thread", capability)
        different_preset = guard.CapabilityCodec(
            str(key),
            guard.capability_context(str(self.workspace), "danger-full-access", "never", "personal-full-control", "a" * 64),
        )
        with self.assertRaises(guard.GuardProtocolError):
            different_preset.decode("thread", capability)

    def test_record_for_repo_a_cannot_be_used_for_repo_b(self):
        other = dict(self.entry, alias="other-repo", repositoryFullName="example/other-repo")
        record = {
            "repoAlias": "sample-repo",
            "repositoryFullName": "example/sample-repo",
            "repoPath": str(self.repo),
            "baseRemote": "origin",
            "baseBranch": "main",
            "registryCanonicalHash": "a" * 64,
            "preset": "managed-repo",
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
        }
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "context mismatch"):
            managed_repo.validate_managed_record(record, other, "a" * 64)

    def test_managed_tool_surface_has_no_generic_start_or_deploy(self):
        names = {
            tool["name"] for tool in guard.build_public_tools(
                "workspace-write", "never", "managed-repo"
            )
        }
        self.assertIn("codex-repo-start", names)
        self.assertIn("codex-repo-publish", names)
        self.assertIn("codex-repo-close", names)
        self.assertNotIn("codex-start", names)
        self.assertNotIn("codex", names)
        self.assertFalse(any("deploy" in name or "run" in name for name in names))
        start = next(
            tool for tool in guard.build_public_tools(
                "workspace-write", "never", "managed-repo"
            ) if tool["name"] == "codex-repo-start"
        )
        properties = start["inputSchema"]["properties"]
        self.assertEqual(set(properties), {"prompt", "repoAlias", "taskName"})
        self.assertNotIn("cwd", properties)
        self.assertNotIn("repoPath", properties)

    def test_async_public_state_exposes_only_safe_managed_identity(self):
        properties = guard.ASYNC_OUTPUT_SCHEMA["properties"]
        self.assertIn("repoAlias", properties)
        self.assertIn("workBranch", properties)
        self.assertNotIn("repoPath", properties)
        self.assertNotIn("workspace", properties)
        state = {
            "jobId": "public-job-capability",
            "threadId": "public-thread-capability",
            "status": "completed",
            "content": "done",
            "contentTruncated": False,
            "updatedAt": 1,
            "repoAlias": "sample-repo",
            "workBranch": "codex/bridge/12345678",
            "repoPath": str(self.repo),
            "workspace": str(self.workspace),
        }
        public = guard.public_job_state(state)
        self.assertEqual(public["repoAlias"], "sample-repo")
        self.assertEqual(public["workBranch"], "codex/bridge/12345678")
        self.assertNotIn("repoPath", public)
        self.assertNotIn("workspace", public)

    def test_managed_configuration_requires_workspace_write_and_never(self):
        executable = self.root / "codex"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        registry_path = self.root / "managed-repos.v1.json"
        registry_path.write_text(json.dumps({
            "registryVersion": managed_repo.REGISTRY_VERSION,
            "repos": [],
        }), encoding="utf-8")
        registry_path.chmod(0o600)
        arguments = [
            "--workspace", str(self.workspace),
            "--codex-bin", str(executable),
            "--desktop-open-bin", "/usr/bin/open",
            "--preset", "managed-repo",
            "--managed-registry", str(registry_path),
            "--sandbox", "workspace-write",
            "--approval-policy", "never",
        ]
        parsed = guard.parse_configuration(arguments)
        self.assertEqual(parsed[3:5], ("workspace-write", "never"))
        unsafe = list(arguments)
        unsafe[unsafe.index("workspace-write")] = "danger-full-access"
        with self.assertRaises(guard.GuardConfigurationError):
            guard.parse_configuration(unsafe)

    def test_deployment_tiers_fail_closed(self):
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "DEPLOYMENT_NOT_AUTHORIZED"):
            managed_repo.authorize_deployment(self.entry, "none")
        production = dict(self.entry, deploymentTier="production")
        with self.assertRaisesRegex(
            managed_repo.ManagedRepoError, "PRODUCTION_DEPLOYMENT_NOT_AUTHORIZED"
        ):
            managed_repo.authorize_deployment(production, "production")
        staging = dict(self.entry, deploymentTier="staging")
        with self.assertRaisesRegex(
            managed_repo.ManagedRepoError, "STAGING_RELEASE_CAPABILITY_REQUIRED"
        ):
            managed_repo.authorize_deployment(staging, "staging")
        unsafe_target = dict(
            self.entry,
            deploymentTier="local-loopback",
            localLoopbackTargets=[{
                "name": "web",
                "executable": "/usr/bin/true",
                "argv": ["--host={host}"],
                "host": "0.0.0.0",
            }],
        )
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "loopback"):
            managed_repo.validate_entry(unsafe_target, verify_live=False)

    def test_local_loopback_surface_uses_registered_target_and_is_revocable(self):
        names = {
            tool["name"] for tool in guard.build_public_tools(
                "workspace-write", "never", "managed-repo",
                allow_local_loopback=True,
            )
        }
        self.assertIn("codex-repo-run-local", names)
        self.assertIn("codex-repo-stop-local", names)
        entry = dict(
            self.entry,
            deploymentTier="local-loopback",
            localLoopbackTargets=[{
                "name": "preview",
                "executable": "/usr/bin/yes",
                "argv": ["{host}"],
                "host": "127.0.0.1",
            }],
        )
        validated = managed_repo.validate_entry(entry, verify_live=False)
        target = managed_repo.authorize_deployment(
            validated, "local-loopback", "preview"
        )
        command = managed_repo.local_target_command(target, str(self.workspace))
        self.assertEqual(command, [
            "/usr/bin/yes", "127.0.0.1",
        ])
        with self.assertRaisesRegex(managed_repo.ManagedRepoError, "unknown"):
            managed_repo.authorize_deployment(
                validated, "local-loopback", "arbitrary"
            )

        job_root = self.root / "jobs"
        job_root.mkdir()
        internal_job_id = str(uuid.uuid4())
        job_dir = job_root / internal_job_id
        job_dir.mkdir()
        fake_pid = 424242
        guard.atomic_write_json(job_dir / "local-process.json", {
            "targetName": "preview",
            "pid": fake_pid,
            "processGroupId": fake_pid,
            "command": command,
            "jobDir": str(job_dir),
            "workspace": str(self.workspace),
            "status": "running",
            "startedAt": 1,
            "updatedAt": 1,
        })
        guard.atomic_write_json(job_dir / "status.json", {
            "internalJobId": internal_job_id,
            "status": "completed",
        })
        with mock.patch.object(
            guard, "process_exists", side_effect=[True, False, False, False]
        ), mock.patch.object(
            guard.os, "getpgid", return_value=fake_pid
        ), mock.patch.object(
            guard.os, "killpg"
        ), mock.patch.object(
            guard, "_local_process_command_matches", return_value=True
        ):
            self.assertEqual(guard.revoke_managed_workers(str(job_root)), 1)
        record = json.loads(
            (job_dir / "local-process.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "stopped")


if __name__ == "__main__":
    unittest.main(verbosity=2)
