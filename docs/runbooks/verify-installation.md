# Verification SOP (static first, no new subsystems)

This SOP reuses the existing static doctor, the operator store validator, and
the portable suites. It adds no new verification entry. Static checks prove
source/config shape only; they never prove service readiness.

## 1. Static shape checks (offline)

From the repository root, against a synthetic or exported config — never a
real protected store:

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/doctor.zsh --static \
  --config /absolute/synthetic-config.plist --source-root /absolute/candidate
```

Expected: aggregated field/file checks; success is `STATIC_CHECKS_PASSED` with
runtime `NOT_RUN` and live identity `NOT_COLLECTED`. The output never prints
`BRIDGE_V1_READY`; live readiness is explicitly `NOT_RUN` at this stage.

Validate an operator store's shape without adopting it, using the packaged
validator (`guard-store-config.py`) exactly as documented in
`docs/runbooks/managed-existing-repo.md`; it reads the designated store only
and performs no migration.

## 2. Portable suites (offline)

```zsh
/bin/zsh tests/portable/test-plugin-package.zsh
/bin/zsh tests/portable/test-public-sanitization.zsh
/bin/zsh tests/portable/test-github-relay-v1-install.zsh
/bin/zsh tests/portable/test-readme-demo.zsh
/bin/zsh tests/portable/test-macos-installer.zsh
/bin/zsh tests/portable/test-public-examples.zsh
```

These cover package/source byte identity, privacy gating, a synthetic
clean-HOME `--no-start` install, README command wiring, the legacy installer,
and the synthetic job examples. They use no real service, model, credential,
or GitHub call.

## 3. Read-only readiness after a Route A (default) install

After the default installer prints `GITHUB_RELAY_V1_STARTED POLICY_SUPPORT=PASS`,
these read-only checks confirm *this* installation's identity and state. They
start nothing and probe nothing.

Service label, arguments, and environment (exact fixed label):

```zsh
/bin/launchctl print "gui/$UID/com.chatgpt-codex-bridge.github-relay"
/usr/bin/plutil -p "$HOME/Library/LaunchAgents/com.chatgpt-codex-bridge.github-relay.plist"
```

Generated config (contains no credentials by design) and the installed store
validator:

```zsh
/usr/bin/plutil -p "$HOME/Library/Application Support/chatgpt-codex-bridge/config.plist"
/usr/bin/python3 -I "$HOME/.local/share/chatgpt-codex-bridge/guard-store-config.py" \
  validate "$HOME/Library/Application Support/chatgpt-codex-bridge/config.plist"
```

Journal state (genuine read-only connection, with locking honored). The
journal is a live mutable database written by the Relay with
`journal_mode=DELETE`; do **not** open it with `immutable=1` (that parameter
declares the file never changes and skips locking/change detection, which can
return stale pages — such as a pre-commit state showing no active jobs — on a
live file), and do not use `nolock` or any lock-bypassing parameter:

```zsh
/usr/bin/sqlite3 -readonly -cmd ".timeout 5000" \
  "$HOME/Library/Application Support/chatgpt-codex-bridge/github-relay.sqlite3" \
  "SELECT status, COUNT(*) FROM relay_jobs GROUP BY status;"
```

Interpreting the result — all of these rules apply:

- Interpret status counts only when the command exits successfully, the output
  parses, and the database identity is this installation's journal.
- `database is locked` / BUSY, a missing file, or a schema/permission error
  means **state not obtained** — never treat it as "zero active jobs".
- Active jobs are exactly the rows with status `queued` or `running`;
  `completed`, `failed`, and `interrupted` are terminal.
- The output is one point-in-time observation; it does not pause Relay
  admission, and querying plus stopping is not an atomic transaction.

## 4. Targeted stop (only with proven identity and no active jobs)

Stop only after all of the following hold: the `launchctl print` output and
plist above name the same fixed label and this installation's
`run-github-relay.zsh` path; you have stopped submitting new tasks to this
Relay; and the journal read in section 3 **succeeded** and shows no `queued`
or `running` rows. If the journal read fails, is locked, or cannot be
confirmed, do not use this no-active-jobs branch — wait and re-check instead
of stopping on unconfirmed state. Then:

```zsh
/bin/launchctl bootout "gui/$UID/com.chatgpt-codex-bridge.github-relay"
/bin/launchctl disable "gui/$UID/com.chatgpt-codex-bridge.github-relay"
```

`bootout` stops and unloads this Relay supervisor; `disable` keeps it from
starting again until you explicitly re-enable it. Stopping the Relay
supervisor does **not** automatically revoke Guard workers already in flight,
does not delete the journal, and does not uninstall anything. Restarting is an
explicit later operator action (`enable` + `bootstrap` against the same
plist). These commands operate the GitHub Relay service only; the legacy
Tunnel `stop`/`uninstall` commands in `portable-plugin.md` are not Relay
operations.

## 5. What static verification does NOT cover

- launchd state, service liveness, polling health: `NOT_RUN` by static checks;
  only the read-only inspections in section 3 observe them.
- Codex policy-support probing: the default (non-`--no-start`) installer runs
  it before writes; do not infer it from configuration output.
- GitHub authentication and the web session's actual tool capability: checked
  by the operator at activation time; see the controller SOP precheck.

Reproduce-note: isolated test HOMEs under `/tmp`/`$TMPDIR` affect the
outside-write marker criterion used by the install tests. That is reproduction
guidance only; do not change sandbox settings.
