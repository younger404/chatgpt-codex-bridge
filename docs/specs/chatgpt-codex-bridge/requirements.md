# ChatGPT–Codex Bridge Requirements

Status: Active; T-413 canonical project grouping complete; T-400 proof 1/2 complete
Date: 2026-08-21
Spec ID: `chatgpt-codex-bridge`

## 1. Problem Statement

The system shall let one ChatGPT web conversation control one local Codex thread on the configured macOS host. The user talks to ChatGPT; ChatGPT starts Codex once, retains the returned `threadId` inside that conversation, and uses `codex-reply` for every follow-up. The active personal profile favors convenience and full local execution rather than per-call enterprise approval workflow.

The target interaction is:

```text
User
  -> ChatGPT web supervisor
  -> Secure MCP Tunnel
  -> local Codex MCP server
  -> local Codex with full host access and no approval prompts
  -> result + threadId
  -> ChatGPT review
  -> codex-reply correction
```

## 2. Evidence Baseline

### Confirmed

- The supplied 14-page PDF demonstrates a single ChatGPT web -> MCP -> CanEngine local execution loop lasting about 67 minutes. It does not demonstrate a Codex thread, `threadId`, `codex-reply`, or asynchronous wake-up.
- OpenAI documents `codex mcp-server` and the `codex` and `codex-reply` tools. `codex-reply` continues a session using the returned `structuredContent.threadId`.
- OpenAI documents Secure MCP Tunnel as an outbound-only HTTPS path from a private MCP server to supported OpenAI products.
- A supported Codex executable and the official Tunnel Client MUST be resolved
  from explicit canonical paths and verified on each device; no historical
  package path or version is portable evidence.
- ChatGPT capability is established only by current app attachment, exact tool
  discovery, accurate annotations, authorization and a harmless end-to-end
  probe. Account labels and connector visibility are insufficient.
- ChatGPT may multiplex repeated `initialize` requests and may later call a
  cached tool schema without a fresh client `tools/list`. The Guard therefore
  replays initialization safely and validates the downstream contract before
  accepting the first tool call.
- Synchronous MCP calls can exceed an intermediary response window even while
  local Codex continues. Durable `codex-start` / `codex-wait` is the supported
  long-running path; `queued` or `running` is never completion.
- The Apps component requires explicit user interaction to re-enter an inactive
  conversation. A successful local follow-up API call is not evidence that a
  visible ChatGPT message was created.
- The personal preset is fixed to `sandbox=danger-full-access` and
  `approval-policy=never`; the safer preset is separately fixed to
  `workspace-write` and `on-request`.
- OpenAI's current Codex documentation states that `danger-full-access` removes filesystem and network sandbox boundaries and that `never` does not stop for approval prompts.

### Corrected

- Full ChatGPT MCP write/modify support has varied by product plan and rollout. Documentation is a supportability baseline, but the implementation classifies capability from the attached app, tool metadata, permission labels, and observed runtime behavior.
- The supplied CanEngine case shows a consumer-style `Plugins/Apps -> create plugin -> Server URL -> first MCP authorization` flow and claims real local writes and command execution, but its exported pages do not display MCP action metadata. It is compatibility evidence, not permission evidence.
- The documented entitlement statement and the supplied external case describe different capability surfaces, while the completed read-only probe confirms only one narrower route. Account tier is therefore not treated as the cause of the Codex draft-app persistence failure. Capability must be classified from the actual app type, tool metadata, permission labels, and runtime behavior.

### Unknown until tested

- Whether CanEngine is connected as a published/allowlisted app, a legacy/gray-rollout plugin, or a custom MCP whose tools are classified as read/fetch despite producing local side effects.
- Whether a second additional T-400 run will reproduce the same start/continue result under a fresh conversation and current quota/latency conditions.
- Whether each mobile ChatGPT client/model/conversation combination that displays the app can also execute Developer MCP tools; mobile visibility alone is not treated as dispatch proof.

## 3. Functional Requirements

### FR-001 — Eligibility gate

The pilot MUST NOT attempt write actions unless the operator verifies all of the following:

