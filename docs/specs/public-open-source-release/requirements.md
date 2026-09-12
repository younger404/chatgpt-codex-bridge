# Public Open-Source Release Requirements (Component-04)

Status: Candidate
Spec ID: `public-open-source-release`

## Goal

Prepare a privately reviewable public-release candidate of the GitHub Relay V1
bridge distribution from one exact private source commit, without performing
any public publication step.

This spec supersedes no earlier spec. `public-release-v1` remains the released
upstream 0.6.x lineage record; this spec covers the new `1.0.0-beta.1`
candidate whose primary path is GitHub Relay V1.

## Requirements

### OSR-001 — Reviewable public tree

Given the exact private candidate commit, the release tree MUST be enumerable
file by file with path, Git mode, content digest, disposition
(`KEEP / EDIT / EXCLUDE`) and reason. The public tree MUST be produced only
from the tracked tree of the final candidate commit; it MUST NOT contain
`.git`, `.project-memory`, virtual environments, caches, untracked files,
operation logs, quarantine material, or old tags/refs.

Acceptance: a stable sorted path/mode/SHA256 manifest, a public-tree digest,
and an archive SHA256 are recorded; the source-commit-to-public-tree mapping is
retained privately.

### OSR-002 — License and attribution

The public tree MUST keep the MIT license text and the
`Copyright (c) 2026 larryppgg` notice, and MUST state that the project derives
from `larryppgg/chatgpt-codex-bridge`. The candidate MUST NOT claim the work is
wholly original, MUST NOT remove upstream attribution, and MUST NOT claim
third-party dependencies are relicensed under this project's MIT terms.
`younger404` MAY appear as the proposed public maintainer/repository owner.
Real personal paths, business aliases, control-repository names, and run
identifiers MUST be replaced with synthetic values.

### OSR-003 — Sanitization and secret scanning of the exact public object

The exact final public export MUST pass:

- the repository privacy gate in `--export` mode with a private denylist held
  outside the repository, without printing matched values;
- a pinned-version generic secret scanner run against the export and against
  the unpacked release archive, with the scanner version and source recorded.

Historical private Git objects are not published and are therefore out of
scope for this tranche; rewriting them MUST NOT be attempted here.

### OSR-004 — Relay-first public documentation

Public documentation MUST present GitHub Relay V1 as the primary path and MUST
keep legacy Secure Tunnel material in a separate legacy section without making
Tunnel a Relay dependency. Quick Start, metadata, examples, and verification
commands MUST be mutually consistent and MUST use real repository-root command
paths. Candidate-stage release refs MUST be marked as proposed; documentation
MUST NOT assert that a not-yet-created repository, tag, or Release exists.

The documentation MUST state that reading GitHub source is different from
creating labeled control Issues, that installing source grants no account
capability, and that the user's own session must actually provide the required
GitHub write tools for their private control repository. It MUST NOT generalize
one session's tool permissions to all users.

### OSR-005 — Release metadata consistency

The plugin manifest version MUST be `1.0.0-beta.1` and its repository,
homepage, and website URLs MUST name the proposed public repository
`https://github.com/younger404/chatgpt-codex-bridge`. Package tests MUST keep
deterministic expectations for these values. SECURITY.md MUST NOT invent a
private contact mailbox or claim that Private Vulnerability Reporting is
enabled; it records the channels that actually exist at publication time.

### OSR-006 — Minimal offline CI

If no applicable CI exists, the candidate MAY add exactly one minimal workflow
that runs the required offline tests with read-only permissions. The workflow
MUST NOT use real account secrets, real models, business repositories, release
tokens, self-hosted runners, or `pull_request_target` for untrusted code. A
workflow file's existence MUST NOT be reported as CI PASS.

### OSR-007 — Private reproducibility evidence

The final export MUST pass, in a synthetic clean HOME:

- `tests/portable/test-plugin-package.zsh`
- `tests/portable/test-public-sanitization.zsh`
- `tests/portable/test-github-relay-v1-install.zsh` (`--no-start` install)
- `tests/portable/test-readme-demo.zsh`
- `tests/portable/test-macos-installer.zsh`

plus the release checklist's applicable offline gates that do not require real
services, models, or credentials. Already-accepted results for unchanged
inputs MUST be labeled `PASS_INHERITED_UNCHANGED_INPUTS`, not fresh PASS.

### OSR-008 — Private candidate delivery and stop

The candidate MUST be delivered as one unmerged pull request against the
private engineering branch, containing the round diff, disposition summary,
attribution, test results, public archive/tree digests, unverified items, and
the proposed public version. This tranche MUST NOT create a remote repository,
change visibility, push publicly, create remote tags or Releases, merge, or
touch real runtime. Delivery stops for main-controller review.

## Non-goals

- Creating the public repository, tag, or Release (separate explicit gates).
- Anonymous clone verification (possible only after publication).
- Third-party real-machine installation claims.
- Repeating already-accepted real canary, authentication, token projection,
  policy probe, launchd, or readiness gates.
- Modifying Relay/Guard admission, execution, capability, registry hash,
  journal schema, publish, or GC behavior.

## Failure and rollback

- A missing scan, missing required verification, or license problem blocks the
  candidate; the blocker is reported exactly instead of a READY claim.
- All candidate edits are recoverable from the base commit; the private
  history and visibility remain unchanged.
