# ADR-0018: Prove Managed Workspace Ownership Before GC

Status: Accepted for PRE463 infrastructure implementation
Date: 2026-08-28

## Context

The managed-repository runbook leaves every isolated worktree for manual cleanup.
That preserves unpublished work but allows Bridge-owned terminal worktrees to
accumulate and can exhaust the filesystem. Disk pressure does not reduce the
ownership evidence required for deletion, and ChatGPT input is not trusted to
name paths, branches, repositories, or internal jobs.

## Decision

Add ownership-aware GC under the existing Guard admission lock. Deletion authority
requires agreement among the canonical Bridge managed root, durable allocation
record, current operator registry identity, and source Git worktree metadata.
Active, dirty, unpublished, foreign, symlinked, identity-mismatched, or otherwise
uncertain work is retained. Eligible work is removed only through source-controlled
`git worktree remove` followed by `git worktree prune`.

Expose `codex-repo-close` with only the existing managed thread capability. Add
SOFT/HARD/EMERGENCY filesystem watermarks around managed admission: safe GC at
SOFT, new-start rejection below HARD after reclamation, and additional
continuation/local-run rejection at EMERGENCY while status, publish, stop, and
close recovery remain available. Persist sanitized deterministic metrics.

Treat the durable job root as a strict snapshot boundary: any canonical UUID
entry with unsafe type or malformed managed state prevents deletion before
candidate evaluation. Select group ownership by the workspace allocation UUID,
never record ordering, and require every continuation to equal the allocation
owner's immutable context.

Worker and local target launch use a durable `launching` phase before process
creation so the absence of a final PID record cannot be mistaken for inactivity.
Ignored Git content is protected work. Removal uses a prepared, sanitized group
receipt plus preflight lifecycle/metric writes; restart recovery finalizes an
already absent exact worktree without issuing another removal. Successful
worktree removal remains `GC_REMOVED` when prune fails, with a durable operator
follow-up reason.

Do not add a background scheduler. Do not grant the sibling `managed-tmp` path as
a writable root in V1 because that would broaden the current workspace-write
boundary; retain this as a P1 limitation.

## Consequences

- Clean published or unchanged terminal worktrees can be reclaimed safely and
  idempotently without caller-selected filesystem authority.
- Disk pressure blocks new pressure but can never convert protected work into a
  deletion candidate.
- Network or ownership ambiguity retains work and may leave starts blocked until
  an operator resolves the retained reason.
- Durable job records remain readable after worktree removal and add only
  backward-compatible lifecycle fields.
- Old records without exact no-launch evidence are retained rather than inferred
  inactive; operators may need to inspect and resolve them manually.
- A malformed UUID durable entry blocks that sweep before any deletion, favoring
  disk retention over uncertain ownership.
- Private versioned receipts make partial group writes and post-removal metric
  failures restart-recoverable without exposing paths or raw identifiers.
- Relay transport, GitHub Issue protocol, merge authority, deployment authority,
  and existing sandbox/approval policy remain unchanged.