1. The exact ChatGPT surface and plan/workspace are recorded without identifiers.
2. The target app can be created or selected and its tools can be discovered on that account.
3. Each tool's declared action/permission classification is reviewed; a side-effecting tool disguised as read/fetch fails the safety gate.
4. For the direct Tunnel route, ChatGPT exposes Tunnel connection and the Platform organization grants Tunnels Read + Use; setup operators also have Tunnels Manage when required.
5. For a CanEngine fallback, its bridge type, local boundary, tool metadata, and authorization prompts are separately documented before Codex is invoked through it.

Acceptance: a timestamped checklist records each item as pass/fail without recording workspace IDs, tunnel IDs, API keys, or other credentials.

### FR-002 — Local executable gate

The system MUST resolve an explicit working Codex executable and MUST NOT rely on `/opt/homebrew/bin/codex` while it remains broken.

Acceptance: the selected executable passes `--version`, `mcp-server --help`, and an MCP `tools/list` smoke test.

### FR-003 — Single-user host boundary

The `personal-full-control` preset is intended for a trusted single-user macOS host and deliberately uses the authority of the configured account. The bridge MUST still fix an exact real workspace path, keep Tunnel credentials out of the repository and project memory, and avoid unrelated files or services.

Acceptance: the active profile resolves to the intended guard, Codex binary, and exact workspace; the runtime key is available without appearing in Git or reports; and ordinary requested project work can proceed on the current account without a corporate-style host-provisioning gate.

### FR-004 — Tool discovery

During raw discovery, the MCP client MUST discover at least the expected Codex tools for the tested version, including `codex` and `codex-reply`. Raw discovery MAY record additional tools without invoking them; that observation alone does not approve them for production use. The guarded production facade MUST require the exact reviewed downstream tool set and schemas, and MUST fail closed if a tool is added, removed, renamed, or structurally changed until the new contract is reviewed.

Acceptance: the raw `tools/list` capture contains both expected tool names and their required fields with secrets and raw identifiers redacted; Guard contract tests reject additional or structurally changed downstream tools.

### FR-005 — Fixed full-control initial call

When ChatGPT calls public `codex(prompt)`, the bridge MUST inject the configured starting `cwd`, `sandbox=danger-full-access`, and `approval-policy=never`. The public call MUST NOT expose a mode, sandbox, approval, model, config, or cwd selector, and the bridge MUST NOT inject a reduced model or reasoning setting.

Acceptance: the downstream call contains exactly the prompt plus the fixed starting path, full-access sandbox, and no-approval policy; a valid `threadId` is returned.

### FR-006 — Full-control write proof

Given a specifically named harmless proof artifact, the full ChatGPT -> Tunnel -> Codex path MUST be able to create it without an intermediate approval request.

Acceptance: the requested artifact exists with exact content, the call returns normally, and no approval UI interrupts the conversation.

### FR-007 — Thread continuity

When ChatGPT receives `structuredContent.threadId` from the initial `codex` call, it MUST write `Codex thread: <threadId>` in its assistant response, retain that value in the same web conversation, and use it in `codex-reply` for every later instruction in that conversation.

Acceptance: the compact thread tag is visible in the first assistant response; the correction occurs in the same Codex thread and the second result reflects prior context without restating the full task.

### FR-008 — No per-call approval workflow

The active personal profile MUST use Codex `approval-policy=never` and ChatGPT plugin permission `full_access`. It MUST NOT add an application-level approval queue, reviewer, or per-call read/write promotion step. A Codex failure is returned to ChatGPT as task feedback, not converted into a new approval workflow.

Acceptance: contract tests and the live proof show the fixed no-approval policy and no approval interruption.

### FR-009 — Revocation

The operator MUST be able to revoke local execution without changing ChatGPT by stopping `tunnel-client` and the local MCP process.

Acceptance: after revocation, a new tool call fails closed and local health reports not ready/disconnected.

### FR-010 — Evidence separation

Reports MUST separately label:

- local CLI/MCP evidence;
- tunnel transport evidence;
- ChatGPT account/UI evidence;
- real Codex task evidence;
- claims sourced only from the supplied PDF or community posts.

Acceptance: no completion status is inferred from HTTP success, tool discovery, or one successful run alone.

