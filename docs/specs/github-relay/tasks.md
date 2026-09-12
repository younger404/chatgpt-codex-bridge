# GitHub-Controlled Managed Codex Relay Tasks

## BRIDGE-RECOVERY-01 isolated candidate (not installed)

- [x] Add only the fixed `sample-gamma` alias and its generated branch prefix.
- [x] Discover all open labeled issue pages, with atomic fail-closed discovery.
- [x] Verify alias/binding negatives, 0/1/100/101/200/201 scans, full `run_once`
  tail admission, page failure/type rejection, and duplicate idempotency.
- [x] Run Relay, Guard, managed-repo, schema, mirror, and Git checks.
- [ ] Independent review and separate publication/deployment authorization.

## Historical task record (not this-run deployment evidence)

- [x] Freeze Tunnel transport and verify installed assets remain.
- [x] Add the R-GH1 request schema.
- [x] Implement strict issue admission and 0600 SQLite replay protection.
- [x] Implement the minimal Guard stdio MCP client and call allowlist.
- [x] Implement safe GitHub labels, comments, and result validation.
- [x] Add the runner and macOS LaunchAgent installer.
- [x] Add all required relay security tests.
- [x] Run the complete existing security regression suite.
- [x] Install the relay and complete the synthetic read-only/no-publish proof.
- [x] Audit capability leakage, checkout/worktree changes, and remote pushes.
- [x] Migrate SQLite v1 rows to the closed multi-operation schema.
- [x] Add discriminated start/reply/publish validation and fixed alias allowlist.
- [x] Implement same-thread reply through `codex-reply-async` only.
- [x] Implement guarded publish through `codex-repo-publish` only.
- [x] Add R-GH2/R-GH3 security, replay, restart, and revocation tests.
- [x] Re-run the complete Bridge security regression suite.
- [ ] Commit and push reviewed R-GH2/R-GH3 infrastructure to `github-relay-v0.2`.
- [ ] Register and verify the fixed `bridge` managed repository entry.
- [ ] Upgrade the local relay without starting the Secure Tunnel.
- [ ] Complete local thread-continuity and Bridge guarded-publish proofs.
- [ ] Audit protected branches, unrelated remotes, capability leakage, and runtime readiness.
- [x] Add a process-lifetime single-instance relay lock.
- [x] Migrate relay SQLite v2 state to the durable v3 result-outbox schema.
- [x] Make start/reply terminal supervision non-blocking.
- [x] Reconcile active Guard jobs through `codex-job-status` after restart.
- [x] Persist validated terminal results before GitHub delivery.
- [x] Retry exact idempotent result comments and terminal labels until acknowledged.
- [x] Reconcile legacy terminal rows without replacement Guard work.
- [x] Add R-GH2.1/R-GH3.1 lock, restart, outbox, retry, and migration tests.
- [x] Re-run the complete Bridge security regression suite.
- [x] Upgrade Relay-only runtime and self-heal the legacy undelivered result.


## BRIDGE-COMPONENT-01 V3 — uninstalled engineering candidate

- [x] Reuse V2 localization; check bound remote and isolate exact base.
- [x] Specify partial evidence, strict identity/window and explicit offline mode.
- [x] Implement shared observer and doctor dispatch; isolate runtime checks.
- [x] Add focused fixtures/CLI isolation and owned-process API smoke.
- [x] Run applicable verification with individual command exit codes.
- [x] Prepare one substantive candidate; final commit/PR identity belongs in the delivery receipt.
- [ ] Owner review and acceptance; no merge, deployment or recovery authorization.

Historical proc_pidinfo cause: UNKNOWN. Live recovery/acceptance: NOT_RUN.


### COMPONENT-01 V3 actual verification (2026-09-09)

Commands run from the candidate repository; each result below is independently
captured, not inferred from the last command in a shell batch.

