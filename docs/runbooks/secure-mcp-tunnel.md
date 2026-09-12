# Secure MCP Tunnel Runbook

> Legacy transport runbook. GitHub Relay V1 is the primary path of the current
> distribution and does not require Tunnel. The pinned dependency records below
> are historical provenance for the Tunnel hotfix, not a Relay requirement.

## managed-repo-v0.1.1 compatibility addendum (historical)

The approved Tunnel dependency for this hotfix is official
`openai/tunnel-client` release `v0.0.11`. Its Darwin arm64 archive SHA-256 is
`3685443b057614ff932d2d477dab94be2082e60bcf4e8b4e378bebc89121b714`
and its exact entries are:

```text
tunnel-client
cloudflared
cloudflared-manifest.json
LICENSE
```

The v0.1.1 verifier also retains legacy single-file archive support. It rejects
every fifth or unsafe entry, duplicate names, symlinks, checksum mismatch, and
payload mismatch. It compares the archive's `tunnel-client` bytes with the
candidate and never executes `cloudflared`. Only after artifact validation does
it run read-only `file`, `codesign`, `xattr`, and `spctl` diagnostics. A
SIGKILL plus a rejecting execution assessment is reported as
`overall_status=RUNTIME_BLOCKED` while preserving
`artifact_provenance_status=PASS`.

Do not remove quarantine, add `spctl` policy exceptions, force-sign an official
binary, or use an interactive operating-system override. The Bridge exposes no
Gatekeeper bypass.

The only approved fallback is a build from
`https://github.com/openai/tunnel-client`, release `v0.0.11`, commit
`8d55683eeef80bc5e360d95abf4692454fafc615`. The checkout must be clean, the
tag must resolve to that exact commit, and `pkg/version/VERSION` must be
`0.0.11`:

```zsh
/bin/zsh scripts/bridge/build-verified-tunnel-client.zsh \
  --source /absolute/path/to/clean/openai-tunnel-client \
  --output /absolute/user-owned/path/tunnel-client \
  --expected-version 0.0.11 \
  --expected-commit 8d55683eeef80bc5e360d95abf4692454fafc615
```

The script alone owns `go mod verify` and the fixed
`go build -trimpath -o <temporary-output> ./cmd/client` command. It requires a
Mach-O arm64 result, version 0.0.11, working `help quickstart`, no quarantine,
and writes `<output>.provenance.json`. Review that receipt and the capability
check before passing the binary to the existing installer with
`--tunnel-client-bin`. Do not start, initialize, or resume a Tunnel as part of
this compatibility hotfix.

The addendum controls v0.1.1. Where the archival proof text below refers to a
single-entry archive, read it as the legacy-only shape; it does not override the
exact official v0.0.11 four-file contract above.

Status: Superseded for active operation by T-115/T-402 on 2026-08-03

> Historical isolated-proof setup guide. Its sterile-account boundary and
> interactive environment-variable key flow are no longer the active personal
> operator path. Use [Codex MCP Guard Runbook](codex-mcp-guard.md); the active
> profile keeps a restricted Tunnel Read + Use key in a mode-`600` file outside
> the repository so restarts do not depend on one shell session.

## Scope and stop conditions

This runbook installs and operates OpenAI's official `tunnel-client` for the
isolated ChatGPT-to-Codex feasibility proof. It does not authorize a Codex tool
call, an operating-system account change, or use against a real repository.
Stop on a checksum mismatch, unexpected archive entry, non-parseable version,
failed `doctor`, missing approval surface, or uncertain isolation boundary.

The installation and verifier below are macOS arm64 only. They use the system
`shasum`, `unzip`, `cmp`, and BSD userland. A different operating system or
architecture needs a separately tested release asset and procedure.

## Authorization and least privilege

Before download, the operator MUST approve the exact stable release and the
absolute, user-owned install destination. Do not use `sudo` or install into a
system-owned directory. The runtime API key MUST have only Tunnels Read + Use;
the setup operator needs Tunnels Manage only while creating or associating the
tunnel. Never place the key, tunnel ID, organization ID, workspace ID, or
generated profile in this repository, logs, reports, or project memory.