### FR-011 — ChatGPT compatibility and policy facade

The stdio facade MUST retain the synchronous compatibility surface
`codex(prompt)` and `codex-reply(prompt, threadId)` and MAY expose the reviewed
personal async/App surface defined by FR-016 through FR-023. Every exposed tool
MUST have complete, truthful action annotations. The facade MUST inject the
configured starting path, `danger-full-access`, and `approval-policy=never`
server-side. Its tool descriptions MUST direct long project work through the
durable start/wait/reply loop and keep the synchronous pair for short work.

The facade MUST accept a valid conversation-carried `threadId` even after the local bridge process restarts; it MUST NOT require the current process to have observed that ID first. It MUST still avoid forwarding Tunnel credentials or unrelated secret-bearing environment variables to Codex and MUST fail closed on unexpected downstream tool names or schema drift. Before a successful `initialize` plus downstream contract verification, it MUST reject client tool discovery and tool calls and MUST NOT forward a premature `notifications/initialized` message. Successful public tool results MUST contain only the reviewed `threadId` and `content` fields; downstream diagnostic fields, injected policy arguments, local paths, and private metadata MUST NOT be copied into the public result.

Acceptance: contract tests prove truthful annotations, prompt-only initial schema, fixed full-control injection, unsafe-input rejection, restart-tolerant reply forwarding, strict initialization ordering, exact public success output, environment filtering, downstream-exit handling, and stdout JSON-RPC cleanliness.

### FR-012 — Persistent Tunnel runtime (superseded deployment form)

Given the user logs in to macOS, a user LaunchAgent MUST start a caller-selected external Tunnel profile without requiring a Terminal window. It MUST keep `tunnel-client` running after an unexpected process exit, MUST use resolved executable and working-directory paths, and MUST write stdout, stderr, and the resolved loopback health URL to stable user-owned paths outside the repository.

The LaunchAgent MUST NOT contain a runtime API key, tunnel ID, workspace ID, raw endpoint, or copied profile contents. It MUST reuse the existing profile and credential-file reference. A versioned management command MUST provide `install`, `restart`, `stop`, and `status` operations without adding a second supervisor process.

Because uninteractive LaunchAgents do not inherit Terminal or Codex application access to macOS privacy-protected folders, the portable installer MUST stage the reviewed Guard source into a current-user runtime directory and the LaunchAgent MUST override only the MCP command to use that copy. The runtime executable path MUST not contain spaces because Tunnel's stdio command string is tokenized before process launch. The unattended Codex starting workspace MUST be caller-selected and validated, and the external Tunnel profile identity and credential references MUST remain unchanged.

Acceptance: FR-013 portable-package tests validate the rendered plist contract and secret exclusions; `launchctl print` shows the loaded user job; `/healthz` and `/readyz` return HTTP 200; the Tunnel metric `commands_poll_last_successful_timestamp_seconds` proves a recent successful Control Plane poll; an intentional process termination is followed by a new PID and restored local plus Control Plane readiness; `tunnel-client doctor --profile <tunnel-profile> --explain` passes. The retired fixed-user root plist and service wrapper are not release artifacts.

### FR-013 — Portable plugin distribution

Given another macOS user clones or installs this repository marketplace, the repository MUST expose one self-contained `chatgpt-codex-bridge` plugin containing a valid manifest, a controller/setup Skill, the reviewed Guard, and current-user service scripts. Installation MUST derive the user's home and UID, MUST accept explicit Tunnel profile, workspace, Codex binary, Tunnel binary, and LaunchAgent label values, and MUST NOT require any fixed real username, home path, or bundled Tunnel profile identity.

The installer MUST validate the selected external Tunnel profile with `doctor`, render a user LaunchAgent with `RunAtLoad` and `KeepAlive`, stage runtime files outside macOS-protected Documents paths, and keep all Tunnel identity and credential material outside Git.

Acceptance: manifest/Skill validation passes; a temporary-home installation renders a valid plist and non-secret config for arbitrary paths; secret and hard-coded-user scans pass; install, doctor, restart, and uninstall tests remain green.

### FR-014 — Fixed install presets

