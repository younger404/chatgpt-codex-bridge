# ADR-0008: Bounded ChatGPT supervisory wait loop

Status: Accepted
Date: 2026-08-15

## Context

The durable bridge correctly completed a GACE M0 job after the originating
ChatGPT model turn ended. The result remained in local durable state, but the
ordinary ChatGPT conversation did not continue to M1. Live proof had already
shown that an Apps component calling `sendFollowUpMessage` without a user
gesture can resolve locally without creating a stored ChatGPT turn. The old
conversation also rendered `Failed to fetch template`, so its explicit return
button was unavailable.

The user requires ChatGPT to remain the supervisor: receive each Codex result,
review it, issue the next instruction on the same Codex thread, and repeat until
the whole requested project is complete.

## Reuse-first decision

Retain and adapt the existing Guard, durable JobStore, App Server worker,
Secure MCP Tunnel, and Apps recovery component.

- Do not build a second relay or a browser-DOM daemon.
- Do not return MCP Tasks until ChatGPT explicitly negotiates the task
  capability; task support is client-dependent.
- Do not revert to one monolithic synchronous Codex call because its lifetime
  can exceed Tunnel/intermediary request windows.
- Do not depend on background `sendFollowUpMessage`; the live host requires an
  explicit user activation for a reliable stored turn.

## Decision

Expose `codex-wait(jobId)` on the personal preset. It is a read-only,
model-visible join over the existing durable job. Each invocation waits for a
fixed bounded host interval, returns immediately on terminal state, and tells
ChatGPT to invoke it again when work is still queued or running.

Tool descriptions make the supervisory contract explicit: after every
`codex-start` or `codex-reply-async`, ChatGPT joins the job before answering;
after a completed tranche it reviews the result and continues the exact
`threadId` when the user's overall acceptance target remains incomplete.

The existing Apps component remains the recovery path if the page closes or the
host ends the model tool loop.

## Consequences

- Active ChatGPT conversations can behave like the long Tool Loop demonstrated
  by the supplied CanEngine case while preserving durable Codex execution.
- A wait call temporarily serializes this single-user Guard, but its duration is
  fixed below 60 seconds and it performs no new execution or mutation.
- Model-directed repeated polling is less deterministic than negotiated MCP
  Tasks, so a fresh web proof is mandatory and the fallback remains visible.
- The mechanism does not wake an inactive consumer conversation. It closes the
  requested loop only while ChatGPT keeps the current response/tool turn alive.
