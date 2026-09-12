# Contributing

This is a spec-driven project. Read `AGENTS.md` first.

## Ground rules

1. Specs before code: update the relevant `docs/specs/<feature>/` files
   (requirements/design/tasks) for any behavior change, and record
   architecture decisions as ADRs.
2. Keep diffs small and scoped; match existing style; no unrelated refactors.
3. Never commit credentials, real installation state, personal paths, real
   control-repository or business identifiers, or private runtime evidence.
   Test fixtures use synthetic values only — do not split real values into
   concatenated fragments to evade scanning.
4. `.project-memory/` stays local and untracked.

## Required checks for changes

Run the most relevant checks for your change, from the repository root:

```zsh
/bin/zsh tests/portable/test-plugin-package.zsh
/bin/zsh tests/portable/test-public-sanitization.zsh
/bin/zsh tests/portable/test-github-relay-v1-install.zsh
/bin/zsh tests/portable/test-readme-demo.zsh
/bin/zsh tests/portable/test-macos-installer.zsh
/bin/zsh tests/portable/test-public-examples.zsh
```

Python changes: run the affected `tests/relay/` or `tests/bridge/` suites with
`PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 <test-file>`. Shell changes:
`/bin/zsh -n <script>` plus the matching portable suite. Record exit codes.

## Privacy gate

Before opening a pull request, the tracked tree must pass:

```zsh
/bin/zsh scripts/release/check-public-sanitization.zsh --repo "$PWD"
```

If you maintain a private denylist, keep it outside the repository and pass it
with `--denylist /absolute/private-file`; the gate reports file/line only and
never prints the matched value.

## Pull requests

One logical change per PR. Describe what ran and what did not; do not claim
"CI PASS" without the actual run. Do not merge your own PR; acceptance is a
separate review step.
