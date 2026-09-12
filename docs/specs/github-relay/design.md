# GitHub-Controlled Managed Codex Relay Design

## Components

- `job-schema-v1.json` is the public request contract.
- `github-issue-relay.py` contains strict admission, SQLite replay protection,
  a minimal line-delimited stdio MCP client, GitHub CLI API calls, result
  sanitization, and the poll loop.
- `run-github-relay.zsh` fixes the existing Bridge config and runs the relay.
- `install-github-relay-macos.zsh` stages only relay files and creates a
  separate user LaunchAgent. It does not alter the Tunnel LaunchAgent.

## Trust boundaries

GitHub provides untrusted issue data. Admission completes before any Guard
process is started. The repository, author, state, label, JSON shape, operation,
alias, and sizes are all closed allowlists.

The existing Guard remains the sole filesystem/Codex authority. Guard bearer
capabilities cross only the stdio boundary into local SQLite. GitHub receives a
fresh random `rjob_` reference with no reversible mapping.

The pinned Guard accepts either of the two exact official Codex MCP
`approval-policy` enum contracts observed across the supported runtime window:
the legacy `untrusted/on-request/never` form and the current
`on-request/never` form. Every other input/output schema field remains an exact
match. The relay bounds `codex-repo-start` to 360 seconds so the Guard's own
300-second managed-repository fetch/allocation boundary can complete; other MCP
requests retain the 60-second bound.

The initial managed-repository allocation remains a bounded synchronous Guard
call because no job capability exists before it returns. Once the Guard returns
that capability, terminal supervision is non-blocking and belongs to the poll
loop.

## Operation model

The schema uses three closed discriminators rather than a shared universal
object. `start` creates a new opaque relay reference. `reply` and `publish`
carry that reference but never accept a repository alias, path, branch, remote,
or Guard identifier from GitHub.

SQLite v2 keeps one row per public request. Start rows have a partial unique
index on `relayJobRef`; reply and publish rows may reference the same start.
Resolving a reference always selects the completed start row and returns its
fixed alias and local thread capability. Existing v1 rows migrate as sample-alpha
start rows in one transaction.

Reply calls `codex-reply-async` with the stored thread capability and rejects a
different returned thread. The Guard resolves that capability back to the
original managed record, so the repository and worktree cannot be selected by
the GitHub caller.

Publish calls only `codex-repo-publish`. The relay validates the Guard's exact
closed result and the alias-specific generated branch prefix, then translates
`base_stale` to the public `baseStale` field. The relay contains no Git command
or push implementation.

The fixed relay alias allowlist is `sample-alpha,sample-beta,sample-gamma` even if the
operator registry later contains more entries. The new alias uses only
`codex/relay/sample-gamma/`; stored alias/thread bindings and caller-supplied
path restrictions are unchanged. Admission grants no business authority.

Issue discovery collects all pages before returning to `run_once`, using the
fixed repository, `state=open`, `labels=bridge-job`, `per_page=100`,
`sort=created`, and `direction=asc`, with `page` increasing from 1. A short or
empty page ends discovery; an API error or non-list page discards the collected
batch. No partial batch reaches admission and no total cap hides the tail.
Existing durable issue/request identity prevents duplicate admission across
repeated scans or overlapping pages.

## Reliability model

SQLite v3 adds a validated public result payload, delivery state, and delivery
timestamp to each request. Admission, Guard execution state, terminal result
durability, and GitHub acknowledgement are separate transitions. The relay
holds a non-blocking `flock` for its full lifetime before SQLite is opened, so
only one process may advance those transitions.

Start and reply persist the Guard job capability and return to polling. Each
cycle calls `codex-job-status` for active jobs. A terminal response is converted
to the same closed public result contract, validated, and committed as a
pending outbox item before GitHub is contacted. Restart therefore resumes
observation from the stored capability instead of synthesizing interruption.

GitHub delivery uses the deterministic complete `BRIDGE_RESULT_V1` comment as
its idempotency key. The relay first recognizes or creates that exact comment,
then applies the terminal label, and only then records delivery. A response
failure after GitHub accepted the comment and a later label failure both retry
without duplicating the comment.

During v2-to-v3 migration, active rows remain active and terminal rows become
legacy outbox candidates. Legacy reconciliation first recognizes an existing
exact result comment. If none exists and a Guard job capability is available,
the relay reconstructs the terminal result with `codex-job-status`; it never
starts replacement work. A legacy row that cannot be reconstructed fails
closed with a generic public result.

## Failure behavior

- Admission failures do not call the Guard and receive only a public-safe
  rejection marker.
- Once admitted, the issue number and request ID are durable. A restart or edit
  cannot re-run the request.
- Guard/protocol/security failures produce a generic failed result. Raw errors,
  stderr, capabilities, paths, or environment are never forwarded.
- An active local row without a durable Guard job capability is failed closed
  rather than allocating another Guard job.
- An active local row with a durable Guard job capability resumes observation
  through `codex-job-status` after restart.
- A GitHub delivery failure leaves a terminal result pending in the outbox and
  is retried without duplicating an already accepted comment.
- An unknown or revoked reply/publish reference fails closed without creating a
  replacement thread or direct Git fallback.

