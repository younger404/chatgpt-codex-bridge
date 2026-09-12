# Public Open-Source Release Design (Component-04)

Status: Candidate
Spec ID: `public-open-source-release`

## Architecture decision reuse

This tranche reuses ADR 0012 (current-tree sanitization, no history rewrite)
and ADR 0013 (private engineering repository plus intentionally unrelated
clean public history). No new ADR is added for those repeated decisions.

## Flow

1. Pin the exact private base (`github-relay-v0.2` HEAD/tree) and build one
   private candidate branch in a task-owned worktree.
2. Edit release-facing material in the candidate: Relay-first bilingual
   documentation, manifest `1.0.0-beta.1` and proposed public URLs,
   deterministic package-test expectations, synthetic test fixtures replacing
   historical business aliases/control-repository literals, SECURITY.md,
   CONTRIBUTING.md, controller SOP, verification SOP, synthetic examples, one
   minimal offline CI workflow, and release-notes draft.
3. Verify the candidate worktree with the relevant portable/Relay suites.
4. Commit; export only the tracked tree of that commit; apply the reviewed
   EXCLUDE list (`docs/plans/`, `docs/reports/`, `docs/research/`,
   `docs/validation/` — private development-process records whose durable
   knowledge lives in specs/ADR/runbooks).
5. Scan the exact export: repository privacy gate with external private
   denylist, then pinned Gitleaks against export and unpacked archive.
6. Install from the export into a synthetic clean HOME with `--no-start` and
   rerun the export-scoped portable suites.
7. Record manifest, digests, and evidence; deliver one unmerged private PR and
   stop. The public tree, private candidate commit, and future public root
   commit are three distinct identities.

## Disposition rules

- KEEP: source, plugin, source/plugin mirrors, tests and fixtures, public
  install dependencies (`.agents/plugins/marketplace.json`), LICENSE, specs,
  ADRs, runbooks, synthetic redacted evidence examples.
- EDIT: files whose release-facing statements would otherwise be stale
  (install identity, version, Relay-first ordering, synthetic fixture values).
- EXCLUDE: private development-process records (plans, reports, research,
  validation evidence). Exclusion happens only in the release tree; private
  history is not deleted.

## Boundaries

- No Relay/Guard admission, execution, capability, registry-hash, journal
  schema, publish, or GC behavior changes. Fixture/identifier edits in tests
  and docs do not alter production logic.
- No new verification subsystem: the existing static doctor, operator store
  validator, and portable suites form the documented verification SOP.
- Candidate-stage docs mark the proposed repository/tag as planned; no
  existence claim is made before Gate 4/5 authorization.

## Alternatives rejected

- Deleting historical process docs from the private repository: out of scope;
  exclusion applies to the release tree only.
- A new `verify-installation.zsh` wrapper: existing static entries already
  cover the SOP; a new entry would be an unneeded system.
- Rewriting or generalizing historical ADR/spec decisions: historical records
  keep their decision context; only private operational literals are replaced
  with synthetic placeholders.
