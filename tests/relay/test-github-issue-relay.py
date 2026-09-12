#!/usr/bin/python3

import importlib.util
import json
import os
import sqlite3
import stat
import tempfile
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELAY_PATH = REPO_ROOT / "scripts" / "relay" / "github-issue-relay.py"
SPEC = importlib.util.spec_from_file_location("github_issue_relay", RELAY_PATH)
relay_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay_module)


CONFIG = relay_module.OperatorConfig('example/control-private', ['fixture-owner'],
    {'sample-alpha': 'codex/relay/sample-alpha/', 'sample-beta': 'codex/relay/sample-beta/',
     'sample-gamma': 'codex/relay/sample-gamma/'}, 'a'*64)

def valid_payload(request_id=None, repo_alias="sample-alpha"):
    return {
        "schema": "codex_bridge_job_v1",
        "requestId": request_id or str(uuid.uuid4()),
        "operation": "start",
        "repoAlias": repo_alias,
        "taskName": "R-GH1 read-only proof",
        "prompt": "Read repository identity only. DO NOT MODIFY. DO NOT COMMIT. DO NOT PUSH.",
    }


def valid_reply_payload(relay_job_ref, request_id=None):
    return {
        "schema": "codex_bridge_job_v1",
        "requestId": request_id or str(uuid.uuid4()),
        "operation": "reply",
        "relayJobRef": relay_job_ref,
        "prompt": "What continuity marker did I give you?",
    }


def valid_publish_payload(relay_job_ref, request_id=None):
    return {
        "schema": "codex_bridge_job_v1",
        "requestId": request_id or str(uuid.uuid4()),
        "operation": "publish",
        "relayJobRef": relay_job_ref,
        "commitMessage": "test: prove guarded relay publish",
    }


def valid_issue(number=1, payload=None):
    return {
        "number": number,
        "repository_url": "https://api.github.com/repos/" + CONFIG.repository,
        "state": "open",
        "user": {"login": "fixture-owner"},
        "labels": [{"name": "bridge-job"}],
        "body": "```json\n{}\n```".format(
            json.dumps(payload or valid_payload(), ensure_ascii=False)
        ),
    }


class FakeGitHub:
    def __init__(self):
        self.config = CONFIG
        self.statuses = []
        self.comments = []
        self.comment_attempts = 0
        self.fail_comment_before = 0
        self.fail_comment_after_accept = 0
        self.fail_terminal_label = 0

    def set_status_label(self, issue_number, status):
        if status in ("completed", "failed") and self.fail_terminal_label:
            self.fail_terminal_label -= 1
            raise relay_module.GitHubError("terminal label fixture failure")
        self.statuses.append((issue_number, status))

    def comment(self, issue_number, body):
        self.comment_attempts += 1
        if self.fail_comment_before:
            self.fail_comment_before -= 1
            raise relay_module.GitHubError("comment fixture failure")
        self.comments.append((issue_number, body))
        if self.fail_comment_after_accept:
            self.fail_comment_after_accept -= 1
            raise relay_module.GitHubError("accepted comment fixture failure")

    def result_comments(self, issue_number):
        return [body for number, body in self.comments if number == issue_number]

    def mark_rejected(self, issue_number):
        self.statuses.append((issue_number, "rejected"))

    def list_open_jobs(self):
        return []


class FakeMcpClient:
    JOB_CAPABILITY = "guard-job-sample-alpha-capability-secret"
    THREAD_CAPABILITY = "guard-thread-sample-alpha-capability-secret"
    THREADS = {
        "sample-alpha": THREAD_CAPABILITY,
        "sample-beta": "guard-thread-sample-beta-capability-secret",
        "sample-gamma": "guard-thread-sample-gamma-capability-secret",
    }
    BRANCHES = {
        "sample-alpha": "codex/relay/sample-alpha/f00dbabe",
        "sample-beta": "codex/relay/sample-beta/b16b00b5",
        "sample-gamma": "codex/relay/sample-gamma/a5a5a5a5",
    }
    PUBLISH_COMMIT = "a" * 40

    def __init__(self):
        self.closed = False
        self.calls = []
        self.jobs = {}
        self.revoked_threads = set()

    def start(self):
        self.closed = False
        return {
            "codex-repo-start",
            "codex-reply-async",
            "codex-wait",
            "codex-job-status",
            "codex-repo-publish",
        }

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "codex-repo-start":
            alias = arguments["repoAlias"]
            job = "guard-job-{}-capability-secret".format(alias)
            self.jobs[job] = {
                "jobId": job,
                "threadId": self.THREADS[alias],
                "status": "completed",
                "repoAlias": alias,
                "workBranch": self.BRANCHES[alias],
                "content": "START_OK=" + alias,
                "contentTruncated": False,
            }
            return dict(self.jobs[job], status="queued", content="")
        if name == "codex-reply-async":
            thread = arguments["threadId"]
            if thread in self.revoked_threads:
                raise relay_module.RelayError("revoked fixture")
            alias = next(
                (key for key, value in self.THREADS.items() if value == thread),
                None,
            )
            if alias is None:
                raise relay_module.RelayError("unknown fixture thread")
            job = "guard-job-reply-{}-capability-secret".format(alias)
            self.jobs[job] = {
                "jobId": job,
                "threadId": thread,
                "status": "completed",
                "repoAlias": alias,
                "workBranch": self.BRANCHES[alias],
                "content": "R_GH2_CONTINUITY_MARKER_824",
                "contentTruncated": False,
            }
            return dict(self.jobs[job], status="queued", content="")
        if name in ("codex-wait", "codex-job-status"):
            return dict(self.jobs[arguments["jobId"]])
        if name == "codex-repo-publish":
            thread = arguments["threadId"]
            if thread in self.revoked_threads:
                raise relay_module.RelayError("revoked fixture")
            alias = next(
                (key for key, value in self.THREADS.items() if value == thread),
                None,
            )
            if alias is None:
                raise relay_module.RelayError("unknown fixture thread")
            return {
                "branch": self.BRANCHES[alias],
                "commit": self.PUBLISH_COMMIT,
                "pushed": True,
                "base_stale": False,
            }
        raise AssertionError("unexpected tool call")

    def close(self):
        self.closed = True


