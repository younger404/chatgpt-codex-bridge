# ADR 0010 — Hydrate and version durable-job widgets compatibly

Status: accepted  
Date: 2026-08-15

## Context

ChatGPT can mount an MCP Apps iframe before the tool result appears in
`window.openai.toolOutput`. It can also retain an immutable template URI in an
existing conversation after the connector advertises a newer URI. The first
case produced a false permanent `missing jobId` state; the second produced
`Failed to fetch template` while the underlying durable Codex job remained
healthy.

## Decision

1. Treat initial ChatGPT globals as an optimization, not a mount precondition.
2. Accept the MCP Apps `ui/notifications/tool-result` notification and the
   ChatGPT `toolOutput`, `toolResponseMetadata`, and `openai:set_globals`
   compatibility paths.
3. Advertise one current immutable widget URI and keep the immediately
   preceding URI readable as a compatibility alias. Both return the current
   backward-compatible HTML; discovery lists only the current URI.
4. Hydration may only bind and poll an existing `jobId`. It cannot create or
   continue a Codex job.
5. Keep redacted response diagnostics that prove the HTML response was flushed
   without logging the template URI or tool result.

## Consequences

Historical conversations can recover their existing durable jobs after a
widget revision, and late host hydration no longer becomes a permanent false
error. Each future incompatible widget revision must deliberately decide which
single prior URI remains supported. A component still cannot unsolicitedly
wake an inactive ChatGPT conversation; the bounded model-visible wait loop and
explicit return control remain separate mechanisms.
