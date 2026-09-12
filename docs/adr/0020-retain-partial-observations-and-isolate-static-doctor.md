# 0020 — Retain partial observations and isolate static doctor

Status: Proposed in BRIDGE-COMPONENT-01 V3 engineering candidate

The retained observer saves samples only after all calls return. Either instance
read can fail without retaining its stage, result length or errno. Existing
static_doctor executes configured runtime checks. These code facts justify
forward fixes independently of the unknown historical OS cause.

Use one packaged observer from existing doctor. Return partial steps on failure,
capture actual native metadata immediately and preserve complete identity plus
the original 15-second window. Separate explicit offline config/source checking
from the old runtime path. Default doctor must not select live checks; existing
doctor automation needs --runtime. status retains its runtime meaning. No new
runner, storage authority, public protocol or installed runtime change.

Fixtures prove current behavior, never historical causality. Static success
covers declared inputs only. Live acceptance needs separate authorization and
runtime evidence. No recovery/deployment follows from this decision.
