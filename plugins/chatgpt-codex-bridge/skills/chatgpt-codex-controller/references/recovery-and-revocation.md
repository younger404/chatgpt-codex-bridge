# Recovery and Revocation

Use `scripts/doctor.zsh --runtime` to validate the generated install. If the external
Tunnel profile fails doctor, repair it with official `tunnel-client` tools.

Temporary revocation:

```zsh
/bin/zsh scripts/chatgpt-codex-bridge.zsh stop
```

Uninstall removes exact bridge-owned generated files and preserves the external
Tunnel profile, credentials, repositories, and Codex conversation history.

For durable jobs:

- `queued` or `running`: continue with `codex-wait(jobId)`.
- `completed`: review the terminal result and decide whether the same thread
  still needs work.
- `failed` or `interrupted`: fix the cause and continue the same thread when
  identity remains valid.
