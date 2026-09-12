# ADR 0015: Use Private GitHub Issues for the R-GH1 Relay

## Status

Accepted for R-GH1 proof.

## Decision

Use Issues in the existing private control repository as the first control
queue. (The historical repository identifier is replaced with the synthetic
placeholder `example/control-private` for publication.) A local outbound-only relay admits a closed request schema and delegates
to the existing managed-repo Guard over stdio. GitHub receives only an opaque
relay reference and a sanitized terminal result.

## Consequences

- No new repository scope, inbound server, public Tunnel, Actions runner, or
  workflow execution is introduced.
- Local SQLite becomes the only mapping between public relay references and
  Guard bearer capabilities.
- R-GH1 supports only `start` and cannot publish. Reply and publish require
  separate future ADRs and contracts.
