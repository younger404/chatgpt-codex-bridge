# Managed Existing Repository Design v0.1.1

## Architecture

```text
operator CLI -> managed-repos.v1.json (0600, atomic)
                         |
ChatGPT -> Guard -> alias resolution + registry hash
                  -> fetch registered base
                  -> Bridge-owned worktree + generated branch
                  -> Codex App Server (workspace-write + never)
                  -> durable job/capability state
                  -> controlled publish to generated branch
```

## Components

### Managed Repository Library

`managed_repo.py` owns registry parsing, canonical JSON hashing, path and remote
identity validation, atomic writes, worktree allocation, branch generation,
publish checks, and deployment-policy validation. The runtime copy is staged
beside the Guard so the Guard and operator CLI use the same implementation.

### Operator CLI

`scripts/managed-repos.zsh` dispatches to the Python library. It derives the
state directory from HOME unless tests explicitly override it. MCP never calls
the mutating CLI.

### Presets

The installer requires `--preset`. Existing presets remain isolated.

| preset | sandbox | approval | start surface |
| --- | --- | --- | --- |
| personal-full-control | danger-full-access | never | new project |
| workspace-safe | workspace-write | on-request | sync diagnostics |
| managed-repo | workspace-write | never | registered repo only |

`managed-repo` stages the registry CLI and passes the registry path and preset
to the Guard. There is no policy fallback.

### Registry

The canonical representation is UTF-8 JSON with sorted keys and compact
separators plus a trailing newline. The SHA-256 of the compact canonical object
(without formatting dependence) is the `registryCanonicalHash`.

Entries contain alias, canonical repo path, repository full name, base remote,
base branch, protected branches, work branch prefix, deployment tier, optional
pre-publish checks, and optional local-loopback targets. All executable and
repository paths are operator-owned absolute canonical paths.

### Worktree Lifecycle

The start path resolves an alias, verifies identity, fetches
`<baseRemote>/<baseBranch>`, resolves the exact remote-tracking SHA, constructs
`<workspace>/managed/<alias>/<job-id>`, and runs:

```text
git worktree add -b <generated-branch> <worktree> <baseRevision>
```

The branch is derived by the Guard and cannot be supplied by ChatGPT. Existing
project instructions remain visible because the worktree contains the original
repository tree.

### Active GC Receipt Compatibility

The GC writer records non-eligible outcomes with `phase=retained`, including
`lifecycleState=ACTIVE`. The receipt reader accepts ACTIVE only for retained
receipts, then lets the existing sweep re-evaluate current activity and dirtiness.
Prepared/removed ACTIVE receipts remain invalid; identity, capability, receipt
shape and all other validation stay unchanged. No schema, migration or ADR is
needed. Rolling back the reader restores the earlier rejection behavior; this
code change does not edit or delete existing runtime receipts.

### Capabilities

The installation codec remains signed with the installation key and preset.
Managed job records additionally carry a canonical managed context. Every
managed capability use reloads the registry, recomputes its hash, and compares
all identity fields before reading, continuing, or publishing. This makes a
registry mutation invalidate earlier managed capabilities after restart.

### App Server

Managed workers use the existing durable App Server path but pass:

```json
{"approvalPolicy":"never","sandbox":"workspace-write"}
```

and the corresponding workspace-write turn sandbox policy. Bootstrap Skill
injection and project-root allocation are disabled for managed starts.

### Publishing

Publishing is synchronous Guard logic, not model logic. It verifies a clean
identity chain from capability to job record to worktree to branch, fetches the
base ref, detects staleness, runs checks, commits staged work, and pushes only
the generated branch. No merge operation exists.

### Deployment

Production has no callable tool. Staging requires a future release capability.
When at least one registered repository has a valid `local-loopback` target,
the Guard exposes start/stop tools that accept only thread and target names.
Executable, argv template, host, and cwd come from operator state; process-group
ownership is recorded and revoked with other Bridge-owned processes.

### Tunnel Client Verification And Source Fallback

Tunnel distribution verification is deliberately separate from installation:

```text
official archive + SHA256SUMS + candidate binary
  -> exact archive-shape and byte-equality verifier
  -> read-only macOS trust diagnostics
  -> PASS | RUNTIME_BLOCKED

official source checkout at reviewed release + commit
  -> clean-source identity checks
  -> fixed Go module verification and fixed client build
  -> runtime and quarantine checks
  -> binary + non-secret provenance receipt
  -> existing installer --tunnel-client-bin input
```

The archive verifier recognizes only the historical single `tunnel-client`
shape or the exact official v0.0.11 four-file shape. Companion files establish
release layout compatibility but are never executed. Artifact provenance and
host runtime capability are independent axes so an operating-system policy
block cannot be mislabeled as a checksum or provenance failure.

The source-build script accepts no command, package, linker flags, or arbitrary
Go flags. It validates the supplied approved commit against the release tag and
the checkout before invoking the two fixed Go commands. The installer remains
transport-agnostic and receives only the verified output binary. Current stdio
Guard operation does not require `cloudflared`; future `cloudflared.managed` or
`cloudflared.token` modes must fail closed unless an explicitly verified
companion is supplied.

## Migration And Rollback

### Explicit-store recovery exception

The wrapper uses a small colocated standard-library `guard-store-config.py`
validator for plist types, canonical paths and filesystem ownership/link/mode
checks; shell-only parsing cannot clearly establish these properties. It emits
only stable error categories. Only operator config supplies job_state_dir;
Guard receives exactly one explicit argument. No Guard/module behavior changes.
Store selection is limited to a direct child of the fixed HOME-derived state
root; workspace intersections and all legacy stores are rejected. Config must
be 0600, its state root operator-owned and not group/world-writable, store 0700
and any existing 32-byte key 0600/single-link. Control characters in the selector
are rejected to preserve the exact path across shell argument extraction. The wrapper
does not repair permissions or recreate keys. Its trusted interpreter and the
colocated helper are part of the reviewed deployment, not caller inputs.

The service dispatcher blocks legacy maintenance for managed or explicit-store
configurations before its existing side effects. Fresh managed installation also
requires the reviewed recovery flow; safe/personal presets remain supported.
An exact future recovery must stage wrapper/helper, B Guard/module and reviewed
Relay together, preserve the existing Relay SQLite, and select a separately
authorized new Guard store. P1/P2/P3 remain inherited core evidence. Real
historical-thread continuity is NOT_PROVEN, not automatically retired.
Rollback requires a separately approved quiet window and preserved evidence;
never clear the journal, re-sign historical records or replay terminal jobs.

Outside the explicit-store recovery exception, the managed preset uses a new job-state generation so legacy capabilities
cannot cross the boundary. Existing presets remain readable by their existing
state. Rollback reinstalls the pinned v0.6.1 ref and restarts the service; the
operator registry is preserved unless explicitly removed.
