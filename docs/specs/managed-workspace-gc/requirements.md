# Managed Workspace GC Requirements v1

## Scope

This specification adds ownership-aware lifecycle closure, safe garbage
collection, and disk-watermark admission control for Bridge-owned managed
repository worktrees. It MUST preserve the existing `managed-repo` authority,
durable-job, Git publish, protected-branch, and deployment boundaries.

## Triggers And Preconditions

- The Guard MUST run in the `managed-repo` preset with `workspace-write` and
  `never` before any requirement in this specification can mutate state.
- A GC candidate MUST originate from a durable managed job record and MUST be
  evaluated under the same exclusive admission lock used for new managed jobs.
- The Bridge MUST evaluate a safe managed sweep at Guard startup where the
  durable job store is available, before every `codex-repo-start`, and during
  `codex-repo-close`.
- A successful publish MUST derive and persist the workspace lifecycle state;
  it MUST NOT require immediate deletion.

## Requirements

### GC-R1 Lifecycle States

The Bridge MUST represent or deterministically derive exactly these managed
workspace lifecycle states: `ACTIVE`, `RETAINED_UNPUBLISHED`, `GC_ELIGIBLE`,
and `GC_REMOVED`.

Acceptance: active workers or local processes derive `ACTIVE`; unsafe terminal
work derives `RETAINED_UNPUBLISHED`; a terminal clean worktree that is unchanged
from its recorded base or exactly represented on its generated remote branch
derives `GC_ELIGIBLE`; successful or previously completed safe removal derives
`GC_REMOVED`.

### GC-R2 Exact Ownership Proof

Before removal, the Bridge MUST prove one exact worktree through all of:

1. the canonical `<bridge-workspace>/managed/<alias>/<allocation-job-id>` root;
2. a durable managed job record whose allocation job ID and workspace match;
3. the current registered repository identity and canonical registry hash; and
4. source-repository Git worktree metadata matching the exact canonical path and
   generated branch.

The Bridge MUST fail closed on an outside-root path, traversal, symlink,
canonicalization failure, registry mismatch, repository mismatch, Git metadata
mismatch, unknown ownership, or incomplete durable record.

Before evaluating any deletion candidate, the Guard MUST build a complete
durable-state snapshot under the admission lock. A canonical UUID-named entry
that is a symlink, is not a directory, or contains a malformed managed record
MUST fail the sweep closed before any worktree removal. Non-UUID unrelated root
entries remain outside candidate enumeration.

The allocation owner MUST be resolved by the UUID final component of the exact
workspace path, and exactly one grouped request MUST have an `internalJobId`
equal to that UUID. Every continuation record MUST exactly match the allocation
owner for `workspace`, repository/remote/base identity including `baseRevision`,
`workBranch`, registry hash, preset, sandbox, and approval policy. Request/status
job identity and the durable internal-thread grouping MUST also be coherent.

Acceptance: focused tests MUST prove that foreign directories, symlink escapes,
traversal paths, and wrong repository identities are retained.

### GC-R3 Protected Work

The Bridge MUST NOT automatically remove a worktree while any associated job is
queued or running, any exactly owned worker remains alive, any registered local
loopback process remains alive, the worktree is dirty, or local commits are not
verified as unchanged from the recorded base or exactly present at the generated
remote branch.

The Guard MUST persist a pre-launch `launching` record before creating either a
worker or registered local process and MUST transition it atomically to an exact
running identity after successful process creation. Missing, malformed,
`launching`, unknown, or unverifiable launch evidence MUST retain the workspace
whenever a child could exist. A missing process record MAY be inactive only when
durable state proves launch was never attempted or completed with no child.

Cleanliness MUST include tracked, staged, untracked, and ignored content. The
Guard MUST use Git-native ignored-file enumeration and MUST retain a worktree
containing any ignored entry, including `.project-memory`; disk pressure MUST
NOT weaken this protection.

Acceptance: active, dirty, unpublished, and active-loopback fixtures MUST remain
present after a sweep, including under simulated disk pressure.

### GC-R4 Safe Removal

The primary worktree removal path MUST be source-repository-controlled
`git worktree remove <exact-canonical-managed-path>` followed by
`git worktree prune`. The implementation MUST NOT use recursive filesystem
deletion as the primary worktree removal mechanism. Auxiliary temp or state MAY
be removed only after the same exact ownership proof.

Acceptance: a published clean worktree and an unchanged clean terminal worktree
MUST be removed, absent from Git worktree metadata after prune, and safe to sweep
again without error.

Before removal, the Guard MUST durably persist a sanitized versioned GC intent
for the exact allocation group and MUST preflight required lifecycle and metric
persistence. If any pre-removal persistence fails, no worktree in that removal
phase may be deleted. If removal succeeds, the intent and all grouped lifecycle
records MUST be restart-recoverable to `GC_REMOVED`, including after partial
multi-record writes or a final metric-write failure. Absence from both the exact
filesystem path and Git worktree metadata under a valid prepared intent MUST
converge to `GC_REMOVED` without another delete attempt.

