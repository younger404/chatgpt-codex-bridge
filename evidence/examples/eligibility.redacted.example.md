# Redacted ChatGPT MCP Eligibility Evidence

checked_date: 2026-08-02
plan: consumer
official_plan_supports_full_custom_mcp_write: FAIL
non_enterprise_canengine_case: USER_CONFIRMED
plugins_directory_visible: PASS
developer_mode_visible: PASS
developer_mode_enabled: YES
write_delete_risk_warning_visible: PASS
custom_app_create_visible: PASS
server_url_connection_visible: PASS
tunnel_connection_visible: PASS
available_tunnel_present: FAIL
platform_tunnel_console_reachable: FAIL
platform_tunnels_read_use: UNVERIFIED
canengine_connection_type: UNVERIFIED
trusted_read_probe_connected: PASS
trusted_read_probe_tool_count: 5
trusted_read_probe_permissions_reviewed: PASS_READ_ONLY
trusted_read_probe_call: PASS
local_codex_tools_discovered: PASS
chatgpt_codex_tools_discovered: UNVERIFIED
declared_codex_tool_permissions_reviewed: UNVERIFIED
result: PARTIAL_PASS

notes: Explicit authorization covered Developer Mode activation, Server URL addition, MCP authorization, and a harmless command. The tested consumer workspace completed a custom read-only MCP call, while Tunnel association and Codex action/write capability remain unverified. No raw account, workspace, organization, plugin, chat, tunnel, endpoint, or credential identifiers are recorded.
