# ADR 0016: Add Relay Thread Continuity and Guarded Publish

## Status

Accepted for R-GH2 and R-GH3 implementation.

## Decision

Extend `codex_bridge_job_v1` with closed `reply` and `publish` discriminators.
GitHub continues to carry only an opaque `relayJobRef`. The local SQLite
mapping resolves that reference to the exact Guard thread capability and fixed
repository alias.

Reply delegates to `codex-reply-async`; publish delegates to
`codex-repo-publish`. The relay does not implement Git or accept caller-selected
repository, worktree, branch, remote, refspec, force, merge, deployment, or
Guard identity fields.

Add a second relay alias for the bridge's own repository, backed by the
operator registry with a dedicated generated prefix and protected engineering
base branch. (Historical alias, prefix, and branch identifiers are replaced
with the synthetic placeholders `sample-beta` / `codex/relay/sample-beta/` for
publication.)

## Consequences

- Completed start mappings survive relay restart and can continue the same
  thread/worktree without exposing capabilities.
- Publish remains subject to existing Guard diff, pre-publish, generated-branch,
  and no-force controls.
- Bridge self-management produces review branches only. It cannot self-merge,
  mutate the running relay, deploy, or restart production automatically.
- Removing or revoking the local mapping fails future reply/publish requests
  closed; no replacement thread or direct Git fallback is attempted.
