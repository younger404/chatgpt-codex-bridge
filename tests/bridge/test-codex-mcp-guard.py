#!/usr/bin/python3

import json
import base64
import hashlib
import hmac
import importlib.util
import os
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "bridge" / "codex-mcp-guard.py"
SYSTEM_PYTHON = "/usr/bin/python3"
SAFETY_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}
READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


FAKE_CODEX_SOURCE = r'''#!/usr/bin/python3
import json
import os
import sys

SCENARIO = __SCENARIO__
STATE_PATH = __file__ + ".state.json"

CODEX_SCHEMA = {
    "additionalProperties": False,
    "properties": {
        "approval-policy": {
            "type": "string",
            "enum": ["untrusted", "on-request", "never"],
        },
        "base-instructions": {"type": "string"},
        "compact-prompt": {"type": "string"},
        "config": {"type": "object", "additionalProperties": True},
        "cwd": {"type": "string"},
        "developer-instructions": {"type": "string"},
        "model": {"type": "string"},
        "prompt": {"type": "string"},
        "sandbox": {
            "type": "string",
            "enum": ["read-only", "workspace-write", "danger-full-access"],
        },
    },
    "required": ["prompt"],
    "type": "object",
}

REPLY_SCHEMA = {
    "properties": {
        "conversationId": {"type": "string"},
        "prompt": {"type": "string"},
        "threadId": {"type": "string"},
    },
    "required": ["prompt"],
    "type": "object",
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "threadId": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["threadId", "content"],
}


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def tools():
    codex_schema = json.loads(json.dumps(CODEX_SCHEMA))
    if SCENARIO == "current_approval_policy":
        codex_schema["properties"]["approval-policy"]["enum"] = [
            "on-request",
            "never",
        ]
    if SCENARIO == "schema_drift":
        del codex_schema["properties"]["cwd"]
    if SCENARIO == "additive_schema_drift":
        codex_schema["properties"]["network-access"] = {
            "type": "string",
            "enum": ["enabled", "disabled"],
        }
    result = [
        {
            "name": "codex",
            "title": "Codex",
            "description": "Raw Codex test tool",
            "inputSchema": codex_schema,
            "outputSchema": OUTPUT_SCHEMA,
        },
        {
            "name": "codex-reply",
            "title": "Codex Reply",
            "description": "Raw Codex reply test tool",
            "inputSchema": REPLY_SCHEMA,
            "outputSchema": OUTPUT_SCHEMA,
        },
    ]
    if SCENARIO == "extra_tool":
        result.append({
            "name": "unexpected",
            "inputSchema": {"type": "object"},
        })
    return result


SECRET_NAMES = {
    "BRIDGE_TEST_SECRET",
    "OPENAI_API_KEY",
    "CONTROL_PLANE_API_KEY",
    "TUNNEL_TOKEN",
    "CODEX_PRIVATE",
    "SSH_AUTH_SOCK",
}


def tool_result(request_id, name, arguments, call_count):
    thread_id = "thread-local-1" if name == "codex" else arguments["threadId"]
    secret_seen = any(name in os.environ for name in SECRET_NAMES)
    diagnostics = {
        "receivedArguments": arguments,
        "callCount": call_count,
        "secretSeen": secret_seen,
        "homeSeen": bool(os.environ.get("HOME")),
    }
    with open(STATE_PATH, "w", encoding="utf-8") as state_file:
        json.dump(diagnostics, state_file, separators=(",", ":"))
    structured = {
        "threadId": thread_id,
        "content": "ok",
        **diagnostics,
    }
    emit({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": structured,
        },
    })


if len(sys.argv) >= 2 and sys.argv[1] == "app-server":
    if SCENARIO == "async_malformed":
        print("not-json", flush=True)
        sys.exit(0)

    requests = []
    requested_cwd = ""
    prompt = ""
    thread_id = ""
    project_id = ""
    project_name = ""
    project_roots = []

    def save_app_server_state():
        with open(STATE_PATH, "w", encoding="utf-8") as state_file:
            json.dump({
                "argv": sys.argv[1:],
                "requests": requests,
                "prompt": prompt,
                "processCwd": os.getcwd(),
                "requestedCwd": requested_cwd,
                "projectId": project_id,
                "projectName": project_name,
                "projectRoots": project_roots,
            }, state_file, ensure_ascii=False, separators=(",", ":"))

    for raw_line in sys.stdin:
        message = json.loads(raw_line)
        requests.append(message)
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            emit({
                "id": message["id"],
                "result": {"userAgent": "fake-codex-app-server/1.0"},
            })
        elif method == "initialized":
            pass
        elif method == "project/create":
            if SCENARIO == "async_project_api_missing":
                emit({
                    "id": message["id"],
                    "error": {"code": -32601, "message": "method not found"},
                })
                continue
            project_id = "project-async-1"
            project_name = params.get("name", "")
            project_roots = params.get("roots", [])
            emit({
                "id": message["id"],
                "result": {
                    "project": {
                        "id": project_id,
                        "name": project_name,
                        "roots": project_roots,
                        "metadata": params.get("metadata") or {},
                        "position": 1,
                        "createdAt": 1,
                        "updatedAt": 1,
                    }
                },
            })
        elif method in ("thread/start", "thread/resume"):
            requested_cwd = params.get("cwd", "")
            thread_id = params.get("threadId") or "thread-async-1"
            requested_project_id = params.get("projectId") or "project-async-1"
            project_id = requested_project_id
            response_cwd = requested_cwd
            if SCENARIO == "async_wrong_cwd":
                response_cwd = os.path.dirname(requested_cwd)
            response_project_id = project_id
            if SCENARIO == "async_project_mismatch":
                response_project_id = "project-wrong"
            source = "vscode"
            if SCENARIO == "async_non_sidebar" or (
                SCENARIO == "resume_exec_source" and method == "thread/resume"
            ):
                source = "exec"
            emit({
                "id": message["id"],
                "result": {
                    "thread": {
                        "id": thread_id,
                        "cwd": response_cwd,
                        "projectId": response_project_id,
                        "source": source,
                        "status": {"type": "idle"},
                    }
                },
            })
        elif method == "project/list":
            emit({
                "id": message["id"],
                "result": {
                    "data": [{
                        "id": project_id,
                        "name": project_name,
                        "roots": project_roots,
                        "metadata": {},
                        "position": 1,
                        "createdAt": 1,
                        "updatedAt": 1,
                    }],
                    "nextCursor": None,
                },
            })
        elif method == "thread/list":
            emit({
                "id": message["id"],
                "result": {
                    "data": [{
                        "id": thread_id,
                        "cwd": requested_cwd,
                        "projectId": project_id,
                        "source": "vscode",
                        "status": {"type": "idle"},
                    }],
                    "nextCursor": None,
                },
            })
        elif method == "thread/name/set":
            emit({"id": message["id"], "result": {}})
        elif method == "turn/start":
            requested_cwd = params.get("cwd", requested_cwd)
            text_inputs = [
                item.get("text", "")
                for item in params.get("input", [])
                if item.get("type") == "text"
            ]
            prompt = "\n".join(text_inputs)
            skill_inputs = [
                item
                for item in params.get("input", [])
                if item.get("type") == "skill"
            ]
            if (
                SCENARIO != "async_no_scaffold"
                and requested_cwd
                and "$workspace-new-project" in prompt
                and "--here" in prompt
                and any(
                    item.get("name") == "workspace-new-project"
                    and item.get("path", "").endswith(
                        "/workspace-new-project/SKILL.md"
                    )
                    for item in skill_inputs
                )
            ):
                for directory in (
                    ".project-memory",
                    "docs/specs",
                    "docs/adr",
                    "src",
                ):
                    os.makedirs(os.path.join(requested_cwd, directory), exist_ok=True)
                for filename in ("AGENTS.md", "README.md", ".gitignore"):
                    with open(
                        os.path.join(requested_cwd, filename),
                        "w",
                        encoding="utf-8",
                    ) as marker:
                        marker.write("fixture\n")
            save_app_server_state()
            emit({
                "id": message["id"],
                "result": {
                    "turn": {
                        "id": "turn-async-1",
                        "items": [],
                        "status": "inProgress",
                        "error": None,
                    }
                },
            })
            if SCENARIO == "async_foreign_turns":
                for event_thread_id, event_turn_id, event_text in (
                    (
                        "thread-child-review-1",
                        "turn-child-review-1",
                        "child provider review must not finish root",
                    ),
                    (
                        thread_id,
                        "turn-unrelated-1",
                        "same-thread unrelated turn must not finish root",
                    ),
                ):
                    emit({
                        "method": "item/completed",
                        "params": {
                            "threadId": event_thread_id,
                            "turnId": event_turn_id,
                            "item": {
                                "type": "agentMessage",
                                "id": "message-" + event_turn_id,
                                "text": event_text,
                                "phase": "final_answer",
                            },
                        },
                    })
                    emit({
                        "method": "turn/completed",
                        "params": {
                            "threadId": event_thread_id,
                            "turn": {
                                "id": event_turn_id,
                                "items": [],
                                "status": "completed",
                                "error": None,
                            },
                        },
                    })
            if SCENARIO == "async_block":
                import time
                time.sleep(60)
            if SCENARIO == "async_slow":
                import time
                time.sleep(0.35)
            status = "failed" if SCENARIO == "async_fail" else "completed"
            content = "async ok: " + prompt
            emit({
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": "turn-async-1",
                    "item": {
                        "type": "agentMessage",
                        "id": "message-async-1",
                        "text": content,
                        "phase": "final_answer",
                    },
                },
            })
            emit({
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": {
                        "id": "turn-async-1",
                        "items": [],
                        "status": status,
                        "error": (
                            {"message": "fixture failure"}
                            if status == "failed"
                            else None
                        ),
                    },
                },
            })
        else:
            emit({"id": message.get("id"), "result": {}})
        save_app_server_state()
    sys.exit(0)


if len(sys.argv) != 2 or sys.argv[1] != "mcp-server":
    sys.exit(64)
if SCENARIO == "early_exit":
    sys.exit(23)

call_count = 0
initialize_count = 0
pending_approval = None
for raw_line in sys.stdin:
    if SCENARIO == "malformed_json":
        sys.stdout.write("not-json\n")
        sys.stdout.flush()
        sys.exit(0)

    message = json.loads(raw_line)
    if pending_approval is not None and message.get("id") == pending_approval["approval_id"] and "method" not in message:
        tool_result(
            pending_approval["id"],
            pending_approval["name"],
            pending_approval["arguments"],
            pending_approval["call_count"],
        )
        pending_approval = None
        continue

    method = message.get("method")
    if method == "initialize":
        initialize_count += 1
        if initialize_count > 1:
            emit({
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": -32600,
                    "message": "initialize called more than once",
                },
            })
        else:
            emit({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "fake-codex", "version": "1.0"},
                },
            })
    elif method == "tools/list":
        emit({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"tools": tools()},
        })
    elif method == "tools/call":
        call_count += 1
        name = message["params"]["name"]
        arguments = message["params"]["arguments"]
        if SCENARIO in ("approval", "approval_same_id"):
            approval_id = message["id"] if SCENARIO == "approval_same_id" else "child-approval-1"
            pending_approval = {
                "id": message["id"],
                "name": name,
                "arguments": arguments,
                "call_count": call_count,
                "approval_id": approval_id,
            }
            emit({
                "jsonrpc": "2.0",
                "id": approval_id,
                "method": "elicitation/create",
                "params": {"message": "approve test"},
            })
        elif SCENARIO == "sync_slow":
            import time
            time.sleep(0.35)
            tool_result(message["id"], name, arguments, call_count)
        else:
            tool_result(message["id"], name, arguments, call_count)
    elif method == "notifications/initialized":
        pass
    else:
        emit({"jsonrpc": "2.0", "id": message.get("id"), "result": {"echo": message}})
'''


