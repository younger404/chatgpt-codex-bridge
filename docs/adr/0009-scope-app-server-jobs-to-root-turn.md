# ADR-0009: Scope App Server jobs to the root turn

Status: Accepted
Date: 2026-08-15

## Context

The live GACE M1 job delegated code, test, and provider-evidence reviews. The
provider reviewer completed first. Its child `turn/completed` event appeared on
the same App Server stream, and the Guard treated the first terminal turn as
the whole durable job. The stored result became the child provider report,
while the parent had not yet synthesized all review and test evidence.

## Decision

Bind every durable job to the root `threadId` and `turnId` obtained from the
worker's own `thread/start|resume` and `turn/start` responses. Only matching
agent-message and terminal events may update the stored root content or finish
the job. Foreign-thread and same-thread/different-turn events remain observable
but cannot mutate root completion state.

## Consequences

- Delegated review can complete in any order without truncating the parent.
- The durable job returns the parent synthesis rather than the first child
  final answer.
- A missing root terminal event leaves the job running/interrupted instead of
  guessing completion from a child event.
- Public MCP schemas and the ChatGPT supervisory contract do not change.
