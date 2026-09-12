# Public Release Sanitization Requirements

Status: Complete
Spec ID: `public-release-sanitization`

## Goal

Prepare the current tracked repository tree for a possible public release
without changing repository visibility or rewriting Git history.

## Requirements

### SR-001 — No committed credentials

The tracked tree MUST NOT contain a usable API key, access token, Tunnel ID,
private key, browser credential, cookie, credential file, or private endpoint.

Acceptance:

- Gitleaks directory scanning of an archive produced from `HEAD` reports zero
  findings.
- Synthetic negative fixtures remain clearly non-usable and bounded to tests.

### SR-002 — No personal device telemetry

The tracked tree MUST NOT disclose the original macOS username, personal home
path, personal LaunchAgent label, device-specific Tunnel profile, timezone,
administrator status, or private-device wording as operational truth.

Historical implementation evidence MAY remain only after replacement with
synthetic placeholders such as `/Users/example-user`, `<tunnel-profile>`, and
`<project-root>`.

Acceptance:

- A repository-wide tracked-text check accepts an optional repository-external
  denylist and rejects every listed literal without printing it.
- All remaining absolute macOS home paths use an approved synthetic account.

### SR-003 — Preserve deliberate publisher attribution

The repository owner used by the canonical install URL MAY remain because it is
the distribution identity exposed by the remote repository itself. Public
attribution MUST NOT be combined with incidental location, account-tier,
administrator, or device-specific telemetry.

Acceptance: publisher metadata is limited to repository/install identity.

### SR-004 — Remove superseded personal deployment assets

The fixed-user LaunchAgent, fixed-user management script, and their fixed-user
contract test MUST be removed from the release tree. The parameterized portable
plugin installer MUST remain the only supported installation path.

Acceptance:

- root documentation points to the portable installer;
- portable install/doctor/uninstall tests still pass;
- no fixed-user service file remains tracked.

### SR-005 — Prevent regression

The repository MUST provide a deterministic, offline tracked-text privacy gate.
It MUST scan the entire tracked tree rather than only the plugin subtree and
MUST fail with file/line evidence without printing credential values.

Acceptance: the gate passes the sanitized tree and a test proves it rejects a
synthetic personal path in a temporary repository.

### SR-006 — Preserve history and publication boundaries

This tranche MUST NOT change repository visibility, force-push, delete tags,
rewrite commits, rotate credentials, or claim that historical Git objects are
sanitized. History inspection MUST be read-only and any rewrite/publication
decision requires a separate explicitly approved change.

Acceptance: the remote remains private and existing refs are unchanged by this
tranche.

## Non-goals

- Anonymous publishing; the current GitHub owner is deliberate attribution.
- Fixing unrelated MCP authorization or background-job admission findings.
- Declaring the repository public-release-ready before Git-history review.
- Modifying any currently installed legacy LaunchAgent during a source-only
  sanitization pass.

## Failure and rollback

- If portable tests regress, restore the removed legacy references only in a
  private branch and keep publication blocked.
- If a real credential is found, stop, report only its type/location, rotate it
  before any history operation, and do not publish.
- All current-tree edits are recoverable from the preceding Git commit.