FAKE_DESKTOP_OPEN_SOURCE = r'''#!/usr/bin/python3
import json
import sys

with open(__file__ + ".state.json", "w", encoding="utf-8") as state_file:
    json.dump({"argv": sys.argv[1:]}, state_file, separators=(",", ":"))
sys.exit(__EXIT_CODE__)
'''


class GuardHarness:
    def __init__(
        self,
        test_case,
        root,
        scenario="normal",
        sandbox=None,
        approval_policy=None,
        job_state_dir=None,
        job_wait_seconds=0.05,
        desktop_open_exit_code=0,
        explicit_workspace_skill=None,
        max_active_jobs=None,
        max_retained_jobs=None,
        job_max_seconds=None,
        sync_max_seconds=None,
    ):
        self.test_case = test_case
        self.root = root
        self.workspace = root / "workspace"
        self.workspace.mkdir(exist_ok=True)
        self.sandbox = sandbox or "danger-full-access"
        self.approval_policy = approval_policy or "never"
        self.job_state_dir = Path(job_state_dir or (root / "jobs"))
        self.home = root / "home"
        self.skill_path = (
            self.home
            / ".codex"
            / "skills"
            / "workspace-new-project"
            / "SKILL.md"
        )
        self.skill_path.parent.mkdir(parents=True, exist_ok=True)
        self.skill_path.write_text(
            "---\nname: workspace-new-project\n---\n# Test skill\n",
            encoding="utf-8",
        )
        self.fake_codex = root / ("fake-codex-" + scenario)
        source = FAKE_CODEX_SOURCE.replace("__SCENARIO__", repr(scenario))
        self.fake_codex.write_text(source, encoding="utf-8")
        self.fake_codex.chmod(self.fake_codex.stat().st_mode | stat.S_IXUSR)
        self.fake_desktop_open = root / "fake-desktop-open"
        self.fake_desktop_open.write_text(
            FAKE_DESKTOP_OPEN_SOURCE.replace(
                "__EXIT_CODE__", str(desktop_open_exit_code)
            ),
            encoding="utf-8",
        )
        self.fake_desktop_open.chmod(
            self.fake_desktop_open.stat().st_mode | stat.S_IXUSR
        )
        command = [
            SYSTEM_PYTHON,
            str(GUARD),
            "--workspace",
            str(self.workspace),
            "--codex-bin",
            str(self.fake_codex),
            "--job-state-dir",
            str(self.job_state_dir),
            "--desktop-open-bin",
            str(self.fake_desktop_open),
            "--job-wait-seconds",
            str(job_wait_seconds),
        ]
        if explicit_workspace_skill is not None:
            command.extend([
                "--workspace-new-project-skill",
                str(explicit_workspace_skill),
            ])
        if max_active_jobs is not None:
            command.extend(["--max-active-jobs", str(max_active_jobs)])
        if max_retained_jobs is not None:
            command.extend(["--max-retained-jobs", str(max_retained_jobs)])
        if job_max_seconds is not None:
            command.extend(["--job-max-seconds", str(job_max_seconds)])
        if sync_max_seconds is not None:
            command.extend(["--sync-max-seconds", str(sync_max_seconds)])
        if sandbox is not None:
            command.extend(["--sandbox", sandbox])
        if approval_policy is not None:
            command.extend(["--approval-policy", approval_policy])
        environment = dict(os.environ)
        environment.update({
            "HOME": str(self.home),
            "BRIDGE_TEST_SECRET": "test-secret-value",
            "OPENAI_API_KEY": "test-openai-key",
            "CONTROL_PLANE_API_KEY": "test-control-plane-key",
            "TUNNEL_TOKEN": "test-tunnel-token",
            "CODEX_PRIVATE": "test-codex-private",
            "SSH_AUTH_SOCK": "/tmp/test-ssh-agent.sock",
        })
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )
        self.stdout_messages = []

    def send(self, message):
        if self.process.stdin is None:
            raise AssertionError("guard stdin unavailable")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout=15.0):
        if self.process.stdout is None:
            raise AssertionError("guard stdout unavailable")
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            stderr = self.stderr_if_exited()
            raise AssertionError("timed out waiting for guard JSON-RPC; stderr=" + stderr)
        line = self.process.stdout.readline()
        if not line:
            stderr = self.stderr_if_exited()
            raise AssertionError("guard stdout closed; stderr=" + stderr)
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            raise AssertionError("guard stdout was not JSON: " + line) from error
        self.stdout_messages.append(message)
        return message

    def receive_stderr_json(self, timeout=5.0):
        if self.process.stderr is None:
            raise AssertionError("guard stderr unavailable")
        ready, _, _ = select.select([self.process.stderr], [], [], timeout)
        if not ready:
            raise AssertionError("timed out waiting for guard diagnostic")
        line = self.process.stderr.readline()
        if not line:
            raise AssertionError("guard stderr closed")
        try:
            return json.loads(line)
        except json.JSONDecodeError as error:
            raise AssertionError("guard stderr diagnostic was not JSON: " + line) from error

    def initialize(self, list_tools=True):
        self.send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "guard-test", "version": "1.0"},
            },
        })
        initialized = self.receive()
        self.test_case.assertEqual(initialized["id"], 1)
        self.test_case.assertIn("result", initialized)
        self.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        if not list_tools:
            return None
        self.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        return self.receive()

    def call(self, request_id, name, arguments):
        self.send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        return self.receive()

    def read_child_state(self):
        state_path = Path(str(self.fake_codex) + ".state.json")
        return json.loads(state_path.read_text(encoding="utf-8"))

    def read_desktop_open_state(self):
        state_path = Path(str(self.fake_desktop_open) + ".state.json")
        return json.loads(state_path.read_text(encoding="utf-8"))

    def capability(self, audience, raw_identifier):
        key = (self.job_state_dir / "capability.key").read_bytes()
        context_payload = json.dumps({
            "approvalPolicy": self.approval_policy,
            "sandbox": self.sandbox,
            "schemaVersion": 2,
            "workspace": str(self.workspace),
        }, sort_keys=True, separators=(",", ":"))
        context = base64.urlsafe_b64encode(
            hashlib.sha256(context_payload.encode("utf-8")).digest()
        ).rstrip(b"=").decode("ascii")
        encoded = base64.urlsafe_b64encode(raw_identifier.encode("utf-8")).rstrip(b"=").decode("ascii")
        signed = f"cgb2.{audience}.{context}.{encoded}".encode("ascii")
        signature = base64.urlsafe_b64encode(
            hmac.new(key, signed, hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        return signed.decode("ascii") + "." + signature

    def job_directories(self):
        result = []
        if not self.job_state_dir.is_dir():
            return result
        for path in self.job_state_dir.iterdir():
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                parsed = uuid.UUID(path.name)
            except ValueError:
                continue
            if str(parsed) == path.name:
                result.append(path)
        return result

    def job_dir_for(self, public_job_id):
        for path in self.job_directories():
            status_path = path / "status.json"
            if not status_path.is_file():
                continue
            state = json.loads(status_path.read_text(encoding="utf-8"))
            if state.get("jobId") == public_job_id:
                return path
        raise AssertionError("public job capability has no durable directory")

    def write_job_fixture(self, internal_job_id, status, **extra):
        public_job_id = self.capability("job", internal_job_id)
        job_dir = self.job_state_dir / internal_job_id
        job_dir.mkdir(parents=True, mode=0o700)
        state = {
            "jobId": public_job_id,
            "internalJobId": internal_job_id,
            "status": status,
            "content": extra.pop("content", "fixture"),
            "contentTruncated": False,
            "updatedAt": time.time(),
            **extra,
        }
        status_path = job_dir / "status.json"
        status_path.write_text(json.dumps(state), encoding="utf-8")
        status_path.chmod(0o600)
        return public_job_id, job_dir, status_path

    def wait_exit(self, timeout=3.0):
        return self.process.wait(timeout=timeout)

    def stderr_if_exited(self):
        if self.process.poll() is None or self.process.stderr is None:
            return ""
        return self.process.stderr.read()

    def stop(self):
        if self.process.poll() is None:
            if self.process.stdin is not None:
                try:
                    self.process.stdin.close()
                except BrokenPipeError:
                    pass
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
        for stream in (
            self.process.stdin,
            self.process.stdout,
            self.process.stderr,
        ):
            if stream is not None and not stream.closed:
                stream.close()


class ExistingStorePreservationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="guard-preservation-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        spec = importlib.util.spec_from_file_location("guard_preservation_test", GUARD)
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)

    def snapshot(self, path):
        info = path.lstat()
        fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_size",
                  "st_nlink", "st_mtime_ns", "st_ctime_ns")
        return tuple(getattr(info, name) for name in fields)

    def existing_key(self, root=None):
        key = (root or self.root) / "capability.key"
        key.write_bytes(b"k" * 32)
        key.chmod(0o600)
        return key

    def store(self, root):
        return self.guard.JobStore(str(root), "/usr/bin/false", str(self.root),
                                   "workspace-write", "never", "/usr/bin/false")

    def test_existing_key_preserves_metadata_and_capabilities(self):
        key = self.existing_key()
        before = self.snapshot(key)
        with mock.patch.object(self.guard.os, "chmod") as chmod:
            codec = self.guard.CapabilityCodec(key)
            chmod.assert_not_called()
        self.assertEqual(codec.key, b"k" * 32)
        token = codec.encode("thread", "synthetic-thread")
        reloaded = self.guard.CapabilityCodec(key)
        self.assertEqual(reloaded.decode("thread", token), "synthetic-thread")
        self.assertEqual(key.read_bytes(), b"k" * 32)
        self.assertEqual(self.snapshot(key), before)

    def test_noncompliant_key_mode_and_size_are_not_repaired(self):
        key = self.existing_key()
        for mode, size in ((0o644, 32), (0o600, 31)):
            with self.subTest(mode=mode, size=size):
                key.write_bytes(b"k" * size)
                key.chmod(mode)
                before = self.snapshot(key)
                with self.assertRaises(self.guard.GuardConfigurationError):
                    self.guard.CapabilityCodec(key)
                self.assertEqual(self.snapshot(key), before)
                self.assertEqual(key.read_bytes(), b"k" * size)

    def test_symlink_and_hardlink_keys_are_rejected_unchanged(self):
        target = self.existing_key()
        for name, link in (("symlink", os.symlink), ("hardlink", os.link)):
            with self.subTest(kind=name):
                alias = self.root / name
                link(target, alias)
                before = self.snapshot(target), self.snapshot(alias)
                with self.assertRaises(self.guard.GuardConfigurationError):
                    self.guard.CapabilityCodec(alias)
                self.assertEqual((self.snapshot(target), self.snapshot(alias)), before)

    def test_wrong_owner_key_is_rejected_unchanged(self):
        key = self.existing_key()
        before = self.snapshot(key)
        with mock.patch.object(self.guard.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(self.guard.GuardConfigurationError):
                self.guard.CapabilityCodec(key)
        self.assertEqual(self.snapshot(key), before)

    def test_existing_root_and_key_preserve_metadata(self):
        root = self.root / "store"
        root.mkdir(mode=0o700)
        key = self.existing_key(root)
        before = self.snapshot(root), self.snapshot(key)
        with mock.patch.object(self.guard.os, "chmod") as chmod:
            self.store(root)
            chmod.assert_not_called()
        self.store(root)
        self.assertEqual((self.snapshot(root), self.snapshot(key)), before)

    def test_existing_wrong_mode_root_is_rejected_unchanged(self):
        root = self.root / "store"
        root.mkdir(mode=0o755)
        root.chmod(0o755)
        before = self.snapshot(root)
        with self.assertRaises(self.guard.GuardConfigurationError):
            self.store(root)
        self.assertEqual(self.snapshot(root), before)
        self.assertEqual(list(root.iterdir()), [])

    def test_existing_wrong_owner_and_symlink_root_are_rejected(self):
        root = self.root / "store"
        root.mkdir(mode=0o700)
        before = self.snapshot(root)
        with mock.patch.object(self.guard.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(self.guard.GuardConfigurationError):
                self.store(root)
        alias = self.root / "alias"
        alias.symlink_to(root)
        with self.assertRaises(self.guard.GuardConfigurationError):
            self.store(alias)
        self.assertEqual(self.snapshot(root), before)
        self.assertEqual(list(root.iterdir()), [])

    def test_new_root_and_key_initialize_under_restrictive_umask(self):
        root = self.root / "new-store"
        previous = os.umask(0o777)
        try:
            store = self.store(root)
        finally:
            os.umask(previous)
        key = root / "capability.key"
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        self.assertEqual(key.stat().st_nlink, 1)
        self.assertEqual(len(store.capabilities.key), 32)
        self.assertEqual(key.read_bytes(), store.capabilities.key)

    def test_source_and_plugin_mirror_are_byte_identical(self):
        mirror = REPO_ROOT / "plugins/chatgpt-codex-bridge/bridge/codex-mcp-guard.py"
        self.assertEqual(GUARD.read_bytes(), mirror.read_bytes())


class CodexMcpGuardContractTest(unittest.TestCase):
    def setUp(self):
        raw_root = tempfile.mkdtemp(prefix="chatgpt-code-guard.", dir="/tmp")
        self.root = Path(os.path.realpath(raw_root))
        self.harnesses = []

    def tearDown(self):
        for harness in self.harnesses:
            harness.stop()
        parent = self.root.parent
        if parent not in (Path("/tmp"), Path("/private/tmp")):
            raise AssertionError("refusing unsafe test cleanup parent")
        if not self.root.name.startswith("chatgpt-code-guard."):
            raise AssertionError("refusing unsafe test cleanup name")
        if self.root.is_symlink():
            raise AssertionError("refusing symlink test cleanup")
        if self.root.exists():
            shutil.rmtree(str(self.root))

    def harness(
        self,
        scenario="normal",
        sandbox=None,
        approval_policy=None,
        job_state_dir=None,
        job_wait_seconds=0.05,
        desktop_open_exit_code=0,
        explicit_workspace_skill=None,
        max_active_jobs=None,
        max_retained_jobs=None,
        job_max_seconds=None,
        sync_max_seconds=None,
    ):
        case_root = self.root / (scenario + "-" + str(len(self.harnesses)))
        case_root.mkdir()
        harness = GuardHarness(
            self,
            case_root,
            scenario,
            sandbox=sandbox,
            approval_policy=approval_policy,
            job_state_dir=job_state_dir,
            job_wait_seconds=job_wait_seconds,
            desktop_open_exit_code=desktop_open_exit_code,
            explicit_workspace_skill=explicit_workspace_skill,
            max_active_jobs=max_active_jobs,
            max_retained_jobs=max_retained_jobs,
            job_max_seconds=job_max_seconds,
            sync_max_seconds=sync_max_seconds,
        )
        self.harnesses.append(harness)
        return harness

    def test_tools_list_exposes_only_truthfully_annotated_narrow_tools(self):
        harness = self.harness()
        response = harness.initialize()
        tools = response["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "codex",
                "codex-reply",
                "codex-start",
                "codex-reply-async",
                "codex-wait",
                "codex-job-open",
                "codex-job-status",
            ],
        )
        for tool in tools[:4]:
            self.assertEqual(tool["annotations"], SAFETY_ANNOTATIONS)
        for tool in tools[4:]:
            self.assertEqual(tool["annotations"], READ_ONLY_ANNOTATIONS)
        self.assertEqual(tools[4]["_meta"]["ui"]["visibility"], ["model"])
        self.assertNotIn("resourceUri", tools[4]["_meta"]["ui"])
        self.assertEqual(tools[5]["annotations"]["readOnlyHint"], True)
        self.assertEqual(tools[5]["_meta"]["ui"]["visibility"], ["model", "app"])
        self.assertEqual(
            tools[5]["_meta"]["ui"]["resourceUri"],
            "ui://chatgpt-codex-bridge/job-status-v4.html",
        )
        self.assertEqual(tools[6]["_meta"]["ui"]["visibility"], ["app"])
        self.assertNotIn("resourceUri", tools[6]["_meta"]["ui"])
        self.assertNotIn("openai/outputTemplate", tools[6]["_meta"])
        self.assertEqual(
            tools[2]["_meta"]["openai/outputTemplate"],
            "ui://chatgpt-codex-bridge/job-status-v4.html",
        )
        start_schema = tools[2]["inputSchema"]
        self.assertEqual(start_schema["required"], ["prompt"])
        self.assertEqual(
            set(start_schema["properties"]),
            {"prompt", "projectName"},
        )
        self.assertNotIn("cwd", json.dumps(start_schema))
        self.assertIn("workspace-new-project", tools[2]["description"])
        self.assertIn("new project", tools[2]["description"].lower())
        self.assertIn("MUST call codex-wait", tools[2]["description"])
        self.assertIn("MUST call codex-wait", tools[3]["description"])
        self.assertIn("MUST call this tool again", tools[4]["description"])
        self.assertIn("same threadId", tools[4]["description"])
        self.assertEqual(tools[4]["inputSchema"]["required"], ["jobId"])
        self.assertEqual(
            set(tools[4]["inputSchema"]["properties"]),
            {"jobId"},
        )
        expected_statuses = [
            "queued", "running", "completed", "failed", "interrupted"
        ]
        for tool in tools[2:]:
            self.assertEqual(
                tool["outputSchema"]["properties"]["status"]["enum"],
                expected_statuses,
            )

        codex_schema = tools[0]["inputSchema"]
        self.assertEqual(codex_schema["type"], "object")
        self.assertFalse(codex_schema["additionalProperties"])
        self.assertEqual(codex_schema["required"], ["prompt"])
        self.assertEqual(set(codex_schema["properties"]), {"prompt"})
        self.assertIn("once per ChatGPT web conversation", tools[0]["description"])
        self.assertIn("Codex thread: <threadId>", tools[0]["description"])
        self.assertIn("MUST NOT use this diagnostic tool", tools[0]["description"])
        self.assertIn("same Codex thread", tools[1]["description"])

        reply_schema = tools[1]["inputSchema"]
        self.assertEqual(reply_schema["type"], "object")
        self.assertFalse(reply_schema["additionalProperties"])
        self.assertEqual(reply_schema["required"], ["prompt", "threadId"])
        self.assertEqual(set(reply_schema["properties"]), {"prompt", "threadId"})

        for tool in tools[:2]:
            output_schema = tool["outputSchema"]
            self.assertEqual(output_schema["type"], "object")
            self.assertFalse(output_schema["additionalProperties"])
            self.assertEqual(output_schema["required"], ["threadId", "content"])
            self.assertEqual(
                set(output_schema["properties"]),
                {"threadId", "content"},
            )

        serialized = json.dumps(tools[:2])
        for forbidden in (
            "cwd",
            "danger-full-access",
            "approval-policy",
            "config",
            "model",
            "developer-instructions",
            "base-instructions",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_initialize_is_replayed_for_tunnel_multiplexing(self):
        harness = self.harness()
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tunnel-client", "version": "1.0"},
            },
        }
        first = dict(request)
        first["id"] = 1
        second = dict(request)
        second["id"] = 2
        harness.send(first)
        first_response = harness.receive()
        self.assertEqual(
            first_response["result"]["capabilities"]["resources"],
            {"listChanged": False},
        )
        harness.send(second)
        second_response = harness.receive()
        self.assertEqual({first_response["id"], second_response["id"]}, {1, 2})
        self.assertEqual(first_response["result"], second_response["result"])

        third = dict(request)
        third["id"] = 3
        harness.send(third)
        third_response = harness.receive()
        self.assertEqual(third_response["id"], 3)
        self.assertEqual(third_response["result"], first_response["result"])

        harness.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        harness.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        harness.send({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/list",
            "params": {},
        })
        tools_response = harness.receive()
        self.assertEqual(tools_response["id"], 4)
        self.assertEqual(
            [tool["name"] for tool in tools_response["result"]["tools"]],
            [
                "codex",
                "codex-reply",
                "codex-start",
                "codex-reply-async",
                "codex-wait",
                "codex-job-open",
                "codex-job-status",
            ],
        )

    def test_codex_call_injects_fixed_full_control_policy_and_filters_environment(self):
        harness = self.harness()
        harness.initialize()
        response = harness.call(3, "codex", {"prompt": "inspect only"})
        structured = response["result"]["structuredContent"]
        self.assertTrue(structured["threadId"].startswith("cgb2.thread."))
        self.assertEqual(structured["content"], "ok")
        self.assertEqual(
            response["result"]["content"],
            [{"type": "text", "text": "ok"}],
        )
        serialized = json.dumps(response)
        for forbidden in (
            str(harness.workspace),
            "danger-full-access",
            "approval-policy",
            "receivedArguments",
            "secretSeen",
            "homeSeen",
        ):
            self.assertNotIn(forbidden, serialized)

        child_state = harness.read_child_state()
        self.assertEqual(child_state["receivedArguments"], {
            "prompt": "inspect only",
            "cwd": str(harness.workspace),
            "sandbox": "danger-full-access",
            "approval-policy": "never",
        })
        self.assertFalse(child_state["secretSeen"])
        self.assertTrue(child_state["homeSeen"])

    def test_workspace_safe_policy_is_fixed_server_side_and_truthfully_described(self):
        harness = self.harness(
            sandbox="workspace-write",
            approval_policy="on-request",
        )
        tools = harness.initialize()["result"]["tools"]
        self.assertIn("workspace-scoped writes", tools[0]["description"])
        self.assertIn("approval prompts", tools[0]["description"])
        self.assertEqual(set(tools[0]["inputSchema"]["properties"]), {"prompt"})

        harness.call(3, "codex", {"prompt": "safe fixture"})
        arguments = harness.read_child_state()["receivedArguments"]
        self.assertEqual(arguments["sandbox"], "workspace-write")
        self.assertEqual(arguments["approval-policy"], "on-request")
        self.assertNotIn("sandbox", tools[0]["inputSchema"]["properties"])
        self.assertNotIn("approval-policy", tools[0]["inputSchema"]["properties"])

    def test_unsupported_policy_pair_fails_configuration(self):
        case_root = self.root / "invalid-policy"
        case_root.mkdir()
        workspace = case_root / "workspace"
        workspace.mkdir()
        fake_codex = case_root / "fake-codex"
        fake_codex.write_text(
            FAKE_CODEX_SOURCE.replace("__SCENARIO__", repr("normal")),
            encoding="utf-8",
        )
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        result = subprocess.run(
            [
                SYSTEM_PYTHON,
                str(GUARD),
                "--workspace",
                str(workspace),
                "--codex-bin",
                str(fake_codex),
                "--sandbox",
                "danger-full-access",
                "--approval-policy",
                "on-request",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("configuration rejected", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_legacy_mode_is_rejected_and_full_control_remains_fixed(self):
        harness = self.harness()
        harness.initialize()
        response = harness.call(3, "codex", {
            "prompt": "write fixture",
            "mode": "workspace-write",
        })
        self.assertEqual(response["error"]["code"], -32602)
        harness.call(4, "codex", {"prompt": "write fixture"})
        arguments = harness.read_child_state()["receivedArguments"]
        self.assertEqual(arguments["sandbox"], "danger-full-access")
        self.assertEqual(arguments["approval-policy"], "never")
        self.assertNotIn("model", arguments)
        self.assertNotIn("config", arguments)

    def test_unsafe_public_arguments_and_unknown_tools_are_rejected_but_persisted_threads_continue(self):
        harness = self.harness()
        harness.initialize()
        unsafe = harness.call(3, "codex", {
            "prompt": "unsafe",
            "cwd": "/",
            "sandbox": "danger-full-access",
            "approval-policy": "never",
        })
        self.assertEqual(unsafe["error"]["code"], -32602)

        unsafe_start = harness.call(8, "codex-start", {
            "prompt": "unsafe project",
            "projectName": "unsafe",
            "cwd": "/",
        })
        self.assertEqual(unsafe_start["error"]["code"], -32602)
        empty_name = harness.call(9, "codex-start", {
            "prompt": "empty name",
            "projectName": "   ",
        })
        self.assertEqual(empty_name["error"]["code"], -32602)
        self.assertEqual(list(harness.workspace.iterdir()), [])

        unknown_tool = harness.call(4, "shell", {"command": "true"})
        self.assertEqual(unknown_tool["error"]["code"], -32601)

        persisted_thread = harness.call(5, "codex-reply", {
            "prompt": "continue",
            "threadId": "thread-from-earlier-bridge-process",
        })
        self.assertEqual(persisted_thread["error"]["code"], -32602)

        started = harness.call(6, "codex", {"prompt": "start"})
        thread_id = started["result"]["structuredContent"]["threadId"]
        continued = harness.call(7, "codex-reply", {
            "prompt": "continue",
            "threadId": thread_id,
        })
        self.assertIn("result", continued)
        forwarded = harness.read_child_state()["receivedArguments"]
        self.assertEqual(forwarded, {"prompt": "continue", "threadId": "thread-local-1"})

    def test_initialize_verifies_contract_before_first_tool_call(self):
        harness = self.harness()
        harness.initialize(list_tools=False)
        response = harness.call(2, "codex", {"prompt": "inspect immediately"})
        self.assertIn("result", response)
        self.assertEqual(
            harness.read_child_state()["receivedArguments"]["prompt"],
            "inspect immediately",
        )

    def test_preinitialize_tool_requests_are_rejected_without_poisoning_lifecycle(self):
        harness = self.harness()
        harness.send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        harness.send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        })
        discovery = harness.receive()
        self.assertEqual(discovery["error"]["code"], -32002)

        call = harness.call(2, "codex", {"prompt": "must not run"})
        self.assertEqual(call["error"]["code"], -32002)

        tools = harness.initialize()
        self.assertEqual(
            [tool["name"] for tool in tools["result"]["tools"]],
            [
                "codex",
                "codex-reply",
                "codex-start",
                "codex-reply-async",
                "codex-wait",
                "codex-job-open",
                "codex-job-status",
            ],
        )

    def test_apps_resource_exposes_self_contained_same_conversation_return_widget(self):
        harness = self.harness()
        initialized = harness.initialize(list_tools=False)
        self.assertIsNone(initialized)
        harness.send({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/list",
            "params": {"_meta": {"progressToken": "chatgpt-template-list"}},
        })
        listing = harness.receive()
        list_diagnostic = harness.receive_stderr_json()
        self.assertEqual(list_diagnostic, {
            "event": "mcp_resource_request",
            "method": "resources/list",
            "paramsType": "dict",
            "paramKeys": ["_meta"],
            "toolListVerified": True,
        })
        resource = listing["result"]["resources"][0]
        self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")
        uri = resource["uri"]
        harness.send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {
                "uri": uri,
                "_meta": {"progressToken": "chatgpt-template-read"},
            },
        })
        response = harness.receive()
        read_diagnostic = harness.receive_stderr_json()
        self.assertEqual(read_diagnostic, {
            "event": "mcp_resource_response",
            "method": "resources/read",
            "paramsType": "dict",
            "paramKeys": ["_meta", "uri"],
            "toolListVerified": True,
            "templateVersion": "current",
            "htmlBytes": len(response["result"]["contents"][0]["text"].encode("utf-8")),
        })
        self.assertNotIn("chatgpt-template-read", json.dumps(read_diagnostic))
        content = response["result"]["contents"][0]
        self.assertEqual(content["uri"], uri)
        html = content["text"]
        self.assertIn("sendFollowUpMessage", html)
        self.assertIn("callTool('codex-job-status'", html)
        self.assertIn("[codex-job:${state.jobId}]", html)
        self.assertIn("setWidgetState", html)
        self.assertIn("hasOwnProperty.call(value, 'result')", html)
        self.assertIn("toolResponseMetadata", html)
        self.assertIn("openai:set_globals", html)
        self.assertIn("ui/notifications/tool-result", html)
        self.assertIn("把结果发给 ChatGPT 审查", html)
        self.assertIn("重新发送结果到 ChatGPT", html)
        self.assertNotIn("send(state, false)", html)
        followup_source = html.split("const followup =", 1)[1].split(
            "const send =", 1
        )[0]
        self.assertNotIn("state.content", followup_source)
        self.assertNotIn("state.threadId", followup_source)
        self.assertIn("codex-wait", followup_source)

        harness.send({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": uri},
        })
        live_shape_response = harness.receive()
        live_shape_diagnostic = harness.receive_stderr_json()
        self.assertEqual(live_shape_response["result"]["contents"][0]["uri"], uri)
        self.assertEqual(live_shape_diagnostic["paramKeys"], ["uri"])
        self.assertNotIn(uri, json.dumps(live_shape_diagnostic))
        self.assertEqual(live_shape_diagnostic["templateVersion"], "current")

        legacy_uri = "ui://chatgpt-codex-bridge/job-status-v2.html"
        harness.send({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": legacy_uri},
        })
        legacy_response = harness.receive()
        legacy_diagnostic = harness.receive_stderr_json()
        legacy_content = legacy_response["result"]["contents"][0]
        self.assertEqual(legacy_content["uri"], legacy_uri)
        self.assertEqual(legacy_content["text"], html)
        self.assertEqual(legacy_diagnostic["paramKeys"], ["uri"])
        self.assertNotIn(legacy_uri, json.dumps(legacy_diagnostic))
        self.assertEqual(legacy_diagnostic["templateVersion"], "legacy")

    def wait_for_job(self, harness, job_id, terminal=True, timeout=4.0):
        deadline = time.time() + timeout
        last = None
        request_id = 100
        while time.time() < deadline:
            request_id += 1
            last = harness.call(request_id, "codex-job-status", {"jobId": job_id})
            status = last["result"]["structuredContent"]["status"]
            if not terminal or status in ("completed", "failed", "interrupted"):
                return last
            time.sleep(0.05)
        raise AssertionError("job did not reach terminal state: " + repr(last))

    def test_public_identifiers_are_scoped_signed_capabilities(self):
        harness = self.harness()
        harness.initialize()

        queued = harness.call(3, "codex-start", {"prompt": "capability fixture"})
        job_id = queued["result"]["structuredContent"]["jobId"]
        self.assertTrue(job_id.startswith("cgb2.job."), job_id)
        self.assertNotIn("thread-async-1", json.dumps(queued))

        final = self.wait_for_job(harness, job_id)["result"]["structuredContent"]
        thread_id = final["threadId"]
        self.assertTrue(thread_id.startswith("cgb2.thread."), thread_id)
        self.assertNotIn("thread-async-1", json.dumps(final))

        forged_job = job_id[:-1] + ("A" if job_id[-1] != "A" else "B")
        forged = harness.call(4, "codex-job-status", {"jobId": forged_job})
        self.assertEqual(forged["error"]["code"], -32602)

        cross_type = harness.call(5, "codex-job-status", {"jobId": thread_id})
        self.assertEqual(cross_type["error"]["code"], -32602)

        self.assertEqual(
            stat.S_IMODE((harness.job_state_dir / "capability.key").stat().st_mode),
            0o600,
        )
        foreign = self.harness()
        foreign.initialize()
        foreign_read = foreign.call(3, "codex-job-status", {"jobId": job_id})
        self.assertEqual(foreign_read["error"]["code"], -32602)

        raw_reply = harness.call(6, "codex-reply-async", {
            "prompt": "raw identifiers are forbidden",
            "threadId": "thread-async-1",
        })
        self.assertEqual(raw_reply["error"]["code"], -32602)

    def test_capabilities_are_bound_to_workspace_and_policy_context(self):
        module_spec = importlib.util.spec_from_file_location(
            "chatgpt_codex_guard_context_test",
            GUARD,
        )
        guard_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(guard_module)
        state_root = self.root / "shared-context-state"
        workspace_a = self.root / "workspace-a"
        workspace_b = self.root / "workspace-b"
        workspace_a.mkdir()
        workspace_b.mkdir()
        first = guard_module.JobStore(
            str(state_root),
            "/usr/bin/true",
            str(workspace_a),
            "danger-full-access",
            "never",
            "/usr/bin/open",
        )
        old_thread = first.capabilities.encode("thread", "thread-context-fixture")
        second = guard_module.JobStore(
            str(state_root),
            "/usr/bin/true",
            str(workspace_b),
            "workspace-write",
            "on-request",
            "/usr/bin/open",
        )

        with self.assertRaises(guard_module.GuardProtocolError):
            second.capabilities.decode("thread", old_thread)

    def test_non_ascii_capability_is_rejected_without_unicode_crash(self):
        module_spec = importlib.util.spec_from_file_location(
            "chatgpt_codex_guard_unicode_test",
            GUARD,
        )
        guard_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(guard_module)
        key_path = self.root / "unicode-capability.key"
        codec = guard_module.CapabilityCodec(key_path)

        with self.assertRaises(guard_module.GuardProtocolError):
            codec.decode("job", "cgb2.job.context.é.signature")

    def test_sync_pair_returns_and_accepts_only_thread_capability(self):
        harness = self.harness()
        harness.initialize()

        started = harness.call(3, "codex", {"prompt": "sync start"})
        thread_id = started["result"]["structuredContent"]["threadId"]
        self.assertTrue(thread_id.startswith("cgb2.thread."), thread_id)
        self.assertNotEqual(thread_id, "thread-local-1")

        continued = harness.call(4, "codex-reply", {
            "prompt": "sync continue",
            "threadId": thread_id,
        })
        self.assertEqual(
            continued["result"]["structuredContent"]["threadId"],
            thread_id,
        )
        self.assertEqual(
            harness.read_child_state()["receivedArguments"]["threadId"],
            "thread-local-1",
        )

    def test_sync_pair_enforces_prompt_limit_before_downstream(self):
        harness = self.harness()
        harness.initialize()

        rejected = harness.call(3, "codex", {
            "prompt": "x" * (256 * 1024 + 1),
        })

        self.assertEqual(rejected["error"]["code"], -32602)
        self.assertFalse(Path(str(harness.fake_codex) + ".state.json").exists())

    def test_sync_call_deadline_stops_unbounded_downstream(self):
        harness = self.harness(scenario="sync_slow", sync_max_seconds=0.1)
        harness.initialize()

        timed_out = harness.call(3, "codex", {"prompt": "bounded sync"})

        self.assertEqual(timed_out["error"]["code"], -32011)
        self.assertNotEqual(harness.wait_exit(), 0)

    def test_async_admission_rejects_oversized_prompt_before_allocation(self):
        harness = self.harness()
        harness.initialize()
        before = list(harness.workspace.iterdir())

        rejected = harness.call(3, "codex-start", {"prompt": "x" * (256 * 1024 + 1)})

        self.assertEqual(rejected["error"]["code"], -32602)
        self.assertEqual(list(harness.workspace.iterdir()), before)
        self.assertFalse((harness.root / "jobs").exists() and any(
            path.is_dir() for path in (harness.root / "jobs").iterdir()
        ))

    def test_thread_project_lookup_fails_closed_when_job_state_is_unavailable(self):
        module_spec = importlib.util.spec_from_file_location(
            "chatgpt_codex_guard_under_test",
            GUARD,
        )
        guard_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(guard_module)
        root = self.root / "lookup-state"
        workspace = self.root / "lookup-workspace"
        workspace.mkdir()
        store = guard_module.JobStore(
            str(root),
            "/usr/bin/true",
            str(workspace),
            "danger-full-access",
            "never",
            "/usr/bin/open",
        )
        thread_id = store.capabilities.encode("thread", "thread-fixture")

        with mock.patch.object(Path, "iterdir", side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(
                guard_module.GuardProtocolError,
                "job state unavailable",
            ):
                store._project_for_thread(thread_id)

    def test_async_admission_caps_active_jobs_atomically(self):
        harness = self.harness(scenario="async_slow", max_active_jobs=2)
        harness.initialize()

        first = harness.call(3, "codex-start", {"prompt": "active one"})
        second = harness.call(4, "codex-start", {"prompt": "active two"})
        third = harness.call(5, "codex-start", {"prompt": "active three"})

        self.assertIn("result", first)
        self.assertIn("result", second)
        self.assertEqual(third["error"]["code"], -32010)
        self.assertIn("active job limit", third["error"]["message"])
        self.wait_for_job(harness, first["result"]["structuredContent"]["jobId"])
        self.wait_for_job(harness, second["result"]["structuredContent"]["jobId"])

    def test_async_admission_caps_retained_jobs_without_deleting_records(self):
        harness = self.harness(max_active_jobs=1, max_retained_jobs=1)
        harness.initialize()
        first = harness.call(3, "codex-start", {"prompt": "retained one"})
        first_job = first["result"]["structuredContent"]["jobId"]
        self.wait_for_job(harness, first_job)
        project_count = len(list(harness.workspace.iterdir()))

        second = harness.call(4, "codex-start", {"prompt": "retained two"})

        self.assertEqual(second["error"]["code"], -32010)
        self.assertIn("retained job limit", second["error"]["message"])
        self.assertEqual(len(list(harness.workspace.iterdir())), project_count)

    def test_async_worker_deadline_fails_terminal_and_stops_app_server(self):
        harness = self.harness(scenario="async_slow", job_max_seconds=0.1)
        harness.initialize()
        queued = harness.call(3, "codex-start", {"prompt": "deadline fixture"})
        job_id = queued["result"]["structuredContent"]["jobId"]

        terminal = self.wait_for_job(harness, job_id)["result"]["structuredContent"]

        self.assertEqual(terminal["status"], "failed")
        self.assertIn("time limit", terminal["content"])

    def test_codex_wait_returns_terminal_result_without_enqueuing_another_job(self):
        harness = self.harness(scenario="async_slow", job_wait_seconds=5.0)
        harness.initialize()
        queued = harness.call(3, "codex-start", {"prompt": "join fixture"})
        job_id = queued["result"]["structuredContent"]["jobId"]
        job_count = len(harness.job_directories())

        joined = harness.call(4, "codex-wait", {"jobId": job_id})

        final = joined["result"]["structuredContent"]
        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["threadId"].startswith("cgb2.thread."))
        self.assertIn("join fixture", final["content"])
        self.assertIn("review this result", joined["result"]["content"][0]["text"])
        self.assertIn("same threadId", joined["result"]["content"][0]["text"])
        self.assertIn(
            "BEGIN UNTRUSTED CODEX OUTPUT",
            joined["result"]["content"][0]["text"],
        )
        self.assertIn(
            "END UNTRUSTED CODEX OUTPUT",
            joined["result"]["content"][0]["text"],
        )
        self.assertEqual(len(harness.job_directories()), job_count)

    def test_revoke_jobs_terminates_detached_worker_process_group(self):
        harness = self.harness(scenario="async_block", job_max_seconds=60)
        harness.initialize()
        queued = harness.call(3, "codex-start", {"prompt": "revoke fixture"})
        job_id = queued["result"]["structuredContent"]["jobId"]
        job_dir = harness.job_dir_for(job_id)
        worker_path = job_dir / "worker.json"
        deadline = time.time() + 3
        while time.time() < deadline and not worker_path.is_file():
            time.sleep(0.02)
        worker = json.loads(worker_path.read_text(encoding="utf-8"))
        pid = worker["pid"]
        harness.stop()

        try:
            module_spec = importlib.util.spec_from_file_location(
                "chatgpt_codex_guard_revoke_test",
                GUARD,
            )
            guard_module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(guard_module)
            with mock.patch.object(
                guard_module, "_worker_command_matches", return_value=True
            ):
                revoked = guard_module.revoke_managed_workers(
                    str(harness.job_state_dir)
                )
            self.assertEqual(revoked, 1)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            state = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "interrupted")
        finally:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_revoke_jobs_rejects_foreign_pid_without_signalling_it(self):
        job_root = self.root / "foreign-jobs"
        job_root.mkdir()
        internal_job_id = str(uuid.uuid4())
        job_dir = job_root / internal_job_id
        job_dir.mkdir()
        foreign = subprocess.Popen(
            ["/bin/sleep", "30"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            (job_dir / "status.json").write_text(json.dumps({
                "internalJobId": internal_job_id,
                "status": "running",
                "content": "",
            }), encoding="utf-8")
            (job_dir / "worker.json").write_text(json.dumps({
                "pid": foreign.pid,
                "processGroupId": foreign.pid,
                "guardScript": str(GUARD),
                "jobDir": str(job_dir),
            }), encoding="utf-8")
            completed = subprocess.run(
                [SYSTEM_PYTHON, str(GUARD), "--revoke-jobs", str(job_root)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
                check=False,
            )
            self.assertEqual(completed.returncode, 70)
            self.assertIsNone(foreign.poll())
        finally:
            if foreign.poll() is None:
                os.killpg(foreign.pid, signal.SIGTERM)
                foreign.wait(timeout=2.0)

    def test_async_job_ignores_foreign_turn_terminals_until_root_completes(self):
        harness = self.harness(scenario="async_foreign_turns")
        harness.initialize()
        queued = harness.call(
            3,
            "codex-start",
            {"prompt": "root turn owns completion"},
        )
        job_id = queued["result"]["structuredContent"]["jobId"]

        final = self.wait_for_job(harness, job_id)["result"]["structuredContent"]

        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["threadId"].startswith("cgb2.thread."))
        self.assertTrue(final["content"].startswith("async ok: "))
        self.assertIn("root turn owns completion", final["content"])
        self.assertNotIn("child provider review", final["content"])
        self.assertNotIn("same-thread unrelated turn", final["content"])

    def test_codex_wait_is_bounded_and_requires_another_wait_while_running(self):
        harness = self.harness(job_wait_seconds=0.05)
        harness.initialize()
        job_id, job_dir, status_path = harness.write_job_fixture(
            "00000000-0000-4000-8000-000000000002",
            "running",
            pid=os.getpid(),
            content="still working",
        )

        started_at = time.monotonic()
        pending = harness.call(3, "codex-wait", {"jobId": job_id})
        elapsed = time.monotonic() - started_at

        self.assertGreaterEqual(elapsed, 0.04)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(pending["result"]["structuredContent"]["status"], "running")
        message = pending["result"]["content"][0]["text"]
        self.assertIn("MUST call codex-wait again", message)
        self.assertIn(job_id, message)

    def test_codex_wait_rejects_unknown_or_extra_arguments(self):
        harness = self.harness()
        harness.initialize()
        unknown = harness.call(
            3,
            "codex-wait",
            {"jobId": "00000000-0000-4000-8000-000000000003"},
        )
        self.assertEqual(unknown["error"]["code"], -32602)
        extra = harness.call(4, "codex-wait", {
            "jobId": "00000000-0000-4000-8000-000000000003",
            "timeout": 999,
        })
        self.assertEqual(extra["error"]["code"], -32602)

    def test_job_open_renders_an_existing_durable_job_without_starting_another(self):
        harness = self.harness()
        harness.initialize()
        queued = harness.call(3, "codex-start", {"prompt": "recover fixture"})
        job_id = queued["result"]["structuredContent"]["jobId"]

        opened = harness.call(4, "codex-job-open", {"jobId": job_id})

        self.assertEqual(opened["result"]["structuredContent"]["jobId"], job_id)
        self.assertEqual(opened["result"]["_meta"], {"jobId": job_id})
        self.assertEqual(
            len(harness.job_directories()),
            1,
            "opening a job must not enqueue a duplicate Codex run",
        )
        terminal = self.wait_for_job(harness, job_id)
        self.assertEqual(
            terminal["result"]["structuredContent"]["status"],
            "completed",
        )

    def test_async_start_creates_project_root_and_requires_workspace_skill(self):
        harness = self.harness()
        harness.initialize()

        queued = harness.call(3, "codex-start", {
            "prompt": "构建真实数据观察项目",
            "projectName": "GACE 观察站",
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        completed = self.wait_for_job(harness, job_id)
        self.assertEqual(completed["result"]["structuredContent"]["status"], "completed")

        project_roots = list(harness.workspace.iterdir())
        self.assertEqual(len(project_roots), 1)
        project_root = project_roots[0]
        self.assertEqual(project_root.name, "GACE-观察站")
        self.assertEqual(project_root.resolve().parent, harness.workspace.resolve())
        for marker in (
            "AGENTS.md",
            "README.md",
            ".gitignore",
            ".project-memory",
            "docs/specs",
            "docs/adr",
            "src",
        ):
            self.assertTrue((project_root / marker).exists(), marker)

        child_state = harness.read_child_state()
        self.assertEqual(child_state["requestedCwd"], str(project_root))
        self.assertEqual(
            child_state["argv"],
            ["app-server", "--listen", "stdio://"],
        )
        methods = [request.get("method") for request in child_state["requests"]]
        self.assertEqual(
            methods,
            [
                "initialize",
                "initialized",
                "project/create",
                "thread/start",
                "thread/name/set",
                "turn/start",
                "project/list",
                "thread/list",
            ],
        )
        project_create = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "project/create"
        )["params"]
        self.assertEqual(project_create["name"], "GACE 观察站")
        self.assertEqual(project_create["roots"], [{"path": str(project_root)}])
        self.assertNotEqual(project_create["idempotencyKey"], job_id)
        self.assertEqual(str(uuid.UUID(project_create["idempotencyKey"])), project_create["idempotencyKey"])
        thread_start = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "thread/start"
        )["params"]
        self.assertEqual(thread_start["cwd"], str(project_root))
        self.assertEqual(thread_start["approvalPolicy"], "never")
        self.assertEqual(thread_start["sandbox"], "danger-full-access")
        self.assertEqual(thread_start["serviceName"], "chatgpt_codex_bridge")
        self.assertEqual(thread_start["projectId"], "project-async-1")
        project_list = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "project/list"
        )["params"]
        self.assertEqual(project_list, {"limit": 100})
        thread_list = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "thread/list"
        )["params"]
        self.assertEqual(thread_list["projectId"], "project-async-1")
        name_set = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "thread/name/set"
        )["params"]
        self.assertEqual(name_set["name"], "GACE 观察站")
        turn_start = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "turn/start"
        )["params"]
        self.assertEqual(turn_start["cwd"], str(project_root))
        self.assertEqual(turn_start["approvalPolicy"], "never")
        self.assertEqual(
            turn_start["sandboxPolicy"],
            {"type": "dangerFullAccess"},
        )
        skill_input = next(
            item for item in turn_start["input"] if item["type"] == "skill"
        )
        self.assertEqual(skill_input, {
            "type": "skill",
            "name": "workspace-new-project",
            "path": str(harness.skill_path),
        })
        self.assertTrue(
            child_state["prompt"].startswith("[BRIDGE REQUIRED NEW PROJECT BOOTSTRAP]")
        )
        self.assertIn("$workspace-new-project", child_state["prompt"])
        self.assertIn("--here", child_state["prompt"])
        self.assertIn("构建真实数据观察项目", child_state["prompt"])

        durable_job_dir = harness.job_dir_for(job_id)
        request = json.loads(
            (durable_job_dir / "request.json").read_text(encoding="utf-8")
        )
        self.assertEqual(request["workspace"], str(project_root))
        self.assertTrue(request["bootstrapRequired"])
        self.assertEqual(request["projectName"], "GACE 观察站")
        status = json.loads(
            (durable_job_dir / "status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(status["projectId"], "project-async-1")
        self.assertEqual(
            harness.read_desktop_open_state()["argv"],
            ["-g", "-b", "com.openai.codex", str(project_root)],
        )
        self.assertNotIn(str(project_root), json.dumps(completed, ensure_ascii=False))

    def test_project_names_are_safe_unique_and_backward_compatible(self):
        harness = self.harness()
        harness.initialize()
        calls = [
            {"prompt": "one", "projectName": "量化 工具"},
            {"prompt": "two", "projectName": "量化 工具"},
            {"prompt": "three", "projectName": "../../.ssh"},
            {"prompt": "four"},
        ]
        for request_id, arguments in enumerate(calls, start=3):
            queued = harness.call(request_id, "codex-start", arguments)
            job_id = queued["result"]["structuredContent"]["jobId"]
            completed = self.wait_for_job(harness, job_id)
            self.assertEqual(
                completed["result"]["structuredContent"]["status"],
                "completed",
            )

        roots = sorted(harness.workspace.iterdir(), key=lambda path: path.name)
        self.assertEqual(len(roots), 4)
        self.assertIn("量化-工具", [path.name for path in roots])
        self.assertIn("量化-工具-2", [path.name for path in roots])
        self.assertTrue(
            any(path.name.startswith("chatgpt-project-") for path in roots)
        )
        for root in roots:
            self.assertEqual(root.resolve().parent, harness.workspace.resolve())
            self.assertNotIn("..", root.name)
            self.assertNotIn("/", root.name)

    def test_async_start_fails_closed_when_desktop_project_registration_fails(self):
        harness = self.harness(desktop_open_exit_code=1)
        harness.initialize()

        queued = harness.call(3, "codex-start", {
            "prompt": "构建项目",
            "projectName": "桌面注册失败验证",
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        terminal = self.wait_for_job(harness, job_id)
        result = terminal["result"]["structuredContent"]

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("threadId", result)
        self.assertFalse(Path(str(harness.fake_codex) + ".state.json").exists())

    def test_async_start_fails_if_workspace_skill_scaffold_is_missing(self):
        harness = self.harness(scenario="async_no_scaffold")
        harness.initialize()
        queued = harness.call(3, "codex-start", {
            "prompt": "pretend initialization succeeded",
            "projectName": "missing-scaffold",
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        failed = self.wait_for_job(harness, job_id)
        final = failed["result"]["structuredContent"]
        self.assertEqual(final["status"], "failed")
        self.assertIn("workspace-new-project", final["content"])

    def test_async_reply_reuses_original_project_root(self):
        harness = self.harness()
        harness.initialize()
        queued = harness.call(3, "codex-start", {
            "prompt": "initialize once",
            "projectName": "same-root",
        })
        first_job_id = queued["result"]["structuredContent"]["jobId"]
        first = self.wait_for_job(harness, first_job_id)["result"]["structuredContent"]
        project_root = next(harness.workspace.iterdir())
        root_count = len(list(harness.workspace.iterdir()))

        queued_reply = harness.call(4, "codex-reply-async", {
            "prompt": "continue in place",
            "threadId": first["threadId"],
        })
        reply_job_id = queued_reply["result"]["structuredContent"]["jobId"]
        reply = self.wait_for_job(harness, reply_job_id)["result"]["structuredContent"]
        self.assertEqual(reply["status"], "completed")
        self.assertEqual(reply["threadId"], first["threadId"])
        self.assertEqual(len(list(harness.workspace.iterdir())), root_count)

        child_state = harness.read_child_state()
        self.assertEqual(child_state["requestedCwd"], str(project_root))
        self.assertEqual(
            child_state["argv"],
            ["app-server", "--listen", "stdio://"],
        )
        methods = [request.get("method") for request in child_state["requests"]]
        self.assertEqual(
            methods,
            ["initialize", "initialized", "thread/resume", "turn/start"],
        )
        resume = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "thread/resume"
        )["params"]
        self.assertEqual(resume["threadId"], "thread-async-1")
        self.assertEqual(resume["cwd"], str(project_root))
        self.assertNotIn("projectId", resume)
        turn = next(
            request
            for request in child_state["requests"]
            if request.get("method") == "turn/start"
        )["params"]
        self.assertEqual(turn["cwd"], str(project_root))
        self.assertEqual([item["type"] for item in turn["input"]], ["text"])
        self.assertNotIn("workspace-new-project", child_state["prompt"])

    def test_async_start_fails_when_workspace_skill_is_not_installed(self):
        harness = self.harness()
        harness.initialize()
        harness.skill_path.unlink()
        queued = harness.call(3, "codex-start", {
            "prompt": "must not pretend skill invocation",
            "projectName": "missing-skill",
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        failed = self.wait_for_job(harness, job_id)
        final = failed["result"]["structuredContent"]
        self.assertEqual(final["status"], "failed")
        self.assertIn("workspace-new-project Skill", final["content"])
        self.assertFalse(Path(str(harness.fake_codex) + ".state.json").exists())

    def test_explicit_workspace_skill_works_without_global_install(self):
        case_root = self.root / "explicit-skill-source"
        case_root.mkdir()
        explicit_skill = case_root / "workspace-new-project" / "SKILL.md"
        explicit_skill.parent.mkdir()
        explicit_skill.write_text(
            "---\nname: workspace-new-project\n---\n# Portable test skill\n",
            encoding="utf-8",
        )
        harness = self.harness(explicit_workspace_skill=explicit_skill)
        harness.skill_path.unlink()
        harness.initialize()
        queued = harness.call(3, "codex-start", {
            "prompt": "initialize from staged skill",
            "projectName": "portable-skill",
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        final = self.wait_for_job(harness, job_id)["result"]["structuredContent"]
        self.assertEqual(final["status"], "completed")
        turn_start = next(
            request
            for request in harness.read_child_state()["requests"]
            if request.get("method") == "turn/start"
        )
        skill_input = next(
            item for item in turn_start["params"]["input"] if item["type"] == "skill"
        )
        self.assertEqual(skill_input["path"], str(explicit_skill))

    def test_async_new_task_fails_if_app_server_is_not_sidebar_rooted(self):
        for scenario in (
            "async_non_sidebar",
            "async_wrong_cwd",
            "async_project_mismatch",
            "async_project_api_missing",
        ):
            with self.subTest(scenario=scenario):
                harness = self.harness(scenario=scenario)
                harness.initialize()
                queued = harness.call(3, "codex-start", {
                    "prompt": "must be sidebar discoverable",
                    "projectName": scenario,
                })
                job_id = queued["result"]["structuredContent"]["jobId"]
                failed = self.wait_for_job(harness, job_id)
                self.assertEqual(
                    failed["result"]["structuredContent"]["status"],
                    "failed",
                )

    def test_async_reply_accepts_legacy_exec_source(self):
        harness = self.harness(scenario="resume_exec_source")
        harness.initialize()
        started = harness.call(3, "codex-start", {
            "prompt": "create legacy-compatible task",
            "projectName": "legacy-compatible",
        })
        thread_id = self.wait_for_job(
            harness,
            started["result"]["structuredContent"]["jobId"],
        )["result"]["structuredContent"]["threadId"]
        queued = harness.call(4, "codex-reply-async", {
            "prompt": "continue legacy thread",
            "threadId": thread_id,
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        completed = self.wait_for_job(harness, job_id)
        final = completed["result"]["structuredContent"]
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["threadId"], thread_id)
        self.assertEqual(
            next(
                request
                for request in harness.read_child_state()["requests"]
                if request.get("method") == "thread/resume"
            )["params"]["threadId"],
            "thread-async-1",
        )

    def test_async_start_returns_immediately_and_job_outlives_mcp_request(self):
        harness = self.harness(scenario="async_slow")
        harness.initialize()
        started_at = time.time()
        queued = harness.call(3, "codex-start", {"prompt": "build fixture"})
        elapsed = time.time() - started_at
        structured = queued["result"]["structuredContent"]
        self.assertLess(elapsed, 0.25)
        self.assertEqual(structured["status"], "queued")
        self.assertIn(
            "MUST call codex-wait",
            queued["result"]["content"][0]["text"],
        )
        self.assertIn("_meta", queued["result"])
        job_id = structured["jobId"]
        harness.stop()

        replacement = GuardHarness(
            self,
            harness.root,
            scenario="async_slow",
            job_state_dir=harness.root / "jobs",
        )
        self.harnesses.append(replacement)
        replacement.initialize()
        completed = self.wait_for_job(replacement, job_id)
        final = completed["result"]["structuredContent"]
        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["threadId"].startswith("cgb2.thread."))
        self.assertIn("build fixture", final["content"])
        self.assertIn("workspace-new-project", final["content"])
        self.assertEqual(
            json.loads(completed["result"]["content"][0]["text"]),
            final,
        )

    def test_async_reply_resumes_exact_thread_and_malformed_worker_fails(self):
        harness = self.harness()
        harness.initialize()
        started = harness.call(3, "codex-start", {
            "prompt": "create reply fixture",
            "projectName": "reply-fixture",
        })
        thread_id = self.wait_for_job(
            harness,
            started["result"]["structuredContent"]["jobId"],
        )["result"]["structuredContent"]["threadId"]
        queued = harness.call(4, "codex-reply-async", {
            "prompt": "continue fixture",
            "threadId": thread_id,
        })
        job_id = queued["result"]["structuredContent"]["jobId"]
        completed = self.wait_for_job(harness, job_id)
        final = completed["result"]["structuredContent"]
        self.assertEqual(final["threadId"], thread_id)
        self.assertIn("continue fixture", final["content"])
        self.assertIn(
            "MUST call codex-wait",
            queued["result"]["content"][0]["text"],
        )

        malformed = self.harness(scenario="async_malformed")
        malformed.initialize()
        queued = malformed.call(3, "codex-start", {"prompt": "malformed"})
        job_id = queued["result"]["structuredContent"]["jobId"]
        failed = self.wait_for_job(malformed, job_id)
        self.assertEqual(failed["result"]["structuredContent"]["status"], "failed")

    def test_async_tools_are_absent_from_workspace_safe_preset(self):
        harness = self.harness(
            sandbox="workspace-write",
            approval_policy="on-request",
        )
        tools = harness.initialize()["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["codex", "codex-reply"])
        rejected = harness.call(3, "codex-start", {"prompt": "must not run"})
        self.assertEqual(rejected["error"]["code"], -32601)

    def test_dead_running_job_is_reported_interrupted_and_state_is_private(self):
        harness = self.harness()
        harness.initialize()
        job_id, _job_dir, status_path = harness.write_job_fixture(
            "00000000-0000-4000-8000-000000000001",
            "running",
            pid=2_147_483_647,
            content="last durable progress",
        )
        response = harness.call(3, "codex-job-status", {"jobId": job_id})
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["status"], "interrupted")
        self.assertEqual(stat.S_IMODE(status_path.stat().st_mode), 0o600)

    def test_unknown_durable_status_fails_closed(self):
        harness = self.harness()
        harness.initialize()
        job_id, _job_dir, _status_path = harness.write_job_fixture(
            "00000000-0000-4000-8000-000000000099",
            "done",
            content="not a supported terminal state",
        )

        response = harness.call(3, "codex-job-status", {"jobId": job_id})
        self.assertEqual(response["error"]["code"], -32602)

    def test_dead_queued_worker_is_reported_interrupted(self):
        harness = self.harness()
        harness.initialize()
        job_id, job_dir, _status_path = harness.write_job_fixture(
            "00000000-0000-4000-8000-000000000098",
            "queued",
            content="queued fixture",
            workerLaunchState="running",
        )
        (job_dir / "worker.json").write_text(json.dumps({
            "status": "running",
            "pid": 2_147_483_647,
            "processGroupId": 2_147_483_647,
            "guardScript": str(GUARD),
            "jobDir": str(job_dir),
        }), encoding="utf-8")

        response = harness.call(3, "codex-job-status", {"jobId": job_id})
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["status"], "interrupted")

    def test_downstream_schema_drift_and_extra_tools_fail_closed(self):
        for scenario in (
            "schema_drift",
            "additive_schema_drift",
            "extra_tool",
        ):
            with self.subTest(scenario=scenario):
                harness = self.harness(scenario=scenario)
                harness.send({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "guard-test", "version": "1.0"},
                    },
                })
                response = harness.receive()
                self.assertEqual(response["error"]["code"], -32001)
                self.assertNotEqual(harness.wait_exit(), 0)

    def test_current_downstream_approval_policy_enum_is_accepted(self):
        harness = self.harness(scenario="current_approval_policy")
        response = harness.initialize()
        self.assertIn("tools", response["result"])

    def test_unsolicited_approval_response_fails_closed(self):
        harness = self.harness(scenario="approval")
        harness.initialize()
        harness.send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex", "arguments": {"prompt": "approval flow"}},
        })
        harness.send({
            "jsonrpc": "2.0",
            "id": "child-approval-1",
            "result": {"action": "accept"},
        })
        self.assertNotEqual(harness.wait_exit(), 0)
        if harness.process.stdout is not None:
            messages = [
                json.loads(line)
                for line in harness.process.stdout.read().splitlines()
            ]
            self.assertFalse(any(message.get("id") == 3 and "result" in message for message in messages))

    def test_duplicate_in_flight_client_request_id_fails_closed_explicitly(self):
        harness = self.harness(scenario="approval")
        harness.initialize()
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex", "arguments": {"prompt": "first"}},
        }
        harness.send(request)
        duplicate = json.loads(json.dumps(request))
        duplicate["params"]["arguments"]["prompt"] = "duplicate"
        harness.send(duplicate)
        response = harness.receive()
        if "error" not in response:
            response = harness.receive()
        self.assertEqual(response["error"]["code"], -32600)
        self.assertNotEqual(harness.wait_exit(), 0)

    def test_cross_direction_request_id_collision_fails_closed(self):
        harness = self.harness(scenario="approval_same_id")
        harness.initialize()
        harness.send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex", "arguments": {"prompt": "collision"}},
        })
        response = harness.receive()
        self.assertIsNone(response["id"])
        self.assertEqual(response["error"]["code"], -32000)
        self.assertNotEqual(harness.wait_exit(), 0)

    def test_malformed_child_output_and_early_exit_fail_closed_with_clean_stdout(self):
        malformed = self.harness(scenario="malformed_json")
        malformed.send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        response = malformed.receive()
        self.assertEqual(response["error"]["code"], -32000)
        self.assertNotEqual(malformed.wait_exit(), 0)

        early = self.harness(scenario="early_exit")
        self.assertNotEqual(early.wait_exit(), 0)
        if early.process.stdout is not None:
            for line in early.process.stdout.read().splitlines():
                json.loads(line)

    def test_child_approval_request_and_client_response_are_bidirectional(self):
        harness = self.harness(scenario="approval")
        harness.initialize()
        harness.send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex", "arguments": {"prompt": "approval flow"}},
        })
        approval = harness.receive()
        self.assertEqual(approval["method"], "elicitation/create")
        self.assertEqual(approval["id"], "child-approval-1")
        harness.send({
            "jsonrpc": "2.0",
            "id": "child-approval-1",
            "result": {"action": "accept"},
        })
        response = harness.receive()
        self.assertEqual(response["id"], 3)
        self.assertEqual(response["result"]["structuredContent"]["content"], "ok")

    def test_cli_rejects_relative_and_symlink_boundaries(self):
        workspace = self.root / "cli-workspace"
        workspace.mkdir()
        fake = self.root / "cli-fake-codex"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        linked_workspace = self.root / "linked-workspace"
        linked_workspace.symlink_to(workspace, target_is_directory=True)
        linked_fake = self.root / "linked-codex"
        linked_fake.symlink_to(fake)

        cases = (
            ["--workspace", "relative", "--codex-bin", str(fake)],
            ["--workspace", str(linked_workspace), "--codex-bin", str(fake)],
            ["--workspace", str(workspace), "--codex-bin", str(linked_fake)],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [SYSTEM_PYTHON, str(GUARD)] + list(arguments),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=3.0,
                )
                self.assertNotEqual(completed.returncode, 0)
                for line in completed.stdout.splitlines():
                    json.loads(line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
