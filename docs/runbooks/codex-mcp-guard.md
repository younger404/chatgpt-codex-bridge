# Codex MCP Guard Runbook

Status: T-410 bounded supervisory wait implemented; live web acceptance pending
Date: 2026-08-15

## Purpose and boundary

The bridge is a dependency-free stdio facade between `tunnel-client` and local
Codex. Short compatibility tools proxy the official `codex mcp-server`; durable
project tools use the official `codex app-server` protocol so their interactive
tasks are discoverable by the Codex desktop sidebar. The facade supplies
truthful action metadata and fixes the user's personal full-control policy
before any request reaches Codex.

T-303 proved one remote read-only call on consumer ChatGPT. T-115 then proved a real full-control write through the mounted connector and a `codex-reply` that preserved the same returned thread identity. The temporary proof file had exactly `START_OK` followed by `REPLY_OK`.

## Public tools

The personal full-control facade exposes:

- `codex-start(prompt, projectName?)`: mandatory for a ChatGPT-led new project;
  creates a unique child project directory, creates an App Server task with
  that directory as `cwd`, sends the installed `workspace-new-project` as an
  explicit Skill input together with `$workspace-new-project --here`, returns
  a durable `jobId` immediately, and renders the same-conversation status
  component;
- `codex-reply-async(prompt, threadId)`: default for corrections and next steps
  on the same Codex thread;
- `codex-wait(jobId)`: model-visible, read-only bounded join; ChatGPT repeats it
  while the job is queued/running, then reviews the terminal result and resumes
  the same thread when the full request remains incomplete;
- `codex-job-open(jobId)`: model-visible read-only recovery that renders a new
  status card for an existing job without starting another Codex run;
- `codex-job-status(jobId)`: app-only short poll used by the component;
- `codex(prompt)` and `codex-reply(prompt, threadId)`: synchronous compatibility
  tools only for work expected to finish within a few minutes.

The four execution tools (`codex`, `codex-reply`, `codex-start`, and
`codex-reply-async`) declare:

```json
{
  "readOnlyHint": false,
  "destructiveHint": true,
  "idempotentHint": false,
  "openWorldHint": true
}
```

The public schemas do not expose `cwd`, sandbox, approval policy, config, model,
or instruction overrides. `projectName` is an optional display name, not a path;
missing names receive a collision-safe fallback for compatibility with cached
ChatGPT schemas. Successful results contain no local project path. The bridge
injects the created project root, `sandbox=danger-full-access`, and
`approval-policy=never`. Model and reasoning settings come from the operator's
normal Codex configuration.

## Start the personal full-control bridge

Use the macOS system Python so the Tunnel command does not depend on Homebrew Python:

```zsh
/usr/bin/python3 /Users/example-user/Documents/chatgpt-codex-bridge/scripts/bridge/codex-mcp-guard.py \
  --workspace /absolute/approved/sandbox/repository \
  --codex-bin /Users/example-user/.local/bin/codex
```

Both paths must already exist, be absolute real paths, and contain no symlink component. A configuration failure prints only a generic diagnostic and exits non-zero.

There is no `--allow-workspace-write` switch. Starting this bridge selects the fixed full-control/no-approval profile.

Before starting it, `scripts/bridge/local-preflight.zsh --sandbox <starting-real-path>` must report `overall_status=PASS`, matching the selected personal preset.

The active Tunnel profile references its restricted Read + Use runtime key through a mode-`600` file outside the repository rather than a transient shell environment variable. Never print, commit, copy into project memory, or place that secret file beneath the workspace. This keeps an ordinary Tunnel restart independent of the shell that originally created the key.

## Child environment

The Codex child receives a positive allowlist of basic process variables such as `HOME`, `PATH`, locale, user, shell, terminal, and temporary-directory settings. Tunnel/API keys, `CODEX_*`, `SSH_AUTH_SOCK`, proxy variables, and unrelated environment values are not inherited. The child stderr is suppressed so it cannot contaminate MCP stdout or leak identifiers into Tunnel logs; guard diagnostics are generic and go to stderr.

## Verification

Run the black-box contract suite:

```zsh
/bin/zsh tests/bridge/test-codex-mcp-guard.zsh
```

