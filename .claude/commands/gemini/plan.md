# Plan via Gemini

Delegate planning for GitHub issue #$ARGUMENTS to Gemini CLI.

## Instructions

Use the Bash tool to invoke Gemini non-interactively. Hybrid C: prefer the existing `/gemini:plan` command if available, otherwise inline workflow.

```bash
gemini -y -p 'Plan the implementation for GitHub issue #$ARGUMENTS in the current repository. If the /gemini:plan command is available, run it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view $ARGUMENTS --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.'
```

After Gemini returns:
- Summarize the plan to the user.
- If the user wants revisions, invoke Gemini again with their feedback appended to the prompt.
- Do not post the plan as a comment yourself — the user owns that step.
