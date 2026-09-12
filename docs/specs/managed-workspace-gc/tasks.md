# Managed Workspace GC Tasks v1

- [x] T01 Verify the registered Bridge base and current worktree HEAD equal
      `b99cc61ffa2164e2fa0209d91f697498936d48e5` before edits.
- [x] T02 Create testable requirements, design, tasks, and ADR before runtime
      changes.
- [x] T03 Add lifecycle, exact ownership, publication, safe removal, prune, and
      deterministic metric primitives to `managed_repo.py`.
- [x] T04 Add focused RED tests for clean published/unchanged collection; active,
      dirty, unpublished, local-process, foreign, symlink, traversal, and identity
      retention; idempotency; and Git metadata pruning.
- [x] T05 Integrate startup/pre-start/post-publish/close GC under the Guard
      admission lock and expose the closed `codex-repo-close` capability surface.
- [x] T06 Add injectable disk usage and prove SOFT, HARD, reclamation, EMERGENCY,
      recovery-surface, and pressure-protected dirty-work behavior.
- [x] T07 Keep script/plugin runtime mirrors byte-synchronized and update the
      managed-existing-repo runbook for automatic safe cleanup and recovery.
- [x] T08 Document `managed-tmp` as a P1 safe limitation because the sibling root
      cannot be authorized without broadening current workspace-write policy.
- [x] T09 Run focused managed-repo and Guard tests, Relay tests, and relevant
      security/portable/package regression tests.
- [x] T10 Run `git diff --check`, inspect the exact changed-path set, and stop
      before commit or publish for ChatGPT audit and Guard-controlled publication.
- [x] T11 Persist worker and local-process pre-launch state and prove every
      missing/launching/crash-gap case retains unless exact no-launch evidence exists.
- [x] T12 Protect ignored-only work and prove moved/network publication failures
      and percentage-dominant watermark boundaries fail closed.
- [x] T13 Resolve the allocation owner by workspace UUID, enforce exact grouped
      immutable/thread identity, and strictly snapshot every UUID durable entry.
- [x] T14 Add prepared/removal receipts, two-phase persistence, restart recovery,
      prune follow-up semantics, and close metrics with fault-injection coverage.
- [x] T15 Synchronize both runtime mirrors, run all required focused/Guard/Relay/
      portable-security tests, re-audit code paths, and stop before republish.
