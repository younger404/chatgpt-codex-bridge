# v0.6.1 Security Hardening Requirements

Status: Approved
Spec ID: `v0.6.1-security-hardening`

## Goal

Close every validated post-release security/privacy finding in public release
`v0.6.0`, preserve the supported ChatGPT → Secure Tunnel → Guard → Codex
workflow, and publish a Chinese operator guide that can be reused as the
repository's release standard.

## Trust boundary

- Publishing or cloning this repository MUST NOT by itself grant remote access
  to a Mac.
- Local execution MUST require a locally installed/running Guard, an official
  per-device Tunnel profile, ChatGPT app authorization, and a valid
  installation/context-scoped capability.
- `personal-full-control` remains an explicit single-user preset. The release
  MUST describe its authority without claiming that public source code alone
  can control a device.

## Requirements

### SH-001 — Complete execution revocation

When `stop`, reinstall preparation, or `uninstall` runs, the bridge MUST block
new calls and terminate every verifiably managed detached worker process group
before reporting success. It MUST fail closed rather than signal an unrelated
or unverifiable PID. Terminal state MUST record interruption.

Acceptance:

- a detached worker and descendant are both gone after revocation;
- a forged/stale worker record is rejected without signalling the foreign PID;
- `stop` cannot print `status=stopped` while a managed worker remains.

### SH-002 — Secure state lifecycle

Uninstall MUST securely remove bridge-owned capability keys and durable job
state after revocation. Tunnel credentials, repositories, project files and
Codex conversation/session history MUST remain untouched.

### SH-003 — Context-bound capabilities

Job/thread capabilities MUST bind audience, normalized workspace, sandbox,
approval policy and format version. A token issued for another workspace,
preset, installation key or legacy format MUST fail before downstream Codex.

### SH-004 — Total input and resource bounds

All public tool paths MUST share the same UTF-8 prompt limit. Synchronous calls
MUST have a bounded in-flight count and wall-clock deadline. Malformed Unicode
capabilities MUST return a protocol error without terminating the Guard.

### SH-005 — Untrusted result separation

The Apps recovery message MUST NOT copy Codex output into a new user-role
message. It MUST send only the signed job handle and an instruction to retrieve
the result through `codex-wait`. Tool results MUST label Codex content as
untrusted data and keep controller instructions outside the data delimiter.

### SH-006 — Verify before execute

When archive/checksum provenance inputs are supplied, the Tunnel verifier MUST
complete checksum, archive-shape and payload-identity checks before executing
the candidate binary. A failed integrity gate MUST cause zero candidate side
effects.

### SH-007 — Public privacy boundary

Tracked source MUST NOT contain real or reconstructable retired usernames,
service namespaces, Tunnel profiles, private timezones, account observations,
host package state, private network failures or measured personal-run latency.
Machine-specific denylist values MUST come from an untracked optional input;
public fixtures MUST be synthetic.

### SH-008 — Chinese illustrated documentation

The repository MUST provide a detailed Chinese guide containing:

- architecture, authorization and same-thread sequence diagrams;
- prerequisites, install, ChatGPT attachment, use, upgrade, stop and uninstall;
- an explicit answer to whether a public repository can control the computer;
- the previously encountered failure modes and their correct diagnosis;
- a reusable GitHub publication/desensitization checklist;
- rollback and verification commands.

### SH-009 — Release gate

Before release, source and packaged Guard copies MUST be byte-identical and all
focused security tests, Guard tests, portable installer/package tests, Zsh and
Python checks, anonymous export privacy scan and Gitleaks scan MUST pass.

### BRIDGE-GUARD-FIX-01 — Existing store preservation (engineering only)

Given an existing canonical, operator-owned root (0700) and private regular
single-link 32-byte key (0600), ordinary JobStore/CapabilityCodec initialization
MUST preserve identity, owner, mode, size, nlink, mtime and ctime without explicit
metadata mutation. Key reads remain required; atime preservation is not promised.
Noncompliant existing objects MUST fail closed without repair. Only exclusively
created new objects MAY initialize their required permissions. HMAC/context,
MCP contracts, GC policy and legacy data MUST remain unchanged. Verification MUST
use synthetic objects and keep runtime mirrors equal; no deployment or recovery
is authorized. Failed validation leaves existing objects unchanged, with the
existing configuration-error boundary. Rollback is source-only.

## Non-goals

- Multi-user or tenant authorization.
- Zero-click wake-up of an inactive ChatGPT conversation.
- Windows/Linux service packaging.
- Adding `.mcp.json` or making Codex recursively call this Guard.
- Deleting user repositories, project directories or Codex session history.

## Failure, rollback and observability

- Revocation or purge uncertainty MUST return non-zero and name only the
  affected bridge-owned state class, never capability values or prompts.
- `v0.6.1` MAY reject `v0.6.0` cards/capabilities; the upgrade guide MUST state
  that active work should be completed before upgrading.
- Public rollback to `v0.6.0` is prohibited because that release contains the
  documented findings and superseded privacy material. Operational rollback is
  `stop` or `uninstall`; source recovery remains in the private authoritative
  repository.
