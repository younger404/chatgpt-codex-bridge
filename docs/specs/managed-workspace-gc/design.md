# Managed Workspace GC Design v1

## Architecture

```text
Guard admission lock
  -> strict complete durable jobs-v4 snapshot
  -> canonical managed root and allocation identity
  -> current operator registry identity
  -> source Git worktree metadata
  -> durable launch evidence + dirty/ignored/publication checks
  -> retained receipt | prepared GC intent
  -> git worktree remove + git worktree prune
  -> recoverable lifecycle + sanitized receipt/gc-status.json metrics
```

`managed_repo.py` owns lifecycle derivation, disk classification, exact Git
ownership checks, publication checks, and safe removal. The Guard owns durable
record enumeration, process-ownership checks, serialization, lifecycle field
updates, public tool schemas, and admission decisions. Relay remains unchanged.

## Candidate Derivation And Ownership

The Guard never scans arbitrary managed directories as deletion candidates. It
first enumerates the complete durable root under the admission lock. A canonical
UUID-named symlink, non-directory, unsafe request/status file, or malformed
managed record invalidates the whole snapshot before deletion begins. Non-UUID
root entries retain their existing job-store treatment. Valid records are grouped
by workspace. The allocation owner is selected only by equality between its
internal job ID and the workspace final UUID; candidate ordering is irrelevant.
Exactly one owner must exist. All continuations must equal that owner across the
full immutable managed context, and request/status job and thread identity must
remain coherent.

The managed library then verifies:

1. the Bridge workspace and managed root are canonical non-symlink directories;
2. the exact path is `<workspace>/managed/<registry-alias>/<allocation-uuid>`;
3. every record matches preset, sandbox, approval, registry hash, repository,
   remote, base, branch, and worktree;
4. `git rev-parse --show-toplevel` and the common Git directory match; and
5. `git worktree list --porcelain -z` from the registered source repository has
   one exact path/branch entry.

Any ambiguous or missing proof returns a retained outcome. It never becomes a
fallback deletion path.

## Lifecycle Evaluation

Under the admission lock, the Guard reconciles durable job state and annotates
each candidate with worker and local-process activity. Before either `Popen`, it
writes a `launching` record and matching status marker; after success it replaces
that record with the exact PID, process group, command, job, and workspace
identity. A crash after process creation but before the running write therefore
leaves conservative `launching` evidence. Missing evidence is inactive only for
an explicit durable `not_attempted`, `launch_failed`, or verified `stopped`
state. A live PID counts only when the existing exact command/job ownership
verifier succeeds. A live foreign PID or malformed record makes ownership
unknown and retains the workspace.

Evaluation order is intentionally conservative:

```text
ownership proof -> active/unknown process -> terminal state -> dirty/ignored state
                -> unchanged base OR exact generated remote branch -> eligible
```

Non-base commits are considered published only when `git ls-remote` reports the
generated remote branch at the exact local HEAD. Network or parse failure retains
the workspace. Eligible removal invokes only `git worktree remove` with the exact
path and then `git worktree prune` from the registered source repository. Git
status is supplemented by `git ls-files --others --ignored --exclude-standard`
so ignored-only work is protected.

Removal is two-phase. Before any destructive command, the Guard writes a
sanitized versioned per-group receipt in `prepared` phase, writes `GC_ELIGIBLE`
to every grouped status, and preflights `gc-status.json`. Only after all
pre-removal writes succeed may deletion start. After `git worktree remove`, the
receipt is advanced to `removed` and all group statuses converge to
`GC_REMOVED`. On restart, a valid prepared/removed receipt plus absence from both
the filesystem and exact Git metadata proves prior removal and finalizes all
records without re-deleting. A prune failure is a durable follow-up reason, not
a reversal of successful removal.

The lifecycle state is persisted additively in associated status records.
Removed records remain available to existing status tools and are excluded from
the retained-workspace quota. A second close recognizes the persisted removed
state without touching the filesystem.

## Locking And Triggers

The existing `admission.lock` serializes:

- startup sweep;
- pre-start disk check, sweep, recheck, and allocation;
- continuation emergency admission;
- publish and post-publish lifecycle derivation;
- local-loopback start/stop; and
- close evaluation/removal.

No background thread is introduced. A new start sweep may collect only terminal
worktrees. Continuation checks protect the selected thread workspace and do not
run a sweep that could collect it before resume.

## Disk Watermarks

A callable disk-usage provider returns total, used, and free bytes for the Bridge
workspace filesystem. Production uses the standard filesystem API; tests inject
a deterministic provider. Classification checks EMERGENCY, then HARD, then SOFT
to select the most severe crossed threshold.

`codex-repo-start` always measures, runs the safe terminal sweep, and measures
again. A post-sweep HARD or EMERGENCY state raises the stable admission error
`MANAGED_WORKSPACE_DISK_PRESSURE`. A continuation or new local target checks the
current state and rejects only EMERGENCY. Status, wait, publish, stop-local, and
close do not use the pressure rejection path.

Sweep metrics use filesystem used bytes (`total - free`) before and after. The
durable private `gc-status.json` contains only exact required numeric fields,
stable retained-reason counts, and the watermark label. Close returns only
sanitized lifecycle/status/reason fields.

Close performs the same disk snapshots and persists the same metric shape as a
sweep. Its per-group versioned receipt is private and contains only phase,
trigger, lifecycle, context hash, removal flag, and stable reason/follow-up
codes; it contains no path or raw identifier.

## Public Close Contract

`codex-repo-close` accepts exactly `{threadId}`. Capability decoding and durable
state resolve the worktree. The closed result contains `status`,
`lifecycleState`, `removed`, and `retainedReason`; it has no path, repository
path, branch selector, internal identifier, or capability echo. Safe removal
returns `GC_REMOVED`; retained work returns `WORKSPACE_NOT_SAFE_TO_GC` with one
stable reason.

## Temp Root Assessment

The desired sibling path `<bridge-workspace>/managed-tmp/...` is outside the
managed worktree cwd that currently defines the workspace-write boundary. Merely
setting `TMPDIR`, `TMP`, and `TEMP` does not grant safe sandbox access; adding the
sibling as a writable root would broaden current authority. V1 therefore leaves
the environment and sandbox unchanged and records a P1 follow-up to investigate
a Codex-supported, exact per-turn additional writable-root capability. No
persistent `/private/tmp` clone is created.

## Observability, Failure, And Rollback

Retained reason codes distinguish activity, local process, dirty or ignored work,
unpublished work, path/canonicalization, identity, Git metadata, unknown evidence,
and removal failure without including sensitive details. A persistence failure
before removal prevents deletion. A final lifecycle/metric failure after proven
removal is recovered through the durable receipt and can never authorize a
second delete attempt.

Rollback restores the prior mirrored runtime files. Additive lifecycle fields are
ignored by the prior implementation. Already removed clean worktrees remain
ordinary removed Git worktrees; all retained work and durable records remain.
