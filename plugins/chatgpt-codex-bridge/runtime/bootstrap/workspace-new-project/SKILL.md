---
name: workspace-new-project
description: Create or initialize a project root with spec-driven docs, ADRs, source layout, AGENTS.md, and ignored project memory. Use first for every ChatGPT-led new project; use --here when the bridge already allocated the final root.
---

# Workspace New Project

Initialize the final project directory before implementation.

## Bridge mode

The ChatGPT Codex Bridge has already created and selected the final project
root. Run the bundled script from this Skill directory in current-directory
mode:

```zsh
/bin/zsh scripts/create_workspace_project.sh --here
```

Do not create a nested child directory. After initialization, write or update
the feature requirements, design, tasks, and any architecture-shaping ADR before
production code. Keep all subsequent command workdirs at the final project root.

## Direct mode

Outside the bridge, use `--base-dir <absolute-parent> <project-name>`. If the
current directory already has strong project markers such as `.git`,
`AGENTS.md`, `docs/specs`, or a manifest, remain in existing-project flow.

## Acceptance

Confirm the final path and require `AGENTS.md`, `README.md`, `.gitignore`,
`docs/specs/`, `docs/adr/`, `src/`, and `.project-memory/`. Project memory MUST
remain ignored by Git.