The thirty-two tests use temporary fake Codex processes and additionally cover
durable detached execution, immediate job-handle return, status recovery from a
later Guard process, existing-job card recovery without duplicate execution,
exact-thread async resume, malformed worker failure, the self-contained MCP
Apps resource, app-only status visibility, the stable follow-up marker,
safe/unique per-project roots, App Server interactive task creation, explicit
Skill input, scaffold enforcement, same-root continuation, bounded non-terminal
waits, terminal joins, and unknown-job rejection.

Secure Tunnel can multiplex more than one `initialize` request onto the same long-lived stdio process. The guard forwards the first initialization to Codex, sends `notifications/initialized`, validates an internal raw `tools/list`, and only then returns the first client initialization response. It caches that successful result and replays it with each additional caller's request ID. This both avoids a second downstream initialization and safely supports a cached ChatGPT app that sends `tools/call` without first issuing its own `tools/list` on the restarted stdio process.

Before that initialization and internal contract check completes, client `tools/list` and `tools/call` requests receive a local `-32002` error. A premature client `notifications/initialized` message is ignored and is not forwarded to the child.

A separate compatibility check may send only `initialize` and `tools/list` through the bridge to the real local Codex MCP server. T-115 passed that check and returned the prompt-only schemas before the live write/continuation proof.

## ChatGPT use

1. Refresh the installed `Codex MCP Guard` app after restarting the Tunnel so ChatGPT sees the prompt-only schema.
2. Open the `Codex MCP Guard` app detail and choose `在聊天中试用` to start a fresh conversation.
3. Before sending the first prompt, verify that the composer visibly contains the `Codex MCP Guard` pill. If the pill is absent, that conversation has no Codex tool; reopen the app detail instead of retrying there.
4. For a new project, give ChatGPT the task and a concise project name. It calls
   `codex-start(prompt, projectName)`, receives a `jobId` immediately, and
   displays a status card. The bridge creates the directory; ChatGPT never
   supplies `cwd`.
5. ChatGPT calls `codex-wait(jobId)` and repeats it while status is queued or
   running. On completion, it reviews the result. If the full project remains
   incomplete, it calls `codex-reply-async(prompt, threadId)` and joins the new
   job the same way. It does not end the user turn merely because one tranche
   was queued or completed.
6. If ChatGPT's model turn or page closes, local Codex still works
   independently. When complete, the status card shows
   `把结果发给 ChatGPT 审查`.
7. Click that recovery control once. It posts a `[codex-job:<jobId>]` message
   into the same conversation with `Codex thread: <threadId>` and the result, then
   ChatGPT starts its review turn. A background component call without this
   user gesture was live-tested and did not create a conversation message.
8. ChatGPT reviews that message and uses `codex-reply-async(prompt, threadId)`
   for any correction or next step. If the page was closed, reopen the same
   conversation so the card can resume polling, then click the return control.

For every new project, the worker's first App Server turn includes the installed
`workspace-new-project` Skill as an explicit input and invokes
`$workspace-new-project --here` in its text. The current directory is already
the final project root, so Codex must not create another nested folder. A
completed Codex turn is still marked failed if `AGENTS.md`, `README.md`,
`.gitignore`, `.project-memory/`, `docs/specs/`, `docs/adr/`, or `src/` is
missing. The partial directory is kept for diagnosis and is never deleted
automatically.

Before creating that App Server project, the worker opens the exact root with
the Codex desktop bundle in background mode. This adds the folder to the saved
project registry without UI clicks. `thread/start` only allocates an identity;
the worker therefore waits for the first root turn to finish before checking
`project/list` and `thread/list`. The desktop sidebar may need a short refresh
to reconcile the durable task to the saved project. A matching `cwd` with a
persistently null desktop project ID is a failed visibility proof.

Later `codex-reply-async` calls resolve the original project root from private
durable job state using `threadId`, call App Server `thread/resume`, and submit
a new turn without reinvoking the new-project Skill; no second project
directory is created.
Historical Codex tasks are not moved by rewriting session or SQLite metadata.

### When a card says `Failed to fetch template`

