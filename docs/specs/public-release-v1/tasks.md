# Public Release v1 Tasks

Status: Released
Spec ID: `public-release-v1`

- [x] PRV1-001 Confirm the public repository name is available and retain the
  private repository as the source of truth.
- [x] PRV1-002 Record requirements, architecture, rollback, and non-goals.
- [x] PRV1-003 Add failing capability-boundary tests.
- [x] PRV1-004 Implement installation-scoped thread/job capabilities and keep
  source/package Guard copies byte-identical.
- [x] PRV1-005 Add failing async-budget and deadline tests.
- [x] PRV1-006 Implement atomic admission and worker lifetime limits.
- [x] PRV1-007 Update version, MIT license, public URLs, controller SOP, and
  compatibility notes.
- [x] PRV1-008 Run complete source and package verification plus secret/privacy
  gates.
- [x] PRV1-009 Obtain independent final review and commit/push the private source
  milestone.
- [x] PRV1-010 Create and verify the one-commit public repository and release
  tag.
- [x] PRV1-011 Close project memory with publication evidence and residual
  limits.

Publication evidence: public `main` contains a single root commit and annotated
tag `chatgpt-codex-bridge-v0.6.0` resolves to that commit. Anonymous API and
clone readback verified public visibility, approved noreply identities, and no
tracked personal-path or identity fixtures.
