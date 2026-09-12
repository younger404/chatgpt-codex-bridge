# GitHub Relay V1 distribution tasks

- [x] Confirm exact baseline and reproduce generic managed rejection/missing package entry.
- [x] Specify fresh installation, privacy and transport separation; record ADR.
- [x] Resolve policy-probe/no-start activation contract: no-start NOT_PROBED,
      plist default Disabled=true; launchd state NOT_PROBED; default mode probes before installation writes.
- [x] Implement dedicated fresh-only installer and exact packaged Relay mirrors.
- [x] Add clean-HOME and package regression; repair contradictory install docs.
- [x] Run required portable, store-selector, Relay and managed-repo checks.

Delivery acceptance (record exact identities and outcomes in the candidate receipt):
export the committed candidate without Git/private state; run package, sanitizer,
private denylist and fresh-HOME installation against that export; create one
unmerged PR and stop for distribution review.

Baseline RED: generic managed install exits nonzero with
`EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY` without HOME mutation; packaged Relay
and dedicated V1 installer are absent. No current runtime was invoked.


Candidate validation: clean-HOME regression, package, sanitizer and legacy macOS
installer passed. Store selector ran 9 tests with 2 environment-dependent skips
(real-Codex metadata and OS-disallowed owner change); COMPONENT-02 13, Relay 63
and managed-repo 56 tests passed. No live operational gates were repeated.
No-start reports policy support and launchd state NOT_PROBED with plist default
Disabled=true. The synthetic probe regression covers supported policy, failed execution and outside writes.


PR #127 activation amendment:
- [x] Reproduce missing disable compensation with synthetic activation failure.
- [x] Keep the plist default inert and compensate activation failure without deleting partial state.
- [x] Correct no-start claims in output, docs and assertions without adding probes.
- [x] Validate focused install, package, sanitizer and legacy installer.
      Exact export acceptance is recorded in the amended candidate receipt.


Amendment RED: the original installer returned failure after synthetic bootstrap
failure without calling disable. GREEN: bootstrap failure, enable failure and
failed disable compensation are exercised without real activation. Partial files
remain unchanged on a rejected second install. No-start output and subprocess
admission distinguish plist defaults from unprobed launchd state.

Amendment syntax/mirror/diff checks passed. Source Relay/Guard, their packaged
mirrors, generic installers and relevant Relay/managed test inputs are unchanged;
the earlier 13/63/56 passing test evidence is retained without redundant reruns.
