# Public Release v1 Design

Status: Released
Spec ID: `public-release-v1`

## Reuse decision

Adapt the existing Guard, installer, plugin, Apps component, tests, and
sanitization gate. Do not create a second MCP server. OpenAI Secure MCP Tunnel
remains the transport, while the Guard remains a stdio server that starts
official Codex MCP/App Server processes.

## Capability boundary

`CapabilityCodec` owns a random 256-bit installation key stored as
`<job-state-root>/capability.key` with mode `0600`. A public value is:

`cgb1.<audience>.<base64url(raw-id)>.<base64url(HMAC-SHA256)>`

The MAC covers the version, audience, and exact raw identifier. Decoding uses
constant-time comparison, validates the requested audience, and rejects empty
or oversized identifiers. `job` capabilities resolve to UUID-named durable
directories; `thread` capabilities resolve to raw Codex thread IDs only after
the codec succeeds.

Workers receive the existing key path from the trusted parent process. Durable
state stores both private raw identifiers and public capabilities; only public
capabilities leave the Guard. The synchronous compatibility pair uses the same
codec before forwarding or returning a thread.

This is deliberately a scoped bearer-capability design, not a claim of
conversation identity. The current ChatGPT MCP call contract does not expose a
stable trusted conversation principal to this stdio server.

## Admission and lifetime boundary

Defaults:

- prompt: at most 256 KiB UTF-8;
- active jobs: at most 2;
- retained jobs: at most 512;
- worker lifetime: at most 4 hours.

The job root owns an advisory `flock` file. Enqueue holds the lock while it
reconciles stale states, counts valid UUID directories, applies the limits,
creates the durable record, and starts the detached worker. A rejected request
does not create a job or project directory.

Terminal records are not pruned automatically in v0.6.0. Hitting the retained
limit fails closed and directs the operator to uninstall/reinstall or use a
future reviewed pruning command. This avoids an automatic recursive deletion
surface in the first public release.

`AppServerClient` receives a monotonic deadline. Every blocking read uses a
selector bounded by the remaining time. Deadline expiry terminates App Server,
persists a failed terminal record, and releases the active slot.

## Publication flow

1. Commit and push the verified private source milestone.
2. Create a new temporary directory under a validated `mktemp -d` path.
3. Export the release commit with `git archive`; do not copy `.git`.
4. Rerun privacy, secret, package, installer, and Guard checks inside the
   export.
5. Initialize a new Git repository, create one release commit and annotated
   tag, create the empty public GitHub repository, and push `main` plus the tag.
6. Read back visibility, commit count, tag target, and install URLs.

## Alternatives rejected

- Making the private repository public: old objects contain private deployment
  history and would cross the approved boundary.
- Rewriting private history: unnecessary blast radius and would disturb the
  existing source/audit chain.
- Trusting caller `_meta` as a conversation principal: not documented as a
  stable authenticated identity at this MCP boundary.
- Adding `.mcp.json`: would create a recursive Codex → Guard → Codex topology.
- Automatic terminal-job deletion: adds a destructive path before a separate
  lifecycle contract exists.
