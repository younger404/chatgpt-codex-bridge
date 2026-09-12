# ChatGPT Codex Bridge

[中文说明](README.zh-CN.md) ·
[GitHub 发布脱敏清单](docs/GITHUB_RELEASE_CHECKLIST.zh-CN.md)

Run one ChatGPT web conversation as the controller of local Codex work on your
own Mac, through **GitHub Relay V1**: a local, outbound-only relay that turns
labeled Issues in *your own private control repository* into guarded,
reviewable Codex jobs. A legacy OpenAI Secure MCP Tunnel transport remains
available separately; it is not a GitHub Relay dependency.

Derived from [larryppgg/chatgpt-codex-bridge](https://github.com/larryppgg/chatgpt-codex-bridge)
(MIT, Copyright (c) 2026 larryppgg). This distribution adds the GitHub Relay
multi-project management capability on top of the upstream bridge. It is a
community package, not an OpenAI product, and it grants no ChatGPT, Codex,
GitHub, Tunnel, or device credentials.

## What GitHub Relay V1 does

```text
ChatGPT conversation -> labeled Issue in your private control repo
  -> local GitHub Relay (outbound poll only) -> local Guard -> Codex
  -> sanitized result comment back on the same Issue
```

- You register repositories yourself with the packaged CLI; the relay never
  accepts a path, branch, remote, or repository from a web request.
- Managed work runs in a separate Git worktree with fixed
  `workspace-write + never` policy; publishing produces a generated branch,
  never a merge or deployment.
- Every request is one strict JSON object on an open `bridge-job` Issue
  authored by an allowed account; replies and reviews bind the exact recorded
  evidence, not a conversation summary.

## Quick Start (GitHub Relay V1)

> **Candidate note:** release tag `v1.0.0-beta.1` and the public repository
> `younger404/chatgpt-codex-bridge` are **proposed**, not yet created. The
> commands below become executable only after the beta is actually published;
> re-check availability at that time.

Prerequisites: macOS; Git; Python 3; GitHub CLI (`gh`) authenticated for your
own account; an installed, working Codex. Existing receipts tested Codex
`0.153.4` and `gh` `2.89.0`; that records what was tested, not a compatibility
promise for other versions.

### 0. Get the source and pick your working root

Primary route — clone the tagged release (once it exists) and run everything
from the **repository root**; every `plugins/...` command below assumes that
working directory:

```zsh
git clone --branch v1.0.0-beta.1 --depth 1 \
  https://github.com/younger404/chatgpt-codex-bridge.git
cd chatgpt-codex-bridge
```

Marketplace route — `codex plugin marketplace add younger404/chatgpt-codex-bridge
--ref v1.0.0-beta.1` then `codex plugin add chatgpt-codex-bridge@chatgpt-codex-bridge`
installs the same package, but your working root is then the **installed plugin
root**, where the same scripts live directly under `scripts/` (not under
`plugins/chatgpt-codex-bridge/`). Do not mix the two path layouts.

### 1. Prepare your own control repository and sample

Create your own empty **private control repository** on GitHub (for example
`you/bridge-control-private`). You must be able to read and create labeled
Issues in it. This open-source repository never acts as a control repository.

Register and verify a sample repository (use your own synthetic sample first;
it needs a matching GitHub `origin` and a protected base branch). From the
repository root:

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh register \
  --alias sample-repo \
  --repo-path /absolute/canonical/repository \
  --repository-full-name you/sample-repo \
  --base-remote origin \
  --base-branch main
/bin/zsh plugins/chatgpt-codex-bridge/scripts/managed-repos.zsh verify sample-repo
```

Registration alone does not enable the GitHub transport.

### 2. Route A — normal new installation (default mode)

Choose this when you actually want the Relay running. The installer is
**fresh-only**: any existing Bridge config, store, key, journal, runtime, or
service file makes it stop with `FRESH_INSTALL_REQUIRED` (it never adopts or
repairs existing state).

Default mode has real side effects — read them before running:

- it runs the required Codex `workspace-write + never` support probe, which
  invokes Codex and may execute a model turn;
- it checks your GitHub CLI authentication;
- it writes a fresh config, job store, capability key, and LaunchAgent plist;
- it explicitly enables and bootstraps the Relay service (the plist itself
  always defaults to `Disabled=true`; activation failure triggers best-effort
  disable of the same label).

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-github-relay-v1-macos.zsh \
  --workspace /absolute/bridge-workspace \
  --codex-bin /absolute/codex \
  --control-repository you/bridge-control-private \
  --allowed-author your-github-login \
  --enable-alias sample-repo
```

Expected success output: `GITHUB_RELAY_V1_STARTED POLICY_SUPPORT=PASS`.

Then perform the read-only readiness checks in
[docs/runbooks/verify-installation.md](docs/runbooks/verify-installation.md):
the service label/argv, the generated config, the store validator, service
state, and journal state. They are read-only; none of them prints
`BRIDGE_V1_READY`.

### 3. Route B — offline evaluation only (`--no-start`)

Choose this only to inspect what the installer would generate, without any
Codex, GitHub, or launchctl calls and without creating a journal:

```zsh
/bin/zsh plugins/chatgpt-codex-bridge/scripts/install-github-relay-v1-macos.zsh \
  --workspace /absolute/bridge-workspace \
  --codex-bin /absolute/codex \
  --control-repository you/bridge-control-private \
  --allowed-author your-github-login \
  --enable-alias sample-repo \
  --no-start
```

Expected output: `GITHUB_RELAY_V1_CONFIGURED POLICY_SUPPORT=NOT_PROBED
PLIST_DEFAULT_DISABLED=true LAUNCHD_STATE=NOT_PROBED
SERVICE_STARTED_BY_INSTALLER=false`.

**`--no-start` is an endpoint, not step one of two.** It leaves a configured
but unverified and unstarted installation; the fresh-only installer will
reject a second run over that state (`FRESH_INSTALL_REQUIRED`), so there is no
supported "rerun without `--no-start` to activate" path. To actually run the
Relay after evaluating, remove the evaluated state deliberately (or use a
different fresh HOME/workspace) and follow Route A from the beginning.

### 4. Drive jobs from ChatGPT

Use the copyable controller block and the capability precheck in
[docs/runbooks/github-relay-v1-controller.md](docs/runbooks/github-relay-v1-controller.md).
A protocol request is the **body** of a new Issue labeled `bridge-job`; the
Relay writes results back as comments on that Issue. An ordinary comment is
not a protocol request.

## ChatGPT-side capability is a separate requirement

Installing this source does **not** grant your ChatGPT/GitHub/Codex accounts
any capability, and reading GitHub source is **not** the same as creating
labeled control Issues. The web controller path works only if your own session
actually offers the GitHub write tools (create Issues with labels, read Issues
and comments) for your private control repository. OpenAI documents a
read-only GitHub app entry, while the GitHub plugin page lists separate write
capability; what matters is the tools visible in *your* conversation. Do not
assume plan names, a connected GitHub account, or an installed Skill imply
write access. If your session is read-only, web-driven delivery is not
available; do not lower product safety boundaries to work around it.

## Legacy: Secure MCP Tunnel

The upstream Secure MCP Tunnel transport (`personal-full-control` /
`workspace-safe` presets, `codex-start` / `codex-wait`, Apps-card recovery)
remains implemented and regression-tested. It is documented as a legacy
transport in [docs/runbooks/secure-mcp-tunnel.md](docs/runbooks/secure-mcp-tunnel.md)
and [docs/runbooks/portable-plugin.md](docs/runbooks/portable-plugin.md), and
is not required for GitHub Relay V1. Its `install-macos.zsh` intentionally
rejects managed-repo stores with
`EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY`; Tunnel stop/uninstall commands
apply to the Tunnel service only, not to a Relay installation.

## Status, privacy, and known limitations

- A registry change revokes old managed capabilities; `registered` is not
  `enabled`; do not change scopes silently during an active task.
- A new relay journal must not point at a control repository with historical
  consumable requests; old journals/keys are not migrated by default.
- `completed`, result delivered, review accepted, publish, merge, and deploy
  are different states. `checksState=WITHHELD` is not "tests PASS"; recorded
  fixed-check events are historical evidence, not an exit code you ran.
- "Same worktree/thread" holds only on the accepted paths; no exactly-once
  claim is made for arbitrary network failures, and no multi-tenant isolation
  is claimed.
- Your control repository stores task requests and sanitized code diffs. Treat
  it under your project's data policy; this software does not claim data never
  leaves your machine.
- Capability keys, registry, journal, and tokens stay outside Git. Never paste
  them into public Issues; configuration logs expose only sanitized metadata.
- Isolated test HOMEs under `/tmp`/`$TMPDIR` affect the outside-write marker
  criterion; that is reproduction guidance, not a sandbox setting change.
- Token projection, `--insecure-storage`, and direct `hosts.yml` writes are
  not normal installation steps.
- macOS LaunchAgent only; Windows/Linux service packaging is not implemented.
- This project does not bypass plan or account limits and is not an OpenAI
  product.

## Documentation map

- Install/upgrade/rollback SOP:
  [skills reference](plugins/chatgpt-codex-bridge/skills/chatgpt-codex-controller/references/install-upgrade-macos.md)
- Web controller SOP (capability precheck, instruction block):
  [docs/runbooks/github-relay-v1-controller.md](docs/runbooks/github-relay-v1-controller.md)
- Verification SOP: [docs/runbooks/verify-installation.md](docs/runbooks/verify-installation.md)
- Managed repositories: [docs/runbooks/managed-existing-repo.md](docs/runbooks/managed-existing-repo.md)
- Relay protocol: [docs/runbooks/relay-component-02.md](docs/runbooks/relay-component-02.md)
- Synthetic job examples: [examples/](examples/README.md)
- Security policy: [SECURITY.md](SECURITY.md) · Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Specs under `docs/specs/`; decisions under `docs/adr/`.

## Verification

```zsh
/bin/zsh tests/portable/test-plugin-package.zsh
/bin/zsh tests/portable/test-public-sanitization.zsh
/bin/zsh tests/portable/test-github-relay-v1-install.zsh
/bin/zsh tests/portable/test-readme-demo.zsh
/bin/zsh tests/portable/test-macos-installer.zsh
```

## License

MIT. See [LICENSE](LICENSE). Upstream Copyright (c) 2026 larryppgg;
maintained in this distribution by younger404. Third-party components keep
their own notices and licenses.
