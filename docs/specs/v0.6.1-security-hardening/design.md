# v0.6.1 Security Hardening Design

Status: Approved
Spec ID: `v0.6.1-security-hardening`

## Reuse decision

Adapt the existing Guard, installer, verifier, Apps widget and release gate.
Do not create a second MCP server or service. Reuse the existing UUID-only job
store, exact-path installer checks, HMAC codec, process-group isolation and
portable package tests, but close their missing lifecycle/context boundaries.

External patterns support the same approach: MCP authorization guidance binds
bearer authority to its intended resource; current Codex process-lifecycle
reports recommend signalling the owned POSIX process group rather than only the
parent PID. A new daemon, browser automation layer or `.mcp.json` would add
coupling without closing any finding.

## Capability v2

Use `cgb2.<audience>.<context>.<raw-id>.<signature>`. `context` is a
SHA-256 digest over a canonical JSON object containing workspace, sandbox,
approval policy and schema version. HMAC covers every visible segment.

The durable store moves to `jobs-v3`, so old `cgb1` records never poison new
state. The same installation key may persist across an ordinary service
restart, but a different context rejects the token. Secure uninstall removes
`jobs-v2`, `jobs-v3` and their keys only after worker revocation.

## Worker ownership and revocation

Each worker record stores PID, process-group ID, canonical worker script and
canonical job directory. Because `start_new_session=True`, PID and PGID MUST be
equal at launch. Revocation:

1. stops the Tunnel LaunchAgent to block new calls;
2. scans only canonical `jobs-v2`/`jobs-v3` roots and UUID child directories;
3. validates regular JSON records and the live command line's exact `--run-job`
   directory before signalling;
4. sends SIGTERM to the owned process group and waits boundedly;
5. refuses success if a managed group remains or ownership cannot be proved;
6. records active jobs as `interrupted`;
7. on uninstall only, removes the exact known state files and empty directories.

## Sync bounds and error isolation

Both sync tools apply `PROMPT_MAX_BYTES`. At most one synchronous Codex request
is in flight. A monotonic deadline is attached to the pending request; expiry
returns a bounded error, terminates the shared downstream child and lets the
LaunchAgent restart a clean Guard. Capability character validation occurs
before ASCII encoding, and all malformed inputs map to `GuardProtocolError`.

## Result trust boundary

The Apps button posts only a signed job handle and a request to call
`codex-wait`; it never copies `state.content` or a raw thread identifier into a
user-role prompt. `codex-wait` returns structured content plus a text rendering
whose data is enclosed in explicit `BEGIN/END UNTRUSTED CODEX OUTPUT` markers.

## Privacy and documentation

The public checker accepts an optional untracked denylist file containing one
literal per line. Repository fixtures use invented sentinel values only. Real
account/host/network/latency evidence is replaced by generalized pitfalls and
acceptance rules. GitHub-rendered Mermaid diagrams provide illustration without
publishing screenshots that may contain personal UI data.

## Rollback

### BRIDGE-GUARD-FIX-01 decision

Separate exclusive creation from existing-object validation inside the current
key loader and root initializer; do not add a store abstraction or permission
repair fallback. Initialize 0600/0700 only on the newly created object, then
validate type, canonical path, current owner and required permissions (plus key
single-link/32-byte identity). Preserve existing error and capability semantics.
Tests pre-create both root and key so unrelated key creation does not invalidate
the existing-root metadata assertion. See ADR 0019 for the bounded decision.

All changes are source-controlled in the private authoritative repository. A
failed code tranche reverts there to the prior commit. Runtime installation is
not mutated during repository tests. The public `v0.6.0` ref is withdrawn
rather than offered as a rollback because it contains the corrected findings.
