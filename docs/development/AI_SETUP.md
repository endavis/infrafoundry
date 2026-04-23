---
title: AI Agent Setup Guide
description: Configure Claude, Gemini, Copilot, and Codex for this project
audience:
  - contributors
  - ai-agents
tags:
  - ai
  - setup
  - configuration
---

# AI Agent Setup Guide

This template is designed primarily for **Claude Code**, which is the only agent that ships the full slash-command workflow and acts as the orchestrator in single-agent and dual-agent flows. **Gemini CLI** is supported in a narrower role (second-opinion planner/reviewer inside Claude-orchestrated commands). **GitHub Copilot CLI** is supported as a standalone alternative that auto-discovers the full slash-command workflow from `.claude/commands/`. **Codex CLI** is supported as a standalone alternative without slash commands. See the comparison table below for the per-agent breakdown.

> **New here?** Start with the [First 5 Minutes walkthrough](ai/first-5-minutes.md) for a narrative tour of the AI agent workflow. This page is the configuration reference.

## Supported AI Agents

### Agent comparison

| Agent | Permission model | Hooks support | Slash commands | LSP | Dual-agent role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Codex CLI** | TOML approval policies (`.codex/config.toml`) | Project-level `tools/hooks/ai/` apply via shell | None shipped | Not documented | Standalone alternative (not part of dual-agent flow) |
| **Gemini CLI** | JSON allowlists + lifecycle hooks (`.gemini/settings.json`) | Project-level hooks apply; Gemini lifecycle hooks supported | 2 output-only (`/plan-issue`, `/review-pr`) | Not documented | Second-opinion reviewer / planner in dual-agent flow |
| **GitHub Copilot CLI** | JSON hook config (`.github/hooks/copilot-hooks.json`) | Project-level hooks apply; Copilot `preToolUse` hook wired | Auto-discovers from `.claude/commands/` | Not documented | Standalone alternative (auto-discovers Claude commands) |
| **Claude Code** | Layered permissions (`.claude/settings.local.json` + `.claude/settings.json` PreToolUse hooks) | Project-level hooks plus Claude PreToolUse hooks | 8 (`plan-issue`, `implement`, `finalize`, `close-issue`, `plan-both`, `review-both`, `gemini-review`, `where-am-i`) | Supported | Primary orchestrator in single-agent and dual-agent flows |

The project-level dangerous-command hooks under `tools/hooks/ai/` apply to all four agents regardless of per-agent config and cannot be bypassed by editing `.claude/settings.local.json`, `.codex/config.toml`, `.gemini/settings.json`, or `.github/hooks/copilot-hooks.json`. See [AI Enforcement Principles](ai/enforcement-principles.md) and [Command Blocking](ai/command-blocking.md).

### 1. Codex CLI (OpenAI)

**Configuration:** `.codex/config.toml`

> **Note**: Project-level dangerous-command hooks under `tools/hooks/ai/` apply to this agent regardless of the per-agent config below. See [AI Enforcement Principles](ai/enforcement-principles.md) and [Command Blocking](ai/command-blocking.md).

Codex CLI directly reads `AGENTS.md` from the project root. The configuration file whitelists common development commands.

**Whitelisted commands:**
- `git` - All git operations
- `gh` - GitHub CLI
- `uv` - UV package manager
- `doit` - Task automation
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Setup:**
```bash
# Codex CLI will automatically use .codex/config.toml if present
# Or copy to global config:
cp .codex/config.toml ~/.codex/config.toml

# Initialize or regenerate AGENTS.md with Codex:
codex
/init
```

