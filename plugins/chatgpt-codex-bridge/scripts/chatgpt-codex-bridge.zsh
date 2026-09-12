#!/bin/zsh
set -euo pipefail

readonly PROGRAM_PATH="${0:A}"
readonly SCRIPT_DIR="${PROGRAM_PATH:h}"
readonly PLUGIN_ROOT="${SCRIPT_DIR:h}"

# Explicit offline/observation modes dispatch before installed config or maintenance.
if [[ "${1:-}" == "doctor" ]]; then
  case "${2:-}" in
    --static|--observe)
      shift
      exec /usr/bin/python3 -I "${SCRIPT_DIR}/bridge-doctor.py" "$@"
      ;;
    --runtime) shift 2; set -- doctor "$@" ;;
    *)
      print -u2 -r -- "Usage: doctor {--static --config <plist> --source-root <source>|--observe --contract <json> --private-output <new-file>|--runtime [--no-start]}"
      exit 2
      ;;
  esac
fi
readonly SOURCE_GUARD="${PLUGIN_ROOT}/bridge/codex-mcp-guard.py"
readonly SOURCE_SUPERVISION="${PLUGIN_ROOT}/bridge/supervision.py"
readonly SOURCE_MANAGED_REPO="${PLUGIN_ROOT}/bridge/managed_repo.py"
readonly SOURCE_RUNTIME_WRAPPER="${SCRIPT_DIR}/run-guard.zsh"
readonly SOURCE_CODEX_RESOLVER="${PLUGIN_ROOT}/bridge/resolve-codex-bin.zsh"
readonly SOURCE_WORKSPACE_SKILL_DIR="${PLUGIN_ROOT}/runtime/bootstrap/workspace-new-project"
readonly DEFAULT_PROFILE="chatgpt-codex"
readonly DEFAULT_WORKSPACE="${HOME}/codex-workspace"
readonly DEFAULT_LABEL="com.chatgpt-codex-bridge.tunnel"
readonly USER_UID="$(/usr/bin/id -u)"
readonly DOMAIN="gui/${USER_UID}"
readonly STATE_DIR="${CHATGPT_CODEX_BRIDGE_STATE_DIR:-${HOME}/Library/Application Support/chatgpt-codex-bridge}"
readonly RUNTIME_DIR="${CHATGPT_CODEX_BRIDGE_RUNTIME_DIR:-${HOME}/.local/share/chatgpt-codex-bridge}"
readonly LOG_DIR="${CHATGPT_CODEX_BRIDGE_LOG_DIR:-${HOME}/Library/Logs/chatgpt-codex-bridge}"
readonly LAUNCH_AGENTS_DIR="${CHATGPT_CODEX_BRIDGE_LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
readonly CONFIG_FILE="${STATE_DIR}/config.plist"
readonly LOCAL_READY_ATTEMPTS=60
readonly CONTROL_PLANE_ATTEMPTS=240

action="${1:-}"
if [[ -n "${action}" ]]; then
  shift
fi

profile_arg=""
workspace_arg=""
codex_bin_arg=""
tunnel_client_bin_arg=""
label_arg=""
preset_arg=""
typeset -i no_start=0

log() {
  print -r -- "chatgpt-codex-bridge: $*"
}

die() {
  print -u2 -r -- "chatgpt-codex-bridge: $*"
  exit 1
}

usage() {
  print -r -- "Usage: ${PROGRAM_PATH} {install|doctor|status|restart|stop|uninstall} [options]"
  print -r -- ""
  print -r -- "Install options:"
  print -r -- "  --profile <name>"
  print -r -- "  --workspace <absolute-directory>"
  print -r -- "  --codex-bin <absolute-executable>"
  print -r -- "  --tunnel-client-bin <absolute-executable>"
  print -r -- "  --label <launchagent-label>"
  print -r -- "  --preset <personal-full-control|workspace-safe|managed-repo> (required)"
}

parse_options() {
  while (( $# > 0 )); do
    case "$1" in
      --profile|--workspace|--codex-bin|--tunnel-client-bin|--label|--preset)
        (( $# >= 2 )) || die "$1 requires a value"
        case "$1" in
          --profile) profile_arg="$2" ;;
          --workspace) workspace_arg="$2" ;;
          --codex-bin) codex_bin_arg="$2" ;;
          --tunnel-client-bin) tunnel_client_bin_arg="$2" ;;
          --label) label_arg="$2" ;;
          --preset) preset_arg="$2" ;;
        esac
        shift 2
        ;;
      --no-start)
        no_start=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *) die "unsupported argument: $1" ;;
    esac
  done
}

