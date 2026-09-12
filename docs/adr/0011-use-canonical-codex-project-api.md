# ADR-0011: Use the canonical Codex project API

Status: Accepted
Date: 2026-08-21

## Context

ADR-0007 used `thread/start(cwd=<new-root>)` because Codex
`0.146.0-alpha.3.1` exposed no project registry mutation method. That produced
an interactive task, but live Codex inspection showed the generated directory
was absent from `list_projects` and its task had `projectId=null`. The user
requires both a visible project folder and its working threads grouped below
that project.

Codex `0.148.0-alpha.21` now exposes experimental App Server methods
`project/create`, `project/import`, `project/list`, and `project/update`.
`thread/start` accepts a `projectId`, and durable thread responses expose their
canonical project assignment.

Live inspection also showed that the desktop saved-project registry and the
experimental App Server project registry use different identifiers. The
supported macOS `open` command can register a directory with the desktop app;
the desktop then reconciles a durable App Server task to that saved project by
its exact root.

## Decision

1. A new-project worker MUST register the allocated root with the Codex desktop
   app using `/usr/bin/open -g -b com.openai.codex <root>`, then call
   `project/create` before `thread/start`.
2. The project creation idempotency key is derived from the durable bridge Job
   ID so replaying the same worker request cannot create duplicate projects.
3. `thread/start` MUST receive the returned App Server `projectId`. Because a
   new thread is not listable until its first turn is written, project and
   thread listing are verified only after that root turn becomes terminal.
4. Private job state stores the App Server `projectId` for diagnostics and
   continuation. Desktop acceptance separately checks that the saved desktop
   project and task converge to one desktop project ID.
5. Existing selected threads MAY be associated with an existing root through
   `project/import`. Direct edits to Codex history, SQLite, or indexes remain
   forbidden.
6. An unavailable or rejected project API is a terminal job failure. The bridge
   MUST NOT fall back to an unassigned exact-`cwd` thread.

## Consequences

- Every successful new project has a real Codex sidebar project identity after
  the desktop registry's bounded reconciliation delay.
- Its initial and continued threads remain grouped under that project.
- Codex versions predating the project API are no longer sufficient for the
  new-project path, although the short synchronous compatibility tools remain.
- A failed thread start may leave an empty registered project and directory for
  diagnosis; the bridge does not delete either automatically.