The portable installer MUST support `personal-full-control` and `workspace-safe`. `personal-full-control` MUST inject `sandbox=danger-full-access` plus `approval-policy=never`; `workspace-safe` MUST inject `sandbox=workspace-write` plus `approval-policy=on-request`. The selected values MUST be fixed in local generated configuration and MUST NOT become public `codex` or `codex-reply` arguments.

For a trusted single-user installation, `personal-full-control` MUST remain the default. Public tool descriptions MUST truthfully describe the installed policy.

Acceptance: Guard tests prove both preset pairs reach downstream Codex, unsupported pairs fail configuration, and both public schemas remain prompt/thread-only.

### FR-015 — Per-device onboarding boundary

The package MUST explain that each device/user requires an independently created or associated Tunnel profile, local Codex authentication, a running local service, and a ChatGPT connector/app attached to the target conversation. Installation MUST NOT copy another device's profile, runtime key, Tunnel ID, ChatGPT authorization, or Codex session history.

Acceptance: the Skill and runbook state the boundary, the repository contains no credential-shaped values, and the installer never reads or writes Codex conversation-history paths.

### FR-016 — Durable asynchronous Codex delegation

Given a ChatGPT web conversation delegates work that may exceed the Secure MCP
Tunnel response lifetime, the bridge MUST durably create a local background job
and return a non-secret `jobId` before the synchronous tool call expires. The
Codex process MUST continue independently of the originating Tunnel request and
MUST persist its status, Codex thread identity, final response, and failure
summary outside the repository.

The long-running path MUST preserve the configured preset policy
(`danger-full-access` plus no approval prompt for the personal preset). It MUST NOT require
the ChatGPT model turn, browser tab, or Tunnel stdio process to remain open while
Codex executes.

Acceptance:

- a fake Codex process can outlive the MCP request and reach a durable terminal
  state;
- a later Guard process can read the same job and continue its Codex thread;
- interrupted or malformed worker output becomes an explicit state instead of
  remaining falsely `running` forever;
- prompts and results are stored with user-only permissions and are never
  committed.

### FR-017 — Same-conversation completion return

Given a durable job was started from a ChatGPT Apps-capable conversation, its
tool result MUST render a component bound to that `jobId`. The component MUST
poll only short local status tools. When the job reaches a terminal state, it
MUST use the host-provided follow-up-message API to post one structured result
message into the same ChatGPT conversation, including the stable Codex thread
identity when available.

The component MUST persist its state, include a deterministic job marker in the
follow-up, and require one explicit user activation before calling the host
follow-up API. It MUST NOT claim that a background follow-up call delivered a
message: live ChatGPT web testing showed that the Promise can resolve without a
new conversation turn when no user gesture is present. It MUST feature-detect
both tool-call and follow-up APIs and explain the fallback when the host does
not expose them.

The bridge MUST expose a model-visible, read-only recovery tool that accepts an
existing `jobId` and renders the same component without enqueueing a second
Codex run. This recovery path MUST be usable when a historical ChatGPT tool
result is pinned to an obsolete app/template snapshot and cannot be repaired by
retrying that old card.

Acceptance:

- resource discovery/read returns a self-contained MCP Apps HTML component;
- async start/reply descriptors reference that resource and allow app-side
  status calls;
- component tests prove polling, terminal rendering, explicit return control,
  follow-up construction, delivery-state persistence, and failure fallback;
- reopening an existing job renders the component and preserves the same job
  without starting another worker;
- the completion marker is stable so duplicate deliveries are recognizable.
- a live web proof shows the explicit control creates a new ChatGPT turn in the
  originating conversation and the assistant receives the exact Codex result.

### FR-018 — Availability boundary and fallback

The system MUST describe this boundary truthfully: Codex execution is durable
while ChatGPT is offline, but a consumer ChatGPT conversation can only receive
the completion while its Apps component is executing. If the browser or
conversation is closed, status polling MUST resume when the component is
rendered again and the user MAY then submit the stored result with one click;
it MUST NOT be described as unsolicited server push or zero-click wake-up.

