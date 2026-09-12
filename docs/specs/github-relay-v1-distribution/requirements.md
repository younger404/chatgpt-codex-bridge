# GitHub Relay V1 distribution requirements

## Scope

Provide a standalone, fresh-only macOS managed GitHub Relay installer in the
plugin. The generic Tunnel installer MUST retain
`EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY`. Existing installations, migration,
recovery, releases and real-service acceptance are outside this change.

## Requirements and acceptance

1. Given an operator registry and a fresh HOME-derived Bridge installation,
   the dedicated installer MUST accept only workspace, Codex executable,
   control repository, allowed author, repeated enabled aliases and no-start.
   Unknown options, duplicate aliases and unregistered aliases MUST fail before
   installation writes. Repository paths and branch prefixes come from Registry.
2. Existing config, job store/key, journal, Guard/Relay runtime or service plist
   MUST cause `FRESH_INSTALL_REQUIRED` before writes. Only the private operator
   registry may pre-exist in the Bridge state directory; it MUST remain intact.
   Unsafe owners, modes, symlinks and workspace/store intersections MUST fail
   closed. No existing state is adopted, repaired or removed.
3. Generated config MUST be canonical, regular, private 0600 and atomic. Policy
   MUST be `managed-repo / workspace-write / never`. Config MUST include current
   Guard, Relay and doctor fields, without credentials or prefix overrides.
   The internally selected `managed-jobs-v1` store MUST be a canonical 0700
   direct state-root child, with a new exclusive 0600 single-link 32-byte random
   capability key. No key bytes may be logged or copied elsewhere.
4. Actual `Registry.load(verify_live=True)`, Guard store validator and Relay
   `OperatorConfig.load()` MUST accept the resulting installation. Prefixes
   MUST remain registry-derived. Offline database construction MUST yield v4
   and the expected installation/control-repository scope.
5. Packaged Relay Python and runner MUST match source bytes. Staged Guard,
   Relay, shared helpers, explicit-store validator and bootstrap skill MUST
   match package bytes, with no symlinks. The only generated LaunchAgent MUST
   be the fixed GitHub Relay service with installation HOME and bounded PATH.
6. `--no-start` MUST make no GitHub calls, start no service or model, and create
   no Relay journal. Normal activation MUST retain the required sandbox policy
   support check and fail closed without GitHub authentication. Configuration
   alone MUST NOT be represented as runtime or policy-support acceptance.
   No-start MUST report POLICY_SUPPORT=NOT_PROBED, PLIST_DEFAULT_DISABLED=true,
   LAUNCHD_STATE=NOT_PROBED and SERVICE_STARTED_BY_INSTALLER=false. It MUST NOT
   infer effective launchd state from the plist; later activation requires review.
7. A synthetic offline clean-HOME regression MUST cover the positive install,
   metadata/identity/config contracts, repeat-install preservation, unknown
   arguments and existing-state rejection. Tests MUST NOT depend on business
   aliases, control Issues, real services, credentials or real model execution.
8. An exact tracked-tree export without Git/private state MUST pass package,
   sanitizer and fresh-HOME install checks. The sanitizer MUST support this
   clean export as well as its existing tracked-worktree mode.

## Failure and evidence

Preflight rejects before install writes. Failures after fresh creation retain
the partial installation for separately reviewed recovery; automatic retries
MUST NOT adopt it. Output contains stable categories, never capabilities.
Candidate tests and export acceptance do not authorize merge or deployment.


## Activation failure amendment

The installer MUST publish the Relay plist with Disabled=true in both modes.
Normal activation MUST explicitly enable then bootstrap. If either activation
call fails after an enable attempt, the installer MUST best-effort disable the
same fixed service target before returning failure. A disable failure MUST be
reported without claiming effective launchd state. Partial runtime, config and
store MUST remain intact and the next fresh install MUST still reject them.
Synthetic regression MUST cover enable success/bootstrap failure/disable called,
with no real service, model or GitHub work; enable failure is also covered.
