# Managed Existing Repository Requirements v0.1.1

## Scope

This specification adds an operator-controlled mode for attaching Codex to an
existing Git repository. It MUST preserve the upstream new-project mode while
preventing ChatGPT from selecting arbitrary paths, Git destinations, or
deployment commands.

## Preconditions

- The bridge is installed with an explicit preset.
- `managed-repo` MUST map to `workspace-write` and `never`.
- The host Codex runtime MUST support that exact pair. Installation MUST fail
  closed when support cannot be verified.
- A managed repository MUST be registered by the local operator before use.

## Requirements

### R1 Existing Repo Registration

Given an operator invokes the registry CLI, the bridge MUST support `register`,
`list`, `verify`, and `remove`. The registry MUST live in the bridge state
directory, be a non-symlink regular file with mode `0600`, and be updated
atomically. Registry entries MUST use synthetic aliases and canonical absolute
repository paths. MCP tools MUST NOT mutate the registry.

Acceptance: valid repositories are accepted; symlinks, non-canonical paths,
wrong remotes, duplicate aliases, missing base branches, and unsafe modes are
rejected or safely repaired as specified.

### R2 Allowlist And Identity

The caller MUST supply only `repoAlias`, never `cwd`, `repoPath`, a remote URL,
or another filesystem path. The bridge MUST verify the repository is Git,
normalize SSH and HTTPS GitHub remotes to `github:owner/repo`, and require an
exact match with `repositoryFullName`.

Acceptance: unknown aliases and arbitrary path fields fail before Codex starts.

### R3 Isolated Worktree

For `codex-repo-start`, the bridge MUST fetch only the registered base remote
and base branch, bind the exact fetched SHA as `baseRevision`, create a unique
branch under the registered prefix, and create a Bridge-owned worktree under
`<bridge-workspace>/managed/<alias>/<job-id>`. Codex MUST use that worktree as
its cwd and MUST NOT run `workspace-new-project` in managed mode.

Acceptance: the source checkout remains unchanged and the worktree starts at
the exact fetched base revision.

### R4 Capability Binding

Managed thread and job capabilities MUST bind installation identity, preset,
registry canonical hash, alias, repository identity, base revision, worktree,
sandbox, and approval policy. A registry or preset change MUST invalidate old
capabilities. A capability for repo A MUST NOT resume or publish repo B.

### R5 Managed Codex Runtime

`managed-repo` MUST expose `codex-repo-start`, `codex-reply-async`,
`codex-wait`, `codex-job-open`, `codex-job-status`, and
`codex-repo-publish`. It MUST NOT expose generic `codex-start`, arbitrary-cwd
tools, or deployment tools when the registered tier is `none`.

### R6 Git Publish Boundary

Publishing MUST be Guard-controlled. The caller MAY provide only `threadId`
and `commitMessage`. The Guard MUST verify the recorded worktree and generated
branch, reject protected branches, run `git diff --check` and registered
`prePublishChecks`, and push only `HEAD:<exact generated branch>` to the
registered remote. Force push, custom refspecs, merge, branch deletion, and
direct protected-branch pushes MUST be unavailable. If the base remote branch
has advanced, the result MUST report `base_stale=true`; it MUST NOT rebase or
merge automatically.

### R7 Deployment Permission Tiers

- `none`: no run or deploy tool is exposed.
- `local-loopback`: only operator-registered executable/argv templates MAY run;
  bind hosts MUST be `127.0.0.1` or `::1`; arbitrary commands, targets, public
  tunnels, LAN binds, and `0.0.0.0` MUST be rejected.
- `staging`: schema MAY exist, but execution MUST fail without a separate
  operator release capability.
- `production`: v0.1 MUST always return
  `PRODUCTION_DEPLOYMENT_NOT_AUTHORIZED` and expose no production tool.

### R8 Recovery And Revocation

Bridge stop, reinstall, and uninstall MUST revoke Bridge-owned workers and
local-loopback process groups. Registry changes require restart. Removing an
alias MUST prevent new attachment and invalidate capabilities after restart.
Source repositories and external credentials MUST be preserved on uninstall.

### R9 Secrets And Paths

The repository MUST NOT contain actual HOME paths, managed repository paths,
Tunnel identities, API keys, connector IDs, raw Codex thread IDs, credentials,
tokens, SSH key paths, Keychain output, or the private registry. Tests and docs
MUST use synthetic values.

### R10 Upgrade And Rollback

Release installation MUST use an exact commit or verified annotated tag.
Floating `main` MUST NOT be an installation target. Upgrades and rollbacks MUST
require restart, doctor verification, and ChatGPT app refresh.

