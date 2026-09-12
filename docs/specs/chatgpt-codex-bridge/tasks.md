# ChatGPT–Codex Bridge Tasks

Status: Draft
Spec ID: `chatgpt-codex-bridge`

## Planning milestone

- [x] T-001 Extract and inspect the supplied PDF.
- [x] T-002 Verify current official ChatGPT Developer Mode, Secure MCP Tunnel, Codex MCP Server, and App Server documentation.
- [x] T-003 Inspect local Codex and tunnel-client availability.
- [x] T-004 Complete reuse/adapt/build research and record the decision.
- [x] T-005 Write requirements, design, ADR, and implementation plan.
- [x] T-006 Record a consumer-workspace target and the supplied non-enterprise CanEngine compatibility case without retaining the owner's account tier.
- [x] T-007 Choose the post-G0 route: run a live consumer capability probe first; retain CanEngine as the bounded fallback.

## Phase 0 — Eligibility and local readiness

- [x] T-100 Record plan/workspace eligibility without storing the owner's account tier or raw IDs; official/observed capability conflict recorded.
- [x] T-101 Confirm the tested consumer workspace exposes Plugins and the high-risk Developer Mode switch without changing configuration.
- [x] T-108 After explicit authorization, enable Developer Mode and inspect connector creation/connection types: Server URL and Secure Tunnel are both exposed.
- [x] T-109 After explicit authorization, create and authorize an OpenAI-hosted read-only MCP probe, review its five tools, and complete one non-mutating `search_openai_docs` call.
- [x] T-106 Classify CanEngine for the direct route as `NOT_INSTALLED / DEFERRED`; it is optional under T-500 and no longer blocks the working Codex path.
- [x] T-110 Compare successful and failed MCP tool metadata: successful read probe has complete read annotations; raw Codex tools return `annotations: null`.
- [x] T-111 After confirmation, implement the narrow Codex MCP metadata/policy guard and its contract tests. Thirteen black-box tests and a real downstream `initialize` plus `tools/list` compatibility check pass; no Codex tool was invoked.
- [x] T-112 Point the existing Tunnel profile at the verified guard, make Tunnel-multiplexed initialization replay-safe, create/connect/refresh the consumer-workspace draft app, and record truthful action metadata.
- [x] T-113 Diagnose the first remote read-only HTTP 504s and adapt guarded read-only thread creation to the observed remote response window using the official per-call low reasoning override.
- [x] T-114 Handle cached-app first calls after Tunnel restart: verify the raw Codex contract during initialization and use `gpt-5.6-terra + low` only for bounded read-only scans.
- [x] T-115 Simplify the private personal profile to `codex(prompt)` with fixed `danger-full-access` + `never`, ChatGPT plugin `full_access`, conversation-carried thread continuity, no public mode, and no local approval/write-enable switch. Contract tests, real Codex discovery, Tunnel health, one external-workspace write, same-thread reply, and plugin permission readback passed.
- [x] T-107 Through the final Codex connector, discover exactly `codex` and `codex-reply` and review their declared permissions without executing a side-effecting action.
- [x] T-102 Select and record `/Users/example-user/.local/bin/codex` as the explicit working Codex binary path for the proof.
- [x] T-103 Run local MCP `tools/list` and verify `codex` plus `codex-reply` schemas.
- [x] T-104 Install official `tunnel-client` only after the operator authorizes installation.
- [x] T-105 Run `tunnel-client doctor` with a redacted profile.

## Phase 1 — Isolated local proof

- [x] T-200 Select the host boundary. On 2026-08-02 the user explicitly chose the configured local account and waived the separate non-admin/VM requirement for this personal-use project.
- [x] T-201 Select the current `chatgpt-code` task branch as the approved personal project workspace instead of provisioning a separate sandbox repository.
- [x] T-202 Capture baseline Git status and content hashes. The final mode-600 ephemeral baseline covered the clean T-114 commit and all 35 tracked entries.
- [x] T-203 Run a bounded read-only Codex MCP proof locally. The guarded summary completed without a client `tools/list` and returned an ephemeral thread identity; host timing is not retained as a portability claim.
- [x] T-204 Verify no filesystem mutation and capture returned `threadId` in ephemeral test state only. All before/after Git and content-hash checks matched; only the presence boolean was retained in durable evidence.

## Phase 2 — Tunnel and ChatGPT proof

