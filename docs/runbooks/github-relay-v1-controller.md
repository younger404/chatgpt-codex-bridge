# GitHub Relay V1 web controller SOP

How one ChatGPT web conversation drives an installed GitHub Relay V1 bridge
through your own private control repository. This SOP creates no Issue for
you; every command is a future operator action, not something this document
performed.

## 1. Capability precheck (before any task)

Two different facts, do not merge them:

```text
reading GitHub source          !=  creating labeled control Issues
installing this source package !=  granting account permissions
```

OpenAI documents a read-only GitHub app entry, while the GitHub plugin page
lists separate write capability. Entries differ; what matters is the tool list
visible in **your** conversation for **your** private control repository.
Plus/Pro/Business plan names, a connected GitHub account, or an installed
Skill do not by themselves prove write access.

Confirm with a harmless check first — for example, ask the conversation to
list open Issues in your private control repository (read) and to create one
labeled test Issue that you close yourself (write). You need all of:

- read Issues and comments in the private control repository;
- create Issues/comments with the `bridge-job` label;
- the connection's authorization scope actually covers that private repository.

If your session is read-only, web-driven delivery is not available. Do not
switch to a weaker transport silently and do not lower product safety
boundaries; use the local operator path instead.

Synthetic feedback template for recording your own precheck (keep it local or
in your private notes; do not file it upstream):

```text
checked_date: <date>
control_repository: <owner/private-repo>   # your own, never this source repo
session_read_issues: PASS | FAIL
session_create_labeled_issue: PASS | FAIL
authz_covers_private_control_repo: PASS | FAIL
result: CAPABLE | READ_ONLY | UNKNOWN
notes: <which entry/app was used; no tokens, no IDs>
```

## 2. Copyable controller instruction block

Give the web conversation one block like the following. Replace every angle-
bracket value. Use your configured alias, a **new canonical UUID** per request,
and the **actual** `relayJobRef` returned by your installation (see
[examples/](../../examples/README.md) for the closed schema shapes).

```text
You are the web controller of my local GitHub Relay V1 bridge.

Control repository: <owner/your-private-control-repo>
Registered alias: <your-alias>   (registered and enabled locally; never send
paths, branches, remotes, or repository names as task authority)

Rules:
1. Every request is exactly one JSON object with schema "codex_bridge_job_v1"
   on an open Issue labeled bridge-job, authored by my allowed account.
2. To start work: operation "start" with my alias, a taskName, and the prompt.
   Use a new UUID requestId every time.
3. Before claiming anything about existing work: operation "query" with the
   actual relayJobRef and a new requestId; report only recorded states.
4. To record my review: operation "review" bound to the CURRENT
   evidenceRequestId and evidenceDigest returned for that exact evidence.
   Conclusions are "accepted" or "changes_requested". A review records my
   declaration about exact evidence; it is not merge, publish, or deploy
   authorization, and new evidence is unreviewed.
5. To continue: operation "reply" with the SAME relayJobRef and a NEW
   requestId, only for the task I explicitly authorize in this conversation.
6. operation "publish" pushes the generated branch only, only when I
   explicitly ask. It never merges, rebases, force-pushes, opens a PR, or
   deploys. Merge, pull requests, and deployment are separate human actions
   outside this bridge.
7. completed / delivered / review-accepted / published / merged / deployed are
   different states. checksState=WITHHELD is not "tests PASS".
8. Never paste capability keys, registry, journal, tokens, or private paths
   into Issues or comments.
```

## 3. Operator states you will see

- `queued`/`running`: admission happened; not a result. Keep waiting.
- `completed`: the managed job reached a terminal state locally.
- delivered: the sanitized result comment was posted and acknowledged.
- review accepted: an allowed author recorded acceptance of exact evidence.
- published: the generated branch was pushed. Nothing was merged or deployed.

## 4. What the control repository stores

Task requests and sanitized code diffs live in your control repository and the
local relay journal. Treat them under your project's data policy. Unsafe
content is withheld with recorded reasons; withheld is not passed.