MCP Tasks MAY be added after a live client capability probe declares
`io.modelcontextprotocol/tasks`. The server MUST NOT return an MCP Task result
to a client that did not opt in. Browser DOM automation MAY be added only as a
separate compatibility fallback if the Apps component path cannot deliver on
the target client.

### FR-019 — Sidebar-visible new-project bootstrap

When a ChatGPT conversation asks Codex to build a new project, ChatGPT MUST use
`codex-start`. The bridge MUST create one unique child directory below its
configured workspace container before starting Codex, and MUST start the new
Codex thread with that child directory as the exact working root. The public
call SHOULD supply a concise `projectName`; an omitted name MUST remain
compatible with older cached ChatGPT tool schemas by generating a visible,
collision-safe fallback name.

The bridge MUST create and run the Codex task through the App Server
`thread/start` and `turn/start` protocol rather than `codex exec`, because the
task MUST be an interactive Codex task that is discoverable by the desktop
sidebar. The first `turn/start` MUST carry the installed
`workspace-new-project` Skill as an explicit Skill input item, and its text
input MUST invoke `$workspace-new-project` in current-directory (`--here`)
mode before analysis or implementation. Because the bridge has already
created the intended project root, Codex MUST NOT create another nested
project directory. A successful new-project job MUST contain the Skill's
required scaffold: `AGENTS.md`, `README.md`, `.gitignore`, `.project-memory/`,
`docs/specs/`, `docs/adr/`, and `src/`. Missing scaffold markers MUST make the
job fail explicitly instead of reporting a successful project start.

For `codex-reply-async`, the bridge MUST resolve the original project working
root from private durable job state using the supplied `threadId`. It MUST NOT
trust a ChatGPT-supplied filesystem path, create a second project directory, or
move/rewrite Codex history metadata. Legacy thread IDs without a recorded
project root MAY continue from the configured workspace container.

Acceptance:

- contract tests prove a safe unique directory is created beneath the
  configured container for Unicode, missing, duplicate, and traversal-shaped
  project names;
- the worker starts an App Server thread whose `cwd` is the exact project root,
  and the first turn contains an explicit `workspace-new-project` Skill input
  plus text naming `$workspace-new-project` and `--here`;
- the App Server task is returned by the Codex desktop task list with the exact
  project-root `cwd` after its first turn completes;
- a zero-exit Codex run without the required scaffold is recorded as failed;
- async continuation uses the same private project root and does not create a
  second directory;
- an existing GACE project is surfaced non-destructively by a new Codex task
  whose `cwd` is `/Users/example-user/codex-workspace/gace`, without editing prior
  session or index files.

### FR-020 — Same-turn supervisory wait loop

When the user asks ChatGPT to finish a project or a multi-step milestone chain,
the bridge MUST keep the durable job design but MUST also expose a model-visible
`codex-wait(jobId)` join primitive. After `codex-start` or
`codex-reply-async`, ChatGPT MUST call `codex-wait` repeatedly while the job is
`queued` or `running`; it MUST NOT present the background submission as the
completed user result.

Each wait call MUST use a server-fixed bounded interval below the normal Tunnel
request window. The public schema MUST accept only `jobId`, MUST remain
read-only, and MUST NOT expose a caller-controlled timeout, filesystem path,
model, sandbox, or approval option. A non-terminal response MUST tell the model
to wait again. A terminal response MUST include the bounded Codex result and its
thread identity when available.

After a completed tranche, ChatGPT MUST review the returned evidence. If the
user's requested acceptance criteria are not yet complete, ChatGPT MUST send the
next instruction through `codex-reply-async` using the exact returned
`threadId`, then join that new job through `codex-wait`. The supervisory loop
stops only when the requested project is complete and verified, Codex needs
material user input, or a real failure/blocker must be reported.

The Apps component and explicit return button MUST remain as recovery for a
closed page, a host-aborted model turn, or a historical conversation. The
same-turn loop MUST NOT be described as a guaranteed asynchronous wake-up: it
works only while ChatGPT keeps the active tool loop alive.

Acceptance:

- tool discovery exposes `codex-wait` to the model on the personal preset and
  omits it from the workspace-safe preset;
