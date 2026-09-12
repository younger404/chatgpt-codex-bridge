# Isolation Boundary Runbook

Status: Superseded for active operation by T-115/T-200 on 2026-08-03

> Historical proof-only runbook. Do not use its non-admin, `read-only`, or
> `on-request` gates for the active personal bridge. The current operator path
> is [Codex MCP Guard Runbook](codex-mcp-guard.md), with the current
> trusted host authority, fixed `danger-full-access`, and
> `approval-policy=never`. This file is retained only to explain the original
> isolated feasibility proof.

## Purpose

This runbook admits only a non-sensitive Git repository to the raw Codex MCP
feasibility proof. It does not make the raw MCP server safe for a personal or
production account.

## Hard gate before the first Codex tool call

Before invoking `codex` or `codex-reply`, the operator MUST use one of:

- a dedicated sterile, non-admin macOS account; or
- an equivalently isolated disposable VM/profile.

The selected environment MUST have no personal or production browser profile,
SSH private key, Keychain dependency, production `.env`, deployment credential,
or access to a real project. The operator MUST attest that the profile has never
been used for personal or production accounts. If the isolation or attestation
is uncertain, record `UNVERIFIED` and stop before the first Codex tool call.

Creating an operating-system account, changing group membership, or changing
filesystem permissions is a separate permission-changing action. Those actions
MUST remain manual and MUST receive explicit authorization for the exact action;
this runbook and checker do not authorize them.

## Repository preparation

1. Create one approved parent directory inside the isolated environment.
2. Create or clone one non-sensitive proof repository beneath that directory.
3. Use a dedicated task branch; `codex/<task>` is recommended. Do not use
   `main` or `master`.
4. Commit the harmless baseline so `git status --porcelain` is empty.
5. Do not add `.env` files, private keys, credentials, tokens, production data,
   or fixtures named like credentials or secrets.
6. Do not use a symbolic link as the repository root and do not commit any
   symbolic-link entry inside the repository. The proof rejects even an
   otherwise harmless internal link so link traversal cannot cross the boundary.

## Automated admission check

Run:

```sh
zsh scripts/bridge/check-sandbox-repo.zsh \
  --approved-root /absolute/path/to/approved-root \
  --repo /absolute/path/to/approved-root/proof-repo
```

The checker resolves both paths and fails closed unless all reported fields are
`PASS`. It requires the repository root to be beneath the approved root, rejects
a symbolic-link repository root, requires an exact Git repository root, rejects
`main`, `master`, and detached HEAD, requires a clean tracked and untracked
baseline, rejects every symbolic-link entry at any repository depth, and scans
files only inside that repository for obvious sensitive-file indicators. It
excludes `.git` and never follows repository symlinks.

The checker deliberately prints status labels only. It does not print repository
paths, filenames, file contents, tokens, or identifiers.

This implementation and its tests are macOS-only. The checker uses the BSD
`find -x` spelling, and the test harness creates its exact temporary root with
`mktemp -d /tmp/...XXXXXX`. Because macOS may resolve `/tmp` to `/private/tmp`,
the cleanup trap validates either exact parent before removing only the one
immutable `mktemp` result. Porting to GNU userland requires a separately tested
`find -xdev` equivalent and temporary-directory contract.

## Meaning and limits

This is an operator-side admission gate. It is not a sandbox, credential scanner,
or server-side policy wrapper. Name and marker checks cannot prove the absence of
all secrets, and raw Codex MCP arguments remain caller-controlled.

For this proof:

- the first Codex call MUST use the exact admitted repository as absolute `cwd`;
- the first call MUST use `sandbox=read-only` and
  `approval-policy=on-request`;
- `workspace-write` MAY be used only after a clean read-only proof and explicit
  approval for the named test artifact;
- `danger-full-access`, direct writes to protected branches, force push, and
  production deployment remain prohibited.

Real-project use requires a later enforcement adapter that rejects unsafe `cwd`,
sandbox, approval, model, configuration, and network arguments server-side, or
an equivalently strong containment boundary.

## Rollback

Stop the tunnel client and revoke the proof connection before inspecting or
reusing the isolated environment. Preserve only non-secret verification status.
Dispose of the VM/profile according to its separately approved lifecycle. Do not
delete or alter Codex session-history files as part of cleanup.
