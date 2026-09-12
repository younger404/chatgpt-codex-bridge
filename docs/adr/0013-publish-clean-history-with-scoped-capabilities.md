# ADR 0013: Publish a clean history with scoped capabilities

Status: Accepted
Date: 2026-08-22

## Context

The private source repository now has a sanitized current tree, but its earlier
Git objects intentionally retain private deployment evidence. A security review
also found that raw thread/job identifiers acted as bearer authorization and
that durable async work had no aggregate budget.

## Decision

Keep the private repository private and authoritative. Publish version 0.6.0 to
a separate public repository created from one validated source archive and one
new root commit.

Before publication, replace raw public identifiers with installation-scoped
HMAC capabilities and add atomic prompt/concurrency/retention/lifetime limits.
Describe the package as single-user local software and do not claim trusted
ChatGPT conversation identity.

License the public release under MIT so other people can install, modify, and
redistribute it.

## Consequences

- Private history and public history are intentionally unrelated.
- Existing pre-0.6.0 cards/identifiers are not guaranteed to continue after an
  upgrade; rollback to the prior pinned ref remains available.
- Public capability values are bearer secrets within one local installation;
  they are scoped and unforgeable but not multi-user authentication.
- Jobs fail closed when the configured aggregate bounds are reached.
- Release engineering must verify both the private source commit and the clean
  export before pushing.
