# Public MCP Contract

The plugin exposes the bridge through the Secure MCP Tunnel, not through a
local `.mcp.json`. Registering the Guard as a Codex-local MCP server would
create a recursive Codex-to-Guard-to-Codex path and would not authorize a
ChatGPT connector.

## Public tools by preset

`personal-full-control`:

- `codex(prompt)` — synchronous new Codex thread for short diagnostics.
- `codex-reply(prompt, threadId)` — synchronous reply to an existing thread.
- `codex-start(prompt, projectName?)` — durable new sidebar project/task.
- `codex-reply-async(prompt, threadId)` — durable exact-thread reply.
- `codex-wait(jobId)` — bounded read-only join.
- `codex-job-open(jobId)` — reopen an existing durable job.
- `codex-job-status(jobId)` — read durable job state.

`workspace-safe` exposes only synchronous `codex` and `codex-reply`.

`managed-repo`:

- `codex-repo-start(repoAlias, prompt, taskName?)` — durable isolated worktree.
- `codex-reply-async(prompt, threadId)` — same managed thread/worktree.
- `codex-wait(jobId)`, `codex-job-open(jobId)`, and
  `codex-job-status(jobId)` — durable job reads.
- `codex-repo-publish(threadId, commitMessage)` — checked push to the exact
  Guard-generated branch.
- When the startup registry contains an authorized local target,
  `codex-repo-run-local(threadId, targetName)` and
  `codex-repo-stop-local(threadId, targetName)` control only that tracked
  loopback process group.

Managed mode never accepts `cwd`, `repoPath`, a remote, refspec, target branch,
force option, merge command, or arbitrary deployment command.

The mutable tools create or continue work. The wait/open/status tools are
read-only and only inspect durable job state. The public descriptions must stay
truthful about thread identity, project identity, and status transitions.

`threadId` and `jobId` are field names retained for tool compatibility. Their
values are installation-scoped HMAC bearer capabilities, not raw Codex IDs or
raw durable UUIDs. They cannot be moved to another bridge installation and MUST
not be shared. This is a single-user local authorization boundary, not tenant or
ChatGPT conversation-principal authentication.

Default async limits are 256 KiB per prompt, two active jobs, 512 retained job
records, and four hours per App Server worker. Limit failures are MCP admission
errors and do not allocate a project or worker.