class PagedFakeGitHub(FakeGitHub, relay_module.GitHubClient):
    list_open_jobs = relay_module.GitHubClient.list_open_jobs

    def __init__(self, issues, fail_page=None, invalid_page=None):
        super().__init__()
        self.issues = issues
        self.fail_page = fail_page
        self.invalid_page = invalid_page
        self.requests = []

    def _api(self, method, endpoint, payload=None):
        self.requests.append((method, endpoint, payload))
        page = int(endpoint.rsplit("&page=", 1)[1])
        if page == self.fail_page:
            raise relay_module.GitHubError("synthetic page failure")
        if page == self.invalid_page:
            return {"items": []}
        return self.issues[(page - 1) * 100:page * 100]


class PaginationTestCase(unittest.TestCase):
    def test_all_page_boundaries_keep_fixed_oldest_first_query(self):
        for count in (0, 1, 100, 101, 200, 201):
            with self.subTest(count=count):
                issues = [valid_issue(number=i) for i in range(1, count + 1)]
                client = PagedFakeGitHub(issues)
                self.assertEqual(client.list_open_jobs(), issues)
                self.assertEqual(client.requests, [
                    ("GET", "/repos/example/control-private/issues"
                     "?state=open&labels=bridge-job&per_page=100&sort=created"
                     "&direction=asc&page={}".format(page), None)
                    for page in range(1, count // 100 + 2)
                ])

    def test_api_failure_and_invalid_page_never_return_partial_batch(self):
        issues = [valid_issue(number=i) for i in range(1, 102)]
        for kwargs in ({"fail_page": 2}, {"invalid_page": 1}, {"invalid_page": 2}):
            with self.subTest(**kwargs):
                with self.assertRaises(relay_module.GitHubError):
                    PagedFakeGitHub(issues, **kwargs).list_open_jobs()

    def test_all_non_list_response_types_fail_closed(self):
        for value in (None, {}, "[]", 1, True):
            with self.subTest(value=value):
                client = relay_module.GitHubClient(config=CONFIG)
                client._api = lambda *args: value
                with self.assertRaises(relay_module.GitHubError):
                    client.list_open_jobs()


class RelayTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "github-relay.sqlite3"
        self.database = relay_module.RelayDatabase(self.database_path, CONFIG)
        self.github = FakeGitHub()
        self.mcp = FakeMcpClient()
        self.relay = relay_module.GitHubIssueRelay(
            self.database, self.github, mcp_factory=lambda: self.mcp
        )

    def complete_issue(self, issue):
        self.relay.process_issue(issue)
        self.relay.supervise_active_jobs()
        self.relay.deliver_pending_results()
        row = self.database.get_by_issue(issue["number"])
        self.assertIsNotNone(row["resultPayload"])
        return json.loads(row["resultPayload"])

    def test_run_once_admits_101st_issue_and_deduplicates_overlapping_repeated_scan(self):
        issues = [valid_issue(number=i) for i in range(1, 102)]
        self.github = PagedFakeGitHub(issues + [issues[-1], issues[0]])
        self.relay.github = self.github
        self.relay.run_once()
        self.assertIsNotNone(self.database.get_by_issue(101))
        self.assertEqual(len([c for c in self.mcp.calls if c[0] == "codex-repo-start"]), 101)
        self.relay.run_once()
        self.assertEqual(len([c for c in self.mcp.calls if c[0] == "codex-repo-start"]), 101)
        count = self.database.connection.execute("SELECT COUNT(*) FROM relay_jobs").fetchone()[0]
        self.assertEqual(count, 101)

    def test_run_once_second_page_failure_or_invalid_type_admits_nothing(self):
        issues = [valid_issue(number=i) for i in range(1, 102)]
        for kwargs in ({"fail_page": 2}, {"invalid_page": 2}):
            with self.subTest(**kwargs):
                self.relay.github = PagedFakeGitHub(issues, **kwargs)
                self.relay.run_once()
                self.assertEqual(self.mcp.calls, [])
                self.assertIsNone(self.database.get_by_issue(1))
                self.assertIsNone(self.database.get_by_issue(101))

    def test_sample_gamma_start_reply_publish_preserve_closed_binding(self):
        start = self.complete_issue(valid_issue(payload=valid_payload(repo_alias="sample-gamma")))
        self.assertEqual(start["status"], "completed")
        self.assertEqual(start["repoAlias"], "sample-gamma")
        self.assertFalse(start["publishAvailable"])
        reply = self.complete_issue(valid_issue(2, valid_reply_payload(start["relayJobRef"])))
        self.assertEqual(reply["status"], "completed")
        self.assertEqual(reply["repoAlias"], "sample-gamma")
        publish = self.complete_issue(valid_issue(3, valid_publish_payload(start["relayJobRef"])))
        self.assertEqual(publish["status"], "completed")
        self.assertEqual(publish["branch"], FakeMcpClient.BRANCHES["sample-gamma"])
        for tool, arguments in self.mcp.calls:
            if tool in ("codex-reply-async", "codex-repo-publish"):
                self.assertEqual(arguments["threadId"], FakeMcpClient.THREADS["sample-gamma"])
                self.assertNotIn("repoAlias", arguments)

    def test_generic_public_alias_schema_and_configured_publish_prefixes(self):
        schema = json.loads((REPO_ROOT / "docs/specs/github-relay/job-schema-v1.json").read_text())
        self.assertNotIn('enum', schema['$defs']['start']['properties']['repoAlias'])
        for alias, prefix in CONFIG.prefixes.items():
            self.assertTrue(FakeMcpClient.BRANCHES[alias].startswith(prefix))
        self.assertNotIn('unregistered-project', CONFIG.prefixes)

    def test_sample_gamma_continuation_and_publish_reject_caller_authority(self):
        for factory in (valid_reply_payload, valid_publish_payload):
            for field in ("repoAlias", "cwd", "repoPath", "baseBranch", "repositoryFullName"):
                with self.subTest(operation=factory.__name__, field=field):
                    payload = factory("rjob_" + "x" * 24)
                    payload[field] = "sample-gamma"
                    with self.assertRaises(relay_module.AdmissionError):
                        self.relay.admit_issue(valid_issue(payload=payload))

    def test_sample_gamma_cross_alias_stored_thread_fails_reply_and_publish(self):
        start = self.complete_issue(valid_issue(payload=valid_payload(repo_alias="sample-gamma")))
        self.database.connection.execute(
            "UPDATE relay_jobs SET repoAlias = 'sample-beta', workBranch = ? WHERE issueNumber = 1",
            (FakeMcpClient.BRANCHES["sample-beta"],))
        self.database.connection.commit()
        for number, factory in enumerate((valid_reply_payload, valid_publish_payload), start=2):
            with self.subTest(operation=factory.__name__):
                result = self.complete_issue(valid_issue(number, factory(start["relayJobRef"])))
                self.assertEqual(result["status"], "interrupted" if factory is valid_reply_payload else "failed")

    def test_single_instance_lock_rejects_a_second_holder(self):
        lock_path = Path(self.temporary.name) / "github-relay.lock"
        first = relay_module.SingleInstanceLock(lock_path)
        second = relay_module.SingleInstanceLock(lock_path)
        first.acquire()
        try:
            with self.assertRaises(relay_module.RelayAlreadyRunning):
                second.acquire()
            metadata = lock_path.lstat()
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertFalse(lock_path.is_symlink())
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)
        finally:
            second.close()
            first.close()

    def test_start_persists_job_and_returns_without_terminal_wait(self):
        result = self.relay.process_issue(valid_issue(number=1))
        self.assertIsNone(result)
        self.assertEqual(
            [name for name, _ in self.mcp.calls],
            ["codex-repo-start"],
        )
        row = self.database.get_by_issue(1)
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["deliveryState"], "pending")
        self.assertEqual(row["localGuardJobCapability"], FakeMcpClient.JOB_CAPABILITY)
        self.assertEqual(json.loads(row["resultPayload"])["supervision"]["executionState"], "queued")
        self.assertEqual(self.github.comments, [])

    def test_two_issues_are_started_before_either_is_supervised(self):
        self.relay.process_issue(valid_issue(number=1))
        self.relay.process_issue(valid_issue(number=2))
        self.assertEqual(
            [name for name, _ in self.mcp.calls],
            ["codex-repo-start", "codex-repo-start"],
        )
        self.assertEqual(
            [row["status"] for row in self.database.active_jobs()],
            ["queued", "queued"],
        )
        self.assertEqual(self.github.comments, [])

    def test_active_job_resumes_after_database_restart_without_replacement(self):
        self.relay.process_issue(valid_issue(number=1))
        self.database.close()
        self.database = relay_module.RelayDatabase(self.database_path, CONFIG)
        self.relay = relay_module.GitHubIssueRelay(
            self.database, self.github, mcp_factory=lambda: self.mcp
        )
        self.relay.supervise_active_jobs()
        self.relay.deliver_pending_results()
        row = self.database.get_by_issue(1)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["deliveryState"], "delivered")
        self.assertEqual(
            [name for name, _ in self.mcp.calls].count("codex-repo-start"), 1
        )
        self.assertIn("codex-job-status", [name for name, _ in self.mcp.calls])

    def test_unbound_active_row_fails_closed_without_starting_replacement(self):
        self.relay.admit_issue(valid_issue(number=1))
        self.relay.reconcile_unbound_active_jobs()
        row = self.database.get_by_issue(1)
        self.assertEqual(row["status"], "interrupted")
        self.assertEqual(row["deliveryState"], "pending")
        self.assertEqual(self.mcp.calls, [])

    def test_transient_guard_status_failure_keeps_job_active_for_retry(self):
        self.relay.process_issue(valid_issue(number=1))
        original_call = self.mcp.call_tool
        failures = [True]

        def transient_call(name, arguments):
            if name == "codex-job-status" and failures:
                failures.pop()
                raise relay_module.RelayError("temporary Guard fixture failure")
            return original_call(name, arguments)

        self.mcp.call_tool = transient_call
        self.relay.supervise_active_jobs()
        row = self.database.get_by_issue(1)
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["deliveryState"], "pending")
        self.relay.supervise_active_jobs()
        self.assertEqual(self.database.get_by_issue(1)["status"], "completed")

    def test_revoked_guard_job_fails_closed_without_replacement(self):
        self.relay.process_issue(valid_issue(number=1))
        original_call = self.mcp.call_tool

        def revoked_call(name, arguments):
            if name == "codex-job-status":
                raise relay_module.GuardMcpError(-32602)
            return original_call(name, arguments)

        self.mcp.call_tool = revoked_call
        self.relay.supervise_active_jobs()
        row = self.database.get_by_issue(1)
        self.assertEqual(row["status"], "interrupted")
        self.assertEqual(row["deliveryState"], "pending")
        self.assertEqual(
            [name for name, _ in self.mcp.calls].count("codex-repo-start"), 1
        )

    def test_comment_failure_keeps_outbox_pending_until_retry(self):
        self.relay.process_issue(valid_issue(number=1))
        self.relay.supervise_active_jobs()
        self.github.fail_comment_before = 1
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "pending")
        self.assertEqual(self.github.comments, [])
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "delivered")
        self.assertEqual(len(self.github.comments), 1)

    def test_accepted_comment_response_failure_is_idempotent_after_restart(self):
        self.relay.process_issue(valid_issue(number=1))
        self.relay.supervise_active_jobs()
        self.github.fail_comment_after_accept = 1
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "pending")
        self.assertEqual(len(self.github.comments), 1)
        self.database.close()
        self.database = relay_module.RelayDatabase(self.database_path, CONFIG)
        self.relay = relay_module.GitHubIssueRelay(
            self.database, self.github, mcp_factory=lambda: self.mcp
        )
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "delivered")
        self.assertEqual(len(self.github.comments), 1)
        self.assertEqual(self.github.comment_attempts, 1)

    def test_terminal_label_failure_retries_without_duplicate_comment(self):
        self.relay.process_issue(valid_issue(number=1))
        self.relay.supervise_active_jobs()
        self.github.fail_terminal_label = 1
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "pending")
        self.assertEqual(len(self.github.comments), 1)
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "delivered")
        self.assertEqual(len(self.github.comments), 1)
        self.assertEqual(self.github.comment_attempts, 1)

    def tearDown(self):
        self.database.close()
        self.temporary.cleanup()

    def test_valid_start_is_admitted_and_completed_without_capability_leak(self):
        issue = valid_issue()
        result = self.complete_issue(issue)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["publishAvailable"])
        self.assertEqual(
            self.github.statuses,
            [(1, "queued"), (1, "running"), (1, "completed")],
        )
        self.assertEqual(len(self.github.comments), 1)
        comment = self.github.comments[0][1]
        self.assertIn("BRIDGE_RESULT_V2", comment)
        self.assertNotIn(FakeMcpClient.JOB_CAPABILITY, comment)
        self.assertNotIn(FakeMcpClient.THREAD_CAPABILITY, comment)
        row = self.database.get_by_issue(1)
        self.assertEqual(row["operation"], "start")
        self.assertEqual(row["repoAlias"], "sample-alpha")
        self.assertEqual(row["workBranch"], FakeMcpClient.BRANCHES["sample-alpha"])
        self.assertEqual(row["localGuardJobCapability"], FakeMcpClient.JOB_CAPABILITY)
        self.assertEqual(row["localGuardThreadCapability"], FakeMcpClient.THREAD_CAPABILITY)

    def test_valid_bridge_start_is_admitted(self):
        result = self.complete_issue(
            valid_issue(payload=valid_payload(repo_alias="sample-beta"))
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["repoAlias"], "sample-beta")
        self.assertEqual(
            self.database.get_by_issue(1)["workBranch"],
            FakeMcpClient.BRANCHES["sample-beta"],
        )

    def test_valid_reply_uses_same_thread_worktree_and_alias(self):
        start = self.complete_issue(valid_issue(number=1))
        reply = self.complete_issue(
            valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        )
        self.assertEqual(reply["status"], "completed")
        self.assertEqual(reply["repoAlias"], "sample-alpha")
        self.assertIn("R_GH2_CONTINUITY_MARKER_824", reply["content"])
        reply_calls = [call for call in self.mcp.calls if call[0] == "codex-reply-async"]
        self.assertEqual(
            reply_calls,
            [
                (
                    "codex-reply-async",
                    {
                        "threadId": FakeMcpClient.THREADS["sample-alpha"],
                        "prompt": "What continuity marker did I give you?",
                    },
                )
            ],
        )
        row = self.database.get_by_issue(2)
        self.assertEqual(row["workBranch"], FakeMcpClient.BRANCHES["sample-alpha"])
        self.assertEqual(row["repoAlias"], "sample-alpha")
        self.assertEqual(
            row["localGuardThreadCapability"], FakeMcpClient.THREADS["sample-alpha"]
        )

    def test_unknown_and_malformed_reply_references_are_rejected(self):
        for number, relay_ref in enumerate(
            ("rjob_" + "x" * 24, "not-a-relay-reference"), start=20
        ):
            with self.subTest(relay_ref=relay_ref):
                with self.assertRaises(relay_module.AdmissionError):
                    self.relay.admit_issue(
                        valid_issue(number=number, payload=valid_reply_payload(relay_ref))
                    )

    def test_reply_forbidden_identity_fields_are_rejected(self):
        relay_ref = "rjob_" + "x" * 24
        forbidden = (
            "threadId",
            "jobId",
            "repoAlias",
            "repoPath",
            "cwd",
            "branch",
            "refspec",
            "force",
            "shell",
            "command",
            "sandbox",
            "approvalPolicy",
            "deployment",
        )
        for index, field in enumerate(forbidden, start=40):
            payload = valid_reply_payload(relay_ref)
            payload[field] = "forbidden"
            with self.subTest(field=field):
                with self.assertRaises(relay_module.AdmissionError):
                    self.relay.admit_issue(valid_issue(number=index, payload=payload))

    def test_cross_repo_mapping_tamper_is_rejected(self):
        start = self.complete_issue(valid_issue(number=1))
        self.database.connection.execute(
            "UPDATE relay_jobs SET repoAlias = 'sample-beta' WHERE issueNumber = 1"
        )
        self.database.connection.commit()
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(
                valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
            )

    def test_cross_repo_thread_capability_reuse_fails_closed(self):
        start = self.complete_issue(valid_issue(number=1))
        self.database.connection.execute(
            """
            UPDATE relay_jobs
            SET repoAlias = 'sample-beta', workBranch = ?
            WHERE issueNumber = 1
            """,
            (FakeMcpClient.BRANCHES["sample-beta"],),
        )
        self.database.connection.commit()
        reply = self.complete_issue(
            valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        )
        self.assertEqual(reply["status"], "interrupted")
        self.assertEqual(reply["repoAlias"], "sample-beta")

    def test_duplicate_reply_request_id_is_rejected(self):
        start = self.complete_issue(valid_issue(number=1))
        request_id = str(uuid.uuid4())
        self.relay.admit_issue(
            valid_issue(
                number=2,
                payload=valid_reply_payload(start["relayJobRef"], request_id),
            )
        )
        with self.assertRaises(relay_module.DuplicateRequestError):
            self.relay.admit_issue(
                valid_issue(
                    number=3,
                    payload=valid_reply_payload(start["relayJobRef"], request_id),
                )
            )

    def test_edited_reply_issue_is_not_executed_again(self):
        start = self.complete_issue(valid_issue(number=1))
        issue = valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        first_row, _, first_admitted = self.relay.admit_issue(issue)
        first_hash = first_row["bodySHA256"]
        issue["body"] = json.dumps(valid_reply_payload(start["relayJobRef"]))
        second_row, second_payload, second_admitted = self.relay.admit_issue(issue)
        self.assertTrue(first_admitted)
        self.assertFalse(second_admitted)
        self.assertIsNone(second_payload)
        self.assertEqual(second_row["bodySHA256"], first_hash)

    def test_reply_survives_relay_database_restart(self):
        start = self.complete_issue(valid_issue(number=1))
        self.database.close()
        self.database = relay_module.RelayDatabase(self.database_path, CONFIG)
        self.relay = relay_module.GitHubIssueRelay(
            self.database, self.github, mcp_factory=lambda: self.mcp
        )
        reply = self.complete_issue(
            valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        )
        self.assertEqual(reply["status"], "completed")
        self.assertEqual(
            self.database.get_by_issue(2)["localGuardThreadCapability"],
            FakeMcpClient.THREADS["sample-alpha"],
        )

    def test_revoked_reply_capability_fails_closed_without_replacement_start(self):
        start = self.complete_issue(valid_issue(number=1))
        self.mcp.revoked_threads.add(FakeMcpClient.THREADS["sample-alpha"])
        reply = self.complete_issue(
            valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        )
        self.assertEqual(reply["status"], "interrupted")
        self.assertEqual(
            len([call for call in self.mcp.calls if call[0] == "codex-repo-start"]),
            1,
        )

    def test_reply_guard_capability_in_content_fails_closed(self):
        start = self.complete_issue(valid_issue(number=1))
        original_call = self.mcp.call_tool

        def leaking_call(name, arguments):
            result = original_call(name, arguments)
            if name == "codex-job-status" and result.get("content", "").startswith(
                "R_GH2_"
            ):
                result["content"] = FakeMcpClient.THREADS["sample-alpha"]
            return result

        self.mcp.call_tool = leaking_call
        reply = self.complete_issue(
            valid_issue(number=2, payload=valid_reply_payload(start["relayJobRef"]))
        )
        self.assertEqual(reply["status"], "interrupted")
        self.assertNotIn(
            FakeMcpClient.THREADS["sample-alpha"], self.github.comments[-1][1]
        )

    def test_valid_publish_invokes_guard_publish(self):
        start = self.complete_issue(
            valid_issue(number=1, payload=valid_payload(repo_alias="sample-beta"))
        )
        publish = self.complete_issue(
            valid_issue(number=2, payload=valid_publish_payload(start["relayJobRef"]))
        )
        self.assertEqual(
            publish,
            {
                "requestId": publish["requestId"],
                "relayJobRef": start["relayJobRef"],
                "status": "completed",
                "repoAlias": "sample-beta",
                "branch": FakeMcpClient.BRANCHES["sample-beta"],
                "commit": FakeMcpClient.PUBLISH_COMMIT,
                "pushed": True,
                "baseStale": False,
            },
        )
        self.assertEqual(
            [call for call in self.mcp.calls if call[0] == "codex-repo-publish"],
            [
                (
                    "codex-repo-publish",
                    {
                        "threadId": FakeMcpClient.THREADS["sample-beta"],
                        "commitMessage": "test: prove guarded relay publish",
                    },
                )
            ],
        )

    def test_unknown_publish_reference_is_rejected(self):
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(
                valid_issue(
                    payload=valid_publish_payload("rjob_" + "x" * 24)
                )
            )

    def test_publish_forbidden_authority_fields_are_rejected(self):
        relay_ref = "rjob_" + "x" * 24
        forbidden = (
            "repoAlias",
            "branch",
            "targetBranch",
            "remote",
            "refspec",
            "force",
            "merge",
            "rebase",
            "tag",
            "pushOptions",
            "cwd",
            "repoPath",
            "shell",
            "command",
        )
        for index, field in enumerate(forbidden, start=70):
            payload = valid_publish_payload(relay_ref)
            payload[field] = "forbidden"
            with self.subTest(field=field):
                with self.assertRaises(relay_module.AdmissionError):
                    self.relay.admit_issue(valid_issue(number=index, payload=payload))

    def test_publish_commit_message_contract_is_enforced(self):
        for index, value in enumerate(("", "x" * 501, "bad\x00message"), start=90):
            payload = valid_publish_payload("rjob_" + "x" * 24)
            payload["commitMessage"] = value
            with self.subTest(value_length=len(value)):
                with self.assertRaises(relay_module.AdmissionError):
                    self.relay.admit_issue(valid_issue(number=index, payload=payload))

    def test_guard_publish_result_is_closed_and_sanitized(self):
        result = relay_module.build_publish_result(
            str(uuid.uuid4()),
            relay_module.make_relay_job_ref(),
            "completed",
            "sample-beta",
            FakeMcpClient.BRANCHES["sample-beta"],
            FakeMcpClient.PUBLISH_COMMIT,
            True,
            False,
        )
        relay_module.validate_public_result(result)
        unsafe = dict(result, threadId=FakeMcpClient.THREADS["sample-beta"])
        with self.assertRaises(relay_module.RelayError):
            relay_module.validate_public_result(unsafe)

    def test_guard_publish_capability_leak_fails_closed(self):
        start = self.complete_issue(
            valid_issue(number=1, payload=valid_payload(repo_alias="sample-beta"))
        )
        original_call = self.mcp.call_tool

        def leaking_call(name, arguments):
            result = original_call(name, arguments)
            if name == "codex-repo-publish":
                result["threadId"] = FakeMcpClient.THREADS["sample-beta"]
            return result

        self.mcp.call_tool = leaking_call
        publish = self.complete_issue(
            valid_issue(number=2, payload=valid_publish_payload(start["relayJobRef"]))
        )
        self.assertEqual(publish["status"], "failed")
        self.assertNotIn(FakeMcpClient.THREADS["sample-beta"], self.github.comments[-1][1])

    def test_wrong_repository_is_rejected(self):
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(valid_issue(), repository="example/wrong")

    def test_wrong_author_is_rejected(self):
        issue = valid_issue()
        issue["user"]["login"] = "someone-else"
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(issue)

    def test_missing_bridge_job_label_is_rejected(self):
        issue = valid_issue()
        issue["labels"] = []
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(issue)

    def test_unknown_operation_is_rejected(self):
        payload = valid_payload()
        payload["operation"] = "delete"
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(valid_issue(payload=payload))

    def test_wrong_repo_alias_is_rejected(self):
        payload = valid_payload()
        payload["repoAlias"] = "other"
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(valid_issue(payload=payload))

    def test_forbidden_and_unknown_job_fields_are_rejected(self):
        forbidden = ["cwd", "repoPath", "branch", "refspec", "force", "shell", "deploy"]
        for index, field in enumerate(forbidden, start=1):
            with self.subTest(field=field):
                payload = valid_payload()
                payload[field] = "forbidden"
                with self.assertRaises(relay_module.AdmissionError):
                    self.relay.admit_issue(valid_issue(number=index, payload=payload))

    def test_duplicate_request_id_is_rejected(self):
        request_id = str(uuid.uuid4())
        first = valid_issue(number=1, payload=valid_payload(request_id))
        second = valid_issue(number=2, payload=valid_payload(request_id))
        self.relay.admit_issue(first)
        with self.assertRaises(relay_module.DuplicateRequestError):
            self.relay.admit_issue(second)

    def test_edited_issue_is_not_executed_again(self):
        issue = valid_issue(number=7)
        first_row, _, first_admitted = self.relay.admit_issue(issue)
        first_hash = first_row["bodySHA256"]
        issue["body"] = json.dumps(valid_payload())
        second_row, second_payload, second_admitted = self.relay.admit_issue(issue)
        self.assertTrue(first_admitted)
        self.assertFalse(second_admitted)
        self.assertIsNone(second_payload)
        self.assertEqual(second_row["bodySHA256"], first_hash)

    def test_oversized_prompt_is_rejected(self):
        payload = valid_payload()
        payload["prompt"] = "x" * (relay_module.PROMPT_MAX_CHARS + 1)
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(valid_issue(payload=payload))

    def test_multibyte_prompt_over_256_kib_is_rejected(self):
        payload = valid_payload()
        payload["prompt"] = "界" * (relay_module.PROMPT_MAX_CHARS // 2)
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(valid_issue(payload=payload))

    def test_guard_capability_in_result_is_rejected(self):
        capability = "guard-job-capability-secret"
        with self.assertRaises(relay_module.ResultSecurityError):
            relay_module.build_public_result(
                str(uuid.uuid4()),
                relay_module.make_relay_job_ref(),
                "completed",
                "unsafe " + capability,
                capabilities=(capability,),
            repo_alias="sample-alpha")

    def test_absolute_local_path_in_result_is_rejected(self):
        with self.assertRaises(relay_module.ResultSecurityError):
            relay_module.build_public_result(
                str(uuid.uuid4()),
                relay_module.make_relay_job_ref(),
                "completed",
                "workspace=/Users/test-user/private/repo",
            repo_alias="sample-alpha")

    def test_unknown_result_field_is_rejected(self):
        payload = relay_module.build_public_result(
            str(uuid.uuid4()),
            relay_module.make_relay_job_ref(),
            "completed",
            "GitStatus=clean",
        repo_alias="sample-alpha")
        payload["branch"] = "main"
        with self.assertRaises(relay_module.RelayError):
            relay_module.validate_public_result(payload)

    def test_result_content_is_truncated_to_contract_limit(self):
        payload = relay_module.build_public_result(
            str(uuid.uuid4()),
            relay_module.make_relay_job_ref(),
            "completed",
            "x" * (relay_module.CONTENT_MAX_CHARS + 1),
        repo_alias="sample-alpha")
        self.assertEqual(len(payload["content"]), relay_module.CONTENT_MAX_CHARS)
        self.assertTrue(payload["contentTruncated"])

    def test_body_parse_ambiguity_is_rejected(self):
        issue = valid_issue()
        issue["body"] = issue["body"] + "\nextra"
        with self.assertRaises(relay_module.AdmissionError):
            self.relay.admit_issue(issue)

    def test_database_is_regular_mode_0600(self):
        metadata = self.database_path.lstat()
        self.assertTrue(stat.S_ISREG(metadata.st_mode))
        self.assertFalse(self.database_path.is_symlink())
        self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600)

    def test_database_rejects_unknown_delivery_state(self):
        self.relay.admit_issue(valid_issue(number=1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE relay_jobs SET deliveryState = 'unknown' WHERE issueNumber = 1"
            )
        self.database.connection.rollback()

    def test_job_schema_is_closed_and_has_required_limits(self):
        schema_path = REPO_ROOT / "docs" / "specs" / "github-relay" / "job-schema-v1.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["oneOf"],
            [
                {"$ref": "#/$defs/start"},
                {"$ref": "#/$defs/reply"},
                {"$ref": "#/$defs/publish"},
                {"$ref": "#/$defs/query"},
                {"$ref": "#/$defs/review"},
            ],
        )
        start = schema["$defs"]["start"]
        reply = schema["$defs"]["reply"]
        publish = schema["$defs"]["publish"]
        for branch in (start, reply, publish):
            self.assertFalse(branch["additionalProperties"])
        self.assertEqual(start["properties"]["operation"]["const"], "start")
        self.assertEqual(start["properties"]["repoAlias"]["pattern"], "^[a-z][a-z0-9-]{0,62}$")
        self.assertEqual(start["properties"]["taskName"]["maxLength"], 120)
        self.assertEqual(start["properties"]["prompt"]["maxLength"], 256 * 1024)
        self.assertEqual(reply["properties"]["operation"]["const"], "reply")
        self.assertEqual(publish["properties"]["operation"]["const"], "publish")
        self.assertEqual(publish["properties"]["commitMessage"]["maxLength"], 500)
        for forbidden in (
            "cwd",
            "repoPath",
            "path",
            "remote",
            "branch",
            "refspec",
            "force",
            "shell",
            "command",
            "executable",
            "deploy",
            "targetName",
            "environment",
            "approvalPolicy",
            "sandbox",
        ):
            self.assertNotIn(forbidden, reply["properties"])
            self.assertNotIn(forbidden, publish["properties"])

    def test_mcp_client_refuses_local_runtime_tools(self):
        client = relay_module.GuardMcpClient()
        for name in (
            "codex-repo-run-local",
            "codex-repo-stop-local",
        ):
            with self.subTest(name=name):
                with self.assertRaises(relay_module.RelayError):
                    client.call_tool(name, {})

    def test_mcp_client_bounds_repo_start_to_guard_fetch_window(self):
        client = relay_module.GuardMcpClient(timeout=60)
        calls = []

        def request(method, params, timeout=None):
            calls.append((method, params, timeout))
            return {"structuredContent": {"status": "queued"}}

        client._request = request
        client.call_tool("codex-repo-start", {"repoAlias": "sample-alpha"})
        client.call_tool("codex-job-status", {"jobId": "local-capability"})

        self.assertEqual(calls[0][2], relay_module.REPO_START_TIMEOUT_SECONDS)
        self.assertIsNone(calls[1][2])

    def test_github_result_comment_scan_trusts_only_fixed_author(self):
        client = relay_module.GitHubClient(config=CONFIG)
        client._api = lambda method, endpoint: [
            {
                "user": {"login": "someone-else"},
                "body": "BRIDGE_RESULT_V1\nforged",
            },
            {
                "user": {"login": "fixture-owner"},
                "body": "BRIDGE_RESULT_V1\ntrusted",
            },
            {"user": {"login": "fixture-owner"}, "body": "ordinary comment"},
        ]
        self.assertEqual(
            client.result_comments(1), ["BRIDGE_RESULT_V1\ntrusted"]
        )

    def test_relay_source_has_no_direct_git_publish_implementation(self):
        source = RELAY_PATH.read_text(encoding="utf-8").lower()
        for forbidden in (
            "git push",
            "git merge",
            "git rebase",
            "git tag",
            "git checkout main",
        ):
            self.assertNotIn(forbidden, source)

    def test_rgh1_database_migrates_transactionally(self):
        legacy_path = Path(self.temporary.name) / "legacy.sqlite3"
        connection = sqlite3.connect(str(legacy_path))
        connection.execute(
            """
            CREATE TABLE relay_jobs (
                requestId TEXT PRIMARY KEY,
                issueNumber INTEGER NOT NULL UNIQUE,
                bodySHA256 TEXT NOT NULL,
                relayJobRef TEXT NOT NULL UNIQUE,
                localGuardJobCapability TEXT,
                localGuardThreadCapability TEXT,
                status TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        values = (
            str(uuid.uuid4()),
            300,
            "b" * 64,
            "rjob_" + "y" * 24,
            FakeMcpClient.JOB_CAPABILITY,
            FakeMcpClient.THREAD_CAPABILITY,
            "completed",
            relay_module.utc_now(),
            relay_module.utc_now(),
        )
        connection.execute(
            "INSERT INTO relay_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values
        )
        connection.commit()
        connection.close()
        os.chmod(legacy_path, 0o600)
        before = legacy_path.read_bytes()
        with self.assertRaisesRegex(relay_module.RelayError, 'OPERATOR_MIGRATION_REQUIRED'):
            relay_module.RelayDatabase(legacy_path, CONFIG)
        self.assertEqual(legacy_path.read_bytes(), before)

    def test_v2_requires_operator_migration_without_changes(self):
        legacy_path = Path(self.temporary.name) / "legacy-v2.sqlite3"
        request_id = str(uuid.uuid4())
        relay_ref = "rjob_" + "z" * 24
        job_capability = "guard-job-legacy-capability-secret"
        connection = sqlite3.connect(str(legacy_path))
        connection.execute(
            """
            CREATE TABLE relay_jobs (
                requestId TEXT PRIMARY KEY,
                issueNumber INTEGER NOT NULL UNIQUE,
                bodySHA256 TEXT NOT NULL,
                operation TEXT NOT NULL,
                relayJobRef TEXT NOT NULL,
                repoAlias TEXT NOT NULL,
                workBranch TEXT,
                localGuardJobCapability TEXT,
                localGuardThreadCapability TEXT,
                status TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX relay_start_ref_unique
            ON relay_jobs(relayJobRef) WHERE operation = 'start'
            """
        )
        connection.execute(
            "INSERT INTO relay_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                315,
                "c" * 64,
                "start",
                relay_ref,
                "sample-beta",
                FakeMcpClient.BRANCHES["sample-beta"],
                job_capability,
                FakeMcpClient.THREADS["sample-beta"],
                "completed",
                relay_module.utc_now(),
                relay_module.utc_now(),
            ),
        )
        active_request_id = str(uuid.uuid4())
        active_job_capability = "guard-job-active-capability-secret"
        connection.execute(
            "INSERT INTO relay_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                active_request_id,
                316,
                "d" * 64,
                "start",
                "rjob_" + "w" * 24,
                "sample-beta",
                FakeMcpClient.BRANCHES["sample-beta"],
                active_job_capability,
                FakeMcpClient.THREADS["sample-beta"],
                "running",
                relay_module.utc_now(),
                relay_module.utc_now(),
            ),
        )
        connection.execute("PRAGMA user_version=2")
        connection.commit()
        connection.close()
        os.chmod(legacy_path, 0o600)
        before = legacy_path.read_bytes()
        with self.assertRaisesRegex(relay_module.RelayError, 'OPERATOR_MIGRATION_REQUIRED'):
            relay_module.RelayDatabase(legacy_path, CONFIG)
        self.assertEqual(legacy_path.read_bytes(), before)

    def test_legacy_exact_comment_is_acknowledged_without_duplication(self):
        row, _, _ = self.relay.admit_issue(valid_issue(number=1))
        result = relay_module.build_public_result(
            row["requestId"],
            row["relayJobRef"],
            "completed",
            "ALREADY_DELIVERED",
            repo_alias=row["repoAlias"],
        )
        body = "BRIDGE_RESULT_V1\n\n```json\n{}\n```".format(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        self.assertNotEqual(body, relay_module.format_result_comment(result))
        self.github.comments.append((1, body))
        self.database.connection.execute(
            """
            UPDATE relay_jobs
            SET status = 'completed', deliveryState = 'legacy'
            WHERE issueNumber = 1
            """
        )
        self.database.connection.commit()
        self.relay.reconcile_legacy_results()
        self.relay.deliver_pending_results()
        self.assertEqual(self.database.get_by_issue(1)["deliveryState"], "delivered")
        self.assertEqual(self.github.comments, [(1, body)])
        self.assertEqual(self.github.comment_attempts, 0)

    def test_launchagent_restarts_only_after_failure(self):
        installer = (
            REPO_ROOT / "scripts" / "relay" / "install-github-relay-macos.zsh"
        ).read_text(encoding="utf-8")
        self.assertIn('"KeepAlive": {"SuccessfulExit": False}', installer)
        self.assertIn('"ThrottleInterval": 15', installer)


if __name__ == "__main__":
    unittest.main()
