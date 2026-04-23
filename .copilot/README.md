# Copilot CLI Configuration

This directory is the GitHub Copilot CLI configuration directory for this repository, parallel to `.claude/`, `.gemini/`, and `.codex/`.

## Workflow Skills

Copilot CLI automatically discovers project skills from `.claude/commands/`. No separate Copilot command files are needed — the full workflow (`/plan-issue`, `/implement`, `/finalize`, `/close-issue`, `/where-am-i`, etc.) is available out of the box.

## Dangerous Command Hook

The dangerous command hook is wired in `.github/hooks/copilot-hooks.json`. It blocks shell commands identified as dangerous before they execute:

```
.github/hooks/copilot-hooks.json → tools/hooks/ai/block-dangerous-commands.py
```

No changes to this hook are needed when adding new slash commands.

## Subagent / Implement Worker

The `implement-worker` subagent used by `/implement` is defined in `.claude/agents/implement-worker.md`. Copilot CLI's `task` tool reads this file when spawning the subagent.

## Temporary Files

Agents must write temporary files to `tmp/agents/copilot/` (not `/tmp/`). Include a context identifier (issue number, PR number, or task ID) in the filename to avoid collisions.

## See Also

- `.claude/commands/` — slash command definitions (auto-discovered by Copilot CLI)
- `.claude/agents/implement-worker.md` — implement-worker subagent definition
- `.github/hooks/copilot-hooks.json` — dangerous command hook wiring
- `docs/development/ai/slash-commands.md` — full workflow and command reference
- `docs/development/ai/command-blocking.md` — hook documentation