## Select the current stable official release

Use only the `openai/tunnel-client` GitHub release API and release downloads.
Do not hard-code a versioned asset URL. In a dedicated directory returned by
`mktemp -d`, fetch `releases/latest`, verify `draft=false` and
`prerelease=false`, and require exactly one asset named like
`tunnel-client-v<semver>-darwin-arm64.zip` plus exactly one
`SHA256SUMS.txt`. Abort if any condition is ambiguous.

The following outline intentionally leaves the approved destination explicit:

```zsh
set -euo pipefail

readonly TUNNEL_RELEASE_API="https://api.github.com/repos/openai/tunnel-client/releases/latest"
readonly TUNNEL_INSTALL_WORK="$(mktemp -d /tmp/cq-tunnel-install.XXXXXX)"
readonly TUNNEL_CLIENT_DEST="/Users/isolated-user/.local/bin/tunnel-client"

[[ "$(uname -m)" == "arm64" ]]
[[ "${TUNNEL_CLIENT_DEST}" == /* ]]
[[ "${TUNNEL_CLIENT_DEST:t}" == "tunnel-client" ]]
[[ -d "${TUNNEL_CLIENT_DEST:h}" && ! -L "${TUNNEL_CLIENT_DEST:h}" ]]
[[ -O "${TUNNEL_CLIENT_DEST:h}" ]]

curl --fail --silent --show-error --location \
  "${TUNNEL_RELEASE_API}" \
  --output "${TUNNEL_INSTALL_WORK}/release.json"

jq -e '.draft == false and .prerelease == false' \
  "${TUNNEL_INSTALL_WORK}/release.json" >/dev/null

TUNNEL_ASSET_NAME="$(jq -er '
  [.assets[].name | select(test("^tunnel-client-v[0-9]+\\.[0-9]+\\.[0-9]+-darwin-arm64\\.zip$"))]
  | if length == 1 then .[0] else error("expected one Darwin arm64 asset") end
' "${TUNNEL_INSTALL_WORK}/release.json")"
TUNNEL_ASSET_URL="$(jq -er --arg name "${TUNNEL_ASSET_NAME}" '
  [.assets[] | select(.name == $name) | .browser_download_url]
  | if length == 1 then .[0] else error("asset URL missing or ambiguous") end
' "${TUNNEL_INSTALL_WORK}/release.json")"
TUNNEL_SUMS_URL="$(jq -er '
  [.assets[] | select(.name == "SHA256SUMS.txt") | .browser_download_url]
  | if length == 1 then .[0] else error("checksum asset missing or ambiguous") end
' "${TUNNEL_INSTALL_WORK}/release.json")"

[[ -n "${TUNNEL_ASSET_NAME}" && -n "${TUNNEL_ASSET_URL}" && -n "${TUNNEL_SUMS_URL}" ]]
curl --fail --silent --show-error --location \
  "${TUNNEL_ASSET_URL}" --output "${TUNNEL_INSTALL_WORK}/${TUNNEL_ASSET_NAME}"
curl --fail --silent --show-error --location \
  "${TUNNEL_SUMS_URL}" --output "${TUNNEL_INSTALL_WORK}/SHA256SUMS.txt"
```

Do not print the release JSON if evidence minimization is required. Asset names,
versions, and checksums are public, but account and tunnel identifiers are not.

## Verify before and after installation

Before installation, verify that the downloaded archive hash matches the exact
line in `SHA256SUMS.txt`. The project verifier requires either the legacy
single `tunnel-client` shape or the exact v0.0.11 four-file shape from the
addendum, and also requires the installed executable to be byte-for-byte
identical to that archive payload:

