---
title: AI Command Blocking
description: Hooks that block dangerous commands from AI agents
audience:
  - contributors
  - ai-agents
tags:
  - ai
  - security
  - hooks
---

# AI CLI Hooks

The `tools/hooks/ai/` directory contains hooks for AI coding assistants (Claude Code, Gemini CLI).

## Block Dangerous Commands

### Purpose

AI agents can sometimes attempt dangerous operations like:

- `--admin` - bypasses branch protection
- `--no-verify` - skips pre-commit hooks
- `git reset --hard` - loses uncommitted changes
- `rm -rf /` or `rm -rf ~` - destructive deletions
- Force push to `main`/`master` - overwrites shared history
- Deleting protected branches
- Merge commits on protected branches - violates linear history

These hooks intercept commands before execution and block dangerous patterns, even if the agent doesn't follow the rules in `AGENTS.md`.

### How It Works

The hook uses Python's `shlex` module to properly parse shell quoting:

1. **Tokenize** the command with `shlex.split()`
2. **Check** for dangerous flags as standalone tokens
3. **Check** for dangerous token sequences (e.g., `rm -rf ~`)
4. **Check** for force push to protected branches (main/master)
5. **Check** for deletion of protected branches
6. **Check** for merge commits on protected branches (linear history)
7. **Block** (exit code 2) or **Allow** (exit code 0)

#### Key Feature: Quote-Aware Parsing

The hook correctly distinguishes between:

```bash
# BLOCKED - actual dangerous flag
gh pr merge --admin

# ALLOWED - flag is just text in a commit message
git commit -m "The --admin flag is dangerous"

# ALLOWED - flag mentioned in heredoc content
doit pr --body="$(cat <<'EOF'
Do not use --force
EOF
)"
```

### Files

| File | Description |
|------|-------------|
| [`block-dangerous-commands.py`](../../../tools/hooks/ai/block-dangerous-commands.py) | The hook script (shared by Claude and Gemini) |
| [`test_hook.py`](../../../tools/hooks/ai/test_hook.py) | Test suite to verify hook behavior |

### Configuration

#### Claude Code

`.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $CLAUDE_PROJECT_DIR/tools/hooks/ai/block-dangerous-commands.py"
          }
        ]
      }
    ]
  }
}
```

#### Gemini CLI

`.gemini/settings.json`:
```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $GEMINI_PROJECT_DIR/tools/hooks/ai/block-dangerous-commands.py"
          }
        ]
      }
    ]
  }
}
```

#### Codex CLI

Codex uses approval policies instead of hooks. See `.codex/config.toml` for deny rules.

### Testing

Run the test suite after making changes:

```bash
python3 tools/hooks/ai/test_hook.py
```

Output shows green for passing tests, red for failures:

```
Testing hook: /path/to/block-dangerous-commands.py

================================================================================
+ ALLOW (expected ALLOW) | safe command              | git status
+ ALLOW (expected ALLOW) | double quoted             | git commit -m "text with --admin"
+ BLOCK (expected BLOCK) | actual --admin flag       | gh pr merge --admin
================================================================================

Results: 14 passed, 0 failed
```

### Blocked Patterns

#### Dangerous Flags (always blocked)

| Flag | Reason |
|------|--------|
| `--admin` | Bypasses branch protection rules |
| `--no-verify` | Skips pre-commit/pre-push hooks |
| `--hard` | Hard reset - can lose uncommitted changes |

#### Dangerous Sequences (consecutive tokens)

| Sequence | Reason |
|----------|--------|
| `rm -rf /` | Destructive: removes root filesystem |
| `rm -rf ~` | Destructive: removes home directory |
| `sudo rm` | Privileged deletion |

#### Protected Branch Operations

Force push, delete, and merge operations are only blocked when targeting protected branches (`main`, `master`).

| Command | Result |
|---------|--------|
| `git push --force origin main` | BLOCKED |
| `git push --force origin feat/branch` | ALLOWED |
| `git push -f origin master` | BLOCKED |
| `git push --force` (no branch) | BLOCKED (safer default) |
| `git push origin --delete main` | BLOCKED |
| `git push origin :main` | BLOCKED |
| `git branch -D main` | BLOCKED |
| `git branch -D feat/old` | ALLOWED |
| `git merge branch` (on main) | BLOCKED (creates merge commit) |
| `git merge --ff-only branch` (on main) | ALLOWED (fast-forward only) |
| `git merge branch` (on feature) | ALLOWED |

#### Blocked Workflow Commands

These commands should use `doit` wrappers or require user approval:

| Command | Use Instead | Reason |
|---------|-------------|--------|
| `gh issue create` | `doit issue --type=<type>` | Ensures proper template and labels |
| `gh pr create` | `doit pr` | Ensures proper template format |
| `gh pr merge` | `doit pr_merge` | Enforces merge commit format: `<type>: <subject> (merges PR #XX, closes #YY)` |
| `uv add` | User runs manually | Dependencies require human approval - suggest package, let user run command |
| `doit release*` | User runs manually | Releases require human approval - AI can help prepare but not execute |

#### Governance Labels

Some labels are governance controls that require human approval. AI agents are blocked from adding these labels:

| Label | Reason |
|-------|--------|
| `ready-to-merge` | Signals human approval that PR is ready for merge. Add manually via `gh pr edit --add-label ready-to-merge` or GitHub web UI. |

### Adding New Patterns

Edit `tools/hooks/ai/block-dangerous-commands.py`:

```python
# Add a new always-blocked flag
DANGEROUS_FLAGS = {
    "--admin": "Bypasses branch protection rules",
    "--new-flag": "Description of why it's dangerous",
}

# Add a new dangerous sequence
DANGEROUS_SEQUENCES = [
    (["rm", "-rf", "/"], "Destructive: removes root filesystem"),
    (["new", "dangerous", "sequence"], "Why it's dangerous"),
]

# Add a new protected branch
PROTECTED_BRANCHES = {"main", "master", "production"}
```

Then run the test suite to verify.

## Related

- [AI Enforcement Principles](enforcement-principles.md) - Why and how we enforce rules in code
- [AGENTS.md](../../../AGENTS.md) - AI agent rules including "When Blocked Protocol"
- [AI Agent Setup](../AI_SETUP.md) - Setting up AI coding assistants