### R11 Tunnel Client Distribution Compatibility

The verifier MUST continue to accept the legacy single-entry Darwin arm64
archive and MUST accept the official `v0.0.11` four-entry archive only when its
entries are exactly `tunnel-client`, `cloudflared`,
`cloudflared-manifest.json`, and `LICENSE`. It MUST reject an additional entry,
duplicate names, absolute or traversal paths, symlinks, checksum mismatch, and
an installed `tunnel-client` whose bytes differ from the archive payload. The
verifier MUST NOT execute the bundled `cloudflared`.

After checksum, archive shape, and payload equality pass, the verifier MUST run
read-only `file`, `codesign`, `xattr`, and `spctl` diagnostics. A byte-exact
official artifact that macOS blocks MUST remain
`artifact_provenance_status=PASS` while runtime is classified
`BLOCKED_BY_OS_POLICY`; the Bridge MUST NOT remove quarantine, add policy
exceptions, force-sign the binary, or instruct the operator to use Open
Anyway.

The Bridge MUST provide a separate source-build verifier for the official
`openai/tunnel-client` repository. For release `v0.0.11`, the operator contract
pins commit `8d55683eeef80bc5e360d95abf4692454fafc615`, a clean tree, and
`pkg/version/VERSION=0.0.11`. The build surface is limited to `go mod verify`
and `go build -trimpath -o <temporary-output> ./cmd/client` under a minimal
environment. The output MUST be a Mach-O arm64 executable whose `--version`
parses `0.0.11`, whose `help quickstart` succeeds, and which has no quarantine
attribute.

The source builder MUST emit a non-secret provenance receipt containing only
the official repository/release/commit identity, tree state, version file,
Go/tool verification, binary digest/version, and runtime capability. The
installer MUST continue to consume only `--tunnel-client-bin`; it MUST NOT
build or select an arbitrary `cloudflared` from `PATH`.

### R12 Explicit Operator Store Recovery

For the recovery wrapper, managed-repo MUST require `job_state_dir` from the
existing operator config.plist, not a caller argument or environment override.
The config MUST be canonical, owner-only, single-link and operator-owned at
the fixed HOME-derived Bridge state root. The precreated store MUST be an
operator-owned canonical 0700 direct child of that root, separate from the
workspace and jobs-v2/v3/v4 (including their parents and descendants).
An existing capability.key MUST be an owner-only regular single-link file.
Invalid inputs MUST fail before Guard exec without paths in diagnostics. The
wrapper MUST NOT create, repair, scan, migrate or erase stores. Managed policy
MUST remain workspace-write/never. Other presets retain their existing path.

Legacy install/restart/stop/uninstall MUST reject explicit-store configs before
any mutation, including service operations and legacy revoke/purge. Managed
recovery requires a separately reviewed exact deployment procedure, not a
generic reinstall. The existing Relay SQLite admission/outbox journal MUST
remain unchanged; selecting a Guard store MUST NOT reset Relay deduplication
or allocate replacements for invalid old references.

Acceptance: actual wrapper metadata twice on synthetic inputs, pre-exec
negative tests, maintenance rejection and persisted-journal deduplication.
No live deployment or historical continuation is proved by these tests.

### R13 Active GC Receipt Round Trip

Given a managed GC sweep writes a retained receipt for an active worker or local
process, the next Guard startup MUST accept that writer-generated
`phase=retained / lifecycleState=ACTIVE` receipt and re-evaluate the current
lifecycle without deleting or executing the job. `prepared + ACTIVE` and
`removed + ACTIVE` MUST still fail closed. Other existing receipt combinations
MUST retain their current compatibility behavior.

Acceptance: repeated active sweeps preserve the worktree; a later terminal,
inactive job with dirty work transitions to `RETAINED_UNPUBLISHED` with
`DIRTY_WORKTREE`. The regression MUST observe no worktree removal. This change
requires no receipt migration and does not authorize live runtime recovery.

## Non-Goals

- Automatic merge to a protected branch.
- Automatic PR approval or production deployment.
- Registry mutation through ChatGPT or MCP.
- Writing directly to the operator's source checkout.
- Replacing the existing `personal-full-control` implementation.

## Failure Modes

All identity, policy, registry, capability, worktree, check, branch, and
deployment mismatches MUST fail closed before the protected action. No failure
MAY silently fall back to `danger-full-access`.

## Observability

Durable job records MUST include the managed repository identity and policy
fields without exposing raw identifiers to the caller. Publish results MUST
report branch, commit, push status, and `base_stale`.
