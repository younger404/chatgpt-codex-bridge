#!/bin/zsh
set -euo pipefail

readonly CONFIG_FILE="${CHATGPT_CODEX_BRIDGE_CONFIG:-}"
reject_config() { print -u2 -r -- "OPERATOR_CONFIG_REJECTED"; exit 64; }
[[ "${CONFIG_FILE}" == /* && -f "${CONFIG_FILE}" && ! -L "${CONFIG_FILE}" ]] || reject_config

value() {
  /usr/bin/plutil -extract "$1" raw -o - "${CONFIG_FILE}" 2>/dev/null
}

readonly PRESET="$(value preset)" || reject_config
if [[ "${PRESET}" == "managed-repo" ]]; then
  [[ -f "${0:A:h}/guard-store-config.py" && ! -L "${0:A:h}/guard-store-config.py" ]] || reject_config
  /usr/bin/python3 -I "${0:A:h}/guard-store-config.py" validate "${CONFIG_FILE}" || exit 64
fi
readonly PYTHON_BIN="$(value python_bin)"
readonly GUARD="$(value runtime_guard)"
readonly WORKSPACE="$(value workspace)"
readonly CODEX_BIN="$(value codex_bin)"
readonly SANDBOX="$(value sandbox)"
readonly APPROVAL_POLICY="$(value approval_policy)"
readonly MANAGED_REGISTRY="$(value managed_registry)"
readonly WORKSPACE_NEW_PROJECT_SKILL="$(value workspace_new_project_skill)"

[[ -x "${PYTHON_BIN}" && -f "${GUARD}" && ! -L "${GUARD}" ]] || reject_config
typeset -a guard_arguments
guard_arguments=(
  --workspace "${WORKSPACE}"
  --codex-bin "${CODEX_BIN}"
  --sandbox "${SANDBOX}"
  --approval-policy "${APPROVAL_POLICY}"
  --preset "${PRESET}"
  --workspace-new-project-skill "${WORKSPACE_NEW_PROJECT_SKILL}"
)
if [[ "${PRESET}" == "managed-repo" ]]; then
  readonly JOB_STATE_DIR="$(value job_state_dir)"
  guard_arguments+=(--managed-registry "${MANAGED_REGISTRY}" --job-state-dir "${JOB_STATE_DIR}")
fi
exec "${PYTHON_BIN}" "${GUARD}" "${guard_arguments[@]}"