A prune failure after successful `git worktree remove` MUST preserve
`GC_REMOVED`, record a stable operator follow-up reason, and remain idempotent.

### GC-R5 Managed Close Tool

The `managed-repo` public surface MUST expose `codex-repo-close`. The caller MUST
supply only an existing managed `threadId`; it MUST NOT supply a cwd, repository
path, arbitrary path, branch, remote, or internal job ID. The Guard MUST resolve
the exact workspace through the capability and durable state.

A clean published or unchanged terminal worktree MAY be removed immediately. An
active, dirty, unpublished, or ownership-uncertain worktree MUST return the stable
sanitized status `WORKSPACE_NOT_SAFE_TO_GC` and remain intact. Repeated close on
an already removed workspace MUST be idempotent.

### GC-R6 Disk Watermarks

Disk usage MUST be measured through a testable abstraction against the filesystem
containing the Bridge workspace. The default free-space boundaries MUST be:

- `SOFT`: free bytes below `max(24 GiB, 15% of filesystem capacity)`;
- `HARD`: free bytes below `max(16 GiB, 10% of filesystem capacity)`; and
- `EMERGENCY`: free bytes below `max(8 GiB, 5% of filesystem capacity)`.

The most severe crossed boundary MUST be reported. At `SOFT`, the Bridge MUST run
safe GC and retain a warning/metric record. At `HARD`, the Bridge MUST run safe GC
and MUST reject a new managed start with `MANAGED_WORKSPACE_DISK_PRESSURE` when
the post-GC measurement remains at `HARD` or `EMERGENCY`. At `EMERGENCY`, the
Bridge MUST additionally reject new managed continuation turns and new local-run
processes that can increase pressure.

Inspection/status/wait, publish, local-process stop, and close recovery surfaces
MUST remain available at `EMERGENCY`. No watermark MAY authorize deletion of
dirty, unpublished, active, foreign, or unproven work.

Acceptance: deterministic disk fixtures MUST prove SOFT sweep, HARD rejection,
post-reclamation start admission, EMERGENCY pressure rejection with recovery
surfaces available, and dirty unpublished retention.

### GC-R7 Observability

Every sweep MUST produce a sanitized metric record with `bytesBefore`,
`bytesAfter`, `reclaimedBytes`, `consideredJobCount`, `removedJobCount`,
`retainedJobCount`, `retainedReasons`, `watermarkState`, `freeBytesBefore`, and
`freeBytesAfter`. Retained reasons MUST be stable symbolic codes. The record MUST
contain no absolute path, raw internal job ID, raw thread ID, or capability.

Acceptance: tests MUST assert the exact metric keys, deterministic counts, and
absence of private identifiers.

`codex-repo-close` MUST persist the same sanitized metric class as a sweep and a
versioned per-group receipt. A close or sweep receipt MUST contain no absolute
path, capability, raw thread ID, or raw internal job ID.

### GC-R8 Per-Job Temp Root Safety

The Bridge MUST NOT grant managed child processes a temp root outside their
existing workspace-write boundary. A Bridge-owned
`<bridge-workspace>/managed-tmp/<alias>/<job-id>` root MAY be implemented only if
it can be bound to the exact job lifecycle without adding a broader writable root.
Otherwise the limitation MUST be documented as a P1 follow-up and `TMPDIR`,
`TMP`, and `TEMP` MUST retain their current sandbox-safe behavior.

Acceptance: this version documents the current inability to authorize the
sibling `managed-tmp` root without broadening workspace-write; it creates no
persistent clone under `/private/tmp`.

## Edge Cases And Failure Modes

- Missing or malformed job, worker, local-process, registry, Git, disk, or
  ownership evidence MUST retain work and fail closed.
- A failed Git worktree removal MUST retain a non-removed lifecycle and MUST NOT
  fall back to blind deletion. A prune failure after proven worktree removal
  MUST preserve `GC_REMOVED` and a durable operator follow-up reason.
- A remote verification timeout or unavailable remote MUST retain non-base work
  as unpublished/unverified.
- A sweep racing with start, continuation, publish, local-run, or close MUST be
  prevented by the Guard admission lock.
- Previously removed durable records MUST remain readable for status and MUST NOT
  consume the retained-workspace admission quota.
- Remote-branch movement, network failure, or malformed `ls-remote` output MUST
  retain non-base work as unpublished.

## Non-Goals

- Background GC threads or a new scheduler.
- Relay transport or GitHub Issue protocol changes.
- Force push, merge, protected-branch push, production deployment, or arbitrary
  path/command authority.
- Deleting source repositories, foreign directories, private registry data, or
  protected retained work.
- Reinstalling or restarting the live Relay or installed Guard.

## Rollback And Migration

The lifecycle fields are additive to existing `jobs-v4` JSON records. Rollback
MUST ignore those fields and preserve durable job semantics. The implementation
MUST NOT rewrite or delete existing job records as a migration step. Reinstalling
the prior pinned runtime disables automatic GC while preserving all retained
worktrees and records for manual recovery.
