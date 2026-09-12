# ADR 0005: Package the Portable Bridge as a Plugin

Status: Accepted
Date: 2026-08-05
Amended: 2026-08-21

## Context

The proven personal bridge is tied to one username, profile, workspace, service label, and LaunchAgent plist. OpenAI now ships an official Tunnel MCP plugin and native runtime commands, but those manage Tunnel operations and detached/tmux runtimes; they do not package this project's ChatGPT-compatible Codex Guard or macOS login-start requirement.

## Decision

Create a self-contained `chatgpt-codex-bridge` plugin in the repository and expose it through the repo marketplace. The plugin contains:

- a concise controller/setup skill;
- progressive controller references and Codex UI metadata;
- a portable `workspace-new-project` Skill staged privately by the installer;
- a standalone operator README;
- the reviewed Guard;
- a parameterized macOS current-user service installer;
- LaunchAgent and runtime-wrapper templates;
- doctor, status, stop, restart, and uninstall entrypoints.

The plugin MUST invoke the official `tunnel-client` and Codex MCP server. It MUST NOT copy Tunnel protocol/runtime ownership from OpenAI's plugin. Device-specific profile identity, Tunnel ID, runtime key references, and ChatGPT connector authorization remain external per-device setup.

The personal install preset remains `danger-full-access` plus `never`. A separate `workspace-safe` install preset uses `workspace-write` plus `on-request`. The selected preset is fixed locally and is never a public MCP argument.

The plugin deliberately MUST NOT contain `.mcp.json`. ChatGPT reaches the Guard
through the separately authorized Secure MCP Tunnel. Registering the Guard as a
Codex-local MCP server would create a recursive Codex-to-Guard-to-Codex control
path and would not authorize ChatGPT Developer Mode.

## Consequences

- Another macOS user can install from the Git marketplace and render paths for their account.
- Every device still needs its own Tunnel/profile, Codex login, running local service, and ChatGPT connector attachment.
- The first distribution target is macOS. Windows Task Scheduler and Linux systemd are later adapters.
- The existing personal service remains valid while the portable installer is tested; migration is not required for T-406.
