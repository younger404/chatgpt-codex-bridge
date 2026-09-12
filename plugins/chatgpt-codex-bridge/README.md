# ChatGPT Codex Bridge

[中文说明](../../README.zh-CN.md) ·
[GitHub 发布脱敏清单](../../docs/GITHUB_RELEASE_CHECKLIST.zh-CN.md)

Portable macOS plugin for one ChatGPT conversation to supervise local Codex
projects through **GitHub Relay V1** (primary) or the legacy OpenAI Secure MCP
Tunnel. Long jobs run durably in one Codex project and task until the requested
outcome is complete.

Derived from [larryppgg/chatgpt-codex-bridge](https://github.com/larryppgg/chatgpt-codex-bridge)
(MIT). This distribution adds the GitHub Relay multi-project management
capability. It is a community package, not an OpenAI product.

## Architectures

`ChatGPT -> private control-repo Issue -> local GitHub Relay -> Guard -> Codex App Server -> managed worktree` (V1, no Tunnel)

`ChatGPT conversation -> Secure MCP Tunnel -> stdio Guard -> Codex App Server -> local project` (legacy)

The package does not ship `.mcp.json`, because loading the Guard as a
Codex-local MCP would create a recursive Codex-to-Guard-to-Codex path.

## GitHub Relay V1 quickstart (primary)

Prerequisites: macOS, Git, Python 3, authenticated GitHub CLI, an installed
working Codex, and your own empty **private control repository** on GitHub.
Secure Tunnel is not required. Existing receipts tested Codex `0.153.4` and
`gh` `2.89.0`; that is a tested-version record, not a compatibility promise.

> Release tag `v1.0.0-beta.1` and the public repository
> `younger404/chatgpt-codex-bridge` are **proposed** and not yet created;
> re-check existence before relying on the install commands below.

Clone the tagged release (once it exists) and work from the **repository
root** — the `plugins/...` paths below assume it:

```zsh
git clone --branch v1.0.0-beta.1 --depth 1 \
  https://github.com/younger404/chatgpt-codex-bridge.git
cd chatgpt-codex-bridge
```

The marketplace route (`codex plugin marketplace add
younger404/chatgpt-codex-bridge --ref v1.0.0-beta.1`, then `codex plugin add
chatgpt-codex-bridge@chatgpt-codex-bridge`) installs the same package; your
working root is then the installed plugin root, where the same scripts live
directly under `scripts/`. Start a new Codex task after plugin installation so
the new Skill inventory is loaded.

Register and verify your own synthetic sample repository, then install fresh.
From the repository root:

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh register \
  --alias sample-repo \
  --repo-path /absolute/canonical/repository \
  --repository-full-name owner/sample-repo \
  --base-remote origin \
  --base-branch main
/bin/zsh plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh verify sample-repo
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-github-relay-v1-macos.zsh \
  --workspace /absolute/bridge-workspace \
  --codex-bin /absolute/codex \
  --control-repository owner/control-private \
  --allowed-author operator-login \
  --enable-alias sample-repo
```

The installer is **fresh-only**: existing Bridge config, stores, keys, journal,
runtime or service files cause `FRESH_INSTALL_REQUIRED`. It does not recover or
upgrade an installation. The generic `install-macos.zsh --preset managed-repo`
continues to reject with `EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY`.

Default mode runs the required workspace-write/never inside/outside write probe
before creating installation files, then launches only the GitHub Relay service
(printing `GITHUB_RELAY_V1_STARTED POLICY_SUPPORT=PASS`). The probe invokes
Codex and may execute a model turn. `--no-start` makes no Codex,
GitHub or launchctl calls, creates no journal, and reports
`POLICY_SUPPORT=NOT_PROBED PLIST_DEFAULT_DISABLED=true LAUNCHD_STATE=NOT_PROBED
SERVICE_STARTED_BY_INSTALLER=false`. The plist defaults to Disabled=true; effective
launchd override state is not probed. Configuration-only output is not activation-ready;
`--no-start` is a terminal offline-evaluation state, not the first step of a
two-step install: the fresh installer cannot be rerun to adopt that state, so
there is no supported rerun-to-activate path. No capability, state path or
branch prefix argument is accepted.

Both modes publish a plist with Disabled=true. Normal activation explicitly enables
and bootstraps the service. Activation failure triggers best-effort disable of the
same fixed label; a disable failure is reported without claiming effective launchd
state. Partial files remain for separately reviewed recovery.

Managed jobs expose `codex-repo-start(repoAlias, prompt, taskName?)`,
`codex-reply-async`, `codex-wait`, and `codex-repo-publish`. Publish pushes the
generated branch only; it does not merge, rebase, force-push, or authorize
deployment. Review binds the exact evidence request ID and digest; new evidence
is unreviewed until an allowed author records a fresh review.

ChatGPT-side tooling is a separate requirement: your session must actually offer
GitHub write tools (labeled Issues, comments) for your private control
repository. A read-only GitHub connection cannot drive the web controller path;
see the repository root README for the capability precheck.

## Legacy: Secure Tunnel quickstart

Prerequisites: macOS, authenticated Codex, Python 3, official `tunnel-client`, a
device-specific Tunnel profile, and an existing workspace directory.

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-macos.zsh \
  --profile <device-profile> \
  --workspace <absolute-workspace> \
  --preset personal-full-control
/bin/zsh plugins/chatgpt-codex-bridge/scripts/doctor.zsh --runtime
```

Then create or refresh a ChatGPT Secure Tunnel app for this device, authorize
the reviewed tools, choose **Use in chat**, and start a new conversation. A
plugin install alone does not create or authorize that ChatGPT app.

The package includes `scripts/verify-tunnel-client.zsh` for the legacy
single-file and official v0.0.11 four-file release layouts, plus
`scripts/build-verified-tunnel-client.zsh` for the pinned official-source
fallback. The installer does not build dependencies; pass only the separately
verified v0.0.11 executable through `--tunnel-client-bin`. Neither helper
changes Gatekeeper policy or selects a `cloudflared` executable from `PATH`.

## Project loop

- New project (Tunnel): `codex-start` → repeated `codex-wait`.
- Managed repository (Relay): `codex-repo-start` → repeated `codex-wait`.
- Continue: `codex-reply-async` on the returned `threadId` → repeated wait.
- Closed page/model turn: reopen the conversation and use the card's explicit
  return control; use `codex-job-open` for a stale template.
- Short diagnostics only: `codex` / `codex-reply`.

The bundled portable `workspace-new-project` Skill initializes spec/ADR/source
structure before implementation. The installer stages it privately under
bridge-owned runtime state, so a clean Mac does not need a preinstalled global
Skill.

Version 1.0.0-beta.1 keeps the 0.6.1 security boundary: signed bearer
capabilities bound to the installation workspace and fixed policy, bounded
synchronous and asynchronous work, untrusted model output, and
stop/restart/uninstall revoking verified bridge-owned process groups. Pre-0.6.1
cards and identifiers do not cross this boundary.

## Secure Tunnel operations (legacy)

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh status
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh restart
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh stop
/bin/zsh plugins/chatgpt-codex-bridge/scripts/uninstall-macos.zsh
```

These commands operate the Tunnel service only; they are not GitHub Relay
commands. For Tunnel upgrades, install a pinned newer Git ref, rerun
`install-macos.zsh` with the same external profile/workspace, then restart, run
doctor, refresh the ChatGPT app, and start a new conversation. Public v0.6.0 is
withdrawn and MUST NOT be used as a rollback target.

Uninstall removes bridge-owned capability/job state but preserves the external
Tunnel profile, credentials, repositories, and Codex conversation history.
Detailed install/upgrade, controller-loop,
MCP-contract, and recovery SOPs are under
`skills/chatgpt-codex-controller/references/`.

## Offline doctor and process evidence

Unqualified `doctor` now prints usage and does not read installed configuration.
Existing runtime checks require `doctor --runtime`; `--no-start` alone is not an
offline guarantee. `status` retains its existing runtime checks. This change does
not install or start anything and does not authorize a recovery attempt.

From the repository root, check an explicitly provided **synthetic/exported**
managed-repo plist and candidate source without opening any referenced runtime,
registry or credential path:

```sh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/doctor.zsh --static \
  --config /absolute/operator-input.plist --source-root /absolute/candidate
```

The plist fields are `preset=managed-repo`, `sandbox=workspace-write`,
`approval_policy=never`, and absolute `python_bin`, `codex_bin`, `runtime_guard`,
`runtime_managed_repo`, `runtime_wrapper`, `managed_registry` values. Referenced
paths are checked for shape only. No executable version/help/doctor is invoked.
Missing fields/files are aggregated. `--expected-digests /absolute/digests.json`
optionally compares expected SHA256 for fixed source paths listed in
`bridge-doctor.py:SOURCE_FILES`; no config-supplied arbitrary file is hashed.
Without expected digests, comparison is `NOT_COLLECTED`, not drift. Success is
`STATIC_CHECKS_PASSED`, with runtime `NOT_RUN` and live identity `NOT_COLLECTED`.
It is not service readiness or historical baseline continuity.

The same entry offers explicit read-only process observation, under separate
permission to inspect the designated process and files:

```sh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/doctor.zsh --observe \
  --contract /absolute/private-identity-input.json \
  --private-output /absolute/new-private-observation.json
```

The JSON contains integer `pid`, `uid`, `ppid`, a `label`, `started_monotonic`
(the actual same-host `time.monotonic()` captured at the authorized start, never
reset on retry), and `files`. Each of `plist`, `launcher`, `runner`, `interpreter`,
`framework`, `application` has an explicit canonical `path` and an existing
expected lowercase `sha256`. This command never generates or adopts a baseline.
Plist label and `[launcher, runner]` command must match; final argv must be exactly
`[interpreter, application, "--watch"]`. All four identity layers and independent
interpreter/framework evidence are required. Only exact launcher/runner evidence
permits another observation inside the original 15 seconds. No service discovery,
start, restart or process cleanup occurs. It does not replace separate duplicate
process/service admission or any later recovery acceptance phase.

stdout is sanitized JSON. Native return lengths, immediate errno, before/after
steps, time, local successful/failed steps and raw input appear only in a new
0600 private file. Existing files are never overwritten. A save error reports
`PRIVATE_RECORD_WRITE_FAILED` on stderr, retains the original `observation_result`,
marks `complete=false`, and exits nonzero. Target exit status remains null when not
obtained; the lsof exit code describes only the independent reader. Historical
RESUME-04 cause remains UNKNOWN, regardless of new fixture/system test results.

## Distribution boundary

This is a community package licensed under MIT. It is not an OpenAI product and
does not grant ChatGPT, Codex, Tunnel, GitHub, or device credentials. Every user
and device performs its own official setup and authorization.

Current platform support is macOS LaunchAgent. Windows and Linux service
packaging are not implemented.
