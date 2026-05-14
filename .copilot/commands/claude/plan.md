# Plan via Claude

Delegate planning for GitHub issue #$ARGUMENTS to Claude Code.

## Instructions

Run Claude Code non-interactively via shell. Hybrid C: prefer the existing `/claude:plan` command if available, otherwise inline workflow.

```bash
claude -p 'Plan the implementation for GitHub issue #$ARGUMENTS in the current repository. If the /claude:plan command is available, run it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view $ARGUMENTS --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.'
```

After Claude returns:
- Summarize the plan to the user.
- If the user wants revisions, invoke Claude again with their feedback appended to the prompt.
- Do not post the plan as a comment yourself — the user owns that step.
