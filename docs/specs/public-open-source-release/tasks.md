# Public Open-Source Release Tasks (Component-04)

Status: Candidate
Spec ID: `public-open-source-release`

- [x] OSR-T01 Pin exact base HEAD/tree; create task-owned worktree and
  `codex/bridge-component-04-public-release` branch; confirm no existing
  candidate branch or open PR.
- [x] OSR-T02 Record requirements and design for the private candidate.
- [x] OSR-T03 Replace historical business-alias/control-repository literals in
  kept tests, specs, and ADR 0015 with synthetic values; keep schemas closed
  and tests deterministic.
- [x] OSR-T04 Rewrite root and plugin documentation Relay-V1-first (zh + en);
  keep legacy Secure Tunnel as a separate section; honest capability and
  limitation statements; repository-root command paths.
- [x] OSR-T05 Set manifest `1.0.0-beta.1` and proposed public URLs; update
  deterministic package-test expectations.
- [x] OSR-T06 Add SECURITY.md, CONTRIBUTING.md, controller SOP with capability
  precheck and synthetic feedback template, verification SOP, synthetic job
  examples validated against the closed schema, minimal offline CI workflow,
  and release-notes draft.
- [x] OSR-T07 Run relevant worktree suites; record exit codes.
- [ ] OSR-T08  <!-- export completed; digest/identity recorded in the delivery receipt --> Commit candidate; export tracked tree; apply EXCLUDE list;
  produce sorted path/mode/SHA256 manifest, public-tree digest, and archive
  SHA256.
- [ ] OSR-T09  <!-- scans completed; evidence in the delivery receipt --> Run privacy gate with external denylist and pinned Gitleaks on
  the export and unpacked archive.
- [ ] OSR-T10  <!-- clean-HOME export install completed; evidence in the delivery receipt --> Clean-HOME `--no-start` install from the export plus
  export-scoped portable suites.
- [ ] OSR-T11 Push candidate branch, open one unmerged PR against
  `github-relay-v0.2`, deliver receipt, and stop for main-controller review.

## PR #128 R1/R2/C1 revision (same branch, same PR)

- [x] OSR-T12 R1: replace split historical personal literals in the public
  package test with synthetic sentinels; real values live only in the
  repository-external private denylist; targeted content check passes.
- [x] OSR-T13 R2: split Quick Start into Route A (default install + read-only
  readiness) and Route B (`--no-start` terminal offline evaluation); align
  acquisition paths; add targeted stop SOP; fix zh Issue-body diagram wording.
- [x] OSR-T14 C1: correct scanner attribution (stopword explanation), verify
  never-valid non-stopword controls on both recorded binaries, prove allowlist
  narrowness, and re-scan the revised export and unpacked archive.

## PR #128 R2-F1 revision (same branch, same PR)

- [x] OSR-T15 R2-F1: replace `immutable=1` live-journal read with a genuine
  lock-honoring read-only CLI connection; correct result interpretation
  (locked/missing = state not obtained, never zero jobs; point-in-time, not
  atomic); stop SOP now requires prior stop of new submissions and forbids
  stopping on unconfirmed state. Synthetic lock/missing counterexamples pass.
