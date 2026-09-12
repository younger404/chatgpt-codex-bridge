# Synthetic GitHub Relay job examples

These five JSON objects are **synthetic** examples of the closed
`codex_bridge_job_v1` request schema
([`docs/specs/github-relay/job-schema-v1.json`](../docs/specs/github-relay/job-schema-v1.json)).
Every ID, reference, and digest is a placeholder; nothing here ran against a
real control repository, and the proposed public repository/tag do not exist
yet.

| File | Operation | Purpose |
| --- | --- | --- |
| `start.sample.json` | `start` | Admit one managed job for a registered alias. |
| `query.sample.json` | `query` | Read the recorded state of an existing reference. |
| `review.sample.json` | `review` | Record an allowed author's conclusion bound to exact evidence. |
| `reply.sample.json` | `reply` | Continue the bound thread after review, with a new request ID. |
| `publish.sample.json` | `publish` | Push the generated branch only (never a merge or deploy). |

Usage notes:

- Replace every placeholder with the values returned by your own installation:
  your registered alias, a new canonical UUID per request, the actual
  `relayJobRef`, and the exact `evidenceRequestId`/`evidenceDigest` being
  reviewed.
- A `review` only records a declaration about exact evidence;
  `changes_requested` is shown here because a first review of synthetic
  evidence cannot be an acceptance.
- A `reply` reuses the original reference with a **new** `requestId`; it does
  not follow from a review automatically.
- These files are validated against the production payload validator by
  `tests/portable/test-public-examples.zsh`:

  ```zsh
  /bin/zsh tests/portable/test-public-examples.zsh
  ```
