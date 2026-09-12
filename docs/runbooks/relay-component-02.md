# COMPONENT-02 candidate: configure and supervise managed projects

This is an **uninstalled engineering candidate** on the COMPONENT-01 baseline.
It does not authorize installation, real store migration, service startup, model
execution, business work, merge or deployment. Commands below are future operator
instructions, not actions performed for candidate acceptance.

## One installation, one private control repository

Use the existing operator `config.plist` (canonical regular file, owner-only 0600).
Keep its existing Guard fields. Add these three transport fields:

```xml
<key>relay_control_repository</key><string>example/control-private</string>
<key>relay_allowed_authors</key><array><string>fixture-owner</string></array>
<key>relay_enabled_aliases</key><array>
  <string>sample-alpha</string><string>sample-beta</string>
</array>
```

`managed_registry` points to the existing private managed-repository registry;
`job_state_dir` selects the existing Guard store containing `capability.key`.
The Relay **reads but never creates or repairs that key**. Missing key/config,
wrong permissions, policy other than managed-repo/workspace-write/never, unknown
enabled aliases or invalid registry produce `OPERATOR_CONFIG_REJECTED`.
Runtime refusal has a sanitized error; no developer-account/repository fallback.

The registry remains the only source of paths, base branches, remotes and generated
branch prefixes. Optional `relay_branch_prefixes` must equal the enabled aliases'
registry prefixes exactly; omitting it avoids duplicated constraints. A new alias
requires no source change. Registration alone does not enable GitHub transport.

After a separately authorized registration, use the existing CLI, for example:

```zsh
/bin/zsh scripts/managed-repos.zsh register \
  --alias sample-alpha --repo-path /operator/repos/sample-alpha \
  --repository-full-name example/sample-alpha --base-remote origin --base-branch main
/bin/zsh scripts/managed-repos.zsh verify sample-alpha
```

Repeat registration for `sample-beta` with its own canonical repository. Then
explicitly include both aliases in `relay_enabled_aliases`. The actual repository
must match its declared GitHub identity. Candidate tests substitute **only** that
remote identity check for their own local bare origins; this is not a supported
runtime local-remote bypass. Registry hash changes revoke old managed capabilities;
adding a project does not promise continuity of earlier execution permissions.
Retained sanitized terminal evidence remains queryable independently.

The existing runner now passes `--config` explicitly. Source invocation is:

```zsh
python3 scripts/relay/github-issue-relay.py --watch --config /operator/config.plist
```

This starts the real control path and is **NOT_RUN here**. The installer including
`--no-start` still has real side effects and is not a static checker. The existing
safe checker is `doctor --static --config … --source-root …`; it aggregates missing
transport fields while never opening config-referenced registry/key/runtime paths.
It proves static source/config shape only, not readiness or authorization.

## Journal identity and compatibility

SQLite v4 binds a singleton scope digest to the existing Guard key's installation
identity plus normalized control repository. Scope is:

1. `installation = SHA256(b"relay-installation-v1\0" + existing_32_byte_key)`
2. `scope = SHA256(canonical_JSON([installation, normalized_control_repository]))`

Both are private local values. Nothing is published. Changing either identity
against the same journal gives `JOURNAL_SCOPE_MISMATCH`. A separate journal cannot
resolve old references, including identical Issue numbers. `--state` chooses an
explicit journal for independently authorized operator use; it never imports refs.

A nonempty v3 journal has no proven historic scope. Opening it without a matching
`--legacy-scope` assertion returns `OPERATOR_MIGRATION_REQUIRED`, preserving rows.
Before a separately authorized migration, the operator must independently establish
that **all** its requests belonged to that installation and control repository.
Only then may that operator supply the exact scope digest as `--legacy-scope`.
Passing the current digest is an assertion of those facts, not a proof that the
program recovered history. Unknown provenance must remain unbound. v1/v2 need
separate explicit migration; this candidate no longer assigns an implicit alias.

Migration is one transaction, preserving request IDs, refs, capabilities, status
and exact terminal/outbox bytes. Existing rows remain protocol version 1; new
requests use V2 result projections. The predecessor rejects v4's extra columns.
Code rollback is **not** a database downgrade. Only synthetic v3 migration was run.

## Read the same task and record review

All requests use `codex_bridge_job_v1` with a new canonical UUID per action, in one
strict JSON object on an open `bridge-job` Issue in the configured repository,
authored by an allowed account. The actual GitHub source URL/author/state/labels
are validated. Caller-supplied paths, commands, aliases on continuation, privilege
fields and unknown fields are rejected by the closed schema.

Start:

```json
{"schema":"codex_bridge_job_v1","requestId":"11111111-1111-4111-8111-111111111111","operation":"start","repoAlias":"sample-alpha","taskName":"Document example","prompt":"Update the example documentation and run its existing check."}
```

Read comments on that Issue through the GitHub connector. A finite initial progress
snapshot and the terminal projection begin `BRIDGE_RESULT_V2`, followed by JSON.
`relayJobRef` remains stable across rounds. `requestId` identifies this action;
`supervision.executionRequestId` identifies the execution evidence being shown.
No model is started by reading an existing comment. A stored-state query can also
be submitted through the same authorized Issue path:

```json
{"schema":"codex_bridge_job_v1","requestId":"22222222-2222-4222-8222-222222222222","operation":"query","relayJobRef":"rjob_syntheticreference00000001"}
```

Use the **actual** returned reference. Query creates a local projection request,
not a development task or turn. It does not invoke Guard. It reports the latest
execution row, actual observation time, finite phase and `current/stale/unknown`
freshness (stale after 120 seconds). Stale means observation age, not task failure.
No token-by-token comments. A retry time never becomes execution progress time.