- contract tests prove bounded non-terminal return, terminal result retrieval,
  invalid/unknown job rejection, and that waiting never enqueues a second job;
- start/reply/wait descriptions require the same `jobId` to be joined before
  ChatGPT answers and require same-thread continuation when work remains;
- a fresh web proof completes at least two consecutive Codex tranches in one
  ChatGPT supervisory loop, or records the exact host/tool-loop boundary if the
  client stops despite the tool contract;
- the previously completed GACE M0 job is recovered by its exact `jobId` and
  the original Codex `threadId` is used when starting M1.

### FR-021 — Root-turn terminal isolation

Each durable App Server job MUST bind completion to the exact root
`threadId` and `turnId` returned by its own `turn/start` request. Agent messages
and `turn/completed` events from delegated child threads, historical turns, or
any other turn MUST NOT replace the root result, change the root terminal
status, or stop the worker.

Given a root turn that delegates independent review, when a child review emits
its own final answer and `turn/completed`, then the public job MUST remain
`running` until the root turn emits a matching terminal event. The eventual
job content MUST be the root turn's final answer. A matching root failure or
interruption MUST still terminate the job truthfully.

Acceptance:

- contract tests emit both a different-thread child completion and a
  same-thread/different-turn completion before the root terminal event;
- neither foreign terminal event may complete the job or replace root content;
- the installed Guard and packaged plugin copy remain byte-identical after the
  fix, and live discovery retains the existing public tool schema.

### FR-022 — Late Apps result hydration

The durable-job component MUST bind to the returned `jobId` whether ChatGPT
exposes structured output before the iframe script starts or hydrates it later.
It MUST accept the current `window.openai.toolOutput` alias, the canonical
`toolResponseMetadata` result envelope, `openai:set_globals` updates, and MCP
Apps `ui/notifications/tool-result` messages. A temporarily missing initial
value MUST remain a waiting state rather than a permanent false "missing
jobId" error.

Acceptance:

- the widget contract names all four hydration paths;
- a hydrated result starts status polling with the returned `jobId` and never
  starts another Codex job;
- historical conversations that retained the immediately preceding immutable
  template URI can still read that URI and receive the current compatible
  widget without changing the newly advertised URI;
- both Guard copies remain byte-identical and all package suites pass.

### FR-023 — Canonical Codex project registration and thread grouping

When `codex-start` creates a new software project, the bridge MUST first open
the exact new directory through the Codex desktop bundle in background mode,
then register it through the Codex App Server project API before starting the
Codex thread. The bridge MUST call `project/create` with the display name, the
exact allocated root, and a durable idempotency key, then MUST pass the returned
App Server `projectId` to `thread/start` together with the same root as `cwd`.

The worker MUST verify all of the following before reporting a successful job.
Project and thread listing MUST occur after the first root turn becomes
terminal because `thread/start` alone does not yet create a listable rollout:

1. `project/create` returns a non-empty project ID, the requested display name,
   and the exact project root;
2. `thread/start` returns the exact project ID and exact `cwd`;
3. `project/list` returns that project and root;
4. `thread/list(projectId)` returns the newly created thread;
5. the required `workspace-new-project --here` scaffold is present.

For a continuation, the bridge MUST resolve both the original project root and
project ID from private durable job state. It MUST resume the existing thread;
it MUST NOT create a second project, second directory, or replacement thread.

For an existing project whose historical thread is currently unassigned or
assigned to the workspace container, an explicit operator migration MAY use
the official `project/import` API to register the existing root and associate
the selected thread IDs. It MUST NOT edit Codex session JSON, SQLite, indexes,
or rollout metadata.

If the installed Codex App Server lacks or rejects the project API, the new
project job MUST fail explicitly. A desktop task with only a matching `cwd` or
with `projectId=null` after a bounded desktop refresh MUST NOT satisfy this
requirement.

Acceptance:

- Codex `list_projects` shows one saved project whose path is the allocated
  directory;
- Codex `list_threads` shows the created thread with that project's ID and
  exact project `cwd`;
- desktop reconciliation may be eventual, but MUST converge within the bounded
  live acceptance window;
