# ADR 0002: Guard Codex MCP Metadata and Policy

Status: Superseded in active operation by T-115 on 2026-08-03
Date: 2026-08-02

This ADR preserves the first Guard design and its historical rationale. The
later T-115 decision removed the public `mode`, read-only model override,
workspace-write flag, `on-request` policy, and process-local thread allowlist.
The active Guard now exposes prompt-only `codex`, strict `codex-reply`, fixed
`danger-full-access` plus `never`, and restart-tolerant conversation-carried
thread IDs as specified in the
[`chatgpt-codex-bridge` requirements](../specs/chatgpt-codex-bridge/requirements.md)
and [current runbook](../runbooks/codex-mcp-guard.md).

## Context

The Secure MCP Tunnel transported ChatGPT's draft scan to the local official `codex mcp-server`, but ChatGPT did not persist the draft app. A successful custom read-only probe on the same tested consumer account declares complete safety annotations. The tested Codex MCP tools instead return `annotations: null`, while OpenAI's current plugin reference requires accurate `readOnlyHint`, `destructiveHint`, and `openWorldHint` metadata.

The raw Codex schemas also let the caller select arbitrary working directories, `danger-full-access`, `approval-policy=never`, config overrides, models, and instructions. Those fields are unsuitable for a remote ChatGPT-facing tool even if app creation succeeds.

## Decision

Use a dependency-free stdio guard between `tunnel-client` and the official Codex MCP server.

The implemented guard:

- expose only `codex` and `codex-reply`;
- label both conservatively as non-read-only, potentially destructive, non-idempotent, and open-world;
- replace the raw public schemas with `codex(prompt, mode)` and `codex-reply(prompt, threadId)`;
- inject the exact approved real path and `approval-policy=on-request`;
- inject `model=gpt-5.6-terra` and `model_reasoning_effort=low` only when starting a read-only thread, keeping the public schema narrow and preserving the normal configured model and effort for workspace-write threads;
- permit only `read-only` by default and require an explicit local flag for `workspace-write`;
- track thread IDs returned through the same process before allowing replies;
- filter inherited environment variables so Tunnel credentials are not passed to Codex;
- fail closed on unexpected tools, malformed JSON-RPC, downstream exit, or schema drift.
- complete the downstream initialized notification and an internal `tools/list` contract check before returning the first client `initialize` response, so a cached ChatGPT app may safely send `tools/call` without first listing tools on the new stdio process.

The guard will never describe Codex as read-only merely to make a restricted product surface accept it. If ChatGPT rejects the honestly annotated app, the direct action route remains unproven and the result will be recorded without weakening metadata.

## Alternatives

- Raw `codex mcp-server`: rejected for the next retry because required annotations are absent and unsafe arguments remain public.
- MetaMCP: rejected for this proof because its Docker/control-plane/gateway footprint is disproportionate.
- `mcp-chain`: rejected because a dependency-heavy general transformer is unnecessary for two fixed tools.
- CanEngine: retained as a separately reviewed fallback, but not part of this package and not yet inspectable.
- Codex App Server facade: deferred because it adds event/state/protocol complexity beyond this compatibility test.

## Consequences

- The proof adds one small locally maintained component and a contract-test obligation.
- ChatGPT draft persistence must be retested; the annotation defect may not be the only cause.
- The guard improves argument containment but does not replace the isolated OS/profile requirement.
- A product-supported workspace remains a possible fallback, not a prerequisite inferred from the failed consumer draft.
- Local contract tests and a real downstream `initialize` plus `tools/list` check pass; no real Codex tool call was made during T-111.
- T-303 established that a synchronous read-only call can exceed an intermediary
  response window even while Codex produces progress. Per-call tuning did not
  make duration deterministic. This is why the public package uses durable
  async start/wait semantics instead of publishing a latency promise.
- The final proof confirmed thread-ID presence without retaining its value and
  verified an unchanged repository baseline. It is functional evidence, not a
  latency SLA.
