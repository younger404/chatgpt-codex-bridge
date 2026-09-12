# ADR 0003: Personal Full-Control Conversation Thread

Status: Accepted
Date: 2026-08-03

## Context

The guarded consumer-workspace/Tunnel/Codex path is proven, but its original public `mode`, local write-enable flag, `on-request` policy, and process-local thread allowlist create steps the single-user preset does not need. The desired product behavior is one ChatGPT web conversation controlling one Codex thread with no per-call approval workflow.

OpenAI documents `codex` as the thread-start primitive and `codex-reply` as the continuation primitive. It also documents that `danger-full-access` removes local filesystem and network sandbox boundaries and that `approval-policy=never` does not stop for approval prompts.

## Decision

Keep the existing official Secure Tunnel, narrow stdio bridge, and official `codex mcp-server`; do not add an agent service, relay, database, approval queue, App Server adapter, or CanEngine to this path.

The active personal profile will:

- expose `codex(prompt)` for the first instruction in a ChatGPT conversation;
- inject the configured starting `cwd`, `sandbox=danger-full-access`, and `approval-policy=never`;
- expose `codex-reply(prompt, threadId)` for every later instruction in that conversation;
- record the returned value in the assistant reply as `Codex thread: <threadId>` so the ChatGPT conversation history itself retains the mapping; no separate database is introduced;
- accept conversation-carried thread IDs after a local bridge restart while verifying that the downstream reply preserves the requested identity;
- retain truthful action metadata, downstream contract validation, JSON-RPC correctness, and secret-environment filtering because these are interoperability mechanics, not user approval workflow.

## Consequences

- Codex can read, write, run commands, and use network access without stopping for approval prompts, to the extent permitted by the current macOS account.
- The public initial schema becomes prompt-only and the obsolete `--allow-workspace-write` switch is removed.
- Initial calls use the operator's normal Codex model and reasoning configuration instead of the old read-only Terra/low override.
- One-to-one mapping is conversational rather than server-owned: each ChatGPT conversation visibly retains and reuses its compact `Codex thread` tag.
- Full access increases blast radius by design; the user explicitly chose that tradeoff for personal convenience.

## Rejected alternatives

- Keep read-only/workspace-write promotion and approvals: rejected by the user's explicit convenience requirement.
- Persist ChatGPT-conversation-to-Codex-thread mappings in a database: rejected as unnecessary complexity because the conversation already retains tool results.
- Build on Codex App Server or Workspace Agent: rejected because `codex` plus `codex-reply` already provide the required synchronous thread lifecycle.
