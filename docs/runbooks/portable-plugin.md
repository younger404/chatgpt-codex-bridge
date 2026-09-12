# Portable ChatGPT–Codex Bridge Plugin

Status: legacy Secure Tunnel runbook. The `chatgpt-codex-bridge-v0.6.1`
ref names the historical upstream release; the current distribution is
`1.0.0-beta.1` (proposed), whose primary path is GitHub Relay V1 — see the
repository root README. Tunnel commands below operate the Tunnel service
only.

## What the plugin does

The repository plugin packages the reviewed Codex MCP Guard, macOS login
service, install/doctor/uninstall commands, and the one-conversation/one-thread
controller Skill. It uses OpenAI's official `tunnel-client`; it does not
implement or replace Tunnel transport.

Installing the plugin does not automatically create a ChatGPT web connector.
The local service and the ChatGPT Secure Tunnel app are separate per-device
steps.

## Install the plugin

The historical upstream install pinned the `chatgpt-codex-bridge-v0.6.1` ref
of `larryppgg/chatgpt-codex-bridge`. For the current distribution, use the
proposed public repository and release documented in the repository root
README (candidate-stage refs are marked proposed and are not yet executable).
From a source checkout, use the scripts directly under
`plugins/chatgpt-codex-bridge/`.

Start a new Codex/ChatGPT desktop session after plugin installation so the new
Skill inventory is loaded.

The repository is public under MIT. It is a community package, not an OpenAI
product. Repository access does not provide any device's Tunnel profile,
credentials, Codex login, or ChatGPT authorization.

## Prepare one Mac

Each Mac needs:

- a working Codex executable and local Codex login;
- the official `tunnel-client`;
- its own external Tunnel profile and runtime-key reference;
- an existing workspace directory.

Do not copy another device's Tunnel profile, credential file, Codex login,
ChatGPT authorization, or Codex conversation history.

Run from the plugin root:

```bash
/bin/zsh scripts/install-macos.zsh \
  --profile <this-device-profile> \
  --workspace <absolute-workspace-directory> \
  --preset personal-full-control

/bin/zsh scripts/doctor.zsh
```

`personal-full-control` is the default and fixes Codex to
`danger-full-access` plus `never`. For a shared or less-trusted workspace, use
`workspace-safe`, which fixes `workspace-write` plus `on-request`. The MCP
caller cannot change these values. The safe preset applies to threads created
through that installation; continue only the signed `threadId` capability
returned by the same attached device app.

Version 0.6.1 starts a new context-bound `jobs-v3` capability store. Older job
cards and identifiers do not cross this security boundary. Complete old work
before upgrading. Public v0.6.0 is withdrawn rather than offered as rollback;
it does not accept v0.6.1 cards or capabilities and retains the corrected
findings.

The installer derives the current user's Home and UID. Optional overrides are:

- `--codex-bin <absolute-executable>`
- `--tunnel-client-bin <absolute-executable>`
- `--label <launchagent-label>`

No sudo is required. Device paths and policy are stored in a non-secret plist;
Tunnel identity and credentials remain in the external Tunnel profile.

## Attach ChatGPT

1. Keep the local service ready.
2. In ChatGPT Developer Mode, create or select a Secure Tunnel app for this
   device's Tunnel.
3. Review the tools, authorize the intended permission, and choose
   **Use in chat**.
4. Verify the app pill is visible in the new conversation.
5. For every new project, let ChatGPT call
   `codex-start(prompt, projectName)`. The display name is not a path: the
   bridge creates a unique child root and an App Server interactive task, then
   passes the installed `workspace-new-project` as an explicit Skill input and
   invokes `$workspace-new-project --here` before implementation. The
   returned `jobId` is joined through repeated `codex-wait(jobId)` calls while
   queued/running. ChatGPT reviews the terminal result and continues the
   returned thread with `codex-reply-async(prompt, threadId)` plus another wait
   loop until the full request is complete. If the page or model turn closes,
   the status component remains the recovery path: click
   `把结果发给 ChatGPT 审查` once to submit the stored result into the same
   conversation. Use the synchronous pair only for short diagnostics.

Use distinct app names for multiple computers, such as `Codex Mac mini` and
`Codex MacBook`. A conversation controls the app/Tunnel attached to that
conversation; it does not automatically select among computers.

## Operations and removal

```bash
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh status
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh restart
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh stop
/bin/zsh plugins/chatgpt-codex-bridge/scripts/uninstall-macos.zsh
```

`stop` unloads the Tunnel and revokes verified bridge-owned worker process
groups. `uninstall` also removes bridge-owned capability/job state and generated
LaunchAgent/runtime/config/log files, while preserving the external Tunnel
profile, credentials, repositories, and Codex conversation history.

Windows Task Scheduler and Linux systemd installers are not included in T-406.
