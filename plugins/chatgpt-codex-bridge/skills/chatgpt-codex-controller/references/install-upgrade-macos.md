# macOS Install, Upgrade, and Rollback

## GitHub Relay V1: fresh managed installation

Register aliases with `plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh`
(from the repository root), then run
`plugins/chatgpt-codex-bridge/scripts/install-github-relay-v1-macos.zsh` with
`--workspace`, `--codex-bin`,
`--control-repository`, `--allowed-author` and one or more `--enable-alias`.
Secure Tunnel is not required. Existing Bridge state is rejected with
`FRESH_INSTALL_REQUIRED`; this entry cannot upgrade or recover it. The generic
installer retains `EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY` for managed mode.

Default mode runs the fixed workspace-write/never Codex support probe and checks
GitHub authentication before installation writes, then enables and bootstraps
the Relay service (`GITHUB_RELAY_V1_STARTED POLICY_SUPPORT=PASS`). This is the
normal new-installation route. `--no-start` invokes neither
Codex nor GitHub/launchctl, creates no journal, reports POLICY_SUPPORT=NOT_PROBED,
PLIST_DEFAULT_DISABLED=true, LAUNCHD_STATE=NOT_PROBED and
SERVICE_STARTED_BY_INSTALLER=false. The plist default does not prove launchd
override state. `--no-start` is a terminal offline-evaluation state, not step
one of two: a second install cannot adopt this state, so there is no supported
rerun-to-activate path; evaluate first, then run Route A in a fresh state.

The plist defaults to Disabled=true in both modes. Default activation explicitly
enables/bootstraps; failure triggers best-effort disable of the same label. A
disable failure is reported without claiming effective disabled state. Partial
installation files remain for reviewed recovery.

## Secure Tunnel: legacy installation and upgrades

Install the plugin with the official `tunnel-client`, a device-specific Tunnel
profile, a workspace path, and the desired preset.

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-macos.zsh \
  --profile <device-profile> \
  --workspace <absolute-workspace> \
  --preset personal-full-control
```

Then run `plugins/chatgpt-codex-bridge/scripts/doctor.zsh --runtime` and refresh the ChatGPT Secure Tunnel app for the
device. A plugin install does not automatically create or authorize the ChatGPT
app attachment.

For upgrades, install the newer Git ref, rerun `install-macos.zsh` with the same
external profile/workspace, restart, run doctor again, and refresh the app.
Rollback by reinstalling the prior known-good ref and repeating the same
restart/doctor/app refresh sequence.

Version 0.6.1 intentionally starts a new context-bound `jobs-v3` store.
Finish older jobs before upgrading. Old cards and capabilities are not accepted
by the new Guard. The public v0.6.0 release is withdrawn; finish old work before
upgrading, or use the private authoritative archive for forensic recovery only.
