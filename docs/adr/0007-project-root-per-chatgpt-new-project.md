# ADR-0007: One project root per ChatGPT-led new project

Status: Superseded by ADR-0011
Date: 2026-08-15

## Context

The durable bridge previously started every new Codex task from
`/Users/example-user/codex-workspace`. Codex desktop groups and filters tasks using the
task working directory, so a project implemented in a later-created child such
as `gace/` can remain visually grouped under the container instead of appearing
as its own sidebar project. The user also has an existing
`workspace-new-project` Skill that is the required source of project scaffolds,
specs, ADRs, and project memory.

Changing only Codex SQLite or session indexes is not a supported project-move
operation and can disagree with immutable rollout metadata. Adding a separate
"new project" tool would also leave ChatGPT free to select the older generic
start path.

## Decision

`codex-start` is the bridge's new-project primitive.

1. The bridge creates one safe, unique child directory below its configured
   workspace container. `projectName` is sanitized into the display name and
   directory stem; it is never accepted as a path. ADR-0011 supersedes this
   ADR's original `cwd`-only visibility mechanism.
2. A detached worker speaks the official Codex App Server JSONL protocol. It
   uses `thread/start` with that exact directory as `cwd`, then `turn/start`, so
   the task is an interactive task discoverable by Codex desktop. `codex exec`
   is rejected for this path because a live test proved its `source=exec`
   tasks do not appear in the desktop task list.
3. The first `turn/start` includes the installed `workspace-new-project` Skill
   as an explicit Skill input item. The accompanying text invokes
   `$workspace-new-project --here` before any implementation.
4. The worker verifies the Skill's required scaffold after a nominally
   successful run and fails the job if the scaffold is absent.
5. Private durable job state records the project root. Async replies resolve it
   from the original `threadId`, call `thread/resume` with the same `cwd`, and
   add a new turn without reinvoking the new-project Skill.
6. Existing incorrectly grouped tasks are not rewritten. A new user-owned
   handoff task may be created with the existing project directory as `cwd`.

## Consequences

- Each future ChatGPT-led new project has a distinct filesystem root. The
  earlier claim that exact-root task visibility also created a Codex sidebar
  project identity was disproved by live `projectId=null` evidence.
- Cached ChatGPT schemas that omit `projectName` remain functional through a
  generated visible fallback name.
- A failed start can leave an empty or partial project directory; it is kept for
  diagnosis and never deleted automatically.
- Continuation depends on private durable job history. A legacy thread without
  that mapping resumes from the configured container for backward
  compatibility.
- Existing Codex history remains intact; there is no migration or metadata
  rewrite.
- Sidebar discovery currently depends on the App Server's interactive task
  source contract. A live task-list acceptance check guards against future
  Codex source-classification drift.