- the project and its thread are visible together in the Codex sidebar;
- a same-thread continuation preserves both project ID and project root;
- the existing GACE root and its dedicated current Codex task are grouped under
  one registered Codex project without rewriting historical task metadata.

### FR-024 — Portable Skill, MCP, and SOP operating kit

Given a different macOS user or a second Mac installs the repository plugin,
the package MUST explain and expose the complete operating path without relying
on this repository's root documentation or this user's private state. The
plugin MUST contain:

1. one concise discoverable controller Skill with UI metadata;
2. progressive-disclosure references for device onboarding, the new-project
   supervisory loop, recovery/revocation, and the public MCP contract;
3. an independent package README that identifies prerequisites, install,
   ChatGPT attachment, verification, upgrade, and uninstall boundaries;
4. the reviewed stdio Guard and current-user service scripts already required
   by FR-013.

The plugin MUST also bundle a portable `workspace-new-project` Skill and its
bootstrap script. Installation MUST stage that Skill under bridge-owned runtime
state and pass its exact validated `SKILL.md` path to the Guard. It MUST NOT
depend on a pre-existing home-global Skill, overwrite another installed Skill,
or contain a user-specific absolute path.

The MCP contract reference MUST list the public tool names, required arguments,
truthful annotations, durable job state transitions, thread/project identity
rules, and terminal/error semantics. It MUST state that the package deliberately
omits `.mcp.json`: the Guard is exposed to ChatGPT through the separately
authorized Secure MCP Tunnel, while registering it as a Codex-local MCP server
would create a Codex-to-Codex loop.

The SOP MUST keep every device's Tunnel profile, Codex login, ChatGPT app
authorization, and runtime state independent. It MUST NOT claim that installing
the plugin alone creates or authorizes a ChatGPT connector.

Acceptance:

- official Skill and plugin validation pass;
- package tests verify every referenced file, UI metadata, tool inventory, and
  the intentional absence of `.mcp.json`;
- an isolated temporary HOME with no preinstalled Skills installs, passes
  doctor, and resolves the staged `workspace-new-project` Skill;
- the package contains no personal path, Tunnel identity, credential-shaped
  value, or Codex history mutation instruction;
- the existing installer, doctor, Guard, bridge, and portable-install suites
  remain green.

## 4. Safety and Security Requirements

### SR-001 — No raw secrets

API keys, tunnel IDs, workspace IDs, tokens, credentials, raw endpoint URLs, cookies, and private egress identifiers MUST NOT be committed, printed into reports, or stored in project memory.

### SR-002 — Fixed personal authority

The local Codex process runs with the broadest local sandbox setting and no approval prompts. This authority is fixed by the host profile rather than caller-selectable fields; task scope still comes from the user's instruction and ChatGPT's prompt.

### SR-003 — CWD allowlist

Every new-project Codex call MUST supply an exact absolute real child path of
the configured workspace container as its starting `cwd`. The bridge MUST
derive that child locally from a display name rather than accepting an
arbitrary caller path. Under `danger-full-access` this remains a starting
directory, not a filesystem containment boundary.

### SR-004 — Recoverable project changes

For repository work, prefer normal branches and milestone commits so changes are easy to inspect or undo. This is Git hygiene, not a per-command permission gate.

### SR-005 — Prompt-injection containment

Untrusted repository content MUST be treated as data, not authority. Only the user's instruction and the bridge's fixed host profile define task authority.

### SR-006 — Narrow public interface

Raw Codex policy and filesystem fields stay private to the local bridge.
ChatGPT sees a task prompt plus an optional project name for a new thread; the
bridge sanitizes that value into a unique directory stem and never accepts a
caller path. A continuation contains a task prompt plus thread ID. ChatGPT
never supplies `cwd`.

## 5. Reliability and Observability Requirements

### RR-001 — Health checks

The runbook MUST verify the selected Codex binary, MCP tool discovery, tunnel `doctor`, tunnel readiness, and ChatGPT tool scan as separate gates.

### RR-002 — Version capture

Each test MUST record Codex and tunnel-client versions, but MUST NOT record credentials or identifiers.

### RR-003 — Repeatability

The end-to-end proof MUST pass at least three fresh runs before the result can be called repeatable. The PDF's 67-minute report remains an N=1 feasibility example.

