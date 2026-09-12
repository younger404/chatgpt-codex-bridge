# v0.6.1 Security Hardening Tasks

Status: In Progress
Spec ID: `v0.6.1-security-hardening`

## BRIDGE-GUARD-FIX-01 (candidate only)

- [x] Add synthetic preservation/rejection/new-object regressions; confirm RED.
- [x] Separate creation from validation in both Guard mirrors.
- [x] Verify 9 focused and 60 total Guard tests; portable selector: 7 pass,
  2 environment-dependent skips. Syntax, mirror and diff checks pass.

Delivery: commit/push the bounded candidate and open a non-merged review PR;
the PR records delivery identity. No tag, release, deployment or recovery.

- [x] SH-T01 Record the post-release findings, trust boundary, design and ADR.
- [x] SH-T02 Add RED tests for verifier ordering and malformed capabilities.
- [x] SH-T03 Add RED tests for context binding and sync resource limits.
- [x] SH-T04 Add RED tests for worker-group revocation and secure uninstall.
- [x] SH-T05 Add RED tests for result trust separation and public privacy.
- [x] SH-T06 Implement Guard, installer, verifier and sanitizer fixes.
- [x] SH-T07 Keep source/package runtime copies byte-identical and bump version.
- [x] SH-T08 Add the illustrated Chinese README and GitHub release checklist.
- [x] SH-T09 Run focused and full verification plus anonymous export audit.
- [ ] SH-T10 Commit, push, publish a corrected tag and verify anonymous install
  truth.
