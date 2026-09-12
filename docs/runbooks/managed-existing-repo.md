# Managed Existing Repository Runbook v0.2

## Boundary

The local operator owns the allowlist. ChatGPT can reference only a synthetic
alias. The private registry remains at
`~/Library/Application Support/chatgpt-codex-bridge/managed-repos.v1.json` with
mode `0600`; do not commit or share it.

## Register

Use a canonical repository root with an `origin` URL matching the declared
GitHub `owner/repository`. The base branch must exist and is protected by
default.

```zsh
/bin/zsh scripts/managed-repos.zsh register \
  --alias sample-repo \
  --repo-path /absolute/canonical/repository \
  --repository-full-name owner/repository \
  --base-remote origin \
  --base-branch main
/bin/zsh scripts/managed-repos.zsh list
/bin/zsh scripts/managed-repos.zsh verify sample-repo
```

Registry mutation is an operator action. Restart the Bridge after every
register or remove operation; the canonical registry hash invalidates old
managed capabilities.

## Install

Install from an exact commit or verified annotated tag. Floating `main` is not
an installation source.

Run from the plugin root after registration:

```zsh
/bin/zsh scripts/install-github-relay-v1-macos.zsh \
  --workspace /absolute/bridge-workspace \
  --codex-bin /absolute/codex \
  --control-repository owner/control-private \
  --allowed-author operator-login \
  --enable-alias sample-repo
```

This fresh-only GitHub Relay V1 entry requires no Secure Tunnel. Existing config,
job stores/keys, journal, runtime or service files cause `FRESH_INSTALL_REQUIRED`;
recovery and upgrade need separate review. The generic Tunnel installer retains
`EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY` for managed mode.

Default startup performs the existing equivalent real Codex support probe for
`workspace-write + never`: an inside write must succeed and an outside write must
fail. There is no policy fallback. GitHub authentication must pass before staging.

For offline configuration, append `--no-start`. It creates a complete private
layout and a Relay plist with **Disabled=true**, but no journal, service, GitHub
calls or model turn. Output is `POLICY_SUPPORT=NOT_PROBED`,
`PLIST_DEFAULT_DISABLED=true`, `LAUNCHD_STATE=NOT_PROBED` and
`SERVICE_STARTED_BY_INSTALLER=false`. The plist default does not establish the
effective launchd override state. Later activation requires
separate review and is not supported by rerunning this fresh-only installer.
Normal activation also starts with a Disabled=true plist, then explicitly enables
and bootstraps. Activation failure attempts disable before returning failure; a
disable failure is reported, and partial files remain for reviewed recovery.

The store is fixed internally to `managed-jobs-v1`, with a new private random key.
Do not copy keys or supply alternate store paths. Installed validation is:

```zsh
/usr/bin/python3 -I "$HOME/.local/share/chatgpt-codex-bridge/guard-store-config.py" \
  validate "$HOME/Library/Application Support/chatgpt-codex-bridge/config.plist"
```

## Work And Publish

`codex-repo-start` fetches the registered base and creates
`<bridge-workspace>/managed/<alias>/<job-id>` at the exact fetched revision.
Codex works only in that worktree. `codex-repo-publish` accepts a thread
capability and commit message, runs `git diff --check` plus registered checks,
commits changes, and pushes `HEAD` only to the generated work branch. A moved
base is reported as `base_stale=true`; no automatic merge or rebase occurs.
Continue corrections with the returned thread capability so every turn remains
in the same worktree. After publish, open a GitHub PR from the generated branch,
require CI and independent review, and merge only through normal repository
governance.

After a terminal clean publish, `codex-repo-close` accepts only that same managed
thread capability and attempts ownership-aware cleanup. It resolves the path,
repository, generated branch, and allocation job exclusively from durable Guard
state. The caller cannot supply a cwd, path, repository, branch, remote, or
internal job ID. A clean worktree that is unchanged from its recorded base or
whose HEAD exactly matches the generated remote branch can be removed; unsafe
work returns `WORKSPACE_NOT_SAFE_TO_GC` with a sanitized retained reason.

Deployment defaults to `none`. Local-loopback entries require fully declared
executables, argv, and `127.0.0.1` or `::1`. Staging needs a separate release
capability. Production is always denied in v0.1.

For a registered `local-loopback` target, `codex-repo-run-local` accepts only
the managed thread and target name; the Guard supplies the fixed executable and
argv, tracks the process group, and writes private logs with the job record.
Use `codex-repo-stop-local` to stop it. Bridge stop, reinstall, and uninstall
also revoke it. No public bind or Tunnel target can be supplied by ChatGPT.
Register such a target with `--deployment-tier local-loopback`,
`--local-target-name`, `--local-executable`, repeated `--local-arg`, and
`--local-host 127.0.0.1` (or `::1`). At least one fixed argv item must contain
`{host}` so the validated loopback value reaches the executable.

