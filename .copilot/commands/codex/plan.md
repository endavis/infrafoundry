# Plan via Codex

Delegate planning for GitHub issue #$ARGUMENTS to Codex CLI.

## Instructions

Run Codex non-interactively via shell. Hybrid C: prefer the existing `$codex-plan` skill if available, otherwise inline workflow. Single-quote the prompt so the literal `$codex-plan` reaches Codex (not the shell).

```bash
codex -a never exec 'Plan the implementation for GitHub issue #$ARGUMENTS in the current repository. If the $codex-plan skill is available, activate it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view $ARGUMENTS --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.'
```

After Codex returns:
- Summarize the plan to the user.
- If the user wants revisions, invoke Codex again with their feedback appended to the prompt.
- Do not post the plan as a comment yourself — the user owns that step.
