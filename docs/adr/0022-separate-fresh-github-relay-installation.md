# ADR 0022 — Separate fresh GitHub Relay installation from Tunnel recovery

Status: candidate.

The generic portable installer is Tunnel-oriented and intentionally rejects
explicit managed stores. Reusing it for GitHub Relay would weaken the reviewed
recovery boundary and still omit current managed transport configuration.

Provide one dedicated fresh-only managed GitHub Relay V1 package entry, shipping
byte-identical source Relay modules and the existing Guard/store helpers. Keep
the generic installer and its recovery rejection unchanged. The new entry owns
only new HOME-derived state and one Relay LaunchAgent; Secure Tunnel is not a
dependency. Existing state needs separately reviewed recovery, never adoption.

Configuration-only installation, policy support, service activation and live
acceptance remain distinct claims. Clean export and offline fixture evidence
prove distribution without repeating already accepted operational gates.


Activation failure must not knowingly leave a future-enabled service: the plist
always defaults to Disabled=true and failed enable/bootstrap is compensated by
a best-effort disable. Existing partial files remain for reviewed recovery.
No-start does not inspect launchd overrides, so its claims distinguish the plist
default from LAUNCHD_STATE=NOT_PROBED and SERVICE_STARTED_BY_INSTALLER=false.
