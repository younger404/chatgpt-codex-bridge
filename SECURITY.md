# Security Policy

## Scope

This repository contains source code, installation scripts, tests, and
documentation for a single-user macOS bridge. It contains no credentials.
The following must never appear in commits, Issues, or pull requests:

- capability signing keys, relay journal/database contents, operator registry
  files, or config plists from a real installation;
- Tunnel profiles, runtime keys, tokens, cookies, SSH keys, or `.env` files;
- real thread/job/conversation/workspace identifiers from your installation;
- personal device paths or account telemetry.

## Reporting a vulnerability

The proposed public repository plans to enable GitHub Private Vulnerability
Reporting; check the repository's Security tab for the channels that are
actually enabled at the time you report. If no private channel is available,
open a public Issue **without** any sensitive detail: describe only the
affected component, the kind of impact, and a way for the maintainer to
reproduce the class of problem with synthetic inputs. Never attach real
credentials, journals, registries, or identifiers to a report.

## If you suspect a secret leaked

Follow the repository release checklist
([docs/GITHUB_RELEASE_CHECKLIST.zh-CN.md](docs/GITHUB_RELEASE_CHECKLIST.zh-CN.md)):
pause distribution, rotate the affected credential, and evaluate history and
caches before deciding on history changes. Deleting only the current file is
not a completed fix, and making a repository private again does not retract
copies already obtained.

## Supported versions

Only the most recent tagged beta/release line is intended to receive fixes.
Candidate-stage refs marked "proposed" are not supported until published.

## Design boundaries worth knowing

- Public job/thread identifiers are installation-scoped HMAC bearer
  capabilities for a single-user local app; they are not multi-user
  authentication and not a trusted ChatGPT conversation identity.
- The relay fails closed on malformed input, unknown aliases, journal scope
  mismatch, and bound-resource drift.
- Stop/restart/uninstall revoke only verified bridge-owned process groups.
