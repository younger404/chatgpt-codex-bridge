# ChatGPT Supervisory Loop

Use this bridge when one ChatGPT web conversation supervises one local Codex
thread on a trusted single-user Mac.

## New project

1. Call `codex-start(prompt, projectName)` once.
2. The bridge creates one sidebar-visible project root, registers it with the
   Codex desktop app, starts one durable background job, and attaches the
   bundled `workspace-new-project` Skill as the first project action.
3. Keep calling `codex-wait(jobId)` while the job is queued or running.
4. On completion, inspect the returned thread and content. If the user's full
   request is still incomplete, call `codex-reply-async(prompt, threadId)` and
   join the returned job again with `codex-wait`.
5. Do not create a second Codex thread for the same project merely because one
   model turn ended.

## Recovery

- If an active card says `Failed to fetch template`, refresh the app and call
  `codex-job-open(jobId)`.
- If the browser page is closed, reopen the same conversation and let the card
  resume polling; then use the explicit return control.
- If the job is `queued` or `running`, join again with `codex-wait(jobId)`.
