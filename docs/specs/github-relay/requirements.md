# GitHub-Controlled Managed Codex Relay Requirements

> Historical R-GH sections below describe the predecessor. COMPONENT-02 below
> supersedes fixed configuration, automatic migration and supervision contracts.
> Historical private identifiers (control repository, operator login, business
> aliases, branch prefixes) are replaced with synthetic placeholders for
> publication; the private history retains the original values.

## Scope

R-GH1 through R-GH3 MUST provide a local, outbound-only relay:

```text
GitHub Issue -> Local Relay -> Existing Guard -> Codex -> GitHub Issue Result
```

The public operations MUST be limited to `start`, `reply`, and `publish`.
The relay MUST NOT merge, deploy, run arbitrary shell, accept custom Git
authority, or invoke raw Codex.

## Admission requirements

- The repository MUST equal the operator's designated private control
  repository (`example/control-private` as the synthetic placeholder).
- The issue MUST be open, authored by the designated allowed author
  (`fixture-owner` as the synthetic placeholder), and carry `bridge-job`.
- The body MUST be exactly one raw JSON object or exactly one Markdown JSON
  fence. Extra prose, multiple fences, duplicate JSON keys, and ambiguous JSON
  MUST be rejected.
- The payload MUST conform to the discriminated `oneOf` branches in
  `job-schema-v1.json` and reject unknown fields.
- `start` MUST accept only `repoAlias=sample-alpha`, `repoAlias=sample-beta`,
  or `repoAlias=sample-gamma`; registry entries MUST NOT expand this allowlist.
  Alias admission is not authorization for business work or publication.
- `reply` MUST accept only a local opaque `relayJobRef` plus `prompt`; it MUST
  reject caller-supplied repository or Guard identity fields.
- `publish` MUST accept only a local opaque `relayJobRef` plus a non-empty,
  NUL-free commit message of at most 500 characters.
- `taskName` MUST be at most 120 characters and `prompt` MUST be at most 256
  KiB (262144 Unicode characters).
- A request ID or issue number admitted once MUST never allocate a second Guard
  job or publish action, including after the issue body is edited.
- An unknown, malformed, revoked, incomplete, or cross-installation relay
  reference MUST fail closed.

## Local state requirements

- State MUST be stored at
  `~/Library/Application Support/chatgpt-codex-bridge/github-relay.sqlite3`.
- The database MUST be a non-symlink regular file with mode `0600`.
- It MUST store request ID, issue number, first-admission body SHA-256,
  operation, opaque relay job reference, fixed repository alias, local Guard
  job/thread capabilities, status, and timestamps.
- The R-GH1 schema MUST migrate transactionally to the multi-operation schema.
  Existing rows MUST become `operation=start`, `repoAlias=sample-alpha` without
  changing their public references or local capability values.
- A start reference MUST bind one local Guard thread capability and repository
  alias. Reply and publish requests MUST resolve only that start mapping.
- Guard job and thread capabilities MUST NOT be emitted to GitHub, logs, stdout,
  or committed files.

## Guard requirements

- The relay MUST start the existing installed `run-guard.zsh` with the existing
  `CHATGPT_CODEX_BRIDGE_CONFIG`.
- It MUST implement only MCP `initialize`, `tools/list`, and `tools/call`.
- It MUST verify `codex-repo-start`, `codex-reply-async`, `codex-wait`,
  `codex-job-status`, and `codex-repo-publish` are present before execution.
- It MUST call `codex-repo-start` with exactly `repoAlias`, `prompt`, and
  `taskName`, and `codex-reply-async` with exactly the locally resolved
  `threadId` plus prompt. Async jobs MUST use only `codex-wait` or
  `codex-job-status` to terminal state.
- Publish MUST call `codex-repo-publish` with exactly the locally resolved
  `threadId` plus validated commit message.
- It MUST NOT call raw Codex, `codex exec`, local-run, or local-stop.
- The relay itself MUST NOT execute `git push`, merge, rebase, tag, or checkout
  the protected base branch. Publish authority remains solely in the Guard.

## Thread continuity requirements

- Given a completed start, when a valid reply references its `relayJobRef`, the
  reply MUST use the exact stored thread capability and MUST remain in the same
  Guard-managed worktree and repository alias.
- The reply schema MUST NOT accept a caller-selected repository alias.
- A relay restart MUST preserve a completed start mapping and permit a later
  reply without exposing or replacing the Guard capability.
- A revoked or mismatched capability MUST return a public-safe failure and MUST
  NOT allocate a replacement thread.

## Publish requirements

- Guard publish output MUST be accepted only with the exact closed fields
  `branch`, `commit`, `pushed`, and `base_stale`.
- A completed public publish result MUST expose only request/reference/status,
  repository alias, generated branch, 40-hex commit, pushed, and base-stale
  facts.
