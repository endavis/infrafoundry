---
title: Claude Code Statusline
description: Custom statusline showing git branch, Python version, and project info
audience:
  - contributors
  - ai-agents
tags:
  - ai
  - claude
  - configuration
---

# Claude Code Statusline

The template includes a custom statusline for Claude Code sessions that provides useful context at a glance.

## Example Output

```
📁 project-name | 🐍 .venv | Python: 3.12.12
@username | 🔀 main (0 files uncommitted, synced 5m ago)
Claude Opus 4.5 | ▓▓░░░░░░░░ ~10% of 200k tokens
💬 work on issue #130
```

## Features

- **Current directory** and Python virtual environment name
- **Python version** currently active
- **GitHub username** (from `gh` CLI)
- **Git branch** with uncommitted file count
- **Sync status** showing ahead/behind commits and last fetch time
- **Model name** with context usage bar (visual + percentage)
- **Last user message** preview for quick context

## Configuration

The statusline is configured in `.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash $CLAUDE_PROJECT_DIR/.claude/statusline-command.sh"
  }
}
```

## Customization

### Color Theme

Edit `.claude/statusline-command.sh` and change the `COLOR` variable at the top:

```bash
# Available themes: gray, orange, blue, teal, green, lavender, rose, gold, slate, cyan
COLOR="blue"
```

### Color Reference

| Theme    | ANSI Code | Description |
|----------|-----------|-------------|
| gray     | 245       | Monochrome, subtle |
| orange   | 173       | Warm, energetic |
| blue     | 74        | Default, calm |
| teal     | 66        | Cool, professional |
| green    | 71        | Fresh, nature |
| lavender | 139       | Soft, creative |
| rose     | 132       | Warm pink |
| gold     | 136       | Rich, elegant |
| slate    | 60        | Dark blue-gray |
| cyan     | 37        | Bright, tech |

The usage segment (opt-in, see below) uses three additional fixed colors that are independent
of the `COLOR` theme:

| Field | Variable | ANSI Code | Description |
|-------|----------|-----------|-------------|
| Percent value | `C_PCT` | 71 (green) | "value" semantics — current consumption |
| `@` separator | `C_DIM` | 238 (dark gray) | dim join between percent and time |
| Reset time | `C_TIME` | 136 (gold) | "schedule" semantics — when the bucket ends |

Edit `.claude/statusline-command.sh` to change these.

### Removing Features

Comment out or remove lines in the "Build output" section of the script:

```bash
# Build output: Model | Dir | Branch (uncommitted) | Context
output="📁 ${dir}"
[[ -n "$venv_name" ]] && output+=" | 🐍 ${venv_name}"
[[ -n "$python_version" ]] && output+=" | Python: ${python_version}"
# [[ -n "$gh_user" ]] && output+="\n@${gh_user}"  # Remove GitHub username
[[ -n "$branch" ]] && output+=" | 🔀 ${branch} ${git_status}"
```

## Opt-In: Claude Max Usage Display

For Claude Max subscribers, an optional helper at `tools/statusline/claude-usage.sh` displays
weekly + 5-hour utilization. The default statusline runs the helper only when the
`CLAUDE_USAGE_STATUSLINE` env var is set, so the default behavior is unchanged.

> **Beta API**: This helper hits an undocumented OAuth endpoint (`/api/oauth/usage`)
> gated by the `anthropic-beta: oauth-2025-04-20` header. Anthropic may change or remove
> this endpoint without notice. When the official `claude --usage` flag ships
> ([anthropics/claude-code#20399](https://github.com/anthropics/claude-code/issues/20399)),
> prefer it.

### Enable

Set `CLAUDE_USAGE_STATUSLINE=1` in your shell environment:

```bash
# In ~/.zshrc, ~/.bashrc, or .envrc.local
export CLAUDE_USAGE_STATUSLINE=1
```

Restart Claude Code. The statusline appends `5h:N%@HHMM wk:N%@aaa-HHMM` to the model/context line.
Times are shown in your local timezone.
To disable temporarily: `unset CLAUDE_USAGE_STATUSLINE` and restart Claude Code.

Example output (helper segment is the trailing portion of the third line):

```
📁 project | 🐍 .venv | Python: 3.12.12
@username | 🔀 main (0 files uncommitted, synced 5m ago)
Claude Opus 4.5 | ▓▓░░░░░░░░ ~10% of 200k tokens | 5h:25%@1800 · wk:6%@Mon-2000
```

### Cache behavior

Responses are cached at `${XDG_CACHE_HOME:-~/.cache}/claude-usage.json` for 60 seconds.
Adjust `MAX_AGE` at the top of the script. To force a refresh: `rm ~/.cache/claude-usage.json`.

### Helper requirements

- Active Claude Code OAuth login (`${CLAUDE_CONFIG_DIR:-~/.claude}/.credentials.json`)
- `curl` for HTTPS
- `jq` (already required by base statusline)
- `python3` for ISO-8601 timestamp formatting (already a project dev dependency)

### Helper troubleshooting

- **Outputs `?`**: missing/expired credentials, no network, beta endpoint changed schema, or
  curl timeout (5s). Debug with `bash -x tools/statusline/claude-usage.sh`.
- **Stale value**: cache has not expired. Delete the cache file or wait 60s.

## Requirements

- `jq` - JSON processor (used for parsing Claude's input)
- `gh` - GitHub CLI (optional, for username display)
- `git` - For branch and status information

## Troubleshooting

### Statusline not appearing

1. Ensure the script is executable: `chmod +x .claude/statusline-command.sh`
2. Check `jq` is installed: `which jq`
3. Test manually: `echo '{}' | bash .claude/statusline-command.sh`

### Colors not displaying

Some terminals may not support 256-color mode. Try setting `COLOR="gray"` for basic output.
