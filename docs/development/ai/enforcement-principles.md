---
title: AI Enforcement Principles
description: How we enforce AI agent behavior in code and settings
audience:
  - contributors
  - ai-agents
tags:
  - ai
  - enforcement
  - hooks
---

# AI Enforcement Principles

## Core Principle

> **All processes are enforced in code or settings as much as possible.**

AI agents do not follow `AGENTS.md` consistently. Instructions alone are insufficient for reliable behavior - enforcement must be automated.

### Why Instructions Alone Are Insufficient

Even when `AGENTS.md` explicitly states "use `doit pr` instead of `gh pr create`", AI agents frequently ignore this guidance. The reasons include:

- **Context window limitations**: Instructions may fall out of context during long conversations
- **Training data bias**: Models default to commonly-used patterns from their training
- **Ambiguous interpretation**: Agents may rationalize exceptions ("this is just a quick fix")
- **No consequences**: Without enforcement, violations go unnoticed

**Solution**: Shift from "tell the agent what to do" to "prevent the agent from doing the wrong thing."

## Enforcement Options

Listed in order of preference:

### 1. GitHub Repository Settings (Most Universal)

GitHub-level enforcement applies to **all** contributors - humans and AI agents alike. This is the strongest form of enforcement because it cannot be bypassed locally.

**Branch Rulesets** (Settings → Rules → Rulesets):
- Require pull request before merging
- Require status checks to pass (CI, merge-gate)
- Require linear history (no merge commits)
- Restrict force pushes and deletions
- Require signed commits

**Example**: Required status checks ensure CI passes before merge:
```
Branch protection for 'main':
├─ Require status checks: ci, merge-gate
├─ Require branches to be up to date
└─ Restrict who can push: (none - all changes via PR)
```

Use GitHub settings when:
- The rule applies to all contributors (not just AI)
- You need server-side enforcement that can't be bypassed
- The rule maps to a GitHub-native feature

### 2. Pre-commit Hooks (Local Git Enforcement)

Pre-commit hooks run locally before commits are created. They enforce rules for all local development but can be bypassed with `--no-verify` (which AI hooks block).

**Example**: Branch naming and commit message enforcement (`.pre-commit-config.yaml`):
```yaml
- repo: local
  hooks:
    - id: no-commit-to-main
      name: Prevent commits to main branch
      entry: bash -c 'if [[ "$(git branch --show-current)" == "main" ]]; then exit 1; fi'
      language: system

- repo: https://github.com/compilerla/conventional-pre-commit
  hooks:
    - id: conventional-pre-commit
      stages: [commit-msg]
```

Use pre-commit hooks when:
- The rule should apply to all local development
- Immediate feedback is valuable (before push)
- The rule can be expressed as a file or commit check

### 3. AI Agent Hooks (PreToolUse/BeforeTool)

Hooks intercept AI tool calls before execution, allowing custom logic to block dangerous patterns. Use when:
- You need to block AI-specific behaviors
- You need pattern matching (not just exact commands)
- You need context-aware decisions (e.g., checking current git branch)

**Example**: Block dangerous commands (`.claude/settings.json`):

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

See [AI Command Blocking](command-blocking.md) for implementation details.

### 4. AI Agent Settings (Allowlists/Denylists)

Settings-based enforcement in agent config files:
- Is declarative and version-controlled
- Works across AI tools that support the setting format
- Requires no custom code

**Example**: Gemini CLI allowed tools list (`.gemini/settings.json`):

```json
{
  "tools": {
    "allowed": [
      "run_shell_command(git)",
      "run_shell_command(gh)",
      "run_shell_command(uv)",
      "run_shell_command(doit)"
    ]
  }
}
```

This implicitly blocks any command not in the allowlist.

### 5. Agent-Specific Configuration (Last Resort)

When hooks aren't available for a particular agent, fall back to agent-specific configuration files. This is the least maintainable because:
- Each agent requires separate configuration
- Patterns may need different syntax per agent
- Changes must be replicated across all agent configs

**Example**: Codex CLI deny rules (`.codex/config.toml`):

```toml
[[approval_policy]]
type = "command"
pattern = "gh\\s+pr\\s+create"
action = "deny"
reason = "BLOCKED: Use 'doit pr' instead of 'gh pr create'. See AGENTS.md."
```

## Currently Enforced Processes

### By GitHub Repository Settings

| Rule | Setting | Effect |
|------|---------|--------|
| All changes via PR | Branch ruleset | Direct push to `main` blocked server-side |
| CI must pass | Required status check | Merge blocked until `ci` workflow succeeds |
| Merge gate label | Required status check | Merge blocked until `merge-gate` succeeds |
| Linear history | Branch ruleset | Merge commits rejected |

> **Note**: GitHub settings require repository admin access to configure. See Settings → Rules → Rulesets.

### By AI Agent Enforcement (Claude, Gemini, Codex)

These patterns are blocked across all AI agents. Claude and Gemini use the shared hook at `tools/hooks/ai/block-dangerous-commands.py`. Codex uses approval policies in `.codex/config.toml` (no hook support).

| Pattern | Command | Claude | Gemini | Codex |
|---------|---------|--------|--------|-------|
| `--admin` flag | `gh pr merge --admin` | Hook | Hook | Config |
| `--no-verify` flag | `git commit --no-verify`, `git push --no-verify` | Hook | Hook | Config |
| `--hard` flag | `git reset --hard` | Hook | Hook | Config |
| `rm -rf /` or `rm -rf ~` | Any shell | Hook | Hook | Config |
| `sudo rm` | Any shell | Hook | Hook | Config |
| Force push to protected branch | `git push --force origin main` | Hook | Hook | Config |
| Delete protected branch | `git push origin --delete main`, `git branch -D main` | Hook | Hook | — |
| Merge commit on protected branch | `git merge` (without `--ff-only`) on `main` | Hook | Hook | — |
| `gh pr create` | Use `doit pr` instead | Hook | Hook | Config |
| `gh issue create` | Use `doit issue` instead | Hook | Hook | Config |
| `uv add` | User runs manually | Hook | Hook | Config |
| `doit release*` | User runs manually | Hook | Hook | Config |