- The generated branch MUST match the fixed prefix for the locally bound alias:
  `codex/relay/sample-alpha/`, `codex/relay/sample-beta/`, or
  `codex/relay/sample-gamma/`, respectively.
- Publish MUST NOT expose a remote, local path, Guard identifier, credential,
  environment value, API key, or Tunnel identifier.

## GitHub and result requirements

- Issue discovery MUST read every page of the fixed repository's open
  `bridge-job` issues, oldest first, at 100 items per page, stopping only on a
  short or empty page. There MUST NOT be a total issue cap.
- A page API error or non-list response MUST fail the discovery cycle closed
  before any newly discovered issue is admitted. Existing active-job/outbox
  reconciliation remains independent. Repeated reads and duplicate issue
  numbers MUST retain existing admission idempotency.
- Authentication MUST use an already-valid GitHub CLI login. Missing auth MUST
  stop the relay; it MUST NOT create a PAT.
- The relay MUST create and use the five specified labels and transition
  queued -> running -> completed/failed.
- A terminal comment MUST begin with `BRIDGE_RESULT_V1` and contain exactly the
  closed content-result fields for start/reply or the closed publish-result
  fields for publish. Content results MUST keep `publishAvailable=false`.
- Result content MUST be limited to 40000 characters and set
  `contentTruncated=true` whenever truncated upstream or locally.
- Result content MUST fail closed if it contains Guard capabilities, job/thread
  identifiers, absolute local paths, credentials, API/Tunnel secrets, or raw
  secret environment values.

## Runtime requirements

- The relay MUST use outbound GitHub API HTTPS only and MUST NOT open a port,
  start an HTTP server, start a Tunnel, invoke a workflow, or require sudo.
- The macOS installer MUST refuse to start while the Secure Tunnel LaunchAgent
  is loaded and MUST preserve the existing config, registry, Guard, Tunnel
  profile, and Tunnel runtime key.

## Reliability requirements

- The relay MUST hold one non-blocking, process-lifetime lock before opening or
  migrating SQLite. A second instance MUST exit cleanly without admitting work.
- Start and reply MUST persist the admitted request and returned Guard job
  capability, then return to the poll loop without waiting for terminal state.
- Every poll cycle MUST observe each active Guard job through
  `codex-job-status`. A relay restart MUST resume observation of the same job;
  it MUST NOT mark a bound active job interrupted or allocate a replacement.
- An active row without a durable Guard job capability MUST fail closed without
  allocating replacement work.
- A terminal public-safe result MUST be validated and persisted in a durable
  result outbox before any GitHub comment or terminal-label attempt.
- Result delivery MUST be idempotent. The relay MUST recognize the exact
  deterministic `BRIDGE_RESULT_V1` comment, retry missing comment or label work,
  and acknowledge delivery only after both are present.
- A temporary GitHub API failure MUST leave the result pending for later retry;
  it MUST NOT lose the result or leave its request permanently running.
- SQLite v2 state MUST migrate transactionally to v3 without changing request
  IDs, public references, capabilities, aliases, branches, or status. Existing
  terminal rows MUST enter legacy reconciliation rather than be discarded.
- A legacy terminal row with a Guard job capability MUST be reconstructed from
  `codex-job-status` when its exact result comment is absent. A pre-existing
  exact result comment MUST be acknowledged without duplication.
- Publish MAY remain synchronous, but its terminal result MUST use the same
  durable outbox and idempotent GitHub delivery path.
- The outbox MUST contain only the validated public result. Guard capabilities,
  raw MCP errors, local paths, credentials, and secret values MUST remain local
  and MUST NOT enter the outbox or GitHub.

## Bridge self-management requirements

- The operator registry MAY add the self-management alias (`repoAlias=sample-beta`
  as the synthetic placeholder) only after the canonical engineering remote
  branch exists.
- The self entry MUST use the designated engineering base branch, work prefix
  `codex/relay/sample-beta/`, deployment tier `none`, and protect the base branch.
- Self-management MUST remain isolated-worktree -> reviewed generated branch ->
  separate integration gate. It MUST NOT self-merge, self-deploy, or restart the
  running relay automatically.

## Acceptance

Given a start and reply pair, the reply MUST recover the prior marker in the
same thread/worktree with zero changes. Given a Bridge-only proof edit and
publish request, only a Guard-generated `codex/relay/sample-beta/` branch MAY be
pushed; protected branches and unrelated remotes MUST remain unchanged.

All relay security tests, existing Bridge/managed-repo regression tests,
`git diff --check`, and `git fsck --full --strict` MUST pass with P0/P1=0.
Reliability acceptance additionally requires single-instance exclusion,
multiple simultaneously active issues, restart reconciliation, durable retry
after GitHub comment/label failures, and self-healing of an undelivered legacy
terminal result without allocating a new Guard job.


## COMPONENT-01 — Observation evidence and offline doctor (V3 candidate)