| Command | Exit | Evidence |
| --- | --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -W error::ResourceWarning tests/portable/test-process-observation.py -v` | 0 | 19 offline tests passed; separately selected system test skipped here |
| `BRIDGE_TEST_OWNED_PROCESS=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -W error::ResourceWarning tests/portable/test-process-observation.py OwnedMacReaderTest -v` | 0 | 1 macOS test: before/after BSD reads, executable and argv on its own harmless child |
| `/bin/zsh tests/portable/test-macos-installer.zsh` | 0 | Existing isolated fake-tool installation and explicit runtime doctor checks |
| `/bin/zsh tests/portable/test-plugin-package.zsh` | 0 | Existing packaging/mirror checks plus both new helpers |
| `PYTHONDONTWRITEBYTECODE=1 /bin/zsh tests/bridge/test-codex-mcp-guard.zsh` | 0 | 60 existing fake-downstream/source Guard tests |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/bridge/test-managed-repo.py` | 0 | 54 existing isolated managed-repo tests |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/relay/test-github-issue-relay.py` | 0 | 63 existing Relay fixture tests |
| `/bin/zsh -n plugins/chatgpt-codex-bridge/scripts/chatgpt-codex-bridge.zsh tests/portable/test-macos-installer.zsh tests/portable/test-plugin-package.zsh` | 0 | Parses service script only; extra argv do not parse extra scripts |
| `/bin/zsh -n tests/portable/test-macos-installer.zsh` | 0 | Installer test syntax checked independently |
| `/bin/zsh -n tests/portable/test-plugin-package.zsh` | 0 | Package test syntax checked independently |
| `PYTHONPYCACHEPREFIX=/private/tmp/bridge-component-01-pycache-01a08527 /usr/bin/python3 -m py_compile plugins/chatgpt-codex-bridge/scripts/process_observation.py plugins/chatgpt-codex-bridge/scripts/bridge-doctor.py tests/portable/test-process-observation.py` | 0 | Compilation; cache confined to task scratch directory |

The first focused test invocation exited 1 because it incorrectly required empty
stderr: Apple's Python launcher emitted a confstr temporary-directory warning.
The assertion now checks valid JSON stdout and absence of private fixture paths;
it does not discard stderr. The corrected tests passed. A first py_compile
invocation without the explicit scratch prefix exited 1 because the sandbox
blocked Apple's default cache directory. The same compilation passed with the
explicit task scratch prefix; no source defect was inferred from that failure.

The owned-child test exercised native bindings; the later changes added exception
metadata/argument bounds and a remaining-window guard, without changing those
bindings. It is not a live Relay identity acceptance or a historical reproduction.
No real service, default protected config/store or previous process was inspected.
The observer's complete identity/lsof/deadline behavior is fixture evidence;
full macOS CLI/lsof identity acceptance is NOT_RUN. Minimal future system check:
supply a synthetic four-layer contract for a task-owned launcher/script process; expect one complete identity result
with private metadata before its original 15-second deadline. Never substitute
real Relay recovery for this check. CI results are recorded separately on the PR.


Final source checks: `git diff --cached --check` exit 0;
`git fsck --full --strict` exit 0;
`/bin/zsh tests/portable/test-public-sanitization.zsh` exit 0.
A final targeted native-metadata regression also covers a positive short return
(sizeof(BsdInfo)-1), ensuring it remains READ_ERROR rather than accepted identity.


### PR #124 R1 — truncated XML plist (2026-09-09)

Reviewed parent: `b6bd7efe10a9ca52c6446b926cd9b1c4ae12fe66`.
Only the static configuration parsing boundary is in scope; observer unchanged.

- [x] Reproduce truncated XML through the existing StaticCliTest doctor CLI.
- [x] Catch ExpatError at config parsing, mark config INVALID and continue all
  remaining static checks; return nonzero with JSON stdout and no raw traceback
  or private local paths in stderr.
- [x] Verify StaticCliTest and changed Python compilation; inspect the three-file diff.

No Guard/managed-repo/Relay suite or process-system rerun. Historical cause stays
UNKNOWN; no live service, protected data, merge, deployment or recovery authority.


R1 command evidence (each exit captured independently):

| Command | Exit | Result |
| --- | --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -W error::ResourceWarning tests/portable/test-process-observation.py StaticCliTest.test_truncated_xml_reports_invalid_config_and_remaining_checks -v` | 1 | Before production fix: regression fails on empty stdout, reproducing R1 through actual doctor CLI |
| `PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -W error::ResourceWarning tests/portable/test-process-observation.py StaticCliTest -v` | 0 | After fix: all 6 static CLI tests pass, including structured INVALID, remaining checks, nonzero CLI status and stderr/path isolation |
| `PYTHONPYCACHEPREFIX=/private/tmp/bridge-component-01-pycache-01a08527 /usr/bin/python3 -m py_compile plugins/chatgpt-codex-bridge/scripts/bridge-doctor.py tests/portable/test-process-observation.py` | 0 | Both changed Python files compile |

The failing-input CLI exits 1 as required; the post-fix regression runner exits 0.
All earlier suite/system evidence above remains historical to its recorded run,
not a claim of full reruns on this R1 candidate. R1 does not change observation,
protected inputs, State or authorization. Final candidate identity is in the
separate R1 delivery receipt and the existing PR #124.

## COMPONENT-02 — uninstalled candidate

- [x] Verify exact predecessor and isolated candidate; read specs and public schema.
- [x] Specify trusted config, v4 binding, supervision and controlled protocol subset.
- [x] Implement config/admission and explicit v3 fixture migration.
- [x] Implement managed worker protocol, bounded evidence and serialized continuation.
- [x] Implement query/review and versioned outbox through actual Relay.
- [x] Run two-project isolated integration and relevant regressions; document results.
- [x] Prepare substantive candidate; exact commit/push/PR is in the delivery receipt.
- [ ] Independent owner review; merge/install/recovery remain unauthorized.

Verification: [COMPONENT-02 isolated evidence](../../validation/component-02.md).
Usage and compatibility: [operator runbook](../../runbooks/relay-component-02.md).

### PR125-R1/R2 — bounded review correction

- [x] Reproduce AWS leakage and artifact rejection losing actual exit 7 through
  Component02Test / isolated fake App Server / final fake GitHub projection.
- [x] Correct shared helper path/content filtering and independent command evidence;
  synchronize package mirror without changing public schema or artifact limits.
- [x] Run affected integration/security checks, mirror, changed-file compilation,
  package and diff checks; record actual commands/exits and unchanged State scope.

Correction evidence: [PR125-R1/R2](../../validation/component-02-pr125-r1-r2.md).
