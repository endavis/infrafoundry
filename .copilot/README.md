# Copilot CLI Configuration

This directory is the GitHub Copilot CLI configuration directory for this repository, parallel to `.claude/`, `.gemini/`, and `.codex/`.

**Important:** Copilot CLI does **not** read any `commands/` directory. Per the installed `@github/copilot` SDK (`sdk/index.d.ts`), Copilot only discovers project skills from `skills/` paths: `.github/skills/`, `.agents/skills/`, and `.claude/skills/` (plus the corresponding personal paths under `~/`).

## Workflow Skills

Copilot-host review skills (self-action and cross-agent bridges) live under `.github/skills/<target>-<action>/SKILL.md`. Because skill names are directory names and cannot contain colons, the slash surface uses hyphen naming:

- **Self-action:** `/copilot-review`, `/copilot-adversarial-review`
- **To Claude:** `/claude-review`, `/claude-adversarial-review`
- **To Codex:** `/codex-review`, `/codex-adversarial-review`
- **To Antigravity:** `/antigravity-review`, `/antigravity-adversarial-review`

The `plan`/`implement` cells are replaced by the shared `implement-issue` skill in a later pyproject-template sync step (#1054).

The `multi-*` orchestrators (`/multi-plan`, `/multi-review`, `/multi-adversarial-review`) come from `.agents/skills/` (interoperable Codex skill path) and are auto-discovered by Copilot.

## Known limitation: delegate-* skill bleed

Copilot reads `.agents/skills/`, which contains the `delegate-<target>-<action>` skills (shared by Codex and Antigravity). Those surface as `/delegate-...` slash commands alongside the canonical Copilot ones. They shell out with Codex/Antigravity syntax and are not intended for Copilot; use the `.github/skills/` entries above instead.

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

- `.github/skills/<target>-<action>/SKILL.md` — Copilot-host workflow skills (8 files). `.github/skills/` is used (instead of `.claude/skills/`) because it's the only Copilot project skill path that Claude does not also read — avoids surfacing duplicate slash commands in Claude.
- `.agents/skills/` — interoperable Codex skill path, also read by Copilot
- `.claude/agents/implement-worker.md` — implement-worker subagent definition
- `.github/hooks/copilot-hooks.json` — dangerous command hook wiring
- `.github/instructions/README.md` — per-stack instruction file pattern for Copilot
- `docs/development/ai/slash-commands.md` — full workflow and command reference
- `docs/development/ai/cross-agent-delegation.md` — cross-agent matrix and per-host invocation
- `docs/development/ai/command-blocking.md` — hook documentation