This section governs bounded engineering verification; historical live and full
Relay lifecycle acceptance above are not rerun. RESUME-04 OS cause is UNKNOWN.

- Before/after instance-read failures MUST retain step, time, actual/expected
  length, immediately available errno (null if unavailable), exception and
  completed local steps. Partial evidence MUST NOT become a complete sample.
- Permission, exit, conflict, timeout and unknown read errors MUST be classified
  from actual evidence. Unknown MUST fail closed. Only an exact accepted
  launcher/runner transition MAY be STARTING.
- Keep launcher bytes/plist command, interpreter, exact application argv,
  independent interpreter/framework evidence and before/after instance checks.
  One supplied monotonic start MUST bind one 15-second deadline including static
  checks and independent observation. No restart, reset or process cleanup.
- Existing doctor MUST expose --static and --observe using shared source. Old
  execution checks require doctor --runtime; status remains its explicit runtime
  command. Unqualified doctor MUST show usage without loading installed config.
- --static MUST require explicit config/source-root, aggregate missing fields
  and files, and distinguish NOT_COLLECTED, DRIFT and NOT_RUN. It MUST NOT follow
  config-referenced runtime paths, execute configured tools, verify registry or
  fall back to home config/store. Success is STATIC_CHECKS_PASSED, never ready.
- Raw observation inputs/paths/argv/native metadata MUST go only to a new explicit
  private file (0600). stdout contains sanitized status/counts; stderr contains
  sanitized CLI/recording errors. Save failure MUST preserve the original result
  and force failure. Never overwrite private evidence.

Acceptance: before/after fixtures, complete-identity/deadline negatives, real
candidate CLI static-isolation tests, owned macOS reader smoke where available,
relevant portable/Guard/managed/Relay tests, syntax/compile, diff and fsck. No live
service, protected data, migration, merge or release. Rollback is reverting the
uninstalled source candidate; no runtime migration is needed.

## COMPONENT-02 — trusted configuration and supervision

- Given explicit private operator plist, Relay MUST use `relay_control_repository`,
  `relay_allowed_authors`, `relay_enabled_aliases`; alias syntax is generic.
  Admission MUST intersect enabled aliases with the existing live validated registry.
  Registry is the sole branch-prefix authority. Missing/invalid inputs MUST reject.
- Journal v4 MUST bind the existing Guard capability-key installation identity and
  control repository before reading mappings. Nonempty v3 requires explicit matching
  legacy scope assertion; v1/v2 require separate operator migration. Mismatch MUST
  reject without adopting/replaying/deleting rows. Old code MUST reject v4 columns.
- Same task reference MUST retain immutable per-request evidence revisions. Query and
  review MUST use closed requests through the same envelope and MUST NOT start work.
  Reviews MUST bind exact evidence request and digest, include authenticated author
  and conclusion, and MUST NOT grant publish/merge/business authority.
- Execution, delivery and review MUST remain separate. Snapshots MUST retain actual
  observation time and finite event phase, and mark stale/unknown explicitly.
  Query delivery time MUST NOT replace execution time.
- Guard MUST collect base/head/tree, changed paths and bounded text diff from the
  owned workspace; actual command exit codes MUST come from matching App Server
  commandExecution events. Missing evidence MUST say NOT_COLLECTED/NOT_RUN.
  Untracked text MUST contribute to candidate digest. Paths/symlinks/secrets/oversize
  content MUST be withheld; local absolute paths and raw IDs MUST never leave Relay.
- PR125-R1: `.env` / `.env.*` artifacts and AWS credential assignments or access-key
  identifiers MUST be withheld by the existing path/content boundary, including
  ordinary source diffs and command text. Final Guard -> Relay -> fake GitHub
  evidence MUST exclude the synthetic credential; safe small text stays reviewable.
- PR125-R2: artifact refusal MUST NOT discard safe command records. Unsupported
  paths or excess file counts MAY yield WITHHELD artifacts, but an actual safe
  command exiting 7 MUST retain exitCode 7 and checksState RECORDED. Unsafe command
  records MUST be withheld independently of artifact evidence.
- Existing outbox MUST deliver versioned snapshots/results/reviews idempotently,
  preserving exact historical V1 bytes. Comment-accepted/label-failed retries MUST
  NOT reexecute. Unbound side effects MUST be interrupted/unknown, never replayed.
- Guard admission lock MUST reject simultaneous turns on the same thread. Managed
  continuation MUST require recorded compatible protocol; no automatic fallback.
- Managed App Server MUST use the public rust-v0.106.0 subset with workspace-write /
  never, fixed cwd and filtered env. Responses, root thread/turn and terminal event
  MUST match; agent text/process exit MUST NOT imply completion. stderr stays private.
- Acceptance MUST exercise two synthetic registered/enabled projects through actual
  Relay/Guard entrypoints with fake downstream, real fixture Git diffs and fixed
  harmless command exits. No real services, protected stores or runtime migration.