## Network and process model

The relay has no listener. `gh api` performs outbound HTTPS to the fixed GitHub
repository. The relay launches the already-installed Guard wrapper over stdio.
The separate LaunchAgent is a long-lived poller and is installable only while
the Secure Tunnel LaunchAgent is stopped. A non-zero relay exit is restarted
after a 15-second throttle; a clean exit remains stopped.

## Rollback

Unload and remove the GitHub relay LaunchAgent and its staged relay runtime.
The existing Bridge config, registry, Guard, Tunnel profile, and Tunnel runtime
key are independent and remain available for later restoration.

The operator may remove the `bridge` registry entry to revoke future
self-management starts. Published proof branches remain ordinary reviewable
remote branches and are never merged by the relay.


## COMPONENT-01 — Explicit inputs in the existing doctor

The portable service dispatches --static/--observe before installed configuration
or maintenance code. --runtime selects old checks; status/install/restart remain
otherwise unchanged. bridge-doctor.py calls process_observation.py: packaged
source helpers, not new services, runners or persistent task records.

Static mode reads an explicit existing-format plist and fixed files under an
explicit candidate source root. It validates the managed-repo policy and field
shapes without opening referenced runtime paths. Optional expected-digests JSON
maps only fixed source-relative paths to SHA256; absent entries are NOT_COLLECTED,
unequal comparable bytes are DRIFT. There is no historical continuity claim.

Observation accepts an explicit private contract: pid/uid/ppid, started_monotonic,
label, and files keyed plist/launcher/runner/interpreter/framework/application,
each with canonical path and expected sha256. It never discovers or starts a
service, nor reads a default config/baseline. Plist label and [launcher, runner]
are exact; final argv is [interpreter, application, --watch]. Only that exact
launcher command is transitional. This is local acceptance input, not a public
protocol or cross-project configuration layer.

Native calls capture ctypes errno immediately (cleared immediately beforehand).
Unknown short reads are READ_ERROR unless actual errno establishes permission or
exit. Unavailable exception errno is null. The retained BSD layout/flavor is
checked against local SDK headers, without speculative ABI changes. Completed
steps and the failed step survive in the partial sample. A final observation
rechecks the same instance after independent interpreter/framework evidence.

lsof stdout/stderr are drained by subprocess.run within the remaining original
window. Its exit code is distinct from unavailable target exit status. No signal
is sent. Private output is exclusive; recording errors preserve original result
and force nonzero exit. Existing historical evidence is untouched.

## COMPONENT-02 design (supersedes historical fixed settings)

Extend the existing operator plist, reusing managed_registry and job_state_dir.
Derive private installation identity from the existing capability.key using a
purpose-separated SHA256; no second identity key or capability format. Journal v4
adds singleton scope metadata and per-row observation/evidence/review projections.
Nonempty v3 requires --legacy-scope matching the target identity/repository digest;
this is an explicit operator assertion, not discovered provenance. Empty v3 can bind.
Unknown old v1/v2 or future schemas fail closed. A scope change requires a separate
journal; references cannot cross it. Registry-hash revocation is unchanged.

Keep one row/request, stable start reference, and immutable terminal resultPayload.
Use the same deliveryState/resultPayload outbox for V2 terminal results, query and
review requests. A finite first running snapshot is a V2 result on the start/reply
Issue; terminal replaces the pending snapshot on that row, retaining delivered
comments on GitHub. No token comments. Query materializes latest execution row from
SQLite only, including current delivery status and latest review for that evidence.
A closed review stores evidenceRequestId + evidenceDigest + conclusion + envelope
author; it never changes execution or triggers continuation. New reply starts with
unreviewed evidence. Reject busy same-reference mutation in both Relay transaction
and Guard admission lock. Interrupted unbound requests expose uncertainty.

Managed worker bypasses project/sidebar bootstrap, uses thread/start or compatible
thread/resume then turn/start. The existing AppServerClient handles stdio/deadline;
validate IDs and collect only root commandExecution exits. thread/read after terminal
confirms stored identity, without another turn. Progress is actual root event time.
The shared supervision helper collects bounded Git data with external diff disabled,
no symlink traversal, safe relative paths and conservative outbound text filtering.
Unsafe artifacts are withheld with a digest, never auto-published. The Relay validates
closed nested evidence again with local capabilities before persisting an outbox.
PR125-R1/R2: reject `.env` / `.env.*` path components before reading artifacts and
extend the existing shared text filter for AWS credential fields/access-key IDs.
Collect safe bounded command records before artifact validation, applying forbidden
local IDs independently to commands and artifacts. Artifact refusal cannot erase
safe exits. No new scanner, path support, size limit, service or schema is added.

Protocol reference: https://github.com/openai/codex/tree/rust-v0.106.0/codex-rs/app-server-protocol/schema/typescript
ThreadStartParams, ThreadResumeParams, ThreadReadParams, TurnStartParams, SandboxPolicy,
ReadOnlyAccess, UserInput, ThreadItem. This is source-schema evidence, not installed
runtime certification. Legacy managed records without protocol cannot resume.
Rollback of source is not rollback of v4 data; predecessor column checking rejects it.