> **Note**: "Hook" = `block-dangerous-commands.py`, "Config" = `.codex/config.toml` approval policy, "—" = not enforced for this agent.

### By Pre-commit Hooks (All Developers and Agents)

| Rule | Hook | Effect |
|------|------|--------|
| No commits to `main` | `no-commit-to-main` | Blocks commit with guidance message |
| Branch naming convention | `check-branch-name` | Requires `<type>/<issue#>-<description>` format |
| No local config files | `no-local-config` | Blocks `*.local` and `*.local.*` files (allows `*.local.example`) |
| Protect dynamic version | `protect-dynamic-version` | Blocks changes to `dynamic =` in pyproject.toml |
| Conventional commits | `conventional-pre-commit` | Requires `<type>: <subject>` format |
| Code formatting | `ruff-format` | Auto-fixes formatting issues |
| Linting | `ruff` | Auto-fixes linting issues |
| Type checking | `mypy` | Blocks commits with type errors |
| Security scan | `bandit` | Blocks commits with security issues |
| Spelling | `codespell` | Blocks commits with spelling errors |
| Private key detection | `detect-private-key` | Blocks commits containing secrets |
| Large file prevention | `check-added-large-files` | Blocks commits with large files |

### By GitHub Workflows (CI/CD)

| Rule | Workflow | Effect |
|------|----------|--------|
| All CI checks must pass | `ci.yml` | Required status check for merge |
| `ready-to-merge` label required | `merge-gate.yml` | Blocks merge without label |
| Full test matrix on merge | `ci.yml` | Runs all Python versions when labeled |
| Minimum 80% test coverage | `ci.yml` + `pyproject.toml` | `fail_under = 80` fails CI if coverage drops |

### By Settings (Agent-Specific)

| Rule | Setting | Agent |
|------|---------|-------|
| Allowed shell commands only | `.gemini/settings.json` tools.allowed | Gemini |
| Deny dangerous patterns | `.codex/config.toml` approval_policy | Codex |
| Block dangerous env vars | `.codex/config.toml` shell_env_policy | Codex |

## Selecting an Enforcement Method

```
Does the rule apply to ALL contributors (humans + AI)?
├─ Yes
│  ├─ Can GitHub enforce it? (branch rules, status checks)
│  │  └─ Yes → Use GitHub settings (Option 1)
│  └─ Is it a commit/file check?
│     └─ Yes → Use pre-commit hooks (Option 2)
└─ No (AI-specific rule)
   ├─ Does it need pattern matching or context?
   │  └─ Yes → Use AI hooks (Option 3)
   └─ Can agent settings handle it?
      ├─ Yes → Use agent settings (Option 4)
      └─ No → Use agent-specific config (Option 5)
```

**Principles**:

| # | Principle | Description |
|---|-----------|-------------|
| 1 | Prefer universal enforcement | GitHub settings > pre-commit > AI hooks |
| 2 | Prefer shared enforcement | One hook for multiple agents is better than separate configs |
| 3 | Block by default | Allowlists are safer than denylists |
| 4 | Fail closed | If enforcement fails, block the action rather than allow it |
| 5 | Test enforcement | Run `tools/hooks/ai/test_hook.py` after AI hook changes |

## Block and Redirect Pattern

When blocking a command, provide an approved alternative when possible. This project uses `doit` wrappers that enforce rules the raw commands don't:

| Blocked Command | Alternative | What the Alternative Enforces |
|-----------------|-------------|-------------------------------|
| `gh issue create` | `doit issue --type=<type>` | Issue template format, required sections, auto-labeling |
| `gh pr create` | `doit pr` | PR template format, proper description structure |
| `doit release` | User runs manually | Human approval for releases |
| `uv add` | User runs manually | Human approval for new dependencies |

**Why wrappers instead of just blocking?**

1. **Enforces structure**: `doit issue` validates required sections, `doit pr` ensures proper format
2. **Reduces friction**: Agents can still complete tasks, just through compliant paths
3. **Consistent output**: All issues/PRs follow the same template regardless of who creates them
4. **Audit trail**: Wrapper can add metadata, logging, or additional checks

**When to use "user runs manually" instead of a wrapper:**

- High-consequence operations (releases, dependency changes)
- Operations that should be rare and deliberate
- When human judgment is required that can't be encoded in a wrapper

## TODO: Potential Future Enforcement

The following AGENTS.md rules are currently instruction-only and could benefit from automated enforcement:

### Low Priority / Difficult to Automate

| Rule | Current State | Why Difficult |
|------|---------------|---------------|
| "One logical change per commit" | Instruction only | Requires human judgment to define "logical." Conventional commits enforcement ensures message describes one change type. |
| "Stop on error" | Instruction only | Requires understanding agent intent |
| "Questions != Instructions" | Instruction only | Requires natural language understanding |
| "Summary before commit" | Instruction only | Requires conversation context analysis |
| "Pre-commit validation before staging" | Instruction only | Would require tracking agent's intended workflow |

## Related Documentation

- [AI Command Blocking](command-blocking.md) - Hook implementation details
- [AGENTS.md](../../../AGENTS.md) - Full AI agent instructions
- [AI Setup Guide](../AI_SETUP.md) - Setting up AI coding assistants
