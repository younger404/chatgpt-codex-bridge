#!/usr/bin/python3

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import plistlib
from xml.parsers.expat import ExpatError
import re
import secrets
import select
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path


# Source checkout and staged Relay both use the same existing registry helper.
_helper = Path(__file__).resolve().parent
if (_helper.parent / 'bridge' / 'managed_repo.py').is_file():
    _helper = _helper.parent / 'bridge'
sys.path.insert(0, str(_helper))
from managed_repo import Registry, ManagedRepoError, canonical_hash
from supervision import ALIAS, digest, empty_evidence, validate_evidence, safe_text

JOB_LABEL = "bridge-job"
STATUS_LABELS = {
    "queued": "bridge-status-queued",
    "running": "bridge-status-running",
    "completed": "bridge-status-completed",
    "failed": "bridge-status-failed",
}
LABEL_DEFINITIONS = {
    JOB_LABEL: ("5319e7", "Managed Codex relay job"),
    STATUS_LABELS["queued"]: ("d4c5f9", "Relay job admitted locally"),
    STATUS_LABELS["running"]: ("fbca04", "Relay job running through Guard"),
    STATUS_LABELS["completed"]: ("0e8a16", "Relay job completed"),
    STATUS_LABELS["failed"]: ("d93f0b", "Relay job failed closed"),
}
START_JOB_FIELDS = {"schema", "requestId", "operation", "repoAlias", "taskName", "prompt"}
REPLY_JOB_FIELDS = {"schema", "requestId", "operation", "relayJobRef", "prompt"}
QUERY_JOB_FIELDS = {"schema", "requestId", "operation", "relayJobRef"}
REVIEW_JOB_FIELDS = QUERY_JOB_FIELDS | {"evidenceRequestId", "evidenceDigest", "conclusion"}
PUBLISH_JOB_FIELDS = {
    "schema", "requestId", "operation", "relayJobRef", "commitMessage"
}
CONTENT_RESULT_FIELDS = {
    "requestId",
    "relayJobRef",
    "status",
    "repoAlias",
    "content",
    "contentTruncated",
    "publishAvailable",
}
PUBLISH_RESULT_FIELDS = {
    "requestId",
    "relayJobRef",
    "status",
    "repoAlias",
    "branch",
    "commit",
    "pushed",
    "baseStale",
}
TERMINAL_STATUSES = {"completed", "failed", "interrupted"}
CALLABLE_TOOLS = {
    "codex-repo-start",
    "codex-reply-async",
    "codex-wait",
    "codex-job-status",
    "codex-repo-publish",
}
REQUIRED_TOOLS = set(CALLABLE_TOOLS)
PROMPT_MAX_CHARS = 256 * 1024
TASK_NAME_MAX_CHARS = 120
COMMIT_MESSAGE_MAX_CHARS = 500
CONTENT_MAX_CHARS = 40000
POLL_SECONDS = 15
REPO_START_TIMEOUT_SECONDS = 360
STATE_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "chatgpt-codex-bridge"
    / "github-relay.sqlite3"
)
LOCK_PATH = STATE_PATH.with_name("github-relay.lock")
CONFIG_PATH = STATE_PATH.parent / "config.plist"
GUARD_RUNNER = (
    Path.home()
    / ".local"
    / "share"
    / "chatgpt-codex-bridge"
    / "run-guard.zsh"
)
RELAY_REF_PATTERN = re.compile(r"^rjob_[A-Za-z0-9_-]{20,64}$")
ABSOLUTE_LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])/(?:Users|home|private|tmp|var(?:/folders)?|Volumes|etc|opt)/[^\s\"'`]+"
)
CAPABILITY_FIELD_PATTERN = re.compile(
    r"(?i)(?:\bjobId\b|\bthreadId\b|\blocalGuardJobCapability\b|"
    r"\blocalGuardThreadCapability\b)"
)
CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:gh[opusr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|"
    r"sk-[A-Za-z0-9_-]{12,}|bearer\s+[A-Za-z0-9._-]{12,}|"
    r"https://[^/\s:@]+:[^@\s]+@github\.com|"
    r"(?:OPENAI_API_KEY|GH_TOKEN|GITHUB_TOKEN|TUNNEL_TOKEN|CODEX_PRIVATE)\s*=|"
    r"(?:Tunnel[ _-]?ID|API[ _-]?key)\s*[:=])"
)


class RelayError(Exception):
    pass


class RelayAlreadyRunning(RelayError):
    pass


class GitHubError(RelayError):
    pass


class GuardMcpError(RelayError):
    def __init__(self, code):
        super().__init__("Guard returned an MCP error")
        self.code = code


class AdmissionError(RelayError):
    pass


class DuplicateRequestError(AdmissionError):
    pass


class ResultSecurityError(RelayError):
    pass


class OperatorConfig:
    """Explicit operator inputs; never create or repair installed Guard storage."""
    def __init__(self, repository, authors, prefixes, installation, registry=None, registry_hash=None):
        if (not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
                or not isinstance(authors, list) or not authors
                or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', x) for x in authors)
                or len(set(authors)) != len(authors)
                or not isinstance(prefixes, dict) or not prefixes
                or any(not isinstance(a, str) or not ALIAS.fullmatch(a) or not isinstance(p, str)
                       or not p.endswith('/') or not re.fullmatch(r'[A-Za-z0-9._/-]+', p)
                       for a, p in prefixes.items())
                or not isinstance(installation, str) or not re.fullmatch(r'[0-9a-f]{64}', installation)):
            raise RelayError('OPERATOR_CONFIG_REJECTED')
        self.repository = repository.lower()
        self.authors = authors
        self.prefixes = prefixes
        self.installation = installation
        self.registry = registry
        self.registry_hash = registry_hash
        self.scope = digest([installation, self.repository])

    @classmethod
    def load(cls, path):
        try:
            path = Path(path)
            verify_regular_private_file(path)
            if not path.is_absolute() or path.resolve() != path or path.stat().st_uid != os.getuid():
                raise ValueError('unsafe config')
            with path.open('rb') as stream:
                cfg = plistlib.load(stream)
            if any(cfg.get(k) != v for k, v in [('preset','managed-repo'),
                    ('sandbox','workspace-write'), ('approval_policy','never')]):
                raise ValueError('policy mismatch')
            enabled = cfg['relay_enabled_aliases']
            if (not isinstance(enabled, list) or not enabled or len(set(enabled)) != len(enabled)
                    or any(not isinstance(a, str) or not ALIAS.fullmatch(a) for a in enabled)):
                raise ValueError('invalid enabled aliases')
            registry = Registry(cfg['managed_registry'])
            document = registry.load(verify_live=True)
            entries = {e['alias']: e for e in document['repos']}
            if any(a not in entries for a in enabled):
                raise ValueError('enabled alias not registered')
            prefixes = {a: entries[a]['workBranchPrefix'] for a in enabled}
            # Optional constraint can only narrow the registry, never override it.
            if 'relay_branch_prefixes' in cfg and cfg['relay_branch_prefixes'] != prefixes:
                raise ValueError('prefix mismatch')
            key = Path(cfg['job_state_dir']) / 'capability.key'
            verify_regular_private_file(key)
            meta = key.stat()
            if key.resolve() != key or meta.st_uid != os.getuid() or meta.st_nlink != 1 or meta.st_size != 32:
                raise ValueError('invalid existing installation key')
            installation = hashlib.sha256(b'relay-installation-v1\0' + key.read_bytes()).hexdigest()
            return cls(cfg['relay_control_repository'], cfg['relay_allowed_authors'],
                       prefixes, installation, registry, canonical_hash(document))
        except (OSError, ValueError, TypeError, KeyError, ManagedRepoError,
                plistlib.InvalidFileException, ExpatError) as error:
            raise RelayError('OPERATOR_CONFIG_REJECTED') from error

    def authorize(self, alias):
        if alias not in self.prefixes:
            raise AdmissionError('alias is not transport enabled')
        if self.registry is not None:
            try:
                entry, _ = self.registry.resolve(alias, self.registry_hash)
            except ManagedRepoError as error:
                raise AdmissionError('registry authorization changed') from error
            if entry['workBranchPrefix'] != self.prefixes[alias]:
                raise AdmissionError('registry prefix changed')
        return self.prefixes[alias]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strict_json_loads(value):
    def reject_duplicate_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise AdmissionError("duplicate JSON key")
            result[key] = item
        return result

    try:
        return json.loads(value, object_pairs_hook=reject_duplicate_keys)
    except AdmissionError:
        raise
    except (TypeError, ValueError) as error:
        raise AdmissionError("invalid JSON payload") from error