ensure_directory() {
  local target="$1"
  if [[ -e "${target}" ]]; then
    [[ -d "${target}" && ! -L "${target}" ]] || die "unsafe directory target"
  else
    /bin/mkdir -p -- "${target}"
  fi
}

real_directory() {
  local target="$1"
  [[ "${target}" == /* && -d "${target}" && ! -L "${target}" ]] \
    || die "workspace must be an existing absolute directory"
  print -r -- "${target:A}"
}

real_executable() {
  local target="$1"
  [[ "${target}" == /* && -f "${target}" && ! -L "${target}" && -x "${target}" ]] \
    || die "executable path is invalid"
  print -r -- "${target:A}"
}

validate_label() {
  [[ "$1" =~ '^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$' ]] \
    || die "LaunchAgent label is invalid"
}

validate_profile() {
  [[ "$1" =~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' ]] \
    || die "Tunnel profile name is invalid"
}

resolve_tunnel_client() {
  local candidate="${tunnel_client_bin_arg}"
  local version_output version_first_line normalized_version
  if [[ -z "${candidate}" ]]; then
    candidate="$(command -v tunnel-client 2>/dev/null || true)"
  fi
  [[ -n "${candidate}" ]] || die "tunnel-client was not found"
  candidate="$(real_executable "${candidate}")"
  version_output="$("${candidate}" --version 2>/dev/null)" \
    || die "tunnel-client is not usable"
  version_first_line="${version_output%%$'\n'*}"
  normalized_version="$(print -r -- "${version_first_line}" \
    | /usr/bin/grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
    | /usr/bin/head -n 1)"
  [[ "${normalized_version}" == "0.0.11" ]] \
    || die "tunnel-client version must be 0.0.11"
  print -r -- "${candidate}"
}

resolve_codex() {
  local requested="${codex_bin_arg}"
  local resolved
  if [[ -n "${requested}" ]]; then
    resolved="$(CODEX_BRIDGE_BIN="${requested}" /bin/zsh "${SOURCE_CODEX_RESOLVER}")"
  else
    resolved="$(/bin/zsh "${SOURCE_CODEX_RESOLVER}")"
  fi
  real_executable "${resolved}"
}

resolve_python() {
  local candidate=""
  if [[ -x /usr/bin/python3 ]]; then
    candidate=/usr/bin/python3
  else
    candidate="$(command -v python3 2>/dev/null || true)"
  fi
  [[ -n "${candidate}" ]] || die "python3 is required to run the Guard"
  real_executable "${candidate}"
}

policy_for_preset() {
  case "$1" in
    personal-full-control) print -r -- $'danger-full-access\tnever' ;;
    workspace-safe) print -r -- $'workspace-write\ton-request' ;;
    managed-repo) print -r -- $'workspace-write\tnever' ;;
    *) die "unsupported preset" ;;
  esac
}

verify_managed_policy_support() {
  local codex_bin="$1"
  local workspace="$2"
  local probe_root outside_marker
  probe_root="$(/usr/bin/mktemp -d "${workspace}/.bridge-policy-probe.XXXXXX")"
  outside_marker="${HOME}/.chatgpt-codex-bridge-policy-probe-${$}"
  /bin/rm -f -- "${outside_marker}"
  if ! "${codex_bin}" exec \
    --ignore-user-config \
    --ephemeral \
    --sandbox workspace-write \
    -c 'approval_policy="never"' \
    --skip-git-repo-check \
    --cd "${probe_root}" \
    "Use the shell to create ./workspace-marker, then attempt to create ${outside_marker}. Do not request approval." \
    >/dev/null 2>&1; then
    /bin/rm -rf -- "${probe_root}"
    die "Codex does not support the required workspace-write + never policy"
  fi
  if [[ ! -f "${probe_root}/workspace-marker" || -e "${outside_marker}" ]]; then
    /bin/rm -rf -- "${probe_root}"
    /bin/rm -f -- "${outside_marker}"
    die "Codex workspace-write + never policy probe failed closed"
  fi
  /bin/rm -rf -- "${probe_root}"
}

write_generated_files() {
  local label="$1"
  local profile="$2"
  local workspace="$3"
  local codex_bin="$4"
  local tunnel_client_bin="$5"
  local python_bin="$6"
  local preset="$7"
  local sandbox="$8"
  local approval_policy="$9"
  local target_plist="${LAUNCH_AGENTS_DIR}/${label}.plist"
  local runtime_guard="${RUNTIME_DIR}/codex-mcp-guard.py"
  local runtime_managed_repo="${RUNTIME_DIR}/managed_repo.py"
  local runtime_wrapper="${RUNTIME_DIR}/run-guard.zsh"
  local runtime_skill_dir="${RUNTIME_DIR}/skills/workspace-new-project"
  local runtime_skill="${runtime_skill_dir}/SKILL.md"
  local runtime_skill_script="${runtime_skill_dir}/scripts/create_workspace_project.sh"
  local health_url_file="${STATE_DIR}/health.url"
  local stdout_log="${LOG_DIR}/tunnel.stdout.log"
  local stderr_log="${LOG_DIR}/tunnel.stderr.log"
  local config_tmp plist_tmp

  [[ "${runtime_wrapper}" != *' '* ]] \
    || die "runtime wrapper path must not contain spaces; choose a macOS home path without spaces"
  ensure_directory "${STATE_DIR}"
  ensure_directory "${RUNTIME_DIR}"
  ensure_directory "${RUNTIME_DIR}/skills"
  ensure_directory "${runtime_skill_dir}"
  ensure_directory "${runtime_skill_dir}/scripts"
  ensure_directory "${LOG_DIR}"
  ensure_directory "${LAUNCH_AGENTS_DIR}"

  for target in "${RUNTIME_DIR}/supervision.py" "${runtime_guard}" "${runtime_managed_repo}" "${runtime_wrapper}" "${runtime_skill}" \
    "${runtime_skill_script}" "${target_plist}" "${CONFIG_FILE}"; do
    [[ ! -e "${target}" || ( -f "${target}" && ! -L "${target}" ) ]] \
      || die "generated target is not a regular file"
  done

  /usr/bin/install -m 700 "${SOURCE_GUARD}" "${runtime_guard}"
  /usr/bin/install -m 600 "${SOURCE_MANAGED_REPO}" "${runtime_managed_repo}"
  /usr/bin/install -m 600 "${SOURCE_SUPERVISION}" "${RUNTIME_DIR}/supervision.py"
  /usr/bin/install -m 700 "${SOURCE_RUNTIME_WRAPPER}" "${runtime_wrapper}"
  /usr/bin/install -m 600 "${SOURCE_WORKSPACE_SKILL_DIR}/SKILL.md" "${runtime_skill}"
  /usr/bin/install -m 700 "${SOURCE_WORKSPACE_SKILL_DIR}/scripts/create_workspace_project.sh" "${runtime_skill_script}"
  config_tmp="$(/usr/bin/mktemp "${STATE_DIR}/config.plist.XXXXXX")"
  plist_tmp="$(/usr/bin/mktemp "${STATE_DIR}/launchagent.plist.XXXXXX")"

  BRIDGE_CONFIG_OUT="${config_tmp}" \
  BRIDGE_LABEL="${label}" \
  BRIDGE_PROFILE="${profile}" \
  BRIDGE_WORKSPACE="${workspace}" \
  BRIDGE_CODEX_BIN="${codex_bin}" \
  BRIDGE_TUNNEL_CLIENT_BIN="${tunnel_client_bin}" \
  BRIDGE_PYTHON_BIN="${python_bin}" \
  BRIDGE_PRESET="${preset}" \
  BRIDGE_SANDBOX="${sandbox}" \
  BRIDGE_APPROVAL_POLICY="${approval_policy}" \
  BRIDGE_RUNTIME_GUARD="${runtime_guard}" \
  BRIDGE_RUNTIME_MANAGED_REPO="${runtime_managed_repo}" \
  BRIDGE_RUNTIME_WRAPPER="${runtime_wrapper}" \
  BRIDGE_MANAGED_REGISTRY="${STATE_DIR}/managed-repos.v1.json" \
  BRIDGE_WORKSPACE_NEW_PROJECT_SKILL="${runtime_skill}" \
  BRIDGE_HEALTH_URL_FILE="${health_url_file}" \
  BRIDGE_STDOUT_LOG="${stdout_log}" \
  BRIDGE_STDERR_LOG="${stderr_log}" \
    "${python_bin}" - <<'PY'
import os
import plistlib

keys = {
    "label": "BRIDGE_LABEL",
    "profile": "BRIDGE_PROFILE",
    "workspace": "BRIDGE_WORKSPACE",
    "codex_bin": "BRIDGE_CODEX_BIN",
    "tunnel_client_bin": "BRIDGE_TUNNEL_CLIENT_BIN",
    "python_bin": "BRIDGE_PYTHON_BIN",
    "preset": "BRIDGE_PRESET",
    "sandbox": "BRIDGE_SANDBOX",
    "approval_policy": "BRIDGE_APPROVAL_POLICY",
    "runtime_guard": "BRIDGE_RUNTIME_GUARD",
    "runtime_managed_repo": "BRIDGE_RUNTIME_MANAGED_REPO",
    "runtime_wrapper": "BRIDGE_RUNTIME_WRAPPER",
    "managed_registry": "BRIDGE_MANAGED_REGISTRY",
    "workspace_new_project_skill": "BRIDGE_WORKSPACE_NEW_PROJECT_SKILL",
    "health_url_file": "BRIDGE_HEALTH_URL_FILE",
    "stdout_log": "BRIDGE_STDOUT_LOG",
    "stderr_log": "BRIDGE_STDERR_LOG",
}
payload = {key: os.environ[env] for key, env in keys.items()}
with open(os.environ["BRIDGE_CONFIG_OUT"], "wb") as stream:
    plistlib.dump(payload, stream, fmt=plistlib.FMT_XML, sort_keys=True)
PY

  BRIDGE_PLIST_OUT="${plist_tmp}" \
  BRIDGE_LABEL="${label}" \
  BRIDGE_TUNNEL_CLIENT_BIN="${tunnel_client_bin}" \
  BRIDGE_PROFILE="${profile}" \
  BRIDGE_HEALTH_URL_FILE="${health_url_file}" \
  BRIDGE_RUNTIME_WRAPPER="${runtime_wrapper}" \
  BRIDGE_STATE_DIR="${STATE_DIR}" \
  BRIDGE_HOME="${HOME}" \
  BRIDGE_CONFIG_FILE="${CONFIG_FILE}" \
  BRIDGE_STDOUT_LOG="${stdout_log}" \
  BRIDGE_STDERR_LOG="${stderr_log}" \
    "${python_bin}" - <<'PY'
import os
import plistlib

payload = {
    "Label": os.environ["BRIDGE_LABEL"],
    "ProgramArguments": [
        os.environ["BRIDGE_TUNNEL_CLIENT_BIN"],
        "run",
        "--profile",
        os.environ["BRIDGE_PROFILE"],
        "--health.listen-addr",
        "127.0.0.1:0",
        "--health.url-file",
        os.environ["BRIDGE_HEALTH_URL_FILE"],
        "--mcp.command",
        "command=" + os.environ["BRIDGE_RUNTIME_WRAPPER"],
    ],
    "WorkingDirectory": os.environ["BRIDGE_STATE_DIR"],
    "EnvironmentVariables": {
        "HOME": os.environ["BRIDGE_HOME"],
        "PATH": os.pathsep.join([
            os.path.join(os.environ["BRIDGE_HOME"], ".local", "bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]),
        "CHATGPT_CODEX_BRIDGE_CONFIG": os.environ["BRIDGE_CONFIG_FILE"],
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 10,
    "ProcessType": "Background",
    "StandardOutPath": os.environ["BRIDGE_STDOUT_LOG"],
    "StandardErrorPath": os.environ["BRIDGE_STDERR_LOG"],
}
with open(os.environ["BRIDGE_PLIST_OUT"], "wb") as stream:
    plistlib.dump(payload, stream, fmt=plistlib.FMT_XML, sort_keys=False)
PY

  /usr/bin/plutil -lint "${config_tmp}" >/dev/null || die "generated config is invalid"
  /usr/bin/plutil -lint "${plist_tmp}" >/dev/null || die "generated LaunchAgent is invalid"
  /bin/chmod 600 "${config_tmp}" "${plist_tmp}"
  /bin/mv -f -- "${config_tmp}" "${CONFIG_FILE}"
  /bin/mv -f -- "${plist_tmp}" "${target_plist}"
}

config_value() {
  /usr/bin/plutil -extract "$1" raw -o - "${CONFIG_FILE}"
}

config_value_optional() {
  local extracted
  extracted="$(/usr/bin/plutil -extract "$1" raw -o - "${CONFIG_FILE}" 2>/dev/null)" \
    || extracted=""
  print -r -- "${extracted}"
}

load_config() {
  [[ -f "${CONFIG_FILE}" && ! -L "${CONFIG_FILE}" ]] \
    || die "bridge is not installed"
  cfg_label="$(config_value label)"
  cfg_profile="$(config_value profile)"
  cfg_workspace="$(config_value workspace)"
  cfg_codex_bin="$(config_value codex_bin)"
  cfg_tunnel_client_bin="$(config_value tunnel_client_bin)"
  cfg_python_bin="$(config_value python_bin)"
  cfg_preset="$(config_value preset)"
  cfg_sandbox="$(config_value sandbox)"
  cfg_approval_policy="$(config_value approval_policy)"
  cfg_runtime_guard="$(config_value runtime_guard)"
  cfg_runtime_managed_repo="$(config_value_optional runtime_managed_repo)"
  cfg_runtime_wrapper="$(config_value runtime_wrapper)"
  cfg_managed_registry="$(config_value_optional managed_registry)"
  if [[ -z "${cfg_runtime_managed_repo}" ]]; then
    cfg_runtime_managed_repo="${RUNTIME_DIR}/managed_repo.py"
  fi
  if [[ -z "${cfg_managed_registry}" ]]; then
    cfg_managed_registry="${STATE_DIR}/managed-repos.v1.json"
  fi
  cfg_workspace_new_project_skill="$(config_value_optional workspace_new_project_skill)"
  if [[ -z "${cfg_workspace_new_project_skill}" ]]; then
    cfg_workspace_new_project_skill="${RUNTIME_DIR}/skills/workspace-new-project/SKILL.md"
  fi
  cfg_health_url_file="$(config_value health_url_file)"
  cfg_stdout_log="$(config_value stdout_log)"
  cfg_stderr_log="$(config_value stderr_log)"
  cfg_target_plist="${LAUNCH_AGENTS_DIR}/${cfg_label}.plist"
  cfg_job="${DOMAIN}/${cfg_label}"
}

revoke_bridge_jobs() {
  local job_root
  [[ -x "${cfg_python_bin}" && -f "${SOURCE_GUARD}" && ! -L "${SOURCE_GUARD}" ]] \
    || die "cannot revoke jobs without the trusted Guard runtime"
  for job_root in "${STATE_DIR}/jobs-v2" "${STATE_DIR}/jobs-v3" "${STATE_DIR}/jobs-v4"; do
    [[ -e "${job_root}" ]] || continue
    [[ -d "${job_root}" && ! -L "${job_root}" ]] \
      || die "refusing unsafe job state root"
    "${cfg_python_bin}" "${SOURCE_GUARD}" --revoke-jobs "${job_root:A}" \
      || die "failed to revoke bridge-owned background jobs"
  done
}

purge_bridge_job_state() {
  local job_root
  for job_root in "${STATE_DIR}/jobs-v2" "${STATE_DIR}/jobs-v3" "${STATE_DIR}/jobs-v4"; do
    [[ -e "${job_root}" ]] || continue
    [[ -d "${job_root}" && ! -L "${job_root}" ]] \
      || die "refusing unsafe job state root"
    "${cfg_python_bin}" "${SOURCE_GUARD}" --purge-jobs "${job_root:A}" \
      || die "failed to purge bridge-owned job state"
  done
}

job_is_loaded() {
  /bin/launchctl print "$1" >/dev/null 2>&1
}

wait_until_unloaded() {
  local job="$1"
  local attempt
  for attempt in {1..40}; do
    job_is_loaded "${job}" || return 0
    /bin/sleep 0.25
  done
  die "LaunchAgent did not finish unloading"
}

health_base_url() {
  local url
  [[ -s "${cfg_health_url_file}" ]] || return 1
  url="$(/usr/bin/tr -d '\r\n' < "${cfg_health_url_file}")"
  case "${url}" in
    http://127.0.0.1:*|http://localhost:*) print -r -- "${url}" ;;
    *) return 1 ;;
  esac
}

health_ready() {
  local url
  url="$(health_base_url)" || return 1
  /usr/bin/curl --fail --silent --show-error --max-time 2 "${url}/healthz" >/dev/null || return 1
  /usr/bin/curl --fail --silent --show-error --max-time 2 "${url}/readyz" >/dev/null || return 1
}

control_plane_ready() {
  local url metrics last_success now
  url="$(health_base_url)" || return 1
  metrics="$(/usr/bin/curl --fail --silent --show-error --max-time 2 "${url}/metrics")" || return 1
  last_success="$(print -rn -- "${metrics}" | /usr/bin/awk '$1 ~ /^commands_poll_last_successful_timestamp_seconds/ { print $2; exit }')"
  [[ -n "${last_success}" ]] || return 1
  now="$(/bin/date +%s)"
  /usr/bin/awk -v last="${last_success}" -v current="${now}" 'BEGIN {
    age = current - last
    exit !(last > 0 && age >= -5 && age <= 90)
  }'
}

wait_until_ready() {
  local attempt
  for attempt in {1..${LOCAL_READY_ATTEMPTS}}; do
    health_ready && break
    /bin/sleep 0.5
  done
  health_ready || die "Tunnel did not become locally ready"
  for attempt in {1..${CONTROL_PLANE_ATTEMPTS}}; do
    control_plane_ready && return 0
    /bin/sleep 0.5
  done
  die "Tunnel did not record a recent control-plane poll"
}

runtime_doctor() {
  load_config
  validate_label "${cfg_label}"
  validate_profile "${cfg_profile}"
  [[ "${cfg_runtime_guard}" == "${RUNTIME_DIR}/codex-mcp-guard.py" \
    && "${cfg_runtime_managed_repo}" == "${RUNTIME_DIR}/managed_repo.py" \
    && "${cfg_runtime_wrapper}" == "${RUNTIME_DIR}/run-guard.zsh" \
    && "${cfg_managed_registry}" == "${STATE_DIR}/managed-repos.v1.json" \
    && "${cfg_workspace_new_project_skill}" == "${RUNTIME_DIR}/skills/workspace-new-project/SKILL.md" \
    && "${cfg_health_url_file}" == "${STATE_DIR}/health.url" \
    && "${cfg_stdout_log}" == "${LOG_DIR}/tunnel.stdout.log" \
    && "${cfg_stderr_log}" == "${LOG_DIR}/tunnel.stderr.log" ]] \
    || die "generated paths do not match this installation"
  [[ "$(real_directory "${cfg_workspace}")" == "${cfg_workspace}" ]] \
    || die "installed workspace is not canonical"
  [[ "$(real_executable "${cfg_codex_bin}")" == "${cfg_codex_bin}" \
    && "$(real_executable "${cfg_tunnel_client_bin}")" == "${cfg_tunnel_client_bin}" \
    && "$(real_executable "${cfg_python_bin}")" == "${cfg_python_bin}" ]] \
    || die "installed executable path is not canonical"
  [[ -f "${cfg_target_plist}" && ! -L "${cfg_target_plist}" ]] || die "generated LaunchAgent is missing"
  [[ -x "${cfg_runtime_guard}" && ! -L "${cfg_runtime_guard}" ]] || die "runtime Guard is missing"
  [[ -f "${cfg_runtime_managed_repo}" && ! -L "${cfg_runtime_managed_repo}" ]] || die "managed repository runtime is missing"
  [[ -x "${cfg_runtime_wrapper}" && ! -L "${cfg_runtime_wrapper}" ]] || die "runtime wrapper is missing"
  [[ -f "${cfg_workspace_new_project_skill}" && ! -L "${cfg_workspace_new_project_skill}" ]] || die "runtime workspace-new-project Skill is missing"
  [[ -x "${RUNTIME_DIR}/skills/workspace-new-project/scripts/create_workspace_project.sh" \
    && ! -L "${RUNTIME_DIR}/skills/workspace-new-project/scripts/create_workspace_project.sh" ]] \
    || die "runtime workspace-new-project bootstrap is missing"
  /usr/bin/plutil -lint "${CONFIG_FILE}" >/dev/null || die "config plist is invalid"
  /usr/bin/plutil -lint "${cfg_target_plist}" >/dev/null || die "LaunchAgent plist is invalid"
  "${cfg_tunnel_client_bin}" --version >/dev/null 2>&1 || die "tunnel-client is not usable"
  "${cfg_tunnel_client_bin}" doctor --profile "${cfg_profile}" >/dev/null || die "Tunnel profile doctor failed"
  "${cfg_codex_bin}" --version >/dev/null 2>&1 || die "Codex is not usable"
  "${cfg_codex_bin}" mcp-server --help >/dev/null 2>&1 || die "Codex MCP server is unavailable"
  "${cfg_python_bin}" "${cfg_runtime_guard}" --help >/dev/null 2>&1 || die "runtime Guard configuration surface is unavailable"
  case "${cfg_preset}:${cfg_sandbox}:${cfg_approval_policy}" in
    personal-full-control:danger-full-access:never|workspace-safe:workspace-write:on-request|managed-repo:workspace-write:never) ;;
    *) die "installed policy pair is unsupported" ;;
  esac
  if [[ "${cfg_preset}" == "managed-repo" ]]; then
    [[ -f "${cfg_managed_registry}" && ! -L "${cfg_managed_registry}" ]] \
      || die "managed repository registry is missing"
    "${cfg_python_bin}" "${cfg_runtime_managed_repo}" \
      --registry "${cfg_managed_registry}" verify >/dev/null \
      || die "managed repository registry verification failed"
  fi
}

prepare_reinstall() {
  local replacement_label="$1"
  [[ -e "${CONFIG_FILE}" ]] || return 0
  load_config
  validate_label "${cfg_label}"
  [[ "${cfg_target_plist}" == "${LAUNCH_AGENTS_DIR}/${cfg_label}.plist" ]] \
    || die "previous LaunchAgent path is invalid"
  if job_is_loaded "${cfg_job}"; then
    (( no_start == 0 )) \
      || die "cannot use --no-start while the previous LaunchAgent is loaded"
    /bin/launchctl bootout "${cfg_job}"
    wait_until_unloaded "${cfg_job}"
  fi
  revoke_bridge_jobs
  if [[ "${cfg_label}" != "${replacement_label}" ]]; then
    remove_exact_file "${cfg_target_plist}" "${LAUNCH_AGENTS_DIR}/${cfg_label}.plist"
  fi
}

install_service() {
  local profile workspace codex_bin tunnel_client_bin python_bin label preset policy sandbox approval_policy target_plist job
  profile="${profile_arg:-${DEFAULT_PROFILE}}"
  workspace="$(real_directory "${workspace_arg:-${DEFAULT_WORKSPACE}}")"
  label="${label_arg:-${DEFAULT_LABEL}}"
  [[ -n "${preset_arg}" ]] || die "install requires an explicit --preset"
  preset="${preset_arg}"
  validate_profile "${profile}"
  validate_label "${label}"
  codex_bin="$(resolve_codex)"
  tunnel_client_bin="$(resolve_tunnel_client)"
  python_bin="$(resolve_python)"
  policy="$(policy_for_preset "${preset}")"
  sandbox="${policy%%$'\t'*}"
  approval_policy="${policy#*$'\t'}"
  [[ -f "${SOURCE_SUPERVISION}" && -f "${SOURCE_GUARD}" && -f "${SOURCE_MANAGED_REPO}" && -f "${SOURCE_RUNTIME_WRAPPER}" \
    && -f "${SOURCE_WORKSPACE_SKILL_DIR}/SKILL.md" \
    && -x "${SOURCE_WORKSPACE_SKILL_DIR}/scripts/create_workspace_project.sh" ]] \
    || die "plugin runtime sources are incomplete"
  if [[ "${preset}" == "managed-repo" ]]; then
    [[ -f "${STATE_DIR}/managed-repos.v1.json" && ! -L "${STATE_DIR}/managed-repos.v1.json" ]] \
      || die "managed repository registry must exist before installation"
    "${python_bin}" "${SOURCE_MANAGED_REPO}" \
      --registry "${STATE_DIR}/managed-repos.v1.json" verify >/dev/null \
      || die "managed repository registry verification failed"
    verify_managed_policy_support "${codex_bin}" "${workspace}"
  fi
  "${tunnel_client_bin}" doctor --profile "${profile}" >/dev/null || die "Tunnel profile doctor failed"
  prepare_reinstall "${label}"
  write_generated_files "${label}" "${profile}" "${workspace}" "${codex_bin}" "${tunnel_client_bin}" "${python_bin}" "${preset}" "${sandbox}" "${approval_policy}"
  target_plist="${LAUNCH_AGENTS_DIR}/${label}.plist"
  job="${DOMAIN}/${label}"
  if (( no_start == 0 )); then
    if job_is_loaded "${job}"; then
      /bin/launchctl bootout "${job}"
      wait_until_unloaded "${job}"
    fi
    /bin/launchctl enable "${job}"
    /bin/launchctl bootstrap "${DOMAIN}" "${target_plist}"
    /bin/launchctl kickstart -k "${job}"
    load_config
    wait_until_ready
    log "installed status=ready label=${label} preset=${preset}"
  else
    log "installed status=configured label=${label} preset=${preset}"
  fi
}

restart_service() {
  runtime_doctor
  (( no_start == 0 )) || {
    log "restart skipped for isolated install"
    return 0
  }
  job_is_loaded "${cfg_job}" || die "LaunchAgent is not loaded"
  /bin/launchctl bootout "${cfg_job}"
  wait_until_unloaded "${cfg_job}"
  revoke_bridge_jobs
  /usr/bin/install -m 700 "${SOURCE_GUARD}" "${cfg_runtime_guard}"
  /usr/bin/install -m 600 "${SOURCE_MANAGED_REPO}" "${cfg_runtime_managed_repo}"
  [[ ! -L "${RUNTIME_DIR}/supervision.py" ]] || die "unsafe supervision helper"
  /usr/bin/install -m 600 "${SOURCE_SUPERVISION}" "${RUNTIME_DIR}/supervision.py"
  /usr/bin/install -m 700 "${SOURCE_RUNTIME_WRAPPER}" "${cfg_runtime_wrapper}"
  /usr/bin/install -m 600 "${SOURCE_WORKSPACE_SKILL_DIR}/SKILL.md" "${cfg_workspace_new_project_skill}"
  /usr/bin/install -m 700 "${SOURCE_WORKSPACE_SKILL_DIR}/scripts/create_workspace_project.sh" \
    "${RUNTIME_DIR}/skills/workspace-new-project/scripts/create_workspace_project.sh"
  /bin/launchctl bootstrap "${DOMAIN}" "${cfg_target_plist}"
  /bin/launchctl kickstart -k "${cfg_job}"
  wait_until_ready
  log "restarted status=ready label=${cfg_label}"
}

status_service() {
  runtime_doctor
  if (( no_start == 1 )); then
    log "status=configured label=${cfg_label} preset=${cfg_preset}"
    return 0
  fi
  job_is_loaded "${cfg_job}" || die "LaunchAgent is not loaded"
  health_ready || die "Tunnel is not locally ready"
  control_plane_ready || die "Tunnel control-plane poll is stale"
  log "status=ready label=${cfg_label} preset=${cfg_preset}"
}

stop_service() {
  load_config
  if (( no_start == 1 )); then
    log "stop skipped for isolated install"
    return 0
  fi
  if job_is_loaded "${cfg_job}"; then
    /bin/launchctl bootout "${cfg_job}"
    wait_until_unloaded "${cfg_job}"
  fi
  revoke_bridge_jobs
  log "status=stopped label=${cfg_label}"
}

remove_exact_file() {
  local target="$1"
  local expected="$2"
  [[ "${target}" == "${expected}" ]] \
    || die "refusing unexpected uninstall target: ${target}"
  if [[ -e "${target}" ]]; then
    [[ -f "${target}" && ! -L "${target}" ]] || die "refusing non-regular uninstall target"
    /bin/rm -f -- "${target}"
  fi
}

uninstall_service() {
  load_config
  if (( no_start == 0 )) && job_is_loaded "${cfg_job}"; then
    /bin/launchctl bootout "${cfg_job}"
    wait_until_unloaded "${cfg_job}"
  fi
  revoke_bridge_jobs
  purge_bridge_job_state
  remove_exact_file "${cfg_target_plist}" "${LAUNCH_AGENTS_DIR}/${cfg_label}.plist"
  remove_exact_file "${cfg_runtime_guard}" "${RUNTIME_DIR}/codex-mcp-guard.py"
  remove_exact_file "${cfg_runtime_managed_repo}" "${RUNTIME_DIR}/managed_repo.py"
  remove_exact_file "${RUNTIME_DIR}/supervision.py" "${RUNTIME_DIR}/supervision.py"
  remove_exact_file "${cfg_runtime_wrapper}" "${RUNTIME_DIR}/run-guard.zsh"
  remove_exact_file "${cfg_workspace_new_project_skill}" "${RUNTIME_DIR}/skills/workspace-new-project/SKILL.md"
  remove_exact_file "${RUNTIME_DIR}/skills/workspace-new-project/scripts/create_workspace_project.sh" \
    "${RUNTIME_DIR}/skills/workspace-new-project/scripts/create_workspace_project.sh"
  remove_exact_file "${cfg_health_url_file}" "${STATE_DIR}/health.url"
  remove_exact_file "${cfg_stdout_log}" "${LOG_DIR}/tunnel.stdout.log"
  remove_exact_file "${cfg_stderr_log}" "${LOG_DIR}/tunnel.stderr.log"
  remove_exact_file "${CONFIG_FILE}" "${STATE_DIR}/config.plist"
  /bin/rmdir "${RUNTIME_DIR}/skills/workspace-new-project/scripts" \
    "${RUNTIME_DIR}/skills/workspace-new-project" "${RUNTIME_DIR}/skills" \
    "${RUNTIME_DIR}" "${STATE_DIR}" "${LOG_DIR}" 2>/dev/null || true
  log "uninstalled label=${cfg_label}; external Tunnel profile preserved"
}

parse_options "$@"
# Generic maintenance cannot preserve the explicit-store recovery contract.
# This runs before config-selected executables, service changes or legacy GC.
case "${action}" in
  install|restart|stop|uninstall)
    [[ "${preset_arg}" != "managed-repo" ]] || die "EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY"
    [[ -f "${SCRIPT_DIR}/guard-store-config.py" && ! -L "${SCRIPT_DIR}/guard-store-config.py" ]] \
      || die "OPERATOR_CONFIG_REJECTED"
    # Existing test overrides must not hide a configured recovery installation.
    /usr/bin/python3 -I "${SCRIPT_DIR}/guard-store-config.py" maintenance \
      "${HOME}/Library/Application Support/chatgpt-codex-bridge/config.plist" || exit 64
    if [[ "${CONFIG_FILE}" != "${HOME}/Library/Application Support/chatgpt-codex-bridge/config.plist" ]]; then
      /usr/bin/python3 -I "${SCRIPT_DIR}/guard-store-config.py" maintenance "${CONFIG_FILE}" || exit 64
    fi
    ;;
esac
case "${action}" in
  install) install_service ;;
  doctor|status) status_service ;;
  restart) restart_service ;;
  stop) stop_service ;;
  uninstall) uninstall_service ;;
  -h|--help|"") usage ;;
  *) usage; exit 2 ;;
esac