```zsh
TUNNEL_ARCHIVE="${TUNNEL_INSTALL_WORK}/${TUNNEL_ASSET_NAME}"
mkdir "${TUNNEL_INSTALL_WORK}/extracted"
/usr/bin/unzip -p "${TUNNEL_ARCHIVE}" tunnel-client \
  > "${TUNNEL_INSTALL_WORK}/extracted/tunnel-client"
chmod 0755 "${TUNNEL_INSTALL_WORK}/extracted/tunnel-client"

/bin/zsh scripts/bridge/verify-tunnel-client.zsh \
  --binary "${TUNNEL_INSTALL_WORK}/extracted/tunnel-client" \
  --archive "${TUNNEL_ARCHIVE}" \
  --checksums "${TUNNEL_INSTALL_WORK}/SHA256SUMS.txt"

/usr/bin/install -m 0755 \
  "${TUNNEL_INSTALL_WORK}/extracted/tunnel-client" \
  "${TUNNEL_CLIENT_DEST}"

/bin/zsh scripts/bridge/verify-tunnel-client.zsh \
  --binary "${TUNNEL_CLIENT_DEST}" \
  --archive "${TUNNEL_ARCHIVE}" \
  --checksums "${TUNNEL_INSTALL_WORK}/SHA256SUMS.txt"
```

Extract only after the verifier accepts the exact archive shape, install with
mode `0755` to the exact approved user-owned destination, then run the verifier
again against the final `TUNNEL_CLIENT_DEST`. `overall_status=PASS` requires
all of: an absolute executable path, successful parseable `--version`, matching
release version, matching SHA-256, an authorized exact archive shape, and
installed-payload equality.

When the installation-time archive and checksum file are no longer available,
the following is a capability check only:

```zsh
/bin/zsh scripts/bridge/verify-tunnel-client.zsh \
  --binary "/absolute/user-owned/path/tunnel-client"
```

It deliberately exits `2` with `overall_status=UNVERIFIED`. A working version
string alone does not prove official provenance. This repository has no durable
installation receipt, so preserve the installation-time PASS as redacted
operator evidence if official provenance must be asserted later; do not invent
that evidence from a post-install version check.

## Initialize without exposing secrets

Use a fresh interactive shell with command tracing disabled. Enter the runtime
key and tunnel ID without putting their values in shell history, then validate
only non-emptiness:

```zsh
unsetopt XTRACE 2>/dev/null || true
read -s "CONTROL_PLANE_API_KEY?Runtime API key: "
print
read -s "CONTROL_PLANE_TUNNEL_ID?Tunnel ID: "
print
[[ -n "${CONTROL_PLANE_API_KEY:-}" && -n "${CONTROL_PLANE_TUNNEL_ID:-}" ]]
export CONTROL_PLANE_API_KEY CONTROL_PLANE_TUNNEL_ID

/absolute/user-owned/path/tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile example-profile \
  --tunnel-id "${CONTROL_PLANE_TUNNEL_ID}" \
  --control-plane-api-key-ref env:CONTROL_PLANE_API_KEY \
  --health-listen-addr 127.0.0.1:0 \
  --mcp-command "/absolute/verified/path/codex mcp-server"
```

The generated profile MUST remain outside the repository and readable only by
the isolated user. Do not use `--force` unless replacement of that exact profile
is separately reviewed and authorized.

## Doctor, foreground operation, and redaction

Run `doctor` interactively before every proof:

```zsh
/absolute/user-owned/path/tunnel-client doctor \
  --profile example-profile \
  --explain
```

Do not pipe, tee, or save raw doctor output. Record only timestamp, client
version, `PASS`/`FAIL_CLOSED`, and the names of failed check categories. Redact
API keys, authorization headers, tunnel/organization/workspace IDs, raw URLs,
and profile contents. Never enable `--log.http-raw-unsafe` or
`--harpoon.capture-payloads` for this proof.

Start in the foreground so process termination is the revocation control:

```zsh
/absolute/user-owned/path/tunnel-client run --profile example-profile
```

Keep the health listener on loopback. Do not background, daemonize, or enable a
remote admin UI. After the bounded proof, press Control-C in that terminal and
wait for the process to exit. Confirm readiness is unreachable without printing
the health URL, then unset the ephemeral values:

```zsh
unset CONTROL_PLANE_API_KEY CONTROL_PLANE_TUNNEL_ID
```

A remote call after stop MUST fail closed before revocation is called proven.
Stopping the local process alone proves only the local half of revocation.
