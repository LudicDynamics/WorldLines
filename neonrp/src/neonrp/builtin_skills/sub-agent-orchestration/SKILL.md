---
name: sub-agent-orchestration
description: Build-mode workflow for creating and delegating to sub-agents.
---

# Purpose

Use this skill when you need to create or coordinate sub-agents in a NeonRP project.

# When To Use

- The user asks to "create an agent" or "set up sub-agents".
- The task benefits from delegation (writer, combat designer, world-builder, QA, etc.).
- You need a repeatable setup workflow in build mode.

# Build-Mode Creation Workflow

1. Pick a unique `agent_id` (example: `lore-writer`).
2. Create directory `agents/<agent_id>/`.
3. Create `agents/<agent_id>/agent.json` with:
   - `id`, `name`, `description`, `version`
   - `system_prompt` (usually `"system.md"`)
   - `permissions` (`read_globs`, `deny_globs`, `direct_write_globs`)
4. Create `agents/<agent_id>/system.md`:
   - Role, boundaries, style, and tool-usage expectations
   - Any domain constraints (lore canon, combat math, tone, etc.)
5. Validate by listing/inspecting agent files.
6. Delegate with `task(agent_id, prompt, resume_run_id?)`.

# Delegation Checklist

- `prompt` must be self-contained: include goals, constraints, paths, acceptance criteria.
- Reference exact files/entities the sub-agent should read first.
- Ask for explicit output expectations (files to change, style constraints, tests/checks).

# Tool Patterns

- Create/update files: `write_file`, `edit_file`
- Verify files: `read_file`, `glob`, `grep`
- Delegate execution: `task(agent_id, prompt, resume_run_id?)`

# Notes By Mode

- `build`: can create new sub-agents and delegate immediately.
- `sandbox` / `play`: focus on delegation and task execution; do not assume agent scaffolding is needed during normal turns.
