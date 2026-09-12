# ADR 0021 — Bind Relay scope and preserve evidence revisions

Status: candidate, COMPONENT-02; no installation authorization.

Use the existing operator plist, managed registry, Guard key identity and SQLite
journal. A second alias directory, execution service or dashboard is unnecessary.
Binding a nonempty unscoped journal to current settings would invent provenance;
require explicit scope assertion, preserving rows and V1 bytes transactionally.

Query and review are local projection operations admitted via the same private
Issue envelope. Execution, durable delivery and explicit review are independent.
A review names an immutable execution request and content digest. Next-turn evidence
cannot inherit approval. Retained evidence survives capability revocation while new
execution still requires enabled registry and Guard capability authorization.

Reuse AppServerClient for managed jobs with a pinned public schema subset. Avoid
experimental project APIs in managed workspaces. No fallback to a fresh thread on
resume failure. A crash after sending a side effect is uncertain, never retryable
without durable identity. This does not promise universal exactly-once execution.

Consequences: v4 needs explicit migration provenance; old source cannot read it.
Real version compatibility, webpage/service closure and deployment remain NOT_RUN.
