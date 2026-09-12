# ChatGPT MCP Workspace Eligibility Gate

Date: 2026-08-02
Scope: account/UI plus an explicitly authorized trusted read-only MCP probe; no credentials, Tunnel creation, installation, local Codex invocation, or write action

## Classification rule

- Required capability: custom MCP modify/write access in the selected ChatGPT surface.
- Eligibility and rollout MUST be determined from the current UI, the attached
  app's actual tool list, its declared annotations, and one separately authorized
  harmless probe.
- Historical screenshots, account labels, connector visibility, and a successful
  read-only MCP do not prove that Developer MCP write tools will execute.
- Until every gate below passes, classify the route as `UNVERIFIED`.

The account label alone does not close this gate. The target account's actual Plugins/Apps surface, connection type, discovered tools, and declared permissions must be inspected. A side-effecting tool presented as read/fetch is not an acceptable bypass.

## Manual checks after a route decision

Perform these checks in order, stopping at each authorization or isolation boundary:

1. Confirm the plan/workspace type without recording account, workspace, or organization identifiers.
2. Record whether the UI says Plugins, Apps, Connectors, or Developer mode.
3. Record whether browsing and creating a plugin/app are visible.
4. Record whether Tunnel is offered as a connection type.
5. Classify CanEngine as published/allowlisted, custom MCP, legacy/gray-rollout, or unknown.
6. Stop and request authorization before enabling Developer Mode.
7. Stop again before adding a Server URL or authorizing an app.
8. Record tool names and declared read/write/action metadata before invoking anything.
9. Execute only a separately authorized non-mutating probe before any action/write tool.

Record only `PASS`, `FAIL`, or `UNVERIFIED`. Do not capture raw IDs, tokens, endpoints, cookies, or screenshots containing account data.

## Decision rules

- Business or Enterprise/Edu plus all required permissions: the officially supported G0 route may proceed.
- A consumer workspace with legitimate target action tools and explicit authorization behavior: proceed as experimental evidence, not as a documented entitlement guarantee.
- A workspace exposing only read/fetch tools: direct write route fails; evaluate the separately bounded CanEngine fallback.
- Any tool whose declared read-only metadata hides local writes or commands: fail closed.
- Any uncertainty: `UNVERIFIED` and stop.

## Safe next routes

1. Direct consumer capability proof: preserves the smallest architecture if the exact target actions are legitimately exposed.
2. Bounded CanEngine-to-Codex bridge: preserves ChatGPT web supervision while adding a reviewed local relay layer.
3. Eligible ChatGPT workspace: remains the officially documented full-MCP route.
4. API or another full MCP client: fallback if neither ChatGPT web route is acceptable.

## Evidence hygiene

Store only the resulting `PASS`, `FAIL`, or `UNVERIFIED` classification and the
generic reason. Do not commit account plan, workspace identity, endpoint,
network error, measured latency, raw tool output, or screenshots containing
personal UI data.
