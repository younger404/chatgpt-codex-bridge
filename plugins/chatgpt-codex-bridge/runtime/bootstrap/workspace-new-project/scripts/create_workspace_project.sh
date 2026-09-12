#!/bin/zsh
set -euo pipefail

usage() {
  print -u2 -- "Usage: create_workspace_project.sh --here | --base-dir <absolute-parent> <project-name>"
}

mode=""
base_dir="${HOME}/codex-workspace"
name=""

while (( $# > 0 )); do
  case "$1" in
    --here) mode="here"; shift ;;
    --base-dir)
      (( $# >= 2 )) || { usage; exit 64; }
      base_dir="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    -*) usage; exit 64 ;;
    *)
      [[ -z "${name}" ]] || { usage; exit 64; }
      name="$1"
      shift
      ;;
  esac
done

if [[ "${mode}" == "here" ]]; then
  [[ -z "${name}" ]] || { usage; exit 64; }
  project_path="${PWD:A}"
  [[ -d "${project_path}" && ! -L "${project_path}" ]] || exit 64
else
  [[ "${base_dir}" == /* && -d "${base_dir}" && ! -L "${base_dir}" ]] || exit 64
  [[ -n "${name}" && "${name}" != "." && "${name}" != ".." && "${name}" != */* ]] || exit 64
  project_path="${base_dir:A}/${name}"
  [[ ! -e "${project_path}" ]] || { print -u2 -- "Project already exists: ${project_path}"; exit 73; }
  /bin/mkdir -- "${project_path}"
fi

/bin/mkdir -p -- \
  "${project_path}/docs/specs" \
  "${project_path}/docs/adr" \
  "${project_path}/src" \
  "${project_path}/.project-memory/events" \
  "${project_path}/.project-memory/summaries" \
  "${project_path}/.project-memory/decisions"

[[ -f "${project_path}/.gitignore" ]] || : > "${project_path}/.gitignore"
/usr/bin/grep -qxF '.project-memory/' "${project_path}/.gitignore" 2>/dev/null \
  || print -r -- '.project-memory/' >> "${project_path}/.gitignore"

if [[ ! -f "${project_path}/README.md" ]]; then
  /usr/bin/printf '%s\n' '# Project' '' 'Spec-driven project. Start in docs/specs before implementation.' > "${project_path}/README.md"
fi

if [[ ! -f "${project_path}/AGENTS.md" ]]; then
  /usr/bin/printf '%s\n' \
    '# Agent Instructions' '' \
    'Treat versioned specs as the source of truth.' '' \
    '- Write requirements, design, and tasks before non-trivial code.' \
    '- Record architecture decisions under docs/adr/.' \
    '- Work one task at a time and verify before completion.' \
    '- Keep .project-memory/ out of Git.' > "${project_path}/AGENTS.md"
fi

if [[ ! -f "${project_path}/docs/specs/README.md" ]]; then
  /usr/bin/printf '%s\n' '# Specs' '' 'Create docs/specs/<feature>/{requirements,design,tasks}.md.' > "${project_path}/docs/specs/README.md"
fi

if [[ ! -f "${project_path}/docs/adr/README.md" ]]; then
  /usr/bin/printf '%s\n' '# ADRs' '' 'Use Context / Decision / Consequences.' > "${project_path}/docs/adr/README.md"
fi

if [[ ! -f "${project_path}/.project-memory/summaries/short.md" ]]; then
  /usr/bin/printf '%s\n' '# Short Summary' '' 'Rolling high-signal project summary.' > "${project_path}/.project-memory/summaries/short.md"
fi

print -r -- "${project_path}"
