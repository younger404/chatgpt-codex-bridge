# ADR 0004: Run the Tunnel as a User LaunchAgent

Status: Accepted
Date: 2026-08-05

## Context

The working Tunnel was launched from a temporary foreground terminal. Its last log entry showed a recovered operational poller, after which the process disappeared without a Guard or Tunnel fatal error. No matching user LaunchAgent existed, so the ChatGPT connector became unavailable whenever that terminal-owned process ended.

## Decision

Reuse macOS `launchd` through a user LaunchAgent. Run the existing absolute `tunnel-client` binary as `run --profile example-profile`, with `RunAtLoad=true`, `KeepAlive=true`, stable loopback health state, and user-library log paths. Keep all Tunnel identity and authentication material in the existing external profile and credential file; the plist contains no secrets or copied identifiers.

Use the service's Application Support directory as `WorkingDirectory`. Do not use the source repository under `~/Documents`; an uninteractive LaunchAgent was observed blocking in `getcwd` on that protected path before it could open a health listener.

Stage the reviewed Guard source into `~/.local/share/chatgpt-codex-bridge/` and override the profile's MCP command at LaunchAgent invocation time. The no-space path is intentional: a live Application Support attempt was tokenized into an invalid Python script argument and exited with status 2. Use `/Users/example-user/codex-workspace` as the unattended starting workspace. This keeps the existing profile, Tunnel identity, and credential reference untouched while avoiding the TCC block observed when Python tried to open the Guard under `~/Documents`.

## Consequences

- The Tunnel starts when the user logs in and is relaunched after an unexpected exit.
- No Terminal window, third-party daemon manager, wrapper relay, or second polling loop is required.
- Explicit new-project tasks start from the existing `codex-workspace` container, so the global `workspace-new-project` route can create the named child project without touching the bridge source repository.
- Temporary revocation remains an exact `launchctl bootout`; reinstall/bootstrap restores service immediately.
- A malformed profile can cause repeated launch attempts, so the installer validates the plist and profile first and launchd throttles restarts.

## Rejected alternatives

- Shell `nohup` or a persistent terminal: rejected because ownership dies with session cleanup and has no login lifecycle.
- Cron or periodic polling: rejected because this is a continuous process, not a scheduled task.
- Homebrew services or another supervisor: rejected because native LaunchAgent semantics are already sufficient and reduce dependencies.