The Codex job may already be running even though the historical ChatGPT card
cannot load its UI. First confirm the Tunnel/Guard is healthy and retry the
card once. The Guard keeps the immediately preceding immutable template URI as
a compatibility alias and serves the current hydration-safe HTML. Do not call
`codex-start` again. If retry still fails, ask ChatGPT in the same conversation:

```text
请使用 Codex MCP Guard 的 codex-job-open 打开上一个后台任务的状态卡，不要调用 codex-start，也不要启动新任务。
```

ChatGPT can use the `jobId` already shown in the preceding tool result. The new
call renders the same durable job and never starts a worker. A successfully
mounted card MUST show that exact `jobId`; an empty skeleton or missing ID is
not acceptance.

### Minimal Mac web smoke

In a fresh conversation with the visible Guard pill, ask ChatGPT to use only `Codex MCP Guard` and have local Codex return one exact marker without reading or writing files. Require the assistant to show `Codex thread: <threadId>`. Then ask it to continue the same thread through `codex-reply` and return a second exact marker. Verify all four signals:

1. the first exact marker is present;
2. a thread tag is present, but its value is not copied into durable evidence;
3. the second exact marker is returned in the same ChatGPT conversation;
4. the local Tunnel log gains a new redacted dispatcher-forward record for the reply.

The 2026-08-10 proof used `T400_MAC_WEB_START_OK` and `T400_MAC_WEB_REPLY_OK` and passed all four signals. It requested no project file access or mutation.

### When ChatGPT says the tool is unavailable or forbidden

First check the conversation surface, not the local service:

1. confirm the composer visibly contains the `Codex MCP Guard` pill;
2. if absent, start a fresh chat from `+ -> Codex MCP Guard` or the app detail's `在聊天中试用` action;
3. from the plugin root, run `/bin/zsh scripts/chatgpt-codex-bridge.zsh status` and `/bin/zsh scripts/doctor.zsh`; require both service readiness and Tunnel profile validation;
4. compare the Tunnel log timestamp before and after the prompt. No new dispatcher record means ChatGPT did not dispatch to this Mac, even if the app is visible elsewhere in the client;
5. do not replace this architecture with Codex Remote, CanEngine, or a Workspace Agent merely because one conversation/model/client surface lacks Developer MCP execution.

The 2026-08-10 Mac failure was repaired by attaching the Guard to a fresh web conversation; the healthy Tunnel did not need a restart.

The ChatGPT plugin-specific permission is set to `full_access`, and local Codex uses `approval-policy=never`, so no read/write mode choice or approval step is expected at either layer. The ChatGPT model selected for the conversation is the supervisor only when that model/mode exposes the attached app tools; the local Codex model remains a separate setting. Long tasks MUST use the async tools because a synchronous Tunnel call can lose its final result at the control-plane TTL even while Codex continues locally.

## Persistent Tunnel service

Use the parameterized plugin service command instead of leaving `tunnel-client` attached to a Terminal window. From the repository root:

```bash
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-macos.zsh \
  --profile <tunnel-profile> \
  --workspace <absolute-workspace> \
  --preset personal-full-control
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh status
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh restart
/bin/zsh plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh stop
/bin/zsh plugins/chatgpt-codex-bridge/scripts/doctor.zsh
```

`install` renders a current-user LaunchAgent, stages the reviewed runtime, bootstraps it into the current GUI domain, and validates readiness. `RunAtLoad` starts it at login and `KeepAlive` restarts an unexpected exit. `status` reports the generated service state; `doctor` validates the external profile and effective runtime contract. `stop` performs an exact `launchctl bootout`; run `restart` or repeat the parameterized install to load it again.

The installer stages `codex-mcp-guard.py` and the bundled `workspace-new-project` Skill under bridge-owned current-user runtime state. The caller supplies the starting workspace during installation; it is validated and retained in non-secret generated configuration. The versioned plugin remains the source of truth and every install/reinstall refreshes the staged runtime.

## Fail-closed behavior

The bridge terminates the child and exits non-zero on malformed downstream JSON, unexpected tools, required schema drift, unmatched downstream responses, or downstream exit. These are protocol integrity checks, not user approval gates. Stop the Tunnel process to disconnect the local endpoint.
