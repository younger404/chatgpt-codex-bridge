#!/usr/bin/python3
"""Operator-owned registry and Git boundary for managed repositories."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import string
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


REGISTRY_VERSION = "managed_repo_registry_v1"
ALIAS_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,62}")
FULL_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REMOTE_NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
BRANCH_PATTERN = re.compile(r"(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]+(?<![./])")
DEPLOYMENT_TIERS = {"none", "local-loopback", "staging", "production"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
GIB = 1024 ** 3
LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_RETAINED = "RETAINED_UNPUBLISHED"
LIFECYCLE_ELIGIBLE = "GC_ELIGIBLE"
LIFECYCLE_REMOVED = "GC_REMOVED"
WATERMARK_NORMAL = "NORMAL"
WATERMARK_SOFT = "SOFT"
WATERMARK_HARD = "HARD"
WATERMARK_EMERGENCY = "EMERGENCY"
RETAINED_ACTIVE_WORKER = "ACTIVE_WORKER"
RETAINED_ACTIVE_LOCAL_PROCESS = "ACTIVE_LOCAL_PROCESS"
RETAINED_DIRTY = "DIRTY_WORKTREE"
RETAINED_IGNORED = "IGNORED_WORKTREE_CONTENT"
RETAINED_UNPUBLISHED = "UNPUBLISHED_WORK"
RETAINED_OUTSIDE_ROOT = "OUTSIDE_MANAGED_ROOT"
RETAINED_UNSAFE_PATH = "SYMLINK_OR_CANONICALIZATION_FAILURE"
RETAINED_IDENTITY = "REGISTRY_OR_REPOSITORY_IDENTITY_MISMATCH"
RETAINED_GIT_METADATA = "GIT_WORKTREE_METADATA_MISMATCH"
RETAINED_UNKNOWN = "UNKNOWN_OWNERSHIP"
RETAINED_REMOVAL_FAILED = "WORKTREE_REMOVAL_FAILED"
RETAINED_PRUNE_FAILED = "WORKTREE_PRUNE_FAILED"
WORKSPACE_NOT_SAFE_TO_GC = "WORKSPACE_NOT_SAFE_TO_GC"
DISK_PRESSURE_ERROR = "MANAGED_WORKSPACE_DISK_PRESSURE"
MANAGED_GROUP_CONTEXT_FIELDS = (
    "workspace", "repoAlias", "repositoryFullName", "repoPath", "baseRemote",
    "baseBranch", "baseRevision", "workBranch", "registryCanonicalHash",
    "preset", "sandbox", "approvalPolicy",
)


class ManagedRepoError(Exception):
    """Fail-closed managed repository policy error."""


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def disk_usage_snapshot(path, usage_provider=None):
    provider = usage_provider or shutil.disk_usage
    try:
        usage = provider(path)
        total, used, free = usage.total, usage.used, usage.free
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise ManagedRepoError("managed workspace disk usage is unavailable") from error
    values = (total, used, free)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ManagedRepoError("managed workspace disk usage is invalid")
    if total <= 0 or used < 0 or free < 0 or used > total or free > total:
        raise ManagedRepoError("managed workspace disk usage is invalid")
    return {"total": total, "used": total - free, "free": free}


def disk_watermark(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {"total", "used", "free"}:
        raise ManagedRepoError("managed workspace disk usage is invalid")
    total = snapshot["total"]
    free = snapshot["free"]
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (total, snapshot["used"], free)
    ) or total <= 0 or free < 0 or free > total:
        raise ManagedRepoError("managed workspace disk usage is invalid")
    emergency = max(8 * GIB, (total * 5 + 99) // 100)
    hard = max(16 * GIB, (total * 10 + 99) // 100)
    soft = max(24 * GIB, (total * 15 + 99) // 100)
    if free < emergency:
        return WATERMARK_EMERGENCY
    if free < hard:
        return WATERMARK_HARD
    if free < soft:
        return WATERMARK_SOFT
    return WATERMARK_NORMAL


def gc_metrics(before, after, outcomes):
    reasons = {}
    removed = 0
    retained = 0
    for outcome in outcomes:
        if outcome.get("lifecycleState") == LIFECYCLE_REMOVED:
            removed += 1
        else:
            retained += 1
            reason = outcome.get("retainedReason") or RETAINED_UNKNOWN
            reasons[reason] = reasons.get(reason, 0) + 1
    bytes_before = before["total"] - before["free"]
    bytes_after = after["total"] - after["free"]
    return {
        "bytesBefore": bytes_before,
        "bytesAfter": bytes_after,
        "reclaimedBytes": max(0, bytes_before - bytes_after),
        "consideredJobCount": len(outcomes),
        "removedJobCount": removed,
        "retainedJobCount": retained,
        "retainedReasons": {key: reasons[key] for key in sorted(reasons)},
        "watermarkState": disk_watermark(before),
        "freeBytesBefore": before["free"],
        "freeBytesAfter": after["free"],
    }


def require_canonical_absolute_path(raw, want_directory=True):
    if not isinstance(raw, str) or not os.path.isabs(raw):
        raise ManagedRepoError("path must be absolute")
    if os.path.normpath(raw) != raw or os.path.realpath(raw) != raw:
        raise ManagedRepoError("path must be canonical and contain no symlinks")
    path = Path(raw)
    if path.is_symlink() or (want_directory and not path.is_dir()):
        raise ManagedRepoError("path has the wrong type")
    if not want_directory and not path.is_file():
        raise ManagedRepoError("path has the wrong type")
    return raw


def normalize_github_remote(raw):
    if not isinstance(raw, str):
        raise ManagedRepoError("remote URL is invalid")
    value = raw.strip()
    patterns = (
        r"git@github\.com:([^/\s]+/[^/\s]+?)(?:\.git)?$",
        r"ssh://git@github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?$",
        r"https://github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?/?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, value, flags=re.IGNORECASE)
        if match:
            full_name = match.group(1)
            if FULL_NAME_PATTERN.fullmatch(full_name):
                return "github:" + full_name.lower()
    raise ManagedRepoError("only canonical GitHub SSH or HTTPS remotes are supported")


def _run(command, cwd=None, timeout=120, check=True):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env={key: value for key, value in os.environ.items() if key != "GIT_DIR"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ManagedRepoError("managed command failed to run") from error
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise ManagedRepoError(detail[:2000])
    return result


def _git(repo_path, *arguments, timeout=120, check=True):
    return _run(["git", "-C", repo_path, *arguments], timeout=timeout, check=check)


def _validate_branch(raw, field):
    if not isinstance(raw, str) or not BRANCH_PATTERN.fullmatch(raw):
        raise ManagedRepoError(field + " is invalid")
    probe = _run(["git", "check-ref-format", "refs/heads/" + raw], check=False)
    if probe.returncode != 0:
        raise ManagedRepoError(field + " is invalid")
    return raw


def _validate_check(raw):
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) > 32
        or any(not isinstance(item, str) or not item or "\x00" in item for item in raw)
    ):
        raise ManagedRepoError("prePublishChecks entries must be non-empty argv arrays")
    executable = raw[0]
    if not os.path.isabs(executable):
        raise ManagedRepoError("prePublishChecks executables must be absolute")
    require_canonical_absolute_path(executable, want_directory=False)
    if not os.access(executable, os.X_OK):
        raise ManagedRepoError("prePublishChecks executable is not executable")
    return list(raw)


def _validate_local_target(raw):
    if not isinstance(raw, dict) or set(raw) != {"name", "executable", "argv", "host"}:
        raise ManagedRepoError("localLoopbackTargets entry is invalid")
    name = raw.get("name")
    if not isinstance(name, str) or not ALIAS_PATTERN.fullmatch(name):
        raise ManagedRepoError("local target name is invalid")
    executable = require_canonical_absolute_path(raw.get("executable"), want_directory=False)
    if not os.access(executable, os.X_OK):
        raise ManagedRepoError("local target executable is not executable")
    argv = raw.get("argv")
    if not isinstance(argv, list) or len(argv) > 32 or any(
        not isinstance(item, str) or "\x00" in item for item in argv
    ):
        raise ManagedRepoError("local target argv is invalid")
    if not any("{host}" in item for item in argv):
        raise ManagedRepoError("local target argv must bind the registered host")
    host = raw.get("host")
    if host not in LOOPBACK_HOSTS:
        raise ManagedRepoError("local target must bind to loopback")
    return {"name": name, "executable": executable, "argv": list(argv), "host": host}


def validate_entry(raw, verify_live=True):
    allowed = {
        "alias", "repoPath", "repositoryFullName", "baseRemote", "baseBranch",
        "protectedBranches", "workBranchPrefix", "deploymentTier",
        "prePublishChecks", "localLoopbackTargets",
    }
    required = allowed - {"prePublishChecks", "localLoopbackTargets"}
    if not isinstance(raw, dict) or not required.issubset(raw) or not set(raw).issubset(allowed):
        raise ManagedRepoError("registry entry fields are invalid")
    alias = raw.get("alias")
    if not isinstance(alias, str) or not ALIAS_PATTERN.fullmatch(alias):
        raise ManagedRepoError("alias is invalid")
    repo_path = require_canonical_absolute_path(raw.get("repoPath"))
    full_name = raw.get("repositoryFullName")
    if not isinstance(full_name, str) or not FULL_NAME_PATTERN.fullmatch(full_name):
        raise ManagedRepoError("repositoryFullName is invalid")
    base_remote = raw.get("baseRemote")
    if not isinstance(base_remote, str) or not REMOTE_NAME_PATTERN.fullmatch(base_remote):
        raise ManagedRepoError("baseRemote is invalid")
    base_branch = _validate_branch(raw.get("baseBranch"), "baseBranch")
    protected = raw.get("protectedBranches")
    if not isinstance(protected, list) or not protected:
        raise ManagedRepoError("protectedBranches must not be empty")
    protected = [_validate_branch(item, "protected branch") for item in protected]
    if len(set(protected)) != len(protected) or base_branch not in protected:
        raise ManagedRepoError("protectedBranches must uniquely include baseBranch")
    prefix = raw.get("workBranchPrefix")
    if not isinstance(prefix, str) or not prefix.endswith("/"):
        raise ManagedRepoError("workBranchPrefix must end with slash")
    _validate_branch(prefix + "probe", "workBranchPrefix")
    tier = raw.get("deploymentTier")
    if tier not in DEPLOYMENT_TIERS:
        raise ManagedRepoError("deploymentTier is invalid")
    checks = [_validate_check(item) for item in raw.get("prePublishChecks", [])]
    targets = [_validate_local_target(item) for item in raw.get("localLoopbackTargets", [])]
    if tier != "local-loopback" and targets:
        raise ManagedRepoError("local targets require local-loopback tier")
    if len({item["name"] for item in targets}) != len(targets):
        raise ManagedRepoError("local target names must be unique")
    entry = {
        "alias": alias,
        "repoPath": repo_path,
        "repositoryFullName": full_name,
        "baseRemote": base_remote,
        "baseBranch": base_branch,
        "protectedBranches": protected,
        "workBranchPrefix": prefix,
        "deploymentTier": tier,
        "prePublishChecks": checks,
        "localLoopbackTargets": targets,
    }
    if verify_live:
        verify_entry(entry)
    return entry


def verify_entry(entry):
    repo_path = entry["repoPath"]
    inside = _git(repo_path, "rev-parse", "--is-inside-work-tree").stdout.strip()
    top = _git(repo_path, "rev-parse", "--show-toplevel").stdout.strip()
    if inside != "true" or top != repo_path:
        raise ManagedRepoError("repoPath must be the canonical Git worktree root")
    remote = _git(repo_path, "remote", "get-url", entry["baseRemote"]).stdout.strip()
    expected = "github:" + entry["repositoryFullName"].lower()
    if normalize_github_remote(remote) != expected:
        raise ManagedRepoError("registered repository identity does not match its remote")
    local = _git(
        repo_path,
        "show-ref", "--verify", "--quiet",
        "refs/heads/" + entry["baseBranch"],
        check=False,
    )
    remote_ref = _git(
        repo_path,
        "show-ref", "--verify", "--quiet",
        "refs/remotes/" + entry["baseRemote"] + "/" + entry["baseBranch"],
        check=False,
    )
    if local.returncode != 0 and remote_ref.returncode != 0:
        raise ManagedRepoError("base branch does not exist locally or on the registered remote")
    return True


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute() or os.path.normpath(str(self.path)) != str(self.path):
            raise ManagedRepoError("registry path must be canonical and absolute")
        if self.path.parent.is_symlink():
            raise ManagedRepoError("registry directory must not be a symlink")

    def load(self, require_exists=True, verify_live=False):
        if not self.path.exists():
            if require_exists:
                raise ManagedRepoError("managed repository registry does not exist")
            return {"registryVersion": REGISTRY_VERSION, "repos": []}
        if self.path.is_symlink() or not self.path.is_file() or os.path.realpath(self.path) != str(self.path):
            raise ManagedRepoError("registry must be a canonical regular file")
        if stat.S_IMODE(self.path.stat().st_mode) != 0o600:
            raise ManagedRepoError("registry mode must be 0600")
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ManagedRepoError("registry JSON is invalid") from error
        if not isinstance(document, dict) or set(document) != {"registryVersion", "repos"}:
            raise ManagedRepoError("registry document fields are invalid")
        if document.get("registryVersion") != REGISTRY_VERSION or not isinstance(document.get("repos"), list):
            raise ManagedRepoError("registry version or repos is invalid")
        entries = [validate_entry(item, verify_live=verify_live) for item in document["repos"]]
        aliases = [item["alias"] for item in entries]
        if len(set(aliases)) != len(aliases):
            raise ManagedRepoError("registry aliases must be unique")
        entries.sort(key=lambda item: item["alias"])
        return {"registryVersion": REGISTRY_VERSION, "repos": entries}

    def write(self, document):
        parent = self.path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if parent.is_symlink() or os.path.realpath(parent) != str(parent):
            raise ManagedRepoError("registry directory must be canonical")
        os.chmod(parent, 0o700)
        validated = {
            "registryVersion": REGISTRY_VERSION,
            "repos": [validate_entry(item, verify_live=True) for item in document["repos"]],
        }
        validated["repos"].sort(key=lambda item: item["alias"])
        payload = (_canonical_json(validated) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".tmp.", dir=parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return validated

    def resolve(self, alias, expected_hash=None):
        document = self.load(verify_live=True)
        digest = canonical_hash(document)
        if expected_hash is not None and digest != expected_hash:
            raise ManagedRepoError("registry changed; restart the bridge")
        for entry in document["repos"]:
            if entry["alias"] == alias:
                return entry, digest
        raise ManagedRepoError("unknown repository alias")


def allocate_worktree(workspace, entry, internal_job_id):
    require_canonical_absolute_path(workspace)
    if not re.fullmatch(r"[0-9a-f-]{36}", internal_job_id):
        raise ManagedRepoError("job id is invalid")
    verify_entry(entry)
    repo = entry["repoPath"]
    remote = entry["baseRemote"]
    base = entry["baseBranch"]
    _git(repo, "fetch", "--no-tags", "--prune", remote, base, timeout=300)
    remote_ref = "refs/remotes/" + remote + "/" + base
    revision = _git(repo, "rev-parse", "--verify", remote_ref + "^{commit}").stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ManagedRepoError("base revision is invalid")
    branch = entry["workBranchPrefix"] + entry["alias"] + "/" + internal_job_id[:8]
    _validate_branch(branch, "generated work branch")
    if branch in entry["protectedBranches"]:
        raise ManagedRepoError("generated branch is protected")
    worktree = Path(workspace) / "managed" / entry["alias"] / internal_job_id
    worktree.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if worktree.exists() or worktree.is_symlink():
        raise ManagedRepoError("managed worktree already exists")
    _git(repo, "worktree", "add", "-b", branch, str(worktree), revision, timeout=300)
    return {
        "workspace": require_canonical_absolute_path(str(worktree)),
        "baseRevision": revision,
        "workBranch": branch,
    }


def validate_managed_context(record, entry, registry_hash):
    expected = {
        "repoAlias": entry["alias"],
        "repositoryFullName": entry["repositoryFullName"],
        "repoPath": entry["repoPath"],
        "baseRemote": entry["baseRemote"],
        "baseBranch": entry["baseBranch"],
        "registryCanonicalHash": registry_hash,
        "preset": "managed-repo",
        "sandbox": "workspace-write",
        "approvalPolicy": "never",
    }
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise ManagedRepoError("managed capability context mismatch")
    revision = record.get("baseRevision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ManagedRepoError("managed base revision is invalid")
    branch = _validate_branch(record.get("workBranch"), "recorded work branch")
    if branch in entry["protectedBranches"] or not branch.startswith(entry["workBranchPrefix"]):
        raise ManagedRepoError("recorded work branch is outside policy")
    return branch


def validate_managed_record(record, entry, registry_hash):
    branch = validate_managed_context(record, entry, registry_hash)
    workspace = require_canonical_absolute_path(record.get("workspace"))
    actual_branch = _git(workspace, "branch", "--show-current").stdout.strip()
    if actual_branch != branch:
        raise ManagedRepoError("managed worktree branch mismatch")
    common = _git(workspace, "rev-parse", "--git-common-dir").stdout.strip()
    common_path = os.path.realpath(os.path.join(workspace, common))
    expected_common = os.path.realpath(os.path.join(entry["repoPath"], ".git"))
    if common_path != expected_common:
        raise ManagedRepoError("managed worktree repository mismatch")
    return workspace


def _retained(reason, lifecycle=LIFECYCLE_RETAINED):
    return {
        "lifecycleState": lifecycle,
        "removed": False,
        "retainedReason": reason,
    }


def _managed_path_reason(bridge_workspace, record):
    workspace = record.get("workspace") if isinstance(record, dict) else None
    alias = record.get("repoAlias") if isinstance(record, dict) else None
    if not isinstance(workspace, str) or not os.path.isabs(workspace):
        return RETAINED_OUTSIDE_ROOT
    if os.path.normpath(workspace) != workspace:
        return RETAINED_OUTSIDE_ROOT
    if os.path.realpath(workspace) != workspace or Path(workspace).is_symlink():
        return RETAINED_UNSAFE_PATH
    if not isinstance(alias, str) or not ALIAS_PATTERN.fullmatch(alias):
        return RETAINED_IDENTITY
    try:
        allocation_id = str(uuid.UUID(Path(workspace).name))
    except (ValueError, AttributeError, TypeError):
        return RETAINED_OUTSIDE_ROOT
    expected = Path(bridge_workspace) / "managed" / alias / allocation_id
    if str(expected) != workspace:
        return RETAINED_OUTSIDE_ROOT
    return ""


def _git_worktree_records(entry):
    result = _git(
        entry["repoPath"], "worktree", "list", "--porcelain", "-z", check=False
    )
    if result.returncode != 0:
        return None
    records = []
    current = {}
    for token in result.stdout.split("\x00"):
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = token.partition(" ")
        current[key] = value if separator else True
    if current:
        records.append(current)
    return records


def _git_worktree_matches(entry, workspace, branch):
    records = _git_worktree_records(entry)
    if records is None:
        return False
    matches = [item for item in records if item.get("worktree") == workspace]
    return len(matches) == 1 and matches[0].get("branch") == "refs/heads/" + branch


def _managed_candidate_group(bridge_workspace, candidate_records, entry, registry_hash):
    if not isinstance(candidate_records, list) or not candidate_records:
        raise ManagedRepoError("managed candidate group is invalid")
    if any(not isinstance(item, dict) for item in candidate_records):
        raise ManagedRepoError("managed candidate group is invalid")
    requests = [item.get("request") for item in candidate_records]
    states = [item.get("state") for item in candidate_records]
    if any(not isinstance(item, dict) for item in requests + states):
        raise ManagedRepoError("managed candidate group is invalid")
    workspaces = {request.get("workspace") for request in requests}
    if len(workspaces) != 1:
        raise ManagedRepoError("managed candidate workspace mismatch")
    workspace = next(iter(workspaces))
    if not isinstance(workspace, str):
        return None, None, RETAINED_OUTSIDE_ROOT
    allocation_name = Path(workspace).name
    try:
        allocation_id = str(uuid.UUID(allocation_name))
    except (ValueError, AttributeError, TypeError):
        return None, None, RETAINED_OUTSIDE_ROOT
    if allocation_id != allocation_name:
        return None, None, RETAINED_OUTSIDE_ROOT
    owners = [
        (request, state) for request, state in zip(requests, states)
        if request.get("internalJobId") == allocation_id
    ]
    if len(owners) != 1:
        raise ManagedRepoError("managed allocation owner mismatch")
    owner, owner_state = owners[0]
    path_reason = _managed_path_reason(bridge_workspace, owner)
    if path_reason:
        return None, None, path_reason
    expected_context = {
        key: owner.get(key) for key in MANAGED_GROUP_CONTEXT_FIELDS
    }
    group_internal_thread = owner_state.get("internalThreadId")
    group_thread = owner_state.get("threadId")
    if not isinstance(group_internal_thread, str) or not isinstance(group_thread, str):
        raise ManagedRepoError("managed thread identity mismatch")
    for request, state in zip(requests, states):
        if any(request.get(key) != value for key, value in expected_context.items()):
            raise ManagedRepoError("managed group context mismatch")
        validate_managed_context(request, entry, registry_hash)
        if (
            state.get("internalJobId") != request.get("internalJobId")
            or state.get("jobId") != request.get("jobId")
            or state.get("internalThreadId") != group_internal_thread
            or state.get("threadId") != group_thread
        ):
            raise ManagedRepoError("managed request state identity mismatch")
        is_owner = request.get("internalJobId") == allocation_id
        expected_request_threads = (
            ("", group_internal_thread) if is_owner else (group_internal_thread,)
        )
        expected_request_capabilities = (
            ("", group_thread) if is_owner else (group_thread,)
        )
        if (
            request.get("internalThreadId") not in expected_request_threads
            or request.get("threadId") not in expected_request_capabilities
        ):
            raise ManagedRepoError("managed request thread mismatch")
    return owner, workspace, ""


def managed_candidate_context_hash(
    bridge_workspace, candidate_records, entry, registry_hash
):
    owner, _workspace, reason = _managed_candidate_group(
        bridge_workspace, candidate_records, entry, registry_hash
    )
    if reason:
        raise ManagedRepoError("managed candidate path is unsafe")
    return canonical_hash({key: owner[key] for key in MANAGED_GROUP_CONTEXT_FIELDS})


def managed_removal_was_completed(
    bridge_workspace, candidate_records, entry, registry_hash
):
    owner, workspace, reason = _managed_candidate_group(
        bridge_workspace, candidate_records, entry, registry_hash
    )
    if reason:
        raise ManagedRepoError("managed candidate path is unsafe")
    require_canonical_absolute_path(bridge_workspace)
    require_canonical_absolute_path(str(Path(bridge_workspace) / "managed"))
    if Path(workspace).exists() or Path(workspace).is_symlink():
        return False
    records = _git_worktree_records(entry)
    if records is None:
        raise ManagedRepoError("Git worktree metadata is unavailable")
    return not any(item.get("worktree") == workspace for item in records)


def prune_managed_worktrees(entry):
    return _git(
        entry["repoPath"], "worktree", "prune", timeout=300, check=False
    ).returncode == 0


def remove_managed_worktree(entry, workspace):
    removed = _git(
        entry["repoPath"], "worktree", "remove", "--", workspace,
        timeout=300, check=False,
    )
    if removed.returncode != 0:
        return _retained(RETAINED_REMOVAL_FAILED)
    prune_failed = not prune_managed_worktrees(entry)
    outcome = {
        "lifecycleState": LIFECYCLE_REMOVED,
        "removed": True,
        "retainedReason": "",
    }
    if prune_failed:
        outcome["operatorFollowupReason"] = RETAINED_PRUNE_FAILED
    return outcome


def evaluate_managed_workspace(
    bridge_workspace, candidate_records, entry, registry_hash, remove=False
):
    try:
        owner, workspace, path_reason = _managed_candidate_group(
            bridge_workspace, candidate_records, entry, registry_hash
        )
        if path_reason:
            return _retained(path_reason)
        require_canonical_absolute_path(bridge_workspace)
        managed_root = str(Path(bridge_workspace) / "managed")
        require_canonical_absolute_path(managed_root)
        validate_managed_record(owner, entry, registry_hash)
        top = _git(workspace, "rev-parse", "--show-toplevel").stdout.strip()
        if top != workspace:
            return _retained(RETAINED_GIT_METADATA)
        if not _git_worktree_matches(entry, workspace, owner["workBranch"]):
            return _retained(RETAINED_GIT_METADATA)
    except ManagedRepoError:
        return _retained(RETAINED_IDENTITY)

    for item in candidate_records:
        worker_state = item.get("workerState", "unknown")
        local_state = item.get("localProcessState", "unknown")
        if worker_state == "active" or item["state"].get("status") in ("queued", "running"):
            return _retained(RETAINED_ACTIVE_WORKER, LIFECYCLE_ACTIVE)
        if local_state == "active":
            return _retained(RETAINED_ACTIVE_LOCAL_PROCESS, LIFECYCLE_ACTIVE)
        if worker_state != "inactive" or local_state != "inactive":
            return _retained(RETAINED_UNKNOWN)
        if item["state"].get("status") not in ("completed", "failed", "interrupted"):
            return _retained(RETAINED_UNKNOWN)

    status = _git(
        workspace, "status", "--porcelain=v1", "--untracked-files=all", check=False
    )
    if status.returncode != 0:
        return _retained(RETAINED_UNKNOWN)
    if status.stdout:
        return _retained(RETAINED_DIRTY)
    ignored = _git(
        workspace, "ls-files", "--others", "--ignored", "--exclude-standard", "-z",
        check=False,
    )
    if ignored.returncode != 0:
        return _retained(RETAINED_UNKNOWN)
    if ignored.stdout:
        return _retained(RETAINED_IGNORED)
    head_result = _git(workspace, "rev-parse", "--verify", "HEAD^{commit}", check=False)
    if head_result.returncode != 0:
        return _retained(RETAINED_UNKNOWN)
    head = head_result.stdout.strip()
    if head != owner["baseRevision"]:
        remote = _git(
            workspace,
            "ls-remote",
            "--heads",
            entry["baseRemote"],
            "refs/heads/" + owner["workBranch"],
            check=False,
            timeout=120,
        )
        lines = [line.split() for line in remote.stdout.splitlines() if line.strip()]
        if (
            remote.returncode != 0
            or len(lines) != 1
            or len(lines[0]) != 2
            or lines[0][0] != head
            or lines[0][1] != "refs/heads/" + owner["workBranch"]
        ):
            return _retained(RETAINED_UNPUBLISHED)
    if not remove:
        return {
            "lifecycleState": LIFECYCLE_ELIGIBLE,
            "removed": False,
            "retainedReason": "",
        }
    return remove_managed_worktree(entry, workspace)


def publish(record, entry, registry_hash, commit_message):
    if not isinstance(commit_message, str) or not commit_message.strip() or len(commit_message.encode("utf-8")) > 4096:
        raise ManagedRepoError("commitMessage is invalid")
    workspace = validate_managed_record(record, entry, registry_hash)
    _git(workspace, "diff", "--check")
    for command in entry["prePublishChecks"]:
        _run(command, cwd=workspace, timeout=900)
    _git(workspace, "add", "--all")
    staged = _git(workspace, "diff", "--cached", "--quiet", check=False)
    if staged.returncode not in (0, 1):
        raise ManagedRepoError("unable to inspect staged changes")
    if staged.returncode == 1:
        _git(workspace, "commit", "-m", commit_message.strip(), timeout=300)
    commit = _git(workspace, "rev-parse", "HEAD^{commit}").stdout.strip()
    remote = entry["baseRemote"]
    base = entry["baseBranch"]
    _git(workspace, "fetch", "--no-tags", remote, base, timeout=300)
    latest_base = _git(
        workspace,
        "rev-parse", "--verify", "refs/remotes/" + remote + "/" + base + "^{commit}",
    ).stdout.strip()
    base_stale = latest_base != record.get("baseRevision")
    branch = record["workBranch"]
    _git(workspace, "push", remote, "HEAD:refs/heads/" + branch, timeout=300)
    return {"branch": branch, "commit": commit, "pushed": True, "base_stale": base_stale}


def authorize_deployment(entry, requested_tier, target_name=None, release_capability=None):
    tier = entry["deploymentTier"]
    if requested_tier == "production" or tier == "production":
        raise ManagedRepoError("PRODUCTION_DEPLOYMENT_NOT_AUTHORIZED")
    if requested_tier != tier:
        raise ManagedRepoError("deployment tier mismatch")
    if tier == "none":
        raise ManagedRepoError("DEPLOYMENT_NOT_AUTHORIZED")
    if tier == "staging" and not release_capability:
        raise ManagedRepoError("STAGING_RELEASE_CAPABILITY_REQUIRED")
    if tier == "local-loopback":
        for target in entry["localLoopbackTargets"]:
            if target["name"] == target_name:
                if target["host"] not in LOOPBACK_HOSTS:
                    raise ManagedRepoError("local target must bind to loopback")
                return target
        raise ManagedRepoError("unknown local-loopback target")
    raise ManagedRepoError("deployment execution is unavailable")


def local_target_command(target, workspace):
    require_canonical_absolute_path(workspace)
    values = {"worktree": workspace, "host": target["host"]}
    command = [target["executable"]]
    formatter = string.Formatter()
    for template in target["argv"]:
        try:
            fields = {
                field_name for _, field_name, _, _ in formatter.parse(template)
                if field_name is not None
            }
            if not fields.issubset(values):
                raise ManagedRepoError("local target argv contains an unknown field")
            command.append(template.format_map(values))
        except (KeyError, ValueError) as error:
            raise ManagedRepoError("local target argv template is invalid") from error
    return command


def cli(argv=None):
    parser = argparse.ArgumentParser(description="Manage the operator-owned repository allowlist")
    parser.add_argument("--registry", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--alias", required=True)
    register.add_argument("--repo-path", "--repo", dest="repo_path", required=True)
    register.add_argument(
        "--repository-full-name", "--repository",
        dest="repository_full_name", required=True,
    )
    register.add_argument("--base-remote", default="origin")
    register.add_argument("--base-branch", default="main")
    register.add_argument(
        "--work-branch-prefix", "--branch-prefix",
        dest="work_branch_prefix", default="codex/bridge/",
    )
    register.add_argument("--deployment-tier", choices=sorted(DEPLOYMENT_TIERS), default="none")
    register.add_argument("--local-target-name")
    register.add_argument("--local-executable")
    register.add_argument("--local-arg", action="append", default=[])
    register.add_argument("--local-host", choices=sorted(LOOPBACK_HOSTS))
    commands.add_parser("list")
    verify = commands.add_parser("verify")
    verify.add_argument("alias", nargs="?")
    remove = commands.add_parser("remove")
    remove.add_argument("alias")
    arguments = parser.parse_args(argv)
    registry = Registry(arguments.registry)
    if arguments.command == "register":
        document = registry.load(require_exists=False)
        if any(item["alias"] == arguments.alias for item in document["repos"]):
            raise ManagedRepoError("alias already exists")
        local_options = (
            arguments.local_target_name,
            arguments.local_executable,
            arguments.local_host,
        )
        if arguments.deployment_tier == "local-loopback":
            if not all(local_options):
                raise ManagedRepoError(
                    "local-loopback registration requires target, executable, and host"
                )
            local_targets = [{
                "name": arguments.local_target_name,
                "executable": arguments.local_executable,
                "argv": arguments.local_arg,
                "host": arguments.local_host,
            }]
        else:
            if any(local_options) or arguments.local_arg:
                raise ManagedRepoError(
                    "local target options require local-loopback tier"
                )
            local_targets = []
        entry = {
            "alias": arguments.alias,
            "repoPath": arguments.repo_path,
            "repositoryFullName": arguments.repository_full_name,
            "baseRemote": arguments.base_remote,
            "baseBranch": arguments.base_branch,
            "protectedBranches": [arguments.base_branch],
            "workBranchPrefix": arguments.work_branch_prefix,
            "deploymentTier": arguments.deployment_tier,
            "prePublishChecks": [],
            "localLoopbackTargets": local_targets,
        }
        document["repos"].append(validate_entry(entry, verify_live=True))
        written = registry.write(document)
        print(_canonical_json({"registered": arguments.alias, "registryCanonicalHash": canonical_hash(written)}))
    elif arguments.command == "list":
        document = registry.load(verify_live=False)
        public = [{key: value for key, value in item.items() if key != "repoPath"} for item in document["repos"]]
        print(json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True))
    elif arguments.command == "verify":
        document = registry.load(verify_live=True)
        if arguments.alias and not any(item["alias"] == arguments.alias for item in document["repos"]):
            raise ManagedRepoError("unknown repository alias")
        print(_canonical_json({"verified": arguments.alias or "all", "registryCanonicalHash": canonical_hash(document)}))
    elif arguments.command == "remove":
        document = registry.load(verify_live=False)
        retained = [item for item in document["repos"] if item["alias"] != arguments.alias]
        if len(retained) == len(document["repos"]):
            raise ManagedRepoError("unknown repository alias")
        document["repos"] = retained
        written = registry.write(document)
        print(_canonical_json({"removed": arguments.alias, "registryCanonicalHash": canonical_hash(written)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(cli())
    except ManagedRepoError as error:
        print("managed-repos: " + str(error), file=sys.stderr)
        raise SystemExit(64)