- [x] T-300 Create/associate the Secure MCP Tunnel with minimum required permissions.
- [x] T-301 Start the tunnel with the guarded Codex MCP command and verify process, liveness, readiness, and a successful control-plane poll.
- [x] T-302 Create and connect the `Codex MCP Guard` draft app, refresh it, discover exactly `codex` and `codex-reply`, and verify both are declared public-write/open-world/mutable.
- [x] T-303 Run the read-only ChatGPT -> Tunnel -> Codex proof. One attached conversation returned the requested bounded summary and reported that a thread identity exists without exposing its value.
- [x] T-304 Superseded by T-115: the user explicitly selected no per-call approval workflow for the active personal profile.
- [x] T-305 Superseded by T-115: bounded workspace-write promotion is replaced by a fixed full-control profile.
- [x] T-306 Use `codex-reply` with the returned `threadId` to continue the artifact. The reply returned the same thread identity and appended the exact expected second line.
- [x] T-308 Diagnose the ChatGPT web "app tool unavailable" report and repeat the prompt-only start/continue smoke. The failed conversation had no `Codex MCP Guard` attachment in its composer. Reopening the app detail and choosing `在聊天中试用` created a fresh attached conversation; `codex` and `codex-reply` produced the two expected lines with the same thread identity.
- [ ] T-307 Stop the tunnel and prove revocation. Local stop passed; the required post-stop remote tool-call failure remains unverified because no draft app persisted.

## Phase 3 — Hardening and repeatability

