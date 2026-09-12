# Managed Existing Repository Tasks v0.1.1

## BRIDGE-RECOVERY-03 (isolated candidate only)

- [x] R03.1 Add fail-closed operator selector and pre-side-effect maintenance guard.
- [x] R03.2 Verify real wrapper metadata on synthetic inputs, rejection cases,
      repeat-store stability and persisted Relay journal semantics.
      OS wrong-owner negative skipped where chown is unavailable; not a PASS.
- [x] R03.3 Verify packaging/syntax/privacy and frozen input/core identities.
- R03.4 Native Draft PR publication identity is recorded in its separate receipt;
      no Ready, merge, deployment or live task is part of candidate acceptance.

- [x] T01 Verify host Codex supports `workspace-write + never` without fallback.
- [x] T02 Create requirements, design, tasks, and ADR before code changes.
- [x] T03 Implement registry schema, validation, canonical hash, atomic storage,
      and operator CLI.
- [x] T04 Add explicit `managed-repo` installer preset and fail-closed default.
- [x] T05 Add managed tool surface and isolated existing-repo worktree start.
- [x] T06 Bind durable jobs and thread capabilities to managed repository context.
- [x] T07 Add Guard-controlled publish and stale-base reporting.
- [x] T08 Add deployment tiers with production permanently denied.
- [x] T09 Add registry, attachment, capability, Git, deployment, sandbox, and
      sanitizer tests.
- [x] T10 Run upstream regression tests, managed tests, sanitization, diff check,
      gitleaks when available, and strict Git fsck.
- [x] T11 Add runbook and README boundary documentation.
- [x] T12 Commit, push private downstream branch, create annotated release tag,
      and record the exact release commit.

## v0.1.1 Tunnel Client Compatibility Hotfix

- [x] T13 Specify the official v0.0.11 four-file archive and separate artifact
      provenance from macOS runtime capability.
- [x] T14 Add RED coverage for archive shape, path/symlink/duplicate rejection,
      payload identity, and Gatekeeper-blocked classification.
- [x] T15 Implement read-only distribution verification without executing or
      trusting the bundled `cloudflared`.
- [x] T16 Add the fixed official-source build path and non-secret provenance
      receipt, with negative coverage for identity, tree, version, module, and
      runtime mismatches.
- [x] T17 Keep the installer binary-only, require tunnel-client v0.0.11, package
      reviewed verifier/build scripts, and document the no-bypass boundary.
- [x] T18 Verify the real official archive, build the pinned source on this Mac,
      replace only the pre-authorized blocked binary, and run full regression.
- [x] T19 Create the v0.1.1 hotfix commit and annotated release tag without
      moving `managed-repo-v0.1.0` or resuming Phase 2 installation.

## COMPONENT-03 GC Receipt Lifecycle Fix

- [x] GC01 Specify retained ACTIVE round trips and fail-closed negative pairings.
- [x] GC02 Reproduce the actual writer-to-reader failure before changing code.
- [x] GC03 Accept ACTIVE only for retained receipts; keep source/plugin identical.
- [x] GC04 Verify repeated active sweep, terminal dirty progression and negative
      pairings, relevant managed Guard tests, syntax, mirrors and diff checks.
- [x] GC05 Submit an unmerged candidate PR for independent engineering review;
      no install, migration, runtime recovery or checks normalization.

Validation: the writer/reader regression failed before the fix with
`GuardProtocolError: invalid GC receipt` on the second active sweep (exit 1).
After the fix both targeted tests passed, including both negative pairings and
terminal/dirty progression. The managed-repo module passed 56 tests. Source/plugin
bytes, touched Python syntax and `git diff --check` passed. Runtime recovery and
real-service acceptance remain outside this candidate.
