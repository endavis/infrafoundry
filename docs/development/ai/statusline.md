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
