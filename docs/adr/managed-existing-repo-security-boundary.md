# ADR: Bind Managed Repository Authority To Operator State

## Status

Accepted for `managed-repo-v0.1.0`.

## Context

The upstream bridge can create new projects under one configured workspace. An
existing repository mode introduces stronger risks: arbitrary cwd selection,
direct writes to a source checkout, remote substitution, protected-branch
pushes, and deployment escalation. ChatGPT input is not a trusted source for
filesystem or Git authority.

## Decision

Only the local operator may register repositories. ChatGPT supplies an alias,
prompt, and task name. The Guard resolves all paths and Git identities from a
private registry, creates a Bridge-owned worktree at an exact fetched base SHA,
and runs Codex with `workspace-write + never`.

Capabilities are installation-scoped and MUST also match the canonical
registry hash, preset, alias, repository identity, base revision, worktree, and
policy recorded for the job. Publishing is a Guard operation limited to the
generated branch. Automatic merge and production deployment do not exist.

## Consequences

- Registry changes revoke prior managed authority after restart.
- Existing work may need to be restarted after operator policy changes.
- The operator, GitHub PR governance, and CI remain separate trust boundaries.
- The bridge can safely fail closed without background approval prompts.
- New-project full-control behavior remains available only through an explicit,
  separate preset.
