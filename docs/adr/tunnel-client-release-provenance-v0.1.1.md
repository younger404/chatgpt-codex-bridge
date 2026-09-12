# ADR: Separate Tunnel Artifact Provenance From macOS Runtime Capability

Status: Accepted for managed-repo-v0.1.1

## Context

The official `openai/tunnel-client` v0.0.11 Darwin arm64 release archive now
contains four files rather than the legacy single binary. The existing verifier
therefore rejects an authentic release before comparing its payload. On this
Mac, the byte-exact official client also passes code-signature verification but
is rejected by the operating-system execution assessment. Treating that host
policy result as a provenance failure obscures the actual boundary.

## Decision

The verifier accepts exactly two release shapes: a legacy single
`tunnel-client`, or the v0.0.11 set `tunnel-client`, `cloudflared`,
`cloudflared-manifest.json`, and `LICENSE`. It rejects every other entry and all
unsafe ZIP metadata, verifies the official checksum, and compares only the
archive's `tunnel-client` payload byte-for-byte with the candidate. It never
executes `cloudflared`.

After artifact checks pass, read-only macOS diagnostics classify runtime
capability separately. No Gatekeeper bypass is implemented or documented. A
verified artifact blocked by macOS is `RUNTIME_BLOCKED`, not provenance
`FAIL`.

When that condition occurs, the supported fallback is a local build from the
official v0.0.11 source tag and its reviewed exact commit. A dedicated script
checks repository identity, tag resolution, clean tree, version file, module
integrity, fixed build command, output architecture/version/help, and absence
of quarantine. It emits a non-secret provenance receipt. The installer remains
binary-only and receives the verified result through `--tunnel-client-bin`.

## Consequences

- Official distribution layout changes no longer create a false stale-contract
  failure for v0.0.11.
- Artifact authenticity and local runtime permission remain auditable as
  independent facts.
- The Bridge cannot silently weaken macOS security policy.
- Source compilation adds a Go toolchain prerequisite but does not expand the
  Bridge's transport, repository, deployment, or authorization surface.
- Future cloudflared-managed transport remains closed until a separate verified
  companion contract is approved.
