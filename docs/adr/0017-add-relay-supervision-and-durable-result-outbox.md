# ADR 0017: Add relay supervision and a durable result outbox

## Status

Accepted

## Context

The v2 GitHub relay waits for each Guard job to become terminal before polling
another Issue. It records a terminal database status before commenting on
GitHub, so a transient GitHub failure can leave a completed request permanently
labelled running with no result. Startup also converts every active row to
interrupted instead of asking the Guard for the durable job's current status.

The Guard already owns durable job execution and exposes `codex-job-status`.
The relay needs reliable orchestration and delivery without expanding Guard or
managed-repository authority.

## Decision

The relay will:

1. hold one non-blocking process-lifetime file lock before SQLite initialization;
2. persist a returned Guard job capability and return to the poll loop instead
   of waiting for terminal state;
3. observe active jobs through `codex-job-status`, including after restart;
4. transactionally persist each validated public terminal result in a SQLite v3
   outbox before contacting GitHub;
5. deliver an exact deterministic `BRIDGE_RESULT_V1` comment and terminal label
   idempotently, retrying until both are acknowledged; and
6. migrate v2 terminal rows into legacy reconciliation, recognizing existing
   comments or reconstructing results from existing Guard jobs without starting
   replacements.

Publish remains synchronous but uses the same terminal outbox. Invalid or
revoked capabilities fail closed. Transient Guard observation failures retain
the active row for retry, while active rows with no job capability become a
generic failed outbox result.

## Consequences

The relay can service multiple Issues while Codex work continues, survive
process restarts, and retain terminal results across GitHub outages. Delivery
is at-least-once internally and effectively once on GitHub because the exact
comment body is its idempotency key.

SQLite and the lock remain local authority-bearing state and require the same
regular-file, non-symlink, `0600` protections. The change adds no network
listener, Tunnel dependency, raw Codex path, Git authority, or new Guard tool.
