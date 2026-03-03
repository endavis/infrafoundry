# Gemini CLI Instructions

## Context

This project uses both Claude Code and Gemini CLI as AI coding assistants.
Gemini shares the same project standards defined in AGENTS.md.

## Collaboration Mode

Gemini may be invoked non-interactively by Claude Code via `gemini -p "..." --yolo`.
When running in this mode:

- **Output to stdout only** — do NOT post directly to GitHub
- Claude handles all GitHub writes (issue comments, PR comments) to preserve governance hooks
- Structure output as clean markdown so Claude can post it as-is

## Output Signing

When producing plans or reviews, always include a signature footer:

```
---
*{Action} by: Gemini* | *Date: {today's date}*
```

Where `{Action}` is "Plan" or "Review".

## Tool Usage

- Use `gh` for reading GitHub data (issues, PRs, diffs)
- Follow the tool hierarchy from AGENTS.md (doit > uv > gh > git > raw commands)
- Prefer file reading tools for codebase exploration