**Documentation:**
- [Codex CLI Documentation](https://developers.openai.com/codex/cli/)
- [Configuring Codex](https://developers.openai.com/codex/local-config/)
- [Codex Security Guide](https://developers.openai.com/codex/security/)

**Codex parity status:** Codex ships no slash commands in this template — `.codex/` contains only `config.toml`. LSP integration is not documented for Codex here. Codex is not part of the dual-agent workflow (Claude and Gemini are); it works as a standalone alternative for contributors who prefer the OpenAI CLI. The project-level hooks under `tools/hooks/ai/` still apply to Codex — see [Command Blocking](ai/command-blocking.md). For the broader slash-command and dual-agent picture, see [Slash Commands and Workflows](ai/slash-commands.md).

### 2. Gemini CLI (Google)

**Configuration:** `.gemini/settings.json`

> **Note**: Project-level dangerous-command hooks under `tools/hooks/ai/` apply to this agent regardless of the per-agent config below. See [AI Enforcement Principles](ai/enforcement-principles.md) and [Command Blocking](ai/command-blocking.md).

Gemini CLI can read `AGENTS.md` (or `GEMINI.md`) from the project root. The configuration file uses allowlists for tools and shell commands, and configures lifecycle hooks.

**Allowlisted commands:**
- `git`, `gh`, `uv`, `doit` - Development tools
- `python`, `pytest`, `ruff`, `mypy` - Python tools
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Core tools enabled:**
- `ShellTool` - Execute shell commands
- `ReadFileTool`, `WriteFileTool` - File operations
- `LSTool`, `GrepTool` - File exploration

**Setup:**
```bash
# Gemini CLI automatically uses .gemini/settings.json if present
# Or copy to global config:
cp .gemini/settings.json ~/.gemini/settings.json

# Ensure hooks are enabled in settings.json:
# {
#   "hooks": { "enabled" : true }
# }

# Use YOLO mode to skip all permission prompts (use with caution):
gemini --yolo
# Or toggle auto-approve with Ctrl+Y during a session
```

**Documentation:**
- [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/)
- [Gemini CLI Hooks](https://geminicli.com/docs/hooks/)
- [Provide Context with GEMINI.md Files](https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html)
- [Sandboxing in Gemini CLI](https://geminicli.com/docs/cli/sandbox/)
- [Gemini CLI Settings](https://geminicli.com/docs/cli/settings/)

### 3. Claude Code (Anthropic)

**Configuration:** `.claude/` directory

> **Note**: Project-level dangerous-command hooks under `tools/hooks/ai/` apply to this agent regardless of the per-agent config below. See [AI Enforcement Principles](ai/enforcement-principles.md) and [Command Blocking](ai/command-blocking.md).

Claude Code uses a reference file (`.claude/claude.md`) that imports `AGENTS.md`.

**Whitelisted commands:**
- `git:*` - All git commands
- `gh:*` - All GitHub CLI commands
- `uv:*` - All uv commands
- `doit:*` - All doit commands
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Setup:**
```bash
# Claude Code automatically detects .claude/ directory
# No additional setup needed
```

**Files:**
- `.claude/claude.md` - Imports AGENTS.md
- `.claude/settings.local.json` - Command permissions
- `.claude/settings.json` - Status line and PreToolUse hooks

**LSP Support (Recommended):**

Claude Code supports Language Server Protocol for enhanced code intelligence:
- Document symbols (functions, classes, variables)
- Go to definition / find references
- Hover information and type checking
- Call hierarchy navigation

**Quick LSP Setup:**
```bash
# 1. Install the LSP plugin from marketplace
/install-plugin @anthropic-ai/claude-code-lsp

# 2. Install development dependencies (includes language server)
doit install_dev

# 3. Enable LSP tool in .envrc.local
echo 'export ENABLE_LSP_TOOL=1' >> .envrc.local
direnv allow

# 4. Start Claude Code
claude
```

For complete setup instructions and troubleshooting, see `.claude/lsp-setup.md` in the repository root.

### 4. GitHub Copilot CLI

**Configuration:** `.copilot/` directory

> **Note**: Project-level dangerous-command hooks under `tools/hooks/ai/` apply to this agent regardless of the per-agent config below. See [AI Enforcement Principles](ai/enforcement-principles.md) and [Command Blocking](ai/command-blocking.md).

GitHub Copilot CLI reads `AGENTS.md` directly and auto-discovers project skills from `.claude/commands/`, so the full slash-command workflow (`/plan-issue`, `/implement`, `/finalize`, `/close-issue`, `/where-am-i`, etc.) is available in Copilot sessions without any parallel command files. The `implement-worker` subagent used by `/implement` is shared with Claude (defined in `.claude/agents/implement-worker.md`).

**Hook wiring:**

The dangerous-command hook is wired in `.github/hooks/copilot-hooks.json`:
```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "python3 ../../tools/hooks/ai/block-dangerous-commands.py",
        "cwd": ".github/hooks",
        "timeoutSec": 10
      }
    ]
  }
}
```

**Setup:**
```bash
# Copilot CLI automatically picks up .github/hooks/copilot-hooks.json
# and reads AGENTS.md; no additional setup needed.
copilot
```

**Files:**
- `.copilot/README.md` - Description of the Copilot CLI config directory
- `.github/hooks/copilot-hooks.json` - `preToolUse` hook wiring
- `.claude/commands/*.md` - Slash commands (auto-discovered by Copilot CLI)
- `.claude/agents/implement-worker.md` - Shared subagent definition

**Documentation:**
- [GitHub Copilot CLI](https://github.com/github/copilot-cli)
- [Copilot CLI Hooks](https://docs.github.com/en/copilot/how-tos/use-copilot-for-common-tasks/use-copilot-in-the-cli)

**Copilot parity status:** Copilot CLI ships no parallel command or agent files — it auto-discovers from `.claude/commands/` and `.claude/agents/`, so every Claude slash command works unchanged in Copilot sessions. Copilot is not part of the dual-agent workflow (Claude and Gemini are); it works as a standalone alternative for contributors who prefer GitHub Copilot. The project-level hooks under `tools/hooks/ai/` apply to Copilot via `.github/hooks/copilot-hooks.json` — see [Command Blocking](ai/command-blocking.md). For the broader slash-command picture, see [Slash Commands and Workflows](ai/slash-commands.md).

### 5. Other AI Tools

The `AGENTS.md` file serves as general-purpose documentation for any AI coding assistant:

- **Cursor**: Reference in `.cursorrules`
- **Codeium**: Reference in project settings
- **Tabnine**: Reference in configuration

> **Note**: For the slash commands and dual-agent workflow this template ships with, see [Slash Commands and Workflows](ai/slash-commands.md).

## AGENTS.md - Universal Context File

The `AGENTS.md` file provides comprehensive project context including:

- Repository structure and architecture
- Development workflows and commands
- Code style and conventions
- Testing expectations
- CI/CD workflows
- Troubleshooting guides

This file is:
- **Read directly** by Codex CLI, Gemini CLI, and GitHub Copilot CLI
- **Imported** by Claude Code via `.claude/claude.md`
- **Referenceable** by other AI tools

## Context files and precedence

This template ships several files that influence agent behavior. They fall into two categories: **context/instruction files** (markdown) and **settings/config files** (JSON or TOML). Knowing which is which — and which one wins on conflict — matters when adapting the template for a new project.

**File inventory:**

- **`AGENTS.md`** (project root, ~20 KB) — universal source of truth for architecture, workflow, tooling hierarchy, and security rules. Read directly by Codex CLI, Gemini CLI, and GitHub Copilot CLI; imported by Claude Code via `@../AGENTS.md` in `.claude/CLAUDE.md`.
- **`.claude/CLAUDE.md`** (~2 KB) — Claude-specific complement. First line is `@../AGENTS.md`, which imports the universal rules; the rest adds Claude-specific layers (token-efficiency guidance, the mandatory TodoWrite plan-test-code loop, the development workflow reminder, and the commit workflow reminder).
- **`GEMINI.md`** (project root, ~1 KB) — Gemini-specific complement. Covers Gemini's stdout-only collaboration mode (so Claude handles GitHub writes), the output signing footer, and Gemini's tool-usage rules. Read alongside `AGENTS.md` by Gemini CLI, not instead of it.
- **`.copilot/README.md`** — describes the Copilot CLI config directory. Copilot CLI reads `AGENTS.md` directly and auto-discovers slash commands from `.claude/commands/`; no Copilot-specific context markdown is required.
- **`.codex/config.toml`** — Codex approval policy file (TOML). Not a context file; configures permissions only. Codex reads `AGENTS.md` directly for instructions.
- **`.claude/settings.json`** — Claude PreToolUse hooks and statusline configuration. Committed.
- **`.claude/settings.local.json`** — local Claude permissions overlay. Not committed.
- **`.gemini/settings.json`** — Gemini tool allowlists and lifecycle hook configuration.
- **`.github/hooks/copilot-hooks.json`** — Copilot CLI `preToolUse` hook wiring that routes shell commands through `tools/hooks/ai/block-dangerous-commands.py`.

**Precedence rules:**

- All four agents treat `AGENTS.md` as the architectural and workflow source of truth.
- Agent-specific markdown files (`.claude/CLAUDE.md`, `GEMINI.md`) **complement** `AGENTS.md` — they cover behaviors specific to that agent's interaction model and do not override the universal rules.
- Settings/config files (`.codex/config.toml`, `.gemini/settings.json`, `.claude/settings*.json`, `.github/hooks/copilot-hooks.json`) configure **permissions and tooling**, not workflow rules. They cannot grant an agent permission to do something `AGENTS.md` forbids.
- Project-level hooks under `tools/hooks/ai/` apply to all agents and cannot be bypassed by per-agent config. This is the strongest layer.

**Conflict resolution:** if an agent-specific file conflicts with `AGENTS.md`, `AGENTS.md` wins for cross-cutting concerns (workflow, architecture, security). An agent-specific file may further restrict its own agent's behavior, but it should not loosen a universal rule.

## Customization

### For Your Project

When using this template for a new project:

1. **Update AGENTS.md**: Customize project-specific details
2. **Adjust permissions**: Modify `.codex/config.toml` and `.claude/settings.local.json` as needed
3. **Add project commands**: Include any custom scripts or tools

### Adding New Commands

**Codex CLI** (`.codex/config.toml`):
```toml
[[approval_policy]]
type = "command"
pattern = "^your-command\\b"
action = "allow"
reason = "Description of command"
```

**Gemini CLI** (`.gemini/settings.json`):
```json
{
  "tools": {
    "allowed": [
      "run_shell_command(your-command)"
    ]
  }
}
```

**Claude Code** (`.claude/settings.local.json`):
```json
{
  "permissions": {
    "allow": [
      "Bash(your-command:*)"
    ]
  }
}
```

**GitHub Copilot CLI** (`.github/hooks/copilot-hooks.json`):

Copilot CLI does not use a per-command allowlist — the dangerous-command hook blocks unsafe patterns; everything else is allowed. To adjust what is blocked, edit the shared hook at `tools/hooks/ai/block-dangerous-commands.py` (which applies to Claude, Gemini, and Copilot alike). New slash commands added under `.claude/commands/<name>.md` are automatically discovered by Copilot CLI — no additional configuration is needed.

## Security Considerations

All configuration files are set up with security in mind.

> **Note**: This template enforces security rules in code and settings, not just instructions. See [AI Enforcement Principles](ai/enforcement-principles.md) for details.

> **Note**: For the architectural rules AI agents must follow when generating code, see [Architectural Conventions](ai/architectural-conventions.md).

**Whitelisted Operations:**
- Read-only file operations
- Safe git operations (status, diff, log, add, commit, push, pull)
- Package management (uv)
- Testing and linting (pytest, ruff, mypy)
- Task automation (doit)

**Protected Information:**
- API keys and tokens are excluded from environment variables
- No dangerous operations (rm -rf, format, etc.) are pre-approved
- Network operations require approval in some modes

## Troubleshooting

### Codex CLI

**Commands still prompt for approval:**
```bash
# Check current config
cat ~/.codex/config.toml

# Copy project config to global
cp .codex/config.toml ~/.codex/config.toml

# Or use project-specific config
codex --config .codex/config.toml
```

**Regenerate AGENTS.md:**
```bash
codex
/init
```

### Claude Code

**Permissions not working:**
- Ensure `.claude/settings.local.json` exists
- Check file is valid JSON
- Restart Claude Code

**Context not loading:**
- Verify `.claude/claude.md` contains `@AGENTS.md`
- Check `AGENTS.md` exists in project root

### Gemini CLI

**Commands still prompt for approval:**
```bash
# Check current config
cat ~/.gemini/settings.json

# Copy project config to global
cp .gemini/settings.json ~/.gemini/settings.json

# Or use YOLO mode (auto-approve all)
gemini --yolo

# Or toggle auto-approve during session
# Press Ctrl+Y
```

**Context not loading:**
- Ensure `AGENTS.md` or `GEMINI.md` exists in project root
- Check `.gemini/settings.json` has `"context": {"files": ["AGENTS.md"]}`
- Verify settings.json is valid JSON

### Copilot CLI

**Hook not firing (dangerous commands going through):**
- Verify `.github/hooks/copilot-hooks.json` exists and is valid JSON
- The hook uses a relative `bash` path (`python3 ../../tools/hooks/ai/block-dangerous-commands.py`) and a `cwd` of `.github/hooks`; both must match your layout
- Run `python3 tools/hooks/ai/test_hook.py` to confirm the shared hook script still passes its test suite

**Slash commands not appearing:**
- Copilot CLI auto-discovers skills from `.claude/commands/` — make sure that directory exists and contains `.md` files with the CLI file format (no YAML frontmatter; leading `# Title` and `## Instructions` sections)
- Restart the Copilot CLI session after adding new command files

**`.copilot/` auto-detection:**
- The `.copilot/` directory exists primarily to document Copilot-specific wiring; Copilot CLI does not require any config files there
- If you move the repository, Copilot CLI still loads `AGENTS.md` from the repo root and the hook from `.github/hooks/copilot-hooks.json`

## Resources

### Codex CLI
- [Codex CLI](https://developers.openai.com/codex/cli/)
- [Codex Configuration](https://developers.openai.com/codex/local-config/)
- [Codex Security Guide](https://developers.openai.com/codex/security/)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)

### Gemini CLI
- [Gemini CLI Documentation](https://geminicli.com/docs/get-started/configuration/)
- [Gemini CLI Hooks](https://geminicli.com/docs/hooks/)
- [GEMINI.md Context Files](https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html)
- [Sandboxing in Gemini CLI](https://geminicli.com/docs/cli/sandbox/)
- [Gemini CLI Settings](https://geminicli.com/docs/cli/settings/)
- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)

### Claude Code
- [Claude Code Documentation](https://claude.com/claude-code)
- [Claude Agent SDK](https://github.com/anthropics/claude-code)

### GitHub Copilot CLI
- [GitHub Copilot CLI](https://github.com/github/copilot-cli)
- [Using Copilot in the CLI](https://docs.github.com/en/copilot/how-tos/use-copilot-for-common-tasks/use-copilot-in-the-cli)
- [GitHub Copilot](https://github.com/features/copilot)

### General AI Coding
- [Cursor](https://cursor.sh/)
- [Codeium](https://codeium.com/)

---

**Note**: The `.codex/`, `.gemini/`, `.claude/`, and `.copilot/` directories should be committed to version control to share consistent AI assistant configuration across the team. .local files should not be committed.
