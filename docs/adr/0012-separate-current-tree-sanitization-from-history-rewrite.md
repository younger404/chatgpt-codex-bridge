# ADR-0012: Separate current-tree sanitization from history rewrite

Status: Accepted
Date: 2026-08-22

## Context

The repository may later be published, but the current private history contains
implementation-era personal deployment details. The portable plugin no longer
depends on those details. Removing them from `HEAD` is reversible; rewriting all
branches and tags is destructive, changes commit identities, can invalidate
signatures and references, and can be recontaminated by older clones.

## Decision

Sanitize only the current tracked tree in this tranche. Remove obsolete
fixed-user deployment assets, replace retained personal telemetry with
synthetic placeholders, and add a repository-wide regression gate. Preserve
all existing Git refs and keep repository visibility private.

A later publication tranche must separately inspect history, decide between a
new clean public repository and a coordinated history rewrite, and obtain
explicit authorization before changing visibility or force-pushing.

## Consequences

- The current checkout becomes suitable for a clean export or squash-based
  public repository after remaining release gates pass.
- The existing private Git history is still sensitive and must not be described
  as sanitized.
- Any installed legacy LaunchAgent continues running until an
  operator intentionally migrates it; deleting its repository copy does not
  stop the live service.
- Publisher attribution remains because the canonical remote already exposes
  that identity; incidental host/account telemetry is removed.
