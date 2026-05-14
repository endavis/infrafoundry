# Review via Claude

Delegate a read-only code review of the current changes to Claude Code. Optional focus area: $ARGUMENTS.

## Instructions

Run Claude Code non-interactively via shell. Hybrid C: prefer the existing `/claude:review` command if available, otherwise the prompt is fully inlined.

```bash
claude -p 'Review the current uncommitted changes and the current branch vs main, read-only. 1) Run `git status` and `git diff` to see what changed. 2) Run `git log main..HEAD --oneline` for branch context. 3) Read AGENTS.md and any relevant ADRs in docs/decisions/. 4) Identify correctness issues, risks, missing tests, style/convention violations, and concrete suggestions. 5) Print findings to stdout in a structured format (Summary / Issues / Suggestions). Do NOT modify any files. Focus area (optional): $ARGUMENTS'
```

After Claude returns:
- Summarize the review findings to the user.
- Highlight any blocking issues vs nits.
- The user decides what to act on; do not auto-apply suggestions.
