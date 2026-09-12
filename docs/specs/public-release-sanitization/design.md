# Public Release Sanitization Design

Status: Accepted
Spec ID: `public-release-sanitization`

## Facts and boundaries

- The portable plugin already derives the current home directory and keeps
  Tunnel credentials outside Git.
- The remaining privacy exposure is concentrated in superseded root-level
  personal deployment assets and historical evidence documents.
- Gitleaks reports no current-tree credential finding.
- Git history is a separate publication boundary and is not rewritten here.

## Decision

Adapt the existing repository instead of creating another MCP or another
working repository:

1. Delete the superseded fixed-user LaunchAgent, management script, and static
   contract test from the current tree.
2. Make the portable plugin the sole documented installer.
3. Replace personal operational literals in retained specifications, ADRs,
   plans, reports, research, and runbooks with synthetic placeholders.
4. Add `scripts/release/check-public-sanitization.zsh`, which enumerates tracked
   text files, rejects retired literals and unapproved macOS home accounts,
   and returns only file/line evidence.
5. Add an isolated test that proves the gate passes this repository and fails a
   synthetic leak.
6. Run Gitleaks against an archive of `HEAD` so ignored runtime memory and Git
   metadata are not mixed into current-tree evidence.

## Reuse decision

- Reuse the current portable plugin and its installer/test harness.
- Reuse the installed Gitleaks scanner for credential detection.
- Reuse GitHub's documented split between current-tree cleanup and coordinated
  history rewriting.
- Do not build a second scanner for credential signatures; the custom gate is
  limited to repository-specific privacy literals that Gitleaks does not model.

## Antifragility review

- **Dependency drift:** the privacy gate uses `git`, `grep`, and `awk`; Gitleaks
  is a separate release verification step.
- **False positives:** approved synthetic accounts are explicit and narrow.
- **Regression:** a negative fixture is created only in a temporary Git repo.
- **Rollback:** all changes are a normal commit; no force push or visibility
  change occurs.
- **Blast radius:** the live legacy LaunchAgent is not booted out or modified;
  only its obsolete source copy is removed from this repository.
- **Observability:** the gate prints category plus tracked file/line, never the
  suspected value.

## Deferred security findings

The Standard security audit may surface runtime authorization or resource
admission issues unrelated to content privacy. They remain explicit blockers
for a later public-release decision, but this sanitization tranche MUST NOT
silently broaden into a behavior redesign.
