# ADR-9005: AI agent command restrictions via hooks

## Status

Accepted

## Decision

Implement tool-level enforcement that blocks dangerous commands (like `--force`, `--admin`, `--no-verify`) before execution via Claude Code PreToolUse hooks, Gemini CLI BeforeTool hooks, and Codex CLI approval policies.

## Rationale

Documentation alone is insufficient - AI agents may violate rules after context compaction or when trying to "help quickly". A real incident occurred where an AI agent attempted to bypass branch protection. Tool-level blocking provides defense in depth, applying restrictions regardless of agent context state.

## Related Issues

- Issue #113: Enforce dangerous command restrictions via hooks and configs
- Issue #117: Block gh issue create and gh pr create commands for AI agents
- Issue #163: Add pre-commit hook to block pyproject.toml version changes
- Issue #164: Block doit release in AI agent hooks
- Issue #166: Block uv add in AI agent hooks
- Issue #362: Add Copilot CLI command-blocking hook integration
- Issue #409: Complete Copilot CLI coverage in AI_SETUP, enforcement-principles, first-5-minutes

## Related Documentation

- [AI Command Blocking](../../development/ai/command-blocking.md)
- [AI Enforcement Principles](../../development/ai/enforcement-principles.md)
- [AI Setup Guide](../../development/AI_SETUP.md)
