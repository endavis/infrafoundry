# Cross-Agent Delegation Matrix

A consistent, explicit-invocation interface that lets any of the four supported AI CLIs (Claude Code, Codex CLI, Gemini CLI, Copilot CLI) hand a task — `plan`, `implement`, `review`, or `adversarial-review` — to any of the other three.

## Why this exists

Each agent already drives *itself* through the issue-driven workflow (`/<ai>:plan`, `/<ai>:implement`, `/ghi-finalize`). This matrix adds the missing piece: deliberate, user-invoked handoff *between* agents, without depending on third-party plugins like `openai/codex-plugin-cc` or community Gemini/Copilot forks.

The matrix replaces what would otherwise be a patchwork of inconsistent third-party plugins. It runs on top of the CLIs' existing non-interactive modes (`-p` / `exec`) and uses the same command names across all hosts, so users learn the surface once.

## Convention

`<prefix><target>:<action>` where:

- **Prefix:** `/` on Claude Code, Gemini CLI, and Copilot CLI; `$` on Codex CLI (Codex's repo-defined commands are skills, not slash commands; OpenAI deprecated `~/.codex/prompts/`).
- **Target:** `claude`, `codex`, `gemini`, `copilot` — the agent to invoke. Can be the **same** agent (self-action) or one of the other three (cross-agent delegation).
- **Action:** `plan`, `implement`, `review`, `adversarial-review`.

Self-action (`/claude:plan`, `/gemini:implement`, `$codex-review`, etc.) and cross-agent delegation (`/gemini:plan` from Claude, `/claude:plan` from Gemini, etc.) share the same naming convention. For self-action the command body runs the work natively in the host agent; for cross-agent delegation it shells out to the target CLI.

| Action | Argument | Notes |
| :--- | :--- | :--- |
| `plan` | issue number (required) | Prefers the target's existing `/<target>:plan` or `$<target>-plan` if available; otherwise inline workflow. |
| `implement` | issue number (required) | Prefers the target's existing `/<target>:implement` or `$<target>-implement` if available; otherwise inline workflow. |
| `review` | optional focus area | Reviews current PR or branch-vs-main changes. |
| `adversarial-review` | optional focus | Steerable challenge review — pressure-tests design, hidden assumptions, alternatives, failure modes. |

## Matrix

The 4 sources × 4 targets × 4 actions = 64 cells (including self-action). Cross-agent delegation is 4 × 3 × 4 = 48 cells.

| Source ↓ / Target → | claude (self) | codex | gemini | copilot |
| :--- | :--- | :--- | :--- | :--- |
| **claude** (`.claude/commands/`) | `/claude:{plan,implement,review,adversarial-review}` | `/codex:{...}` | `/gemini:{...}` | `/copilot:{...}` |
| **codex** (`.agents/skills/`) | `$delegate-claude-{...}` | `$codex-{plan,implement,review,adversarial-review}` | `$delegate-gemini-{...}` | `$delegate-copilot-{...}` |
| **gemini** (`.gemini/commands/`) | `/claude:{...}` | `/codex:{...}` | `/gemini:{plan,implement,review,adversarial-review}` | `/copilot:{...}` |
| **copilot** (`.copilot/commands/`) | `/claude:{...}` | `/codex:{...}` | `/gemini:{...}` | `/copilot:{plan,implement,review,adversarial-review}` |

Each cell expands to `{plan, implement, review, adversarial-review}`. The diagonal (self-action) cells use the same `<ai>:<action>` naming convention; they run natively in the host agent rather than shelling out.

## Non-interactive flags per CLI

Each bridge invokes the target CLI in headless mode. Each CLI requires a flag to skip the interactive approval prompts that would otherwise block tool calls when no human is at the terminal:

| Target | Invocation | Why |
| :--- | :--- | :--- |
| Claude Code | `claude -p '<prompt>'` | `-p` runs headless. No additional approval-bypass flag needed for the typical tool surface. |
| Codex CLI | `codex -a never exec '<prompt>'` | `-a never` (`--ask-for-approval never`) prevents Codex from asking the (absent) user before running shell commands. Without it, every tool call in the delegated session is denied. |
| Gemini CLI | `gemini -y -p '<prompt>'` | `-y` (`--yolo`) auto-accepts all tool calls. Without it, `run_shell_command` calls are denied by policy in non-interactive mode. |
| Copilot CLI | `copilot --allow-all -p '<prompt>'` | `--allow-all` enables all permissions (equivalent to `--allow-all-tools --allow-all-paths --allow-all-urls`). Without it, Copilot prompts for path or URL access mid-session, which the absent user can't answer. **Order matters:** `--allow-all` must precede `-p`, since `-p <text>` consumes its argument and would otherwise grab the next flag. |

These flags are intentional: in delegated invocations, the human is at the *source* agent and not at the target's prompt. Approval prompts in the target session can never be answered, so they must be bypassed. The source agent retains full visibility through captured stdout and can stop the chain at any point.

## Hybrid C: how a delegation actually executes

Each command body is a prompt that the source agent reads. The body tells the source agent to invoke the target's CLI in non-interactive mode via the source's tool layer (Bash/exec) and pass a prompt that:

1. **Asks the target to activate its existing self-action command if available** (`/claude:plan`, `$codex-implement`, etc.).
2. **Falls back to an inline workflow** (steps the target should follow if the self-action command isn't available or doesn't activate in non-interactive mode).

This dual-path design — Hybrid C — works regardless of whether each CLI's non-interactive mode resolves slash commands or skill mentions. If resolution works, the target uses its existing solo command and stays consistent with self-action behavior. If it doesn't, the target falls through to the inline steps and still does the right thing.

The output of the target CLI is captured by the source agent's tool layer (e.g., Bash) and re-injected into the source's conversation context, so the source can iterate on the result.

## Per-host invocation examples

```text
# In Claude Code
/codex:plan 42                 # Claude delegates planning of issue 42 to Codex
/gemini:adversarial-review     # Claude delegates an adversarial review of current changes to Gemini

# In Codex CLI
$delegate-claude-implement 42  # Codex delegates implementation of issue 42 to Claude
$delegate-gemini-review        # Codex delegates a review of current changes to Gemini

# In Gemini CLI
/claude:plan 42                # Gemini delegates planning of issue 42 to Claude
/copilot:review                # Gemini delegates a review of current changes to Copilot

# In Copilot CLI
/codex:adversarial-review      # Copilot delegates an adversarial review to Codex
/gemini:implement 42           # Copilot delegates implementation of issue 42 to Gemini
```

## Payload schema

| Action | Required | Optional |
| :--- | :--- | :--- |
| `plan` | issue number | — |
| `implement` | issue number | — |
| `review` | — | focus area / file scope |
| `adversarial-review` | — | focus area / risk dimension |

All cells receive a single freeform string argument that the source agent interpolates into the prompt. Issue numbers map to `$ARGUMENTS` (Claude/Copilot markdown commands), `{{args}}` (Gemini TOML commands), or are extracted from the user's natural language (Codex skills).

## Path conflict between Codex and Gemini

Per OpenAI's Codex skills docs, the only repo-local skill path is `.agents/skills/` (no `.codex/skills/` variant). Per Gemini CLI's docs, Gemini also loads skills from `.agents/skills/` — the path is documented as "an interoperable path for managing agent-specific expertise that remains compatible across different AI tools."

This means the 12 Codex-source delegation skills under `.agents/skills/delegate-*` would be auto-loaded by Gemini and could be mis-activated by Gemini's model.

**Mitigation:** `.gemini/settings.json` has a `skills.disabled` list that excludes specific skill names from Gemini's loading. All 12 `delegate-*` skill names are added there:

```json
"skills": {
  "disabled": [
    "delegate-claude-plan",
    "delegate-claude-implement",
    "delegate-claude-review",
    "delegate-claude-adversarial-review",
    "delegate-gemini-plan",
    "delegate-gemini-implement",
    "delegate-gemini-review",
    "delegate-gemini-adversarial-review",
    "delegate-copilot-plan",
    "delegate-copilot-implement",
    "delegate-copilot-review",
    "delegate-copilot-adversarial-review"
  ]
}
```

Inverse directions are clean by construction: Codex does not read `.gemini/commands/`, `.claude/commands/`, or `.copilot/commands/`; Claude and Copilot do not read `.agents/skills/`. Only the Gemini ↔ Codex pair shares a path.

## Multi-agent orchestration (`/multi-*`)

In addition to the 1-to-1 delegation matrix above, this template ships three N-to-1 orchestrators that let any host agent run **any combination** of agents in parallel and synthesize the results:

| Command | Args | Description |
| :--- | :--- | :--- |
| `/multi-plan <ais...> <issue#>` | agent list + issue number | Each listed agent independently plans the issue; plans posted as separate comments; synthesized plan posted after user approval. |
| `/multi-review <ais...>` | agent list | Each listed agent independently reviews the current PR; reviews posted as separate comments; synthesis posted after user approval. |
| `/multi-adversarial-review <ais...>` | agent list | Each listed agent independently challenges the current changes; synthesis posted to PR (if exists) after user approval. |

Each command is available for all four hosts:
- Claude: `.claude/commands/multi-{plan,review,adversarial-review}.md`
- Gemini: `.gemini/commands/multi-{plan,review,adversarial-review}.toml`
- Copilot: `.copilot/commands/multi-{plan,review,adversarial-review}.md`
- Codex: `.agents/skills/multi-{plan,review,adversarial-review}/SKILL.md`

## Out of scope (v1)

- Background jobs (`status`, `result`, `cancel` analogues)
- Session resume across delegations
- ACP-style brokering for long-running tasks
- Streaming output

These are deliberate omissions to keep v1 small. Synchronous-only invocation only.

## Relationship to existing artifacts

- `/<ai>:plan`, `/<ai>:implement`, `/<ai>:review`, `/<ai>:adversarial-review` — self-action and cross-agent delegation share the same naming convention. Self-action files live in `.<ai>/commands/<ai>/` (or `.agents/skills/codex-<action>/` for Codex).
- `ghi-finalize`, `ghi-status` — these cover the post-implementation steps (commit, PR creation, status reporting).
- `/multi-plan`, `/multi-review`, `/multi-adversarial-review` — N-to-1 orchestrators that dispatch to any combination of agents. See [Multi-agent orchestration](#multi-agent-orchestration-multi-) above.
- `.claude/commands/`, `.gemini/commands/`, `.copilot/commands/`, `.agents/skills/` — established per-agent config directories. Self-action commands are in `<dir>/<ai>/` subdirectories; cross-agent bridges are in `<dir>/<target>/` subdirectories.
- `.gemini/settings.json` `skills.disabled` — existing pattern, extended with 12 delegation entries and 3 multi-orchestrator entries (to prevent `.agents/skills/multi-*` from conflicting with Gemini's native TOML variants).

## See also

- [Slash Commands & Workflows](slash-commands.md) — reference for the underlying workflow commands.
- [First 5 Minutes with an AI Agent](first-5-minutes.md) — narrative onboarding for the issue-driven flow this matrix complements.
