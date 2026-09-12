# GitHub Relay V1 distribution design

The public `scripts/install-github-relay-v1-macos.zsh` entry delegates closed
argument parsing and private filesystem creation to one packaged Python helper.
The existing generic installer remains unchanged. See ADR 0022.

The helper validates all inputs, the HOME-derived destinations and the actual
operator Registry before mutations. A fresh state root may contain only the
registry. Runtime and Relay LaunchAgent targets must be absent. Canonical
owner-controlled ancestors and exclusive creation prevent adoption of existing
state. Config publication is atomic and cannot overwrite a pre-existing file.
No cleanup removes another invocation's artifacts; a partial install fails
closed on the next invocation.

Stage Guard/helpers under the fixed Bridge runtime root and the exact packaged
Relay/runner plus shared helpers under `github-relay`. Stage the existing
bootstrap skill. Generate the fixed Relay LaunchAgent using the reviewed source
service label, restart interval, log paths and runner; explicitly bind HOME/PATH.
No Tunnel assets or service are installed by this entry.

Use the existing managed policy and validators; do not add a schema, migration
framework or second Relay implementation. Configuration-only mode is distinct
from successful runtime activation. In no-start mode, do not invoke Codex;
report `POLICY_SUPPORT=NOT_PROBED`, `PLIST_DEFAULT_DISABLED=true`,
`LAUNCHD_STATE=NOT_PROBED` and `SERVICE_STARTED_BY_INSTALLER=false`. A plist
default cannot prove launchd override state. This is not activation-ready.
Default start mode first runs the existing equivalent `codex exec` workspace
marker/outside-marker probe with workspace-write and never, then checks GitHub
authentication, before creating installation files. Later activation of a
no-start installation requires separate review; rerunning this fresh installer
must reject it. The operator explicitly selected this separation.

Tests use synthetic local repositories with GitHub-form origin identities,
packaged registration, temporary HOME/workspace and a fake Codex executable.
Actual config loading and offline database construction exercise the product
contract. Installed Guard initialize/tools-list is allowed only with no model
execution. Directory counts, subprocess calls and immutable input snapshots
support no-start and repeat-install assertions.

Package checks pin Relay mirrors in addition to existing mirrors. Sanitization
keeps tracked-file behavior for Git worktrees and scans all export files when
there is no repository metadata, enabling exact `git archive` acceptance.


Activation publishes an inert plist default (Disabled=true), then explicitly
calls enable/bootstrap. A failure from either call triggers best-effort disable
of that same service target. If compensation also fails, report it and retain
the original activation failure; do not report the service disabled. Never
remove or repair the partial files, and never retry fresh installation over them.