### RR-004 — Timeout and interruption

Synchronous compatibility calls MUST remain bounded and have a manual stop
procedure. Durable Codex execution plus deferred component delivery are in
scope. Unsolicited server push into a completely inactive consumer ChatGPT
conversation remains out of scope.

## 6. Non-Goals for MVP

- Operating the user's general desktop or browser.
- Adding CanEngine to the critical path.
- Building a custom Workspace Agent.
- Wrapping Codex App Server.
- Background 24/7 execution or automatic reverse wake-up.
- Production deployment or force push.
- Proving that a single long tool loop is production reliable.
- Rewriting Codex session JSON, SQLite, indexes, or rollout metadata to repair
  historical sidebar grouping. Official `project/import` association is in
  scope when the user explicitly requests it.

## 7. Promotion Gates

| Gate | Required evidence | Failure action |
|---|---|---|
| G0 Account/surface | Actual plugin/app UI, tool discovery, declared permissions, and official entitlement comparison | Keep `PARTIAL_PASS`; no connector activation or write until resolved |
| G1 Local | Working explicit Codex binary and tool list | Repair CLI path before continuing |
| G1a Metadata facade | Truthful annotations, narrowed schemas, policy injection, and contract tests | Do not retry ChatGPT app creation |
| G2 Host boundary | Selected host policy, exact workspace, and credential handling verified | Correct the profile before calling Codex |
| G3 Initial call | Full-control policy injected and returned threadId | Diagnose the bridge contract |
| G4 No-approval | No approval interruption under `never` | Treat as policy propagation failure |
| G5 Write | Named proof artifact is created as requested | Return failure evidence to ChatGPT |
| G6 Continuity | `codex-reply` uses same threadId | Mark Agent-to-Agent loop unproven |
| G7 Repeatability | Three clean end-to-end runs | Keep status experimental |
| G8 Project visibility | Saved Codex project path equals the created root; the new task has that `projectId` and exact `cwd`; the required Skill scaffold exists | Fail the job; preserve the directory/project for diagnosis |

### Current gate result

As of 2026-08-21, `G0 Account/surface`, `G1 Local`, `G1a Metadata facade`, `G2 Host boundary`, `G3 Initial call`, `G4 No-approval`, `G5 Write`, `G6 Continuity`, and `G8 Project visibility` have passed. T-413 registered a fresh root with the desktop app, completed one real App Server task, and then observed the saved project and task converge to the same desktop project ID with exact `cwd`. `G7 Repeatability` and the post-stop remote revocation check remain open.

Promotion sequence:

1. completed: inspect the available consumer Plugins and Developer Mode UI without changing configuration;
2. completed after explicit authorization: enable Developer Mode and inspect Server URL and Secure Tunnel connection types;
3. completed after explicit authorization: create and authorize a trusted read-only MCP probe, review its five tools, and execute one non-mutating call;
4. completed after explicit authorization: restore Platform tunnel-console access, install the verified official client, create and associate the tunnel, run `doctor`, and verify local readiness;
5. completed: point the Tunnel profile at the guard, repair repeated initialization, create/connect/refresh the app, and verify its two truthful action tools;
6. completed: run T-303 through the selected project workspace and verify no filesystem mutation;
7. completed: deploy T-115 fixed full-control policy, create one harmless proof artifact, and continue the same Codex thread with `codex-reply`, both through the connector and through one attached ChatGPT web conversation;
8. evaluate CanEngine only as an optional second local-execution tool, not as a prerequisite for the direct Codex route.

## 8. Source References

- OpenAI: [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta)
- OpenAI: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- OpenAI: [Codex MCP Server](https://learn.chatgpt.com/docs/mcp-server)
- OpenAI: [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- GitHub: [openai/codex](https://github.com/openai/codex)
- GitHub: [openai/tunnel-client](https://github.com/openai/tunnel-client)
- Upstream risk: [openai/codex#18243](https://github.com/openai/codex/issues/18243)
- Supplied PDF: `CodeX额度不够？我让ChatGPT网页版接管电脑，连续干活67分钟`, pages 1-14.
