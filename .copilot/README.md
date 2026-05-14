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

## Per-Stack Instructions

GitHub Copilot natively discovers instruction files placed in `.github/instructions/` and named
`NAME.instructions.md`. Each file begins with YAML frontmatter (`applyTo: '<glob>'`) that gates
it to a specific path scope, followed by a skill-gated, numbered self-check body (≤30 lines) and
an `Observed failures:` footer.

This is the Copilot equivalent of `.claude/rules/` (loaded via `@import` in `.claude/CLAUDE.md`)
and `.gemini/rules/` (loaded via `@` directive in `GEMINI.md`). The discipline — build from
observed failures, not generic advice — is shared across all three CLIs.

See [`.github/instructions/README.md`](../.github/instructions/README.md) for the full pattern,
file structure, and a worked example.

## See Also

- `.claude/commands/` — slash command definitions (auto-discovered by Copilot CLI)
- `.claude/agents/implement-worker.md` — implement-worker subagent definition
- `.github/hooks/copilot-hooks.json` — dangerous command hook wiring
- `.github/instructions/README.md` — per-stack instruction file pattern for Copilot
- `docs/development/ai/slash-commands.md` — full workflow and command reference
- `docs/development/ai/command-blocking.md` — hook documentation
