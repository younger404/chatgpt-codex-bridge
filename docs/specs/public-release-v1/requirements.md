# Public Release v1 Requirements

Status: Released
Spec ID: `public-release-v1`

## Goal

Publish a clean-history, reusable public release of ChatGPT Codex Bridge without
exposing private repository history or leaving the two validated runtime
security findings open.

## Requirements

### PR-001 — Clean public history

The public repository MUST be created from a validated archive of one private
source commit. It MUST NOT share Git objects, refs, tags, remotes, or commit
history with the private source repository.

Acceptance:

- the public `main` branch has one initial release commit;
- the public tag points at that commit;
- the private repository remains private and its history is unchanged.

### PR-002 — Public distribution identity

All install URLs, plugin metadata, marketplace metadata, and release docs MUST
name `https://github.com/larryppgg/chatgpt-codex-bridge` and release
`chatgpt-codex-bridge-v0.6.0`.

The public repository MUST include an MIT license and MUST NOT claim that
OpenAI endorses or supports this community package.

### PR-003 — Scoped bearer capabilities

The Guard MUST NOT expose or accept raw Codex thread identifiers or raw durable
job UUIDs at the public MCP boundary. It MUST issue installation-scoped,
HMAC-authenticated bearer capabilities with distinct `thread` and `job`
audiences.

Given a missing, malformed, forged, cross-type, or installation-foreign
capability, reply, wait, open, and status calls MUST fail closed before reaching
Codex App Server or durable job content.

The signing key MUST be generated locally with owner-only permissions and MUST
remain outside Git. Capability possession remains authorization within this
single-user local app; no unsupported ChatGPT conversation-principal claim may
be made.

### PR-004 — Bounded async admission

The Guard MUST enforce all of the following before spawning a worker:

- a maximum UTF-8 prompt byte size;
- an atomic maximum count of queued/running jobs;
- a maximum retained durable-job count;
- a maximum wall-clock lifetime for each App Server job.

Admission failures MUST NOT allocate a project directory or worker and MUST
return a stable MCP error. Existing terminal records MUST NOT be deleted
automatically in this release.

### PR-005 — Compatibility and recovery

The public field names `threadId` and `jobId` MAY remain for ChatGPT tool
compatibility, but their values MUST be scoped capabilities rather than raw
local identifiers. New-project creation, same-thread continuation, bounded
wait, Apps recovery, Codex sidebar registration, and bundled
`workspace-new-project` bootstrap MUST continue to work.

Version `0.6.0` MAY reject identifiers issued by pre-0.6.0 installations; this
breaking security boundary MUST be documented in upgrade and rollback SOPs.

### PR-006 — Verification and publication gate

Before public repository creation, the source commit and the clean export MUST
both pass:

- Guard regression tests;
- portable plugin and macOS installer tests;
- public sanitization tests;
- source/package byte-identity checks;
- Gitleaks current-tree scan;
- an independent final diff review.

If any gate fails or a usable secret is found, publication MUST stop.

## Non-goals

- Multi-user or tenant isolation.
- Zero-click reverse wake-up of an inactive ChatGPT conversation.
- Windows or Linux service packaging.
- Publishing the private source repository or rewriting its history.
- Adding `.mcp.json` or making Codex load the Guard as its own MCP server.

## Failure, rollback, and observability

- Before remote creation, rollback is the previous private commit.
- After public creation, a failed publication is corrected by a new public
  commit/tag; the private history remains the source of truth.
- Admission rejection, invalid capability, and deadline expiry MUST be visible
  as bounded MCP/job errors without logging capability or prompt contents.