def extract_job_payload(body):
    if not isinstance(body, str):
        raise AdmissionError("issue body must be text")
    stripped = body.strip()
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL)
    payload_text = fence.group(1).strip() if fence else stripped
    if not payload_text or "```" in payload_text:
        raise AdmissionError("ambiguous issue body")
    payload = strict_json_loads(payload_text)
    if not isinstance(payload, dict):
        raise AdmissionError("payload must be an object")
    return payload


def validate_job_payload(payload, config=None):
    if not isinstance(payload, dict):
        raise AdmissionError("payload must be an object")
    if payload.get("schema") != "codex_bridge_job_v1":
        raise AdmissionError("unknown schema")
    request_id = payload.get("requestId")
    if not isinstance(request_id, str):
        raise AdmissionError("requestId must be UUID text")
    try:
        parsed_request_id = uuid.UUID(request_id)
    except (ValueError, AttributeError) as error:
        raise AdmissionError("requestId must be a UUID") from error
    if str(parsed_request_id) != request_id.lower():
        raise AdmissionError("requestId must use canonical UUID form")
    operation = payload.get("operation")
    if not isinstance(operation, str):
        raise AdmissionError("operation must be text")
    expected_fields = {
        "start": START_JOB_FIELDS,
        "reply": REPLY_JOB_FIELDS,
        "publish": PUBLISH_JOB_FIELDS,
        "query": QUERY_JOB_FIELDS,
        "review": REVIEW_JOB_FIELDS,
    }.get(operation)
    if expected_fields is None:
        raise AdmissionError("operation is not allowed")
    if set(payload) != expected_fields:
        raise AdmissionError("unknown or missing payload field")
    if operation == "start":
        if not isinstance(payload.get("repoAlias"), str) or not ALIAS.fullmatch(payload['repoAlias']):
            raise AdmissionError("repoAlias is invalid")
        if config is None:
            raise AdmissionError("operator configuration required")
        config.authorize(payload['repoAlias'])
        task_name = payload.get("taskName")
        if (
            not isinstance(task_name, str)
            or not task_name
            or len(task_name) > TASK_NAME_MAX_CHARS
        ):
            raise AdmissionError("taskName is invalid")
    if operation in {"start", "reply"}:
        prompt = payload.get("prompt")
        if (
            not isinstance(prompt, str)
            or len(prompt) > PROMPT_MAX_CHARS
            or len(prompt.encode("utf-8")) > PROMPT_MAX_CHARS
        ):
            raise AdmissionError("prompt is invalid")
    if operation in {"reply", "publish", "query", "review"}:
        relay_job_ref = payload.get("relayJobRef")
        if not isinstance(relay_job_ref, str) or not RELAY_REF_PATTERN.fullmatch(
            relay_job_ref
        ):
            raise AdmissionError("relayJobRef is invalid")
    if operation == "publish":
        commit_message = payload.get("commitMessage")
        if (
            not isinstance(commit_message, str)
            or not commit_message
            or len(commit_message) > COMMIT_MESSAGE_MAX_CHARS
            or "\x00" in commit_message
        ):
            raise AdmissionError("commitMessage is invalid")
    if operation == 'review':
        if (not isinstance(payload['evidenceRequestId'], str)
                or not re.fullmatch(r'[0-9a-f-]{36}', payload['evidenceRequestId'])
                or not isinstance(payload['evidenceDigest'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', payload['evidenceDigest'])
                or payload['conclusion'] not in ('accepted', 'changes_requested')):
            raise AdmissionError('invalid review')
    return dict(payload)


def issue_label_names(issue):
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return set()
    names = set()
    for label in labels:
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and isinstance(label.get("name"), str):
            names.add(label["name"])
    return names


def validate_issue_envelope(issue, repository, config):
    if repository != config.repository:
        raise AdmissionError("wrong repository")
    if not isinstance(issue, dict) or issue.get("state") != "open":
        raise AdmissionError("issue must be open")
    if "pull_request" in issue:
        raise AdmissionError("pull requests are not jobs")
    if issue.get('repository_url') != 'https://api.github.com/repos/' + config.repository:
        raise AdmissionError('wrong issue source')
    user = issue.get("user")
    if not isinstance(user, dict) or user.get("login") not in config.authors:
        raise AdmissionError("wrong issue author")
    if JOB_LABEL not in issue_label_names(issue):
        raise AdmissionError("missing bridge-job label")
    number = issue.get("number")
    if not isinstance(number, int) or number <= 0:
        raise AdmissionError("invalid issue number")
    return number


def make_relay_job_ref():
    return "rjob_" + secrets.token_urlsafe(24)


def verify_regular_private_file(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise RelayError("required local file is missing") from error
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise RelayError("local file is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RelayError("local file mode is not 0600")


class SingleInstanceLock:
    def __init__(self, path=LOCK_PATH):
        self.path = Path(path)
        self.descriptor = None

    def acquire(self):
        parent = self.path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise RelayError("unsafe relay state directory")
        if self.path.exists() or self.path.is_symlink():
            verify_regular_private_file(self.path)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(str(self.path), flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise RelayError("relay lock is not a regular file")
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RelayAlreadyRunning("relay is already running") from error
            path_metadata = self.path.lstat()
            if (
                path_metadata.st_dev != metadata.st_dev
                or path_metadata.st_ino != metadata.st_ino
            ):
                raise RelayError("relay lock path changed during acquisition")
        except Exception:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        verify_regular_private_file(self.path)
        return self

    def close(self):
        if self.descriptor is None:
            return
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self.descriptor)
            self.descriptor = None


class RelayDatabase:
    LEGACY_COLUMNS = {
        "requestId",
        "issueNumber",
        "bodySHA256",
        "relayJobRef",
        "localGuardJobCapability",
        "localGuardThreadCapability",
        "status",
        "createdAt",
        "updatedAt",
    }
    V2_COLUMNS = LEGACY_COLUMNS | {"operation", "repoAlias", "workBranch"}
    V3_COLUMNS = V2_COLUMNS | {
        "resultPayload",
        "deliveryState",
        "deliveredAt",
    }

    CURRENT_COLUMNS = V3_COLUMNS | {'observation', 'evidence', 'reviewRecord', 'protocolVersion'}

    def __init__(self, path=STATE_PATH, config=None, legacy_scope=None):
        if config is None:
            raise RelayError('operator configuration required')
        self.config = config
        self.legacy_scope = legacy_scope
        self.path = Path(path)
        self._prepare_path()
        self.connection = sqlite3.connect(str(self.path), timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        try:
            self._ensure_schema()
        except Exception:
            self.connection.close()
            raise
        os.chmod(self.path, 0o600)
        verify_regular_private_file(self.path)

    def _create_v3_table(self):
        self.connection.execute(
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
                resultPayload TEXT,
                deliveryState TEXT NOT NULL CHECK (
                    deliveryState IN ('none', 'pending', 'delivered', 'legacy')
                ),
                deliveredAt TEXT,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX relay_start_ref_unique
            ON relay_jobs(relayJobRef) WHERE operation = 'start'
            """
        )

    def _ensure_schema(self):
        columns = {row['name'] for row in self.connection.execute('PRAGMA table_info(relay_jobs)')}
        version = self.connection.execute('PRAGMA user_version').fetchone()[0]
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            if columns == self.CURRENT_COLUMNS and version == 4:
                scope = self.connection.execute('SELECT scope FROM relay_scope WHERE singleton=1').fetchone()
                if scope is None or scope[0] != self.config.scope:
                    raise RelayError('JOURNAL_SCOPE_MISMATCH')
            elif not columns or (columns == self.V3_COLUMNS and version == 3):
                if columns:
                    count = self.connection.execute('SELECT count(*) FROM relay_jobs').fetchone()[0]
                    if count and self.legacy_scope != self.config.scope:
                        raise RelayError('OPERATOR_MIGRATION_REQUIRED')
                else:
                    self._create_v3_table()
                for field in ('observation', 'evidence', 'reviewRecord'):
                    self.connection.execute('ALTER TABLE relay_jobs ADD COLUMN ' + field + ' TEXT')
                self.connection.execute('ALTER TABLE relay_jobs ADD COLUMN protocolVersion INTEGER NOT NULL DEFAULT 1')
                self.connection.execute('CREATE TABLE relay_scope (singleton INTEGER PRIMARY KEY CHECK(singleton=1), scope TEXT NOT NULL)')
                self.connection.execute('INSERT INTO relay_scope VALUES (1, ?)', (self.config.scope,))
                self.connection.execute('PRAGMA user_version=4')
            else:
                raise RelayError('OPERATOR_MIGRATION_REQUIRED')
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _prepare_path(self):
        parent = self.path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise RelayError("unsafe relay state directory")
        if self.path.exists() or self.path.is_symlink():
            verify_regular_private_file(self.path)
            return
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(str(self.path), flags, 0o600)
        os.close(descriptor)
        os.chmod(self.path, 0o600)

    def close(self):
        self.connection.close()

    def get_by_issue(self, issue_number):
        return self.connection.execute(
            "SELECT * FROM relay_jobs WHERE issueNumber = ?", (issue_number,)
        ).fetchone()

    def get_by_request(self, request_id):
        return self.connection.execute(
            "SELECT * FROM relay_jobs WHERE requestId = ?", (request_id,)
        ).fetchone()

    def resolve_start(self, relay_job_ref, executing=True):
        row = self.connection.execute(
            """
            SELECT * FROM relay_jobs
            WHERE operation = 'start' AND relayJobRef = ?
            """,
            (relay_job_ref,),
        ).fetchone()
        if row is None or (executing and row["status"] != "completed"):
            raise AdmissionError("unknown or incomplete relayJobRef")
        if not executing:
            return row
        alias = row["repoAlias"]
        prefix = self.config.authorize(alias)
        branch = row["workBranch"]
        thread_capability = row["localGuardThreadCapability"]
        if (
            not isinstance(branch, str)
            or not branch.startswith(prefix)
            or not isinstance(thread_capability, str)
            or not thread_capability
        ):
            raise AdmissionError("relayJobRef mapping is invalid")
        return row

    def admit(
        self,
        request_id,
        issue_number,
        body_hash,
        operation,
        relay_job_ref,
        repo_alias,
        work_branch=None,
        thread_capability=None,
    ):
        now = utc_now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            existing_issue = self.get_by_issue(issue_number)
            if existing_issue is not None:
                self.connection.rollback()
                return existing_issue, False
            if self.get_by_request(request_id) is not None:
                raise DuplicateRequestError("duplicate requestId")
            if operation in ('reply', 'publish') and self.connection.execute(
                    "SELECT 1 FROM relay_jobs WHERE relayJobRef=? AND operation IN ('start','reply','publish') AND status IN ('queued','running')",
                    (relay_job_ref,)).fetchone():
                raise AdmissionError('task is busy')
            self.connection.execute(
                """
                INSERT INTO relay_jobs (
                    requestId, issueNumber, bodySHA256, operation, relayJobRef,
                    repoAlias, workBranch,
                    localGuardJobCapability, localGuardThreadCapability,
                    status, resultPayload, deliveryState, deliveredAt,
                    createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'queued', NULL, 'none', NULL, ?, ?)
                """,
                (
                    request_id,
                    issue_number,
                    body_hash,
                    operation,
                    relay_job_ref,
                    repo_alias,
                    work_branch,
                    thread_capability,
                    now,
                    now,
                ),
            )
            self.connection.execute('UPDATE relay_jobs SET protocolVersion=2 WHERE requestId=?', (request_id,))
            self.connection.commit()
            return self.get_by_issue(issue_number), True
        except Exception:
            self.connection.rollback()
            raise

    def update_guard_state(
        self,
        request_id,
        status,
        job_capability=None,
        thread_capability=None,
        work_branch=None,
    ):
        self.connection.execute(
            """
            UPDATE relay_jobs
            SET status = ?,
                localGuardJobCapability = COALESCE(?, localGuardJobCapability),
                localGuardThreadCapability = COALESCE(?, localGuardThreadCapability),
                workBranch = COALESCE(?, workBranch),
                updatedAt = ?
            WHERE requestId = ?
            """,
            (
                status,
                job_capability,
                thread_capability,
                work_branch,
                utc_now(),
                request_id,
            ),
        )
        self.connection.commit()

    def active_jobs(self):
        return self.connection.execute(
            """
            SELECT * FROM relay_jobs
            WHERE operation IN ('start','reply','publish') AND status IN ('queued', 'running')
            ORDER BY createdAt
            """
        ).fetchall()

    def unbound_active_jobs(self):
        return self.connection.execute(
            """
            SELECT * FROM relay_jobs
            WHERE status IN ('queued', 'running')
              AND localGuardJobCapability IS NULL
            ORDER BY createdAt
            """
        ).fetchall()

    def pending_results(self):
        return self.connection.execute(
            """
            SELECT * FROM relay_jobs
            WHERE deliveryState = 'pending' AND resultPayload IS NOT NULL
            ORDER BY updatedAt
            """
        ).fetchall()

    def legacy_results(self):
        return self.connection.execute(
            """
            SELECT * FROM relay_jobs
            WHERE deliveryState = 'legacy'
            ORDER BY updatedAt
            """
        ).fetchall()

    def latest_execution(self, reference):
        return self.connection.execute("SELECT * FROM relay_jobs WHERE relayJobRef=? AND operation IN ('start','reply') ORDER BY rowid DESC LIMIT 1", (reference,)).fetchone()

    def observe(self, request_id, state):
        phase = state.get('phase', 'unknown')
        if phase not in ('queued', 'running', 'thread/started', 'thread/resumed', 'turn/started',
                         'item/completed', 'turn/completed', 'unknown'):
            phase = 'unknown'
        observed = state.get('updatedAt')
        if type(observed) not in (int, float) or not 0 < observed < 1e12:
            observed = None
        observation = dict(observedAt=observed, phase=phase)
        evidence = state.get('evidence', empty_evidence())
        try:
            row = self.get_by_request(request_id)
            validate_evidence(evidence, (row['localGuardJobCapability'], row['localGuardThreadCapability']))
        except ValueError as error:
            raise ResultSecurityError('unsafe evidence') from error
        self.connection.execute('UPDATE relay_jobs SET observation=?, evidence=? WHERE requestId=?',
                                (json.dumps(observation), json.dumps(evidence), request_id))
        self.connection.commit()

    def snapshot(self, row):
        observation = json.loads(row['observation']) if row['observation'] else dict(observedAt=None, phase='unknown')
        observed = observation['observedAt']
        evidence = json.loads(row['evidence']) if row['evidence'] else empty_evidence()
        review = self.connection.execute("SELECT reviewRecord FROM relay_jobs WHERE relayJobRef=? AND reviewRecord IS NOT NULL ORDER BY rowid DESC", (row['relayJobRef'],)).fetchall()
        evidence_digest = digest(evidence)
        matching = [json.loads(r[0]) for r in review if json.loads(r[0])['evidenceRequestId'] == row['requestId'] and json.loads(r[0])['evidenceDigest'] == evidence_digest]
        return dict(executionRequestId=row['requestId'], executionState=row['status'],
                    observedAt=observed, phase=observation['phase'],
                    freshness='unknown' if observed is None else ('stale' if time.time()-observed > 120 else 'current'),
                    deliveryState=row['deliveryState'], reviewState='recorded' if matching else 'unreviewed',
                    review=matching[0] if matching else None, evidence=evidence, evidenceDigest=evidence_digest)

    def persist_result(self, request_id, payload):
        now = utc_now()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.get_by_request(request_id)
            if row is None:
                raise RelayError("result request mapping changed")
            if row['status'] in TERMINAL_STATUSES and row['resultPayload'] is not None:
                if json.loads(row['resultPayload']) != payload:
                    raise RelayError('terminal result is immutable')
                self.connection.rollback()
                return
            validate_result_for_row(row, payload)
            encoded = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            self.connection.execute(
                """
                UPDATE relay_jobs
                SET status = ?, resultPayload = ?, deliveryState = 'pending',
                    deliveredAt = NULL, updatedAt = ?
                WHERE requestId = ?
                """,
                (payload["status"], encoded, now, request_id),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def restore_active(self, request_id, status):
        if status not in {"queued", "running"}:
            raise RelayError("active Guard status is invalid")
        self.connection.execute(
            """
            UPDATE relay_jobs
            SET status = ?, resultPayload = NULL, deliveryState = 'none',
                deliveredAt = NULL, updatedAt = ?
            WHERE requestId = ?
            """,
            (status, utc_now(), request_id),
        )
        self.connection.commit()

    def mark_delivered(self, request_id):
        now = utc_now()
        self.connection.execute(
            """
            UPDATE relay_jobs
            SET deliveryState = 'delivered', deliveredAt = ?, updatedAt = ?
            WHERE requestId = ? AND deliveryState = 'pending'
            """,
            (now, now, request_id),
        )
        self.connection.commit()


class GitHubClient:
    def __init__(self, gh_bin=None, config=None):
        if config is None:
            raise RelayError('operator configuration required')
        self.config = config
        resolved = gh_bin or "gh"
        self.gh_bin = resolved

    def auth_ok(self):
        result = subprocess.run(
            [self.gh_bin, "auth", "status", "--hostname", "github.com"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=20,
        )
        return result.returncode == 0

    def _api(self, method, endpoint, payload=None):
        arguments = [self.gh_bin, "api", "--method", method, endpoint]
        input_bytes = None
        if payload is not None:
            arguments.extend(["--input", "-"])
            input_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result = subprocess.run(
            arguments,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise GitHubError("GitHub API request failed")
        if not result.stdout:
            return None
        try:
            return json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise GitHubError("GitHub API response was invalid") from error

    def ensure_labels(self):
        owner, repository = self.config.repository.split("/", 1)
        for name, (color, description) in LABEL_DEFINITIONS.items():
            encoded = urllib.parse.quote(name, safe="")
            endpoint = "/repos/{}/{}/labels/{}".format(owner, repository, encoded)
            try:
                self._api("GET", endpoint)
                continue
            except GitHubError:
                pass
            self._api(
                "POST",
                "/repos/{}/{}/labels".format(owner, repository),
                {"name": name, "color": color, "description": description},
            )

    def list_open_jobs(self):
        owner, repository = self.config.repository.split("/", 1)
        endpoint = (
            "/repos/{}/{}/issues?state=open&labels={}&per_page=100&sort=created&direction=asc"
        ).format(owner, repository, urllib.parse.quote(JOB_LABEL, safe=""))
        issues = []
        page = 1
        while True:
            batch = self._api("GET", endpoint + "&page={}".format(page))
            if not isinstance(batch, list):
                raise GitHubError("GitHub issue list was invalid")
            issues.extend(batch)
            if len(batch) < 100:
                return issues
            page += 1

    def get_issue(self, issue_number):
        issue = self._api(
            "GET", "/repos/{}/issues/{}".format(self.config.repository, issue_number)
        )
        if not isinstance(issue, dict):
            raise GitHubError("GitHub issue response was invalid")
        return issue

    def set_status_label(self, issue_number, status):
        if status not in STATUS_LABELS:
            raise RelayError("unknown relay label status")
        issue = self.get_issue(issue_number)
        labels = issue_label_names(issue)
        labels = {name for name in labels if name not in set(STATUS_LABELS.values())}
        labels.add(JOB_LABEL)
        labels.add(STATUS_LABELS[status])
        self._api(
            "PATCH",
            "/repos/{}/issues/{}".format(self.config.repository, issue_number),
            {"labels": sorted(labels)},
        )

    def mark_rejected(self, issue_number):
        issue = self.get_issue(issue_number)
        labels = issue_label_names(issue)
        labels = {
            name
            for name in labels
            if name != JOB_LABEL and name not in set(STATUS_LABELS.values())
        }
        labels.add(STATUS_LABELS["failed"])
        self._api(
            "PATCH",
            "/repos/{}/issues/{}".format(self.config.repository, issue_number),
            {"labels": sorted(labels)},
        )

    def comment(self, issue_number, body):
        self._api(
            "POST",
            "/repos/{}/issues/{}/comments".format(self.config.repository, issue_number),
            {"body": body},
        )

    def result_comments(self, issue_number):
        comments = []
        page = 1
        while True:
            batch = self._api(
                "GET",
                "/repos/{}/issues/{}/comments?per_page=100&page={}".format(
                    self.config.repository, issue_number, page
                ),
            )
            if not isinstance(batch, list):
                raise GitHubError("GitHub comment list was invalid")
            for comment in batch:
                body = comment.get("body") if isinstance(comment, dict) else None
                user = comment.get("user") if isinstance(comment, dict) else None
                if (
                    isinstance(user, dict)
                    and user.get("login") in self.config.authors
                    and isinstance(body, str)
                    and body.startswith(("BRIDGE_RESULT_V1\n", "BRIDGE_RESULT_V2\n"))
                ):
                    comments.append(body)
            if len(batch) < 100:
                return comments
            page += 1

class GuardMcpClient:
    def __init__(self, guard_runner=GUARD_RUNNER, config_path=CONFIG_PATH, timeout=60):
        self.guard_runner = Path(guard_runner)
        self.config_path = Path(config_path)
        self.timeout = timeout
        self.next_id = 1
        self.process = None

    def start(self):
        verify_regular_private_file(self.config_path)
        if self.guard_runner.is_symlink() or not self.guard_runner.is_file():
            raise RelayError("installed Guard runner is unavailable")
        environment = {}
        for name in ("HOME", "USER", "LOGNAME", "PATH", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME"):
            if name in os.environ:
                environment[name] = os.environ[name]
        environment["CHATGPT_CODEX_BRIDGE_CONFIG"] = str(self.config_path)
        self.process = subprocess.Popen(
            ["/bin/zsh", str(self.guard_runner)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            cwd=str(Path.home()),
            env=environment,
            bufsize=1,
        )
        initialized = self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "github-issue-relay", "version": "1.0"},
            },
        )
        if not isinstance(initialized, dict):
            raise RelayError("Guard initialize failed")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        listed = self._request("tools/list", {})
        tools = listed.get("tools") if isinstance(listed, dict) else None
        if not isinstance(tools, list):
            raise RelayError("Guard tools/list failed")
        names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        if not REQUIRED_TOOLS.issubset(names):
            raise RelayError("required Guard tools are unavailable")
        return names

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None

    def _send(self, message):
        if self.process is None or self.process.stdin is None:
            raise RelayError("Guard is not running")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _receive(self, request_id, timeout=None):
        if self.process is None or self.process.stdout is None:
            raise RelayError("Guard is not running")
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RelayError("Guard exited")
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not readable:
                break
            line = self.process.stdout.readline()
            if not line:
                raise RelayError("Guard output closed")
            try:
                message = json.loads(line)
            except ValueError as error:
                raise RelayError("Guard emitted invalid JSON") from error
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    error = message.get("error")
                    code = error.get("code") if isinstance(error, dict) else None
                    raise GuardMcpError(code if isinstance(code, int) else 0)
                return message.get("result")
            if "method" in message and "id" in message:
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32601, "message": "Unsupported server request"},
                    }
                )
        raise RelayError("Guard MCP request timed out")

    def _request(self, method, params, timeout=None):
        request_id = self.next_id
        self.next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        return self._receive(request_id, timeout=timeout)

    def call_tool(self, name, arguments):
        if name not in CALLABLE_TOOLS:
            raise RelayError("tool call is not allowed")
        timeout = REPO_START_TIMEOUT_SECONDS if name == "codex-repo-start" else None
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout=timeout,
        )
        if not isinstance(result, dict) or result.get("isError") is True:
            raise RelayError("Guard tool call failed")
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            raise RelayError("Guard tool result is invalid")
        return structured


SUPERVISION_FIELDS = {'executionRequestId', 'executionState', 'observedAt', 'phase',
                      'freshness', 'deliveryState', 'reviewState', 'review', 'evidence', 'evidenceDigest'}


def validate_supervision(value):
    if not isinstance(value, dict) or set(value) != SUPERVISION_FIELDS:
        raise RelayError('invalid supervision fields')
    if (not isinstance(value['executionRequestId'], str)
            or not re.fullmatch(r'[0-9a-f-]{36}', value['executionRequestId'])
            or value['executionState'] not in TERMINAL_STATUSES | {'queued','running'}
            or value['freshness'] not in ('current','stale','unknown')
            or value['deliveryState'] not in ('none','pending','delivered','legacy')
            or value['reviewState'] not in ('unreviewed','recorded')
            or value['phase'] not in ('queued','running','thread/started','thread/resumed',
                                     'turn/started','item/completed','turn/completed','unknown')
            or (value['observedAt'] is not None and (type(value['observedAt']) not in (float,int)
                or not 0 < value['observedAt'] < 1e12))):
        raise RelayError('invalid supervision state')
    try:
        validate_evidence(value['evidence'])
    except ValueError as error:
        raise ResultSecurityError('invalid evidence') from error
    if digest(value['evidence']) != value['evidenceDigest']:
        raise RelayError('evidence digest mismatch')
    review = value['review']
    if review is not None:
        if (not isinstance(review, dict) or set(review) != {'evidenceRequestId','evidenceDigest','author','conclusion'}
                or review['evidenceRequestId'] != value['executionRequestId']
                or review['evidenceDigest'] != value['evidenceDigest']
                or review['conclusion'] not in ('accepted','changes_requested')
                or not isinstance(review['author'], str)
                or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', review['author'])):
            raise RelayError('invalid review record')
    if (review is None) != (value['reviewState'] == 'unreviewed'):
        raise RelayError('review state mismatch')
    if not safe_text(json.dumps(value, ensure_ascii=False)):
        raise ResultSecurityError('unsafe supervision')


def validate_public_result(payload):
    original = payload
    v2 = isinstance(payload, dict) and payload.get('schema') == 'bridge_result_v2'
    if v2:
        if set(payload) != CONTENT_RESULT_FIELDS | {'schema','supervision'}:
            raise RelayError('invalid V2 result fields')
        validate_supervision(payload['supervision'])
        payload = {k: v for k, v in payload.items() if k not in ('schema','supervision')}
    if not isinstance(payload, dict) or set(payload) not in (
        CONTENT_RESULT_FIELDS,
        PUBLISH_RESULT_FIELDS,
    ):
        raise RelayError("result has unknown or missing fields")
    repo_alias = payload.get("repoAlias")
    if not isinstance(repo_alias, str) or not ALIAS.fullmatch(repo_alias):
        raise RelayError("result repository alias is invalid")
    if not isinstance(payload.get("requestId"), str):
        raise RelayError("result requestId is invalid")
    if not isinstance(payload.get("relayJobRef"), str) or not RELAY_REF_PATTERN.fullmatch(
        payload["relayJobRef"]
    ):
        raise RelayError("result relayJobRef is invalid")
    if set(payload) == CONTENT_RESULT_FIELDS:
        if payload.get("publishAvailable") is not False:
            raise RelayError("result authority is invalid")
        if payload.get("status") not in (TERMINAL_STATUSES | ({"queued","running"} if v2 else set())):
            raise RelayError("result status is invalid")
        if (
            not isinstance(payload.get("content"), str)
            or len(payload["content"]) > CONTENT_MAX_CHARS
        ):
            raise RelayError("result content is invalid")
        if not isinstance(payload.get("contentTruncated"), bool):
            raise RelayError("result truncation flag is invalid")
    else:
        status = payload.get("status")
        branch = payload.get("branch")
        commit = payload.get("commit")
        if status not in {"completed", "failed"}:
            raise RelayError("publish result status is invalid")
        if not isinstance(payload.get("pushed"), bool) or not isinstance(
            payload.get("baseStale"), bool
        ):
            raise RelayError("publish result flags are invalid")
        if status == "completed":
            if (
                not isinstance(branch, str)
                or not re.fullmatch(r"(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]+(?<![./])", branch)
                or not isinstance(commit, str)
                or re.fullmatch(r"[0-9a-f]{40}", commit) is None
                or payload["pushed"] is not True
            ):
                raise RelayError("publish result authority is invalid")
        elif (
            branch != ""
            or commit != ""
            or payload["pushed"] is not False
            or payload["baseStale"] is not False
        ):
            raise RelayError("failed publish result is invalid")
    return original


def assert_safe_content(content, capabilities=()):
    for capability in capabilities:
        if capability and capability in content:
            raise ResultSecurityError("Guard capability detected")
    if CAPABILITY_FIELD_PATTERN.search(content):
        raise ResultSecurityError("Guard capability field detected")
    if ABSOLUTE_LOCAL_PATH_PATTERN.search(content):
        raise ResultSecurityError("absolute local path detected")
    if CREDENTIAL_PATTERN.search(content):
        raise ResultSecurityError("credential-shaped content detected")


def build_public_result(
    request_id,
    relay_job_ref,
    status,
    content,
    capabilities=(),
    source_truncated=False,
    repo_alias=None,
):
    if status not in TERMINAL_STATUSES or not isinstance(content, str):
        raise RelayError("terminal result is invalid")
    assert_safe_content(content, capabilities)
    content_truncated = bool(source_truncated)
    if len(content) > CONTENT_MAX_CHARS:
        content = content[:CONTENT_MAX_CHARS]
        content_truncated = True
    payload = {
        "requestId": request_id,
        "relayJobRef": relay_job_ref,
        "status": status,
        "repoAlias": repo_alias,
        "content": content,
        "contentTruncated": content_truncated,
        "publishAvailable": False,
    }
    return validate_public_result(payload)


def build_publish_result(
    request_id,
    relay_job_ref,
    status,
    repo_alias,
    branch,
    commit,
    pushed,
    base_stale,
):
    payload = {
        "requestId": request_id,
        "relayJobRef": relay_job_ref,
        "status": status,
        "repoAlias": repo_alias,
        "branch": branch,
        "commit": commit,
        "pushed": pushed,
        "baseStale": base_stale,
    }
    return validate_public_result(payload)


def format_result_comment(payload):
    validate_public_result(payload)
    return "{}\n\n```json\n{}\n```".format(
        'BRIDGE_RESULT_V2' if payload.get('schema') == 'bridge_result_v2' else 'BRIDGE_RESULT_V1',
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    )


def validate_result_for_row(row, payload):
    validate_public_result(payload)
    if (
        payload["requestId"] != row["requestId"]
        or payload["relayJobRef"] != row["relayJobRef"]
        or payload["repoAlias"] != row["repoAlias"]
        or (
            payload["status"] != row["status"]
            and row["status"] in TERMINAL_STATUSES
            and row["deliveryState"] in {"pending", "delivered"}
        )
    ):
        raise RelayError("result relay mapping changed")
    if row["operation"] == "publish":
        if set(payload) != PUBLISH_RESULT_FIELDS:
            raise RelayError("result operation changed")
    elif set(payload) not in (CONTENT_RESULT_FIELDS, CONTENT_RESULT_FIELDS | {'schema','supervision'}):
        raise RelayError("result operation changed")
    else:
        assert_safe_content(
            payload["content"],
            capabilities=(
                row["localGuardJobCapability"],
                row["localGuardThreadCapability"],
            ),
        )
    if payload.get('schema') == 'bridge_result_v2':
        serialized = json.dumps(payload, ensure_ascii=False)
        assert_safe_content(serialized, (row['localGuardJobCapability'], row['localGuardThreadCapability']))
    return payload


class GitHubIssueRelay:
    def __init__(self, database, github, mcp_factory=None):
        self.config = database.config
        self.database = database
        self.github = github
        self.mcp_factory = mcp_factory or GuardMcpClient

    def admit_issue(self, issue, repository=None):
        repository = self.config.repository if repository is None else repository
        issue_number = validate_issue_envelope(issue, repository, self.config)
        existing = self.database.get_by_issue(issue_number)
        if existing is not None:
            return existing, None, False
        body = issue.get("body")
        payload = validate_job_payload(extract_job_payload(body), self.config)
        operation = payload["operation"]
        if operation == "start":
            relay_job_ref = make_relay_job_ref()
            repo_alias = payload["repoAlias"]
            work_branch = None
            thread_capability = None
        else:
            relay_job_ref = payload["relayJobRef"]
            mapping = self.database.resolve_start(relay_job_ref, executing=operation in ("reply", "publish"))
            repo_alias = mapping["repoAlias"]
            work_branch = mapping["workBranch"]
            thread_capability = mapping["localGuardThreadCapability"]
        if operation == 'review':
            evidence_row = self.database.get_by_request(payload['evidenceRequestId'])
            if (evidence_row is None or evidence_row['relayJobRef'] != relay_job_ref
                    or evidence_row['operation'] not in ('start','reply')
                    or evidence_row['status'] not in TERMINAL_STATUSES
                    or evidence_row['evidence'] is None
                    or digest(json.loads(evidence_row['evidence'])) != payload['evidenceDigest']):
                raise AdmissionError('review evidence mismatch')
        row, admitted = self.database.admit(
            payload["requestId"],
            issue_number,
            sha256_text(body),
            operation,
            relay_job_ref,
            repo_alias,
            work_branch,
            thread_capability,
        )
        return row, payload if admitted else None, admitted

    def reject_issue(self, issue_number):
        self.github.mark_rejected(issue_number)
        self.github.comment(issue_number, "BRIDGE_ADMISSION_REJECTED_V1\n\nreason=invalid_request")

    def _managed_identity(self, row, state, terminal=False):
        thread_capability = state.get("threadId") or row["localGuardThreadCapability"]
        repo_alias = state.get("repoAlias")
        work_branch = state.get("workBranch")
        if state.get("jobId") != row["localGuardJobCapability"]:
            raise RelayError("Guard job identity changed")
        if state.get("threadId") is not None and not isinstance(
            state.get("threadId"), str
        ):
            raise RelayError("Guard returned an invalid thread capability")
        if row["operation"] == "reply" and state.get("threadId") not in (
            None,
            row["localGuardThreadCapability"],
        ):
            raise RelayError("Guard reply changed thread identity")
        if repo_alias is not None and repo_alias != row["repoAlias"]:
            raise RelayError("Guard managed repository changed")
        if work_branch is not None and (
            not isinstance(work_branch, str)
            or not work_branch.startswith(self.config.prefixes.get(row["repoAlias"], "\0"))
            or (
                row["operation"] == "reply"
                and work_branch != row["workBranch"]
            )
        ):
            raise RelayError("Guard managed branch changed")
        if terminal and (
            not isinstance(thread_capability, str)
            or not thread_capability
            or repo_alias != row["repoAlias"]
            or not isinstance(work_branch, str)
        ):
            raise RelayError("Guard terminal managed identity is incomplete")
        return thread_capability, work_branch

    def _terminal_result(self, row, terminal):
        status = terminal.get("status")
        content = terminal.get("content")
        if status not in TERMINAL_STATUSES or not isinstance(content, str):
            raise RelayError("Guard terminal result is invalid")
        thread_capability, work_branch = self._managed_identity(
            row, terminal, terminal=True
        )
        self.database.update_guard_state(
            row["requestId"],
            "running",
            row["localGuardJobCapability"],
            thread_capability,
            work_branch,
        )
        capabilities = tuple(
            value
            for value in (row["localGuardJobCapability"], thread_capability)
            if isinstance(value, str)
        )
        self.database.observe(row['requestId'], terminal)
        current = self.database.get_by_request(row['requestId'])
        payload = build_public_result(
            row["requestId"],
            row["relayJobRef"],
            status,
            content,
            capabilities=capabilities,
            source_truncated=terminal.get("contentTruncated") is True,
            repo_alias=row["repoAlias"],
        )
        if row['protocolVersion'] == 2:
            payload['schema'] = 'bridge_result_v2'
            payload['supervision'] = self.database.snapshot(current)
            payload['supervision']['executionState'] = status
        return payload

    def _projection_result(self, row, source, content='Stored task supervision.'):
        payload = build_public_result(row['requestId'], row['relayJobRef'], 'completed',
                                      content, repo_alias=row['repoAlias'])
        payload.update(schema='bridge_result_v2', supervision=self.database.snapshot(source))
        return payload

    def _query_or_review(self, row, payload, issue):
        if row['operation'] == 'review':
            record = {k: payload[k] for k in ('evidenceRequestId','evidenceDigest','conclusion')}
            record['author'] = issue['user']['login']
            self.database.connection.execute('UPDATE relay_jobs SET reviewRecord=? WHERE requestId=?',
                                             (json.dumps(record), row['requestId']))
            self.database.connection.commit()
            source = self.database.get_by_request(payload['evidenceRequestId'])
        else:
            source = self.database.latest_execution(row['relayJobRef'])
        return self._projection_result(row, source)

    def _progress_result(self, row):
        if row['protocolVersion'] != 2 or row['resultPayload'] is not None:
            return
        payload = self._projection_result(row, row, 'Execution observed; terminal evidence pending.')
        payload['status'] = row['status']
        self.database.persist_result(row['requestId'], payload)

    def _start_async(self, row, payload):
        client = self.mcp_factory()
        thread_capability = row["localGuardThreadCapability"]
        try:
            client.start()
            if row["operation"] == "start":
                tool_name = "codex-repo-start"
                arguments = {
                    "repoAlias": row["repoAlias"],
                    "prompt": payload["prompt"],
                    "taskName": payload["taskName"],
                }
            elif row["operation"] == "reply":
                tool_name = "codex-reply-async"
                arguments = {
                    "threadId": thread_capability,
                    "prompt": payload["prompt"],
                }
            else:
                raise RelayError("operation is not asynchronous")
            started = client.call_tool(tool_name, arguments)
            job_capability = started.get("jobId")
            if not isinstance(job_capability, str) or not job_capability:
                raise RelayError("Guard did not return a job capability")
            observed_status = started.get('status')
            if observed_status not in TERMINAL_STATUSES | {'queued', 'running'}:
                raise RelayError('Guard start status is invalid')
            active_status = observed_status if observed_status in {'queued','running'} else 'running'
            self.database.update_guard_state(
                row["requestId"], active_status, job_capability, thread_capability
            )
            current = self.database.get_by_request(row["requestId"])
            started_thread, started_branch = self._managed_identity(current, started)
            self.database.update_guard_state(
                row["requestId"],
                active_status,
                job_capability,
                started_thread,
                started_branch,
            )
            self.database.observe(row['requestId'], started)
            if started.get("status") in TERMINAL_STATUSES:
                current = self.database.get_by_request(row["requestId"])
                self.database.persist_result(
                    row["requestId"], self._terminal_result(current, started)
                )
        finally:
            client.close()

    def _execute_publish(self, row, payload):
        client = self.mcp_factory()
        try:
            client.start()
            terminal = client.call_tool(
                "codex-repo-publish",
                {
                    "threadId": row["localGuardThreadCapability"],
                    "commitMessage": payload["commitMessage"],
                },
            )
            if set(terminal) != {"branch", "commit", "pushed", "base_stale"}:
                raise RelayError("Guard publish result is not closed")
            if (not isinstance(terminal['branch'], str) or terminal['branch'] != row['workBranch']
                    or not terminal['branch'].startswith(self.config.authorize(row['repoAlias']))):
                raise RelayError('publish branch mismatch')
            return build_publish_result(
                row["requestId"],
                row["relayJobRef"],
                "completed",
                row["repoAlias"],
                terminal["branch"],
                terminal["commit"],
                terminal["pushed"],
                terminal["base_stale"],
            )
        finally:
            client.close()

    def _failed_result(self, row):
        if row["operation"] == "publish":
            return build_publish_result(
                row["requestId"],
                row["relayJobRef"],
                "failed",
                row["repoAlias"],
                "",
                "",
                False,
                False,
            )
        payload = build_public_result(
            row["requestId"],
            row["relayJobRef"],
            "interrupted",
            "Execution outcome unknown or interrupted; no automatic replay.",
            repo_alias=row["repoAlias"],
        )

        if row['protocolVersion'] == 2:
            current = self.database.get_by_request(row['requestId'])
            payload.update(schema='bridge_result_v2', supervision=self.database.snapshot(current))
            payload['supervision']['executionState'] = 'interrupted'
        return payload

    @staticmethod
    def _parse_result_comment(row, body):
        match = re.fullmatch(
            r"BRIDGE_RESULT_V[12]\n\n```json\n(.*)\n```", body, re.DOTALL
        )
        if match is None:
            return None
        try:
            payload = strict_json_loads(match.group(1))
            validate_result_for_row(row, payload)
        except RelayError:
            return None
        legacy_body = "BRIDGE_RESULT_V1\n\n```json\n{}\n```".format(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
        if (
            payload["requestId"] != row["requestId"]
            or payload["relayJobRef"] != row["relayJobRef"]
            or payload["repoAlias"] != row["repoAlias"]
            or payload["status"] != row["status"]
            or body not in ((format_result_comment(payload), legacy_body) if "schema" not in payload else (format_result_comment(payload),))
        ):
            return None
        return payload

    def process_issue(self, issue):
        issue_number = issue.get("number") if isinstance(issue, dict) else None
        try:
            row, payload, admitted = self.admit_issue(issue)
        except AdmissionError:
            if (type(issue_number) is int and issue_number > 0 and isinstance(issue, dict)
                    and issue.get('repository_url') == 'https://api.github.com/repos/' + self.config.repository):
                try:
                    self.reject_issue(issue_number)
                except GitHubError:
                    pass
            return None
        if not admitted:
            return None
        try:
            self.github.set_status_label(row["issueNumber"], "queued")
        except GitHubError:
            pass
        result = None
        try:
            if row['operation'] in ('query','review'):
                result = self._query_or_review(row, payload, issue)
                self.database.persist_result(row['requestId'], result)
            elif row["operation"] == "publish":
                self.database.update_guard_state(row["requestId"], "running")
                result = self._execute_publish(row, payload)
                self.database.persist_result(row["requestId"], result)
            else:
                self._start_async(row, payload)
                current = self.database.get_by_request(row['requestId'])
                if current['status'] in ('queued','running'):
                    self._progress_result(current)
        except (RelayError, OSError, subprocess.SubprocessError):
            result = self._failed_result(row)
            self.database.persist_result(row["requestId"], result)
        try:
            self.github.set_status_label(row["issueNumber"], "running")
        except GitHubError:
            pass
        return result

    def reconcile_unbound_active_jobs(self):
        for row in self.database.unbound_active_jobs():
            self.database.persist_result(row["requestId"], self._failed_result(row))

    def supervise_active_jobs(self):
        rows = [
            row
            for row in self.database.active_jobs()
            if isinstance(row["localGuardJobCapability"], str)
            and row["localGuardJobCapability"]
        ]
        if not rows:
            return
        client = self.mcp_factory()
        try:
            try:
                client.start()
            except (RelayError, OSError, subprocess.SubprocessError):
                return
            for row in rows:
                try:
                    state = client.call_tool(
                        "codex-job-status",
                        {"jobId": row["localGuardJobCapability"]},
                    )
                except GuardMcpError as error:
                    if error.code == -32602:
                        self.database.persist_result(
                            row["requestId"], self._failed_result(row)
                        )
                    continue
                except (RelayError, OSError, subprocess.SubprocessError):
                    continue
                status = state.get("status")
                if status in TERMINAL_STATUSES:
                    try:
                        result = self._terminal_result(row, state)
                    except RelayError:
                        result = self._failed_result(row)
                    self.database.persist_result(row["requestId"], result)
                elif status in {"queued", "running"}:
                    try:
                        self.database.observe(row['requestId'], state)
                        thread_capability, work_branch = self._managed_identity(
                            row, state
                        )
                        self.database.update_guard_state(
                            row["requestId"],
                            status,
                            row["localGuardJobCapability"],
                            thread_capability,
                            work_branch,
                        )
                        self._progress_result(self.database.get_by_request(row['requestId']))
                    except RelayError:
                        self.database.persist_result(
                            row["requestId"], self._failed_result(row)
                        )
                else:
                    self.database.persist_result(
                        row["requestId"], self._failed_result(row)
                    )
        finally:
            client.close()

    def reconcile_legacy_results(self):
        for row in self.database.legacy_results():
            try:
                comments = self.github.result_comments(row["issueNumber"])
            except GitHubError:
                continue
            existing = next(
                (
                    payload
                    for payload in (
                        self._parse_result_comment(row, body) for body in comments
                    )
                    if payload is not None
                ),
                None,
            )
            if existing is not None:
                self.database.persist_result(row["requestId"], existing)
                continue
            job_capability = row["localGuardJobCapability"]
            if not isinstance(job_capability, str) or not job_capability:
                self.database.persist_result(row["requestId"], self._failed_result(row))
                continue
            client = self.mcp_factory()
            try:
                try:
                    client.start()
                    state = client.call_tool(
                        "codex-job-status", {"jobId": job_capability}
                    )
                except GuardMcpError as error:
                    if error.code == -32602:
                        self.database.persist_result(
                            row["requestId"], self._failed_result(row)
                        )
                    continue
                except (RelayError, OSError, subprocess.SubprocessError):
                    continue
                status = state.get("status")
                if status in TERMINAL_STATUSES:
                    try:
                        result = self._terminal_result(row, state)
                    except RelayError:
                        result = self._failed_result(row)
                    self.database.persist_result(row["requestId"], result)
                elif status in {"queued", "running"}:
                    self.database.restore_active(row["requestId"], status)
                else:
                    self.database.persist_result(
                        row["requestId"], self._failed_result(row)
                    )
            finally:
                client.close()

    def deliver_pending_results(self):
        for row in self.database.pending_results():
            try:
                payload = strict_json_loads(row["resultPayload"])
                validate_result_for_row(row, payload)
                body = format_result_comment(payload)
                comments = self.github.result_comments(row["issueNumber"])
                matching_comment = body in comments or any(
                    parsed == payload
                    for parsed in (
                        self._parse_result_comment(row, comment)
                        for comment in comments
                    )
                    if parsed is not None
                )
                if not matching_comment:
                    self.github.comment(row["issueNumber"], body)
                github_status = (
                    payload["status"] if payload["status"] in {"queued", "running", "completed"} else "failed"
                )
                self.github.set_status_label(row["issueNumber"], github_status)
            except GitHubError:
                continue
            self.database.mark_delivered(row["requestId"])

    def recover_incomplete(self):
        self.reconcile_unbound_active_jobs()
        self.supervise_active_jobs()

    def run_once(self):
        self.reconcile_unbound_active_jobs()
        self.supervise_active_jobs()
        self.reconcile_legacy_results()
        self.deliver_pending_results()
        try:
            issues = self.github.list_open_jobs()
        except GitHubError:
            return
        for issue in issues:
            self.process_issue(issue)
        self.deliver_pending_results()


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description="GitHub-controlled Managed Codex relay")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--watch", action="store_true")
    parser.add_argument('--config')
    parser.add_argument('--state', type=Path, default=STATE_PATH)
    parser.add_argument('--legacy-scope')
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_arguments(argv or sys.argv[1:])
    try:
        config = OperatorConfig.load(arguments.config)
    except RelayError:
        print('{"error":"OPERATOR_CONFIG_REJECTED"}', file=sys.stderr)
        return 64
    instance_lock = SingleInstanceLock(arguments.state.with_suffix('.lock'))
    try:
        instance_lock.acquire()
    except RelayAlreadyRunning:
        return 0
    except (RelayError, OSError):
        print('{"error":"RELAY_LOCK_REJECTED"}', file=sys.stderr)
        return 1
    database = None
    try:
        database = RelayDatabase(arguments.state, config, arguments.legacy_scope)
        github = GitHubClient(config=config)
        if not github.auth_ok():
            print(
                "github-relay: GitHub authentication unavailable; stopped",
                file=sys.stderr,
            )
            return 78
        github.ensure_labels()
        relay = GitHubIssueRelay(database, github, lambda: GuardMcpClient(config_path=arguments.config))
        if arguments.once:
            relay.run_once()
            return 0
        while True:
            relay.run_once()
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    except (RelayError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        code = str(error) if str(error) in {'JOURNAL_SCOPE_MISMATCH','OPERATOR_MIGRATION_REQUIRED'} else 'RELAY_STOPPED'
        print(json.dumps({'error':code}), file=sys.stderr)
        return 1
    finally:
        if database is not None:
            database.close()
        instance_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