The supervision object separates:

- `executionState`: queued/running/completed/failed/interrupted.
- `deliveryState`: the evidence row's observed none/pending/delivered/legacy state.
  A terminal comment's snapshot can say pending because it was composed before
  GitHub acknowledgement; a later query reads the updated delivered state.
- `reviewState`: unreviewed or recorded, with the exact structured review if any.

Evidence contains base/head/tree, changed relative files, bounded inline text diff,
`candidateDigest` covering uncommitted diff and untracked text, actual recorded
commands and nullable exit codes. `NOT_RUN`/`NOT_COLLECTED` never imply success.
A small `review-note.txt` is included inline in acceptance fixtures; a reader needs
no local filesystem access. ASCII relative paths, <=64 files, bounded individual
files and <=16 KB public text are supported. Binary, secret-shaped, escaping/symlink
or oversized content is explicitly WITHHELD/TRUNCATED; no automatic upload/publish.
A model's claim that tests passed is never converted into command evidence.

To record review, copy the **execution request ID and evidenceDigest** from that
round (including the candidate's uncommitted identity):

```json
{"schema":"codex_bridge_job_v1","requestId":"33333333-3333-4333-8333-333333333333","operation":"review","relayJobRef":"rjob_syntheticreference00000001","evidenceRequestId":"11111111-1111-4111-8111-111111111111","evidenceDigest":"0000000000000000000000000000000000000000000000000000000000000000","conclusion":"changes_requested"}
```

Replace example IDs/digest with returned values. Conclusions are `accepted` or
`changes_requested`; the author comes from the authenticated Issue envelope.
A random comment, completion or successful delivery does not record review. A
review only records an authorized account's declaration about exact evidence;
it does not prove comprehension, Human Owner business approval, GitHub APPROVED,
merge/deploy permission or authorization for another turn.

Then explicitly continue using the original reference and a **new** request ID:

```json
{"schema":"codex_bridge_job_v1","requestId":"44444444-4444-4444-8444-444444444444","operation":"reply","relayJobRef":"rjob_syntheticreference00000001","prompt":"Apply the requested clarification and rerun the affected check."}
```

This uses the original Guard thread/workspace/alias. Both Relay's journal transaction
and Guard's admission lock reject overlapping turns on that thread. New evidence is
unreviewed even if an older revision was accepted. Terminal evidence is immutable.
A separately authorized `publish` remains the existing closed ref/commitMessage
operation; it never follows automatically from review. The returned branch must
match both the bound work branch and registry prefix. No merges or deployments.

## Delivery and protocol evidence level

V1 comments retain exact legacy recognition. V2 projections reuse resultPayload and
deliveryState in the same journal. Outbox-before-delivery, exact-comment detection,
label retry and restart do not call start/reply/publish again. An admitted request
whose side effect lacks a durable mapping is interrupted/unknown, never replayed.
This does not claim universal exactly-once behavior for arbitrary network crashes.

The Guard remains Relay's only executor. Managed MCP initialization and tool listing
are now local Guard contracts; no raw MCP child is needed merely to list tools/read
stored status. Managed workers reuse AppServerClient's stdio protocol:
thread/start or compatible thread/resume, turn/start, matching root events, then
thread/read to confirm stored identity. No experimental project/sidebar APIs,
process API or fallback thread. The worker requires workspace-write/never, fixed cwd,
explicit turn writable root, disabled network, filtered environment and deadline.
The first thread response must confirm cwd/policy. Responses have exact typed IDs;
foreign thread/turn events cannot complete the root. agentMessage or process exit 0
alone cannot complete a managed execution. Protocol/exit/timeout are distinguished
in private status; stderr is separate, bounded at 64 KB and private 0600.

Source-contract target: OpenAI **rust-v0.106.0**, App Server v2 schemas:
[versioned official schema directory](https://github.com/openai/codex/tree/rust-v0.106.0/codex-rs/app-server-protocol/schema/typescript/v2).
Read ThreadStartParams/Response, ThreadResumeParams/Response, ThreadReadParams,
TurnStartParams, SandboxPolicy, ReadOnlyAccess, UserInput, ThreadItem and Turn.
Fixtures implement only the consumed subset. This is source-schema plus synthetic
stdio evidence, **not certification of any installed Codex version**. No installed
Codex --help/--version/schema/probe was run.

Managed records without this protocol marker are refused for continuation; no silent
legacy-thread migration. The unrelated existing personal/MCP path and its locked
schema validation remain as a transition and are regression-tested with fakes.

## Candidate acceptance and subsequent NOT_RUN work

`tests/relay/test-component-02.py` uses actual Relay admission/journal/outbox,
Guard MCP message dispatch, Guard JobStore allocation/worker and the existing
AppServerClient against an owned fake executable. Its two fixture repositories
produce real Git diffs and a real fixed Python check exit. HOME/state/key/registry
and processes are isolated. The two projects differ only in trusted configuration.
GitHub itself is fake, including reads, accepted-comment failure and label failure.

Not run: real GitHub connector -> live services -> real model across projects;
installed version compatibility; protected journal/thread migration; full macOS
service/CLI/lsof composition; clean real installation/distribution; recovery.
Each needs separate authorization. Minimal later acceptance is to install the exact
reviewed candidate into an isolated test installation, register/enable two nonbusiness
projects, verify the installed version/schema, and repeat start/query/evidence/review/
reply while comparing Guard's original thread/workspace and actual checks. Expected:
readable evidence, independent states, same-thread continuation and zero duplicate
execution. Migration needs its own verified provenance and rollback preparation.
None of these gaps authorizes running a stopped real service now.
