# ADR-0014: Bind capabilities and revoke owned process groups

Status: Accepted
Date: 2026-08-22

## Context

Public `v0.6.0` correctly hid raw Codex identifiers and bounded asynchronous
jobs, but a post-release audit proved two deeper lifecycle failures: an old
capability crossed later workspace/policy changes, and a detached worker could
survive Guard stop/uninstall. Uninstall also retained the signing key and job
state, so reinstall was not a security reset.

## Decision

Introduce context-bound `cgb2` capabilities and an isolated `jobs-v3` store.
Bind every token to workspace, sandbox, approval policy and schema version.
Track the owned worker process group, stop the Tunnel entrypoint first, validate
worker ownership from the exact job path, and terminate the complete process
group before reporting revocation. Secure uninstall removes only bridge-owned
job/capability state after revocation.

## Consequences

- `v0.6.0` job cards and thread capabilities do not continue into `v0.6.1`.
- Ordinary restarts in one unchanged installation preserve `v0.6.1` cards.
- Stop/uninstall may fail closed if a process record cannot be safely attributed;
  this is preferable to signalling an unrelated PID or claiming false revocation.
- Tunnel profiles, credentials, repositories, project files and Codex session
  history remain external and are never purged by the bridge.
