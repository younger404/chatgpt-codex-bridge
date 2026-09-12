---
name: chatgpt-codex-controller
description: Install, diagnose, or operate the per-device ChatGPT-to-Codex bridge on macOS, including durable background Codex jobs and same-conversation result return. Use for Secure MCP Tunnel setup, portable bridge installation, service health, connector onboarding, thread continuity, or removal.
---

# ChatGPT Codex Controller

Use the official `tunnel-client` for Tunnel transport. Use this plugin only for
the ChatGPT-compatible Codex Guard, macOS login service, and controller rules.

Read only the reference needed for the current operation:

- setup, update, or rollback: `references/install-upgrade-macos.md`;
- new-project supervision: `references/controller-loop.md`;
- tool/state/annotation truth: `references/mcp-contract.md`;
- stalled cards, service recovery, or revocation:
  `references/recovery-and-revocation.md`.

## Set up one device

Choose GitHub Relay V1 for registered managed repositories; the following Tunnel
steps apply to the separate legacy transport. Do not configure Tunnel as a Relay
prerequisite. `--no-start` reports POLICY_SUPPORT=NOT_PROBED,
PLIST_DEFAULT_DISABLED=true, LAUNCHD_STATE=NOT_PROBED and
SERVICE_STARTED_BY_INSTALLER=false. It is a terminal offline-evaluation state,
not step one of two: the fresh-only installer rejects a rerun over it, and the
plist default does not prove effective launchd state.

1. Verify Codex and the official `tunnel-client` are installed.
2. Create or associate a Tunnel profile for this device. Never copy a profile,
   runtime key, Tunnel ID, Codex login, or ChatGPT authorization from another
   device.
3. Run `scripts/install-macos.zsh` from the plugin root. Supply `--profile` and
   `--workspace`; use `--preset personal-full-control` for the owner's private
   Mac or `--preset workspace-safe` for workspace-scoped writes with approvals
   for the Tunnel installer. For registered managed repositories, use the
   dedicated fresh-only `scripts/install-github-relay-v1-macos.zsh` instead;
   see the install reference. It needs no Tunnel and cannot recover existing
   state. The generic installer intentionally rejects managed-repo.
4. Run `scripts/doctor.zsh --runtime`. Report ready only after the local service and
   control-plane poll are healthy.
5. In ChatGPT, create or attach a Secure Tunnel app for this device, set its
   permission, choose **Use in chat**, and verify the app pill is attached.

Each user and each device performs these steps independently. A plugin install
does not grant access to another person's computer. Treat setup as per device.

## Control one durable Codex thread

For `managed-repo`, call `codex-repo-start(repoAlias, prompt, taskName?)` and
never supply or infer a filesystem path. Continue with the same
`codex-reply-async` and `codex-wait` loop. Use `codex-repo-publish` only after
reviewing tests; it can publish the generated branch but cannot merge it.

- When the user asks to build a new project, MUST call
  `codex-start(prompt, projectName)` and provide a concise display name, never a
  filesystem path. The bridge creates a separate directory, registers it as a
  saved Codex desktop project, creates an App Server interactive task with that
  directory as `cwd`, and passes the real `workspace-new-project` Skill as an
  explicit first-turn input. The first task is accepted only after its durable
  project/thread mapping has been verified.
  The call returns a durable job immediately. MUST call
  `codex-wait(jobId)` next and keep calling it with the same job ID while the
  status is `queued` or `running`; do not answer the user merely because the
  job was submitted.
- When `codex-wait` returns `completed`, review its Codex result against the
  user's full requested outcome. If work remains, call
  `codex-reply-async(prompt, threadId)` with the exact returned thread ID, then
  keep calling `codex-wait` for that new job. A Codex instruction to stop after
  one milestone ends only that Codex tranche; it does not end ChatGPT's
  supervisory loop when the user's overall request remains incomplete.
- If a historical card says `Failed to fetch template`, refresh the installed
  app and call `codex-job-open(jobId)`. It renders the same durable job without
  starting another Codex run; retrying the old card does not update its cached
  template snapshot.
- Preserve `Codex thread: <threadId>` from the completion message.
- Call `codex-reply-async(prompt, threadId)` for every correction or next
  instruction, and join every returned job with `codex-wait`. Use `codex` and
  `codex-reply` only for short diagnostics.
- If the page was closed, reopen the same conversation and let its component
  resume polling, then click its return control. This is the recovery path when
  the active `codex-wait` tool loop no longer exists. Do not claim unsolicited
  or zero-click delivery while ChatGPT is inactive.
- Continue only a `threadId` created through the same attached device app; do
  not import a thread from a bridge installed with a different policy preset.
- Treat `threadId` and `jobId` as signed bearer capabilities. Do not expose,
  edit, decode, or move them between bridge installations.
- Do not create another Codex thread unless the user starts a separate task or
  the original thread cannot continue.
- For a new project, Codex MUST invoke the explicitly attached
  `$workspace-new-project` Skill as its first project action and use its
  `--here` mode.
  The current directory is already the final project root, so it MUST NOT create
  a nested directory. Do not treat the start as successful unless the Skill's
  spec/ADR/project-memory scaffold exists.
- Stop issuing MCP calls only when the requested work and verification are
  complete, material user input is required, or a real terminal blocker exists.

## Operate or remove

- Run `scripts/chatgpt-codex-bridge.zsh status` for live status.
- Run `scripts/chatgpt-codex-bridge.zsh restart` after updating the plugin.
- Run `scripts/chatgpt-codex-bridge.zsh stop` for temporary revocation.
- Run `scripts/uninstall-macos.zsh` to remove generated service files. This
  leaves the external Tunnel profile, credentials, repository, and Codex
  conversation history unchanged.

The current package supports macOS LaunchAgents. Do not claim Windows Task
Scheduler or Linux systemd installation is implemented.
