# ADR-0001: Use the Official Codex MCP Path for the First Proof

Date: 2026-08-01
Status: Superseded for active operation by T-115/T-200 on 2026-08-03

This ADR records the original isolated feasibility-proof decision. Its
non-admin, read-only, and `on-request` constraints are no longer the active
operator policy. The current system of record is
[`chatgpt-codex-bridge` requirements](../specs/chatgpt-codex-bridge/requirements.md)
and the [Codex MCP Guard runbook](../runbooks/codex-mcp-guard.md), which define
the user's selected personal full-control preset.

## Context

The project aims to let a ChatGPT web conversation supervise a local Codex coding agent. The supplied CanEngine case demonstrates local MCP execution but not Codex thread orchestration. Earlier candidate designs included a Workspace Agent, cloud relay, Mac worker, CanEngine, and a custom Codex App Server wrapper.

OpenAI currently provides:

- `codex mcp-server`, exposing `codex` and `codex-reply`;
- `structuredContent.threadId` for continuing a Codex conversation;
- Secure MCP Tunnel for outbound-only access to a private stdio or HTTP MCP server;
- Codex App Server for richer custom-client integration.

The full ChatGPT MCP write path is account-gated and currently documented for Business and Enterprise/Edu. The raw Codex MCP tool schema also permits unsafe runtime arguments, so it is not sufficient as a production security boundary.

The target proof used a consumer workspace, and the supplied CanEngine case described a non-enterprise flow. Because product entitlements and rollouts can differ, G0 requires a live capability and tool-metadata probe instead of an automatic account-tier failure.

After explicit authorization, Developer Mode was enabled and the create-app form exposed both Server URL and Secure Tunnel connections. An OpenAI-hosted read-only MCP probe was created, authorized, scanned as five read tools, and invoked successfully from a fresh ChatGPT conversation. Local `codex mcp-server` discovery independently returned exactly `codex` and `codex-reply`. The decision therefore advances to the Tunnel gate, without treating the read proof as evidence of custom write support.

## Decision

Use `ChatGPT web -> Secure MCP Tunnel -> codex mcp-server` as the first isolated feasibility proof.

The proof will:

- run only in a sterile non-admin profile or disposable VM;
- use a non-sensitive sandbox repository;
- prove read-only, bounded write with approval, returned `threadId`, `codex-reply`, and revocation;
- stop rather than relax to `danger-full-access` or approval `never`;
- require three clean runs before being called repeatable.

CanEngine, Codex App Server integration, Workspace Agent, custom relay, event bus, and asynchronous reverse wake-up are deferred.

Real-repository use requires a separate policy-enforcement adapter or an equivalently strong host boundary.

## Consequences

### Positive

- Reuses official maintained components.
- Proves the exact thread-continuity primitive required by the product.
- Minimizes initial moving parts and public network exposure.
- Keeps later richer control-plane work optional.

### Negative

- Depends on eligible ChatGPT workspace permissions and tunnel association.
- Does not provide durable jobs or spontaneous reverse wake-up.
- Requires an isolated host/profile because raw tool parameters are not sufficiently constrained.
- May be blocked by current macOS restricted-sandbox behavior.

### Follow-up decisions

- Whether the consumer account legitimately exposes the direct Codex tool actions; otherwise whether CanEngine can serve as a bounded bridge to Codex without false permission metadata.
- Whether to repair or replace the broken Homebrew Codex installation.
- Whether the stable launcher should use the ChatGPT App binary or a separately managed official CLI.
- Whether a narrow enforcement adapter is required before any real project pilot.
- Whether richer lifecycle needs justify an MCP facade over Codex App Server.
