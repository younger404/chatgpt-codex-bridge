# Agent Instructions (Spec-Driven)

This project uses spec-driven development. Treat specs as the single source of truth.

## Spec Structure (3 files + ADR)

For each feature, create:
- `docs/specs/<feature>/requirements.md` (what)
- `docs/specs/<feature>/design.md` (how)
- `docs/specs/<feature>/tasks.md` (task order)

Record key decisions in `docs/adr/` as ADRs (why + consequences).

## Spec Principles

- Every requirement must be testable and have acceptance criteria.
- Use RFC 2119 words: MUST / SHOULD / MAY to express strength.
- Use EARS or Given-When-Then for requirements to reduce ambiguity.
- Explicitly list: triggers/preconditions, edge cases, non-goals, failure modes,
  observability/acceptance, rollback/migration.
- Specs are versioned assets; update specs before code changes.

## Execution Rules (SOP)

1. Read specs first.
2. Work one task at a time (from `tasks.md`).
3. Provide a short plan and get confirmation before code edits.
4. Keep diffs small; avoid unrelated changes.
5. Run the required verification command(s).
6. Update `tasks.md` (mark done) and, if needed, update specs/ADR.

## When Spec-Driven is Required

- Multi-file or multi-module changes.
- Data migration or release risk.
- Long-lived features or cross-team work.

For quick spikes or one-off scripts, keep a minimal spec (requirements + tasks).

## Project Long Memory (Codex)

- Store project memory in `.project-memory/` (events, summaries, facts, decisions).
- Update memory after meaningful changes or decisions.
- Never commit `.project-memory/` (kept in `.gitignore`).
