# ADR 0006: Durable Codex Jobs and ChatGPT Apps Return

Date: 2026-08-10
Status: Accepted for T-407

## Context

A fresh ChatGPT web call reached the local Guard and started Codex, but Codex
spent about ten minutes on repository process work. The Secure MCP Tunnel then
reached its connection TTL and stopped forwarding the response. Codex had done
real work, yet ChatGPT received neither the final result nor a reusable thread
identity and incorrectly summarized the failure as zero callable functions.

The user requires a simpler interaction: ChatGPT gives Codex a task, Codex may
work for a long time, and its completion must appear in the same ChatGPT
conversation so ChatGPT can review it and issue the next Codex instruction.

## Reuse-first decision

Use the official mechanisms where each fits:

- Secure MCP Tunnel for ChatGPT-to-Mac transport;
- Codex CLI persisted sessions for long-running local agent work;
- MCP Apps resources and app-side tool calls for status polling;
- `window.openai.sendFollowUpMessage` for a component-authored message in the
  same ChatGPT conversation.

Do not initially build a browser extension that edits ChatGPT's DOM. That path
is more brittle, needs selector maintenance, and duplicates an official
same-conversation message API. Do not rely on MCP Tasks until the ChatGPT client
explicitly negotiates the extension; the MCP specification says host support
varies and requires client and server opt-in.

## Decision

Add durable async start/reply tools to the existing Guard. They create a local
job and return a job handle immediately. A detached Codex worker persists its
thread identity and final answer independently of the Tunnel request. The async
tool renders a versioned ChatGPT Apps component that polls the short status
tool. When terminal, the component exposes one explicit return button; that
user activation posts the result through `sendFollowUpMessage`.

Keep the proven synchronous tools for short compatibility checks. Route normal
project work to the async tools through explicit tool descriptions.

## Consequences

- Tunnel TTL no longer limits Codex execution time.
- The result is durably recoverable after Tunnel or Guard restart.
- The same browser conversation can receive the completion without the model
  remaining active; ChatGPT web currently requires one explicit click before
  the component may create the follow-up turn.
- If the ChatGPT page is closed, the job still finishes but result delivery
  waits until the component runs again and the user clicks return. This is not
  server-initiated push.
- Live testing rejected a zero-click claim: a background follow-up Promise
  resolved but no conversation message appeared, while the clicked control
  created a new turn and exact assistant response in the originating chat.
- A future browser relay can cover fully inactive consumer conversations if the
  official component path proves insufficient on the target client.