- [ ] T-400 Run two additional fresh end-to-end proofs. Proof 1/2 passed on 2026-08-10 from a fresh Mac web conversation: the visible Guard pill led to exact `T400_MAC_WEB_START_OK`, a returned thread tag, exact same-conversation `T400_MAC_WEB_REPLY_OK`, and new local Tunnel dispatch records. One additional fresh proof remains.
- [x] T-401 Adopt the existing narrow Guard as the compatibility/policy bridge; do not build a second agent service or relay.
- [x] T-402 Review and harden contract drift, initialization lifecycle, public-result redaction, host-policy preflight, secret filtering, unsafe public input, thread identity, and JSON-RPC negative tests. The Guard now publishes exact success output, rejects pre-initialize tool traffic, and keeps raw/public schemas separate; the preflight matches the selected personal preset; 14 Guard tests, every bridge test script, a real-child `initialize`/`tools/list` check, and independent re-review passed.
- [x] T-403 Add structured redacted evidence output and operator runbook. The 2026-08-10 redacted proof report records preconditions, start/continue gates, local dispatch evidence, evidence boundaries, and the no-restart diagnosis without retaining thread, request, plugin, Tunnel, or credential values; the Guard runbook now includes the repeatable smoke and unavailable/forbidden triage.
- [ ] T-404 Re-score the system against the 95/100 delivery rubric.
- [x] T-405 Make the example Tunnel a macOS user LaunchAgent with login startup, unexpected-exit recovery, stable loopback health state, non-secret logs, versioned service controls, static contract tests, and restart verification. Service readiness and synchronous model completion are recorded as separate evidence gates.
- [x] T-406 Package the proven bridge as a portable repository plugin with a controller Skill, parameterized macOS installer, per-device configuration, fixed personal/safe presets, isolated install validation, and no hard-coded user identity or credentials. Plugin version `0.1.0` passed the repository package checks, 16 Guard contract tests, isolated install/doctor/uninstall tests, official Skill validation, and a fresh GitHub marketplace install from remote commit `b9e312c` as an enabled plugin.
- [x] T-407 Replace long synchronous project calls with a durable background Codex job path and an MCP Apps component that returns the completed result to the originating ChatGPT conversation. The implementation preserves short synchronous tools, stores private jobs outside Git, supports exact-thread async reply, tolerates Guard/Tunnel request exit, and passed 21 contract tests. A real ChatGPT web proof showed background component submission is silently ignored without a user gesture; the final one-click component control created a new turn in the same conversation and ChatGPT replied with the exact Codex marker.
- [x] T-408 Diagnose and repair the recurring live ChatGPT `Failed to fetch template` error without interrupting the durable Codex job. The Guard now keeps the immediately preceding immutable template URI readable and emits redacted resource response diagnostics. In the originating GACE conversation, retrying the recovered M2 card removed the fetch error and mounted the exact existing job without changing its worker PID or creating another job.
- [x] T-409 Make every ChatGPT-led new-project start create a unique sidebar-visible project root, require the existing `workspace-new-project --here` Skill before implementation, enforce its scaffold, resume later turns in the same root, and surface the existing GACE project with a non-destructive Codex handoff task. The implementation uses App Server interactive threads instead of `codex exec`, passes the real Skill as an explicit first-turn input, passed 29 Guard tests plus all bridge/portable suites, completed a real new-project and same-thread continuation, and exposed both the new proof task and GACE in the Codex task list with exact project-root `cwd` values.
- [x] T-410 Add a model-visible bounded `codex-wait(jobId)` join, require ChatGPT to keep the active tool loop alive through terminal results, retain the Apps one-click fallback, and recover the exact GACE M0 job into a same-thread M1 continuation. The implementation passes 33 Guard cases, all bridge/portable suites, live staged discovery, and healthy Tunnel service checks. The original ChatGPT web conversation repeatedly waited on the corrected M1 job, consumed its complete parent result, verified M1 PASS, and issued M2 through `codex-reply-async` on the exact same Codex thread. A 28-minute model-turn ceiling was recovered in the same web conversation without duplicating the Codex job.
- [x] T-411 Scope App Server terminal handling to the root `threadId + turnId`. Live GACE M1 evidence showed a delegated provider reviewer emitting `turn/completed` before the parent synthesis; the Guard returned that child report as the job result and closed the parent worker. Foreign-thread and same-thread/foreign-turn regression fixtures now prove those events cannot mutate root content or completion; both Guard copies are byte-identical and deployed, 33 Guard tests pass, and the resumed live M1 job returned the comprehensive root report before ChatGPT issued M2 on the original thread.
- [x] T-412 Hydrate the durable-job Apps card from late ChatGPT/MCP Apps result delivery. The v3 widget accepts `toolOutput`, `toolResponseMetadata`, `openai:set_globals`, and `ui/notifications/tool-result`, waits instead of emitting a false missing-job error, and preserves the immediately preceding v2 URI as a compatibility alias. The originating GACE conversation rendered two recovered instances showing the exact existing M2 `jobId` and `running` state; 33 Guard cases and every bridge/portable suite pass, both Guard copies are byte-identical, and the deployed Tunnel is ready.
- [x] T-413 Register every new directory with the Codex desktop app, create its canonical App Server project, bind `thread/start` to the returned project ID, verify project/thread listing after the first durable turn, preserve identity on continuation, and repair GACE with a dedicated saved project plus task. The Guard now fails closed when desktop registration fails; 34 Guard tests and all bridge/portable suites pass. A fresh real job returned the exact marker and, after bounded desktop reconciliation, `list_projects` and `list_threads` showed one saved project and its task with the same desktop project ID and exact root.
- [x] T-414 Package the proven controller experience as a self-contained portable operating kit: bundled `workspace-new-project`, progressive Skill references and UI metadata, plugin README, truthful seven-tool MCP contract, upgrade/rollback SOP, isolated-home installer proof, versioned release ref, and remote push. The package keeps `workspace-new-project` under a non-indexed runtime bootstrap directory, stages it privately at install time, and now passes 44 Guard contracts plus official Skill/plugin and empty-HOME installer validation. Public release details are governed by `public-release-v1` and `chatgpt-codex-bridge-v0.6.0`.

## Deferred phases

- [ ] T-500 Evaluate CanEngine as a separate generic local-execution tool.
- [ ] T-600 Extend the narrow App Server worker only if events beyond terminal status, steer, interrupt, interactive approvals, or reviews gain independent value.
- [ ] T-700 Evaluate Workspace Agent/API Trigger only if asynchronous reverse wake-up becomes a real requirement.

## Stop conditions

- Stop if the ChatGPT workspace cannot perform full MCP write actions.
- Stop if the tunnel cannot be associated with the target workspace.
- Stop if the fixed `danger-full-access` + `never` policy is not propagated as specified.
- Stop on any out-of-scope filesystem or network activity.

Current state: T-413 proves the required folder-plus-task sidebar model with a fresh real project. The desktop and experimental App Server registries use different internal IDs, so acceptance is performed at both layers and only the desktop layer is used for the final sidebar claim. T-400 remains open for one more fresh synchronous proof.