## Revoke And Roll Back

Stop or restart the service after registry changes. Removing an alias blocks
new attachment after restart. Uninstall revokes Bridge workers and job state
but preserves repositories, credentials, Tunnel profile, and the registry.

To roll back a legacy Tunnel installation, reinstall the prior pinned,
known-good security-hardened ref (the historical upstream ref was
`chatgpt-codex-bridge-v0.6.1`), restart, run doctor, refresh the ChatGPT app,
and start a new conversation. The fresh-only GitHub Relay V1 installer does
not support rollback-by-reinstall; rejected partial state requires separately
reviewed recovery. Existing managed worktrees and pushed branches
are not merged or deleted automatically.

## Cleanup

The Guard performs ownership-aware managed sweeps at startup, before a new
managed start, and when `codex-repo-close` is called. A successful publish marks
or derives eligibility but does not require immediate removal. There is no
background GC thread.

Automatic removal requires all four ownership proofs: canonical managed root,
durable allocation record, current registered repository identity, and exact Git
worktree metadata. The Guard then requires every associated job and local process
to have exact inactive launch evidence, a clean worktree with no ignored entries,
and either the recorded base revision or an exact generated-remote-branch HEAD.
Before removal it persists a versioned prepared receipt and preflights lifecycle
and metric writes. Removal uses the registered source repository to run
`git worktree remove <exact-managed-path>` followed by `git worktree prune`. It
never falls back to recursive deletion. Startup or the next close completes a
prepared receipt when the exact path and Git metadata both prove prior removal.

Stable retained reasons include:

- `ACTIVE_WORKER` or `ACTIVE_LOCAL_PROCESS`: wait for the job or stop the
  registered local target, then retry close.
- `DIRTY_WORKTREE`: inspect the existing managed thread, correct or intentionally
  publish the changes, then retry.
- `IGNORED_WORKTREE_CONTENT`: inspect ignored files such as `.project-memory` and
  preserve, export, or intentionally publish their needed contents. Cleanup never
  deletes ignored files globally or merely to satisfy a disk watermark.
- `UNPUBLISHED_WORK`: publish through `codex-repo-publish`; do not push or rewrite
  refs manually through the cleanup path.
- `OUTSIDE_MANAGED_ROOT`, `SYMLINK_OR_CANONICALIZATION_FAILURE`,
  `REGISTRY_OR_REPOSITORY_IDENTITY_MISMATCH`, `GIT_WORKTREE_METADATA_MISMATCH`, or
  `UNKNOWN_OWNERSHIP`: stop automatic cleanup and inspect the registry, durable
  status, and source repository worktree list. Preserve the directory until all
  four ownership proofs agree.
- `WORKTREE_REMOVAL_FAILED`: inspect Git worktree metadata and filesystem health;
  never substitute blind recursive deletion.
- `WORKTREE_PRUNE_FAILED`: the exact worktree was already removed and remains
  `GC_REMOVED`; inspect source-repository worktree metadata and retry an operator
  prune only after confirming repository identity. Do not recreate or re-delete
  the managed path.

A missing, malformed, or `launching` worker/local-process record is protected
unknown evidence unless durable state explicitly proves no launch, failed launch
with no child, or verified stop. A canonical UUID-named symlink, non-directory,
or malformed durable job entry blocks the sweep before any candidate deletion;
inspect the job-store entry without following links or deleting retained work.

The private `gc-status.json` operator record contains only sanitized counts,
bytes, free-space measurements, watermark state, and retained-reason counts. It
contains no managed path, capability, raw thread ID, or internal job ID.
Each evaluated group also has a private versioned sanitized GC receipt. A close
updates the same metric class. Receipt phases allow recovery from removal/prune,
partial lifecycle, or final metric-write failures without a second delete.

Disk pressure is measured on the filesystem containing the Bridge workspace.
SOFT is free space below `max(24 GiB, 15%)`; HARD is below
`max(16 GiB, 10%)`; EMERGENCY is below `max(8 GiB, 5%)`. SOFT triggers a safe
sweep and warning metrics. HARD blocks new managed starts if the post-sweep
measurement remains below HARD. EMERGENCY also blocks new continuation turns and
new local targets, while status/wait, publish, stop-local, and close remain
available for recovery. Watermarks never authorize deletion of dirty,
unpublished, active, foreign, symlinked, or unproven work.

Per-job `managed-tmp` is deferred. That sibling directory is outside the current
worktree-based workspace-write boundary, so setting `TMPDIR`, `TMP`, or `TEMP`
there would require broader writable-root authority. Keep the current sandbox and
temporary-directory behavior until an exact per-job writable-root mechanism is
reviewed; do not create persistent clones under `/private/tmp`.
