# 0019 — Validate existing Guard store objects without chmod

Status: Accepted for BRIDGE-GUARD-FIX-01 engineering candidate

Existing-key/root chmod can change ctime even when permissions are already
correct. Ordinary loading will therefore validate existing objects, failing
closed on noncompliance; permission initialization is limited to exclusive new
creation. This preserves HMAC/context, MCP and GC semantics without another
storage abstraction. Reads may affect atime. Existing objects are never repaired
or replaced. No live store migration, deployment or recovery follows from this
source decision; focused synthetic tests and byte-identical mirrors are required.
