#!/bin/zsh

set -u

if (( $# != 4 )) \
  || [[ "$1" != "--approved-root" ]] \
  || [[ -z "$2" ]] \
  || [[ "$3" != "--repo" ]] \
  || [[ -z "$4" ]]; then
  print -u2 -r -- "Usage: check-sandbox-repo.zsh --approved-root <directory> --repo <repository>"
  exit 64
fi

readonly approved_input="${2:a}"
readonly repo_input="${4:a}"

boundary_status="FAIL"
symlink_status="FAIL"
git_repo_status="FAIL"
branch_status="FAIL"
baseline_status="FAIL"
symlink_entries_status="FAIL"
sensitive_files_status="FAIL"

approved_resolved=""
repo_resolved=""

if [[ -d "${approved_input}" && ! -L "${approved_input}" ]]; then
  approved_resolved="${approved_input:A}"
fi

if [[ -d "${repo_input}" ]]; then
  repo_resolved="${repo_input:A}"
fi

if [[ -n "${approved_resolved}" && -n "${repo_resolved}" ]]; then
  case "${repo_resolved}" in
    "${approved_resolved}"/*) boundary_status="PASS" ;;
  esac
fi

if [[ -n "${repo_resolved}" && ! -L "${repo_input}" ]]; then
  symlink_status="PASS"
fi

git_root=""
if [[ "${boundary_status}" == "PASS" && "${symlink_status}" == "PASS" ]]; then
  git_root="$(command git -C "${repo_resolved}" rev-parse --show-toplevel 2>/dev/null)"
  git_root_status=$?
  if (( git_root_status == 0 )) \
    && [[ -n "${git_root}" ]] \
    && [[ "${git_root:A}" == "${repo_resolved}" ]]; then
    git_repo_status="PASS"
  fi
fi

if [[ "${git_repo_status}" == "PASS" ]]; then
  branch_name="$(command git -C "${repo_resolved}" symbolic-ref --quiet --short HEAD 2>/dev/null)"
  branch_name_status=$?
  if (( branch_name_status == 0 )) \
    && [[ -n "${branch_name}" ]] \
    && [[ "${branch_name}" != "main" ]] \
    && [[ "${branch_name}" != "master" ]]; then
    branch_status="PASS"
  fi

  porcelain="$(command git -C "${repo_resolved}" status --porcelain=v1 --untracked-files=all 2>/dev/null)"
  porcelain_status=$?
  if (( porcelain_status == 0 )) && [[ -z "${porcelain}" ]]; then
    baseline_status="PASS"
  fi

  symlink_entry="$(
    command find -x "${repo_resolved}" \
      \( -path "${repo_resolved}/.git" -o -path "${repo_resolved}/.git/*" \) -prune \
      -o -type l -print -quit 2>/dev/null
  )"
  symlink_scan_status=$?
  if (( symlink_scan_status == 0 )) && [[ -z "${symlink_entry}" ]]; then
    symlink_entries_status="PASS"
  fi

  sensitive_files_status="PASS"
  scan_complete="NO"
  while IFS= read -r -d $'\0' candidate; do
    if [[ -z "${candidate}" ]]; then
      scan_complete="YES"
      continue
    fi

    base_name="${candidate:t:l}"
    case "${base_name}" in
      .env|.env.*|id_rsa|id_dsa|id_ecdsa|id_ed25519|*.pem|*.key|*.p12|*.pfx|*.ppk|credentials|credentials.*|*credential*.json|*private*key*|*secret*.json)
        sensitive_files_status="FAIL"
        break
        ;;
    esac

    command grep -E -q -- '-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----' "${candidate}" 2>/dev/null
    grep_status=$?
    if (( grep_status == 0 )); then
      sensitive_files_status="FAIL"
      break
    fi
    if (( grep_status > 1 )); then
      sensitive_files_status="FAIL"
      break
    fi
  done < <(
    command find -x "${repo_resolved}" \
      \( -path "${repo_resolved}/.git" -o -path "${repo_resolved}/.git/*" \) -prune \
      -o -type f -print0 2>/dev/null \
      && command printf '\0'
  )
  if [[ "${sensitive_files_status}" == "PASS" && "${scan_complete}" != "YES" ]]; then
    sensitive_files_status="FAIL"
  fi
fi

overall_status="FAIL"
if [[ "${boundary_status}" == "PASS" \
   && "${symlink_status}" == "PASS" \
   && "${git_repo_status}" == "PASS" \
   && "${branch_status}" == "PASS" \
   && "${baseline_status}" == "PASS" \
   && "${symlink_entries_status}" == "PASS" \
   && "${sensitive_files_status}" == "PASS" ]]; then
  overall_status="PASS"
fi

print -r -- "boundary=${boundary_status}"
print -r -- "symlink=${symlink_status}"
print -r -- "git_repo=${git_repo_status}"
print -r -- "branch=${branch_status}"
print -r -- "baseline=${baseline_status}"
print -r -- "symlink_entries=${symlink_entries_status}"
print -r -- "sensitive_files=${sensitive_files_status}"
print -r -- "overall_status=${overall_status}"

[[ "${overall_status}" == "PASS" ]]
