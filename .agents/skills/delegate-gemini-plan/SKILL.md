---
name: delegate-gemini-plan
description: Delegate planning for a GitHub issue from a Codex session to Gemini CLI. Hands the planning work to Gemini via `gemini -p` and returns the plan to Codex.
---

# Delegate Plan to Gemini

Hand off planning work for a GitHub issue to Gemini CLI from a Codex session.

## When to use

Use this skill when the user explicitly wants planning done by Gemini (not Codex itself).

Expected prompt shape:

- `$delegate-gemini-plan plan issue 399`
- `$delegate-gemini-plan delegate planning for #399 to Gemini`

If the issue number is missing, ask for it before continuing.

## Instructions

1. Confirm the issue number from the user's request.
2. Run Gemini CLI non-interactively. Hybrid C: prefer the existing `/gemini:plan` command if available, otherwise inline workflow.

   ```bash
   gemini -y -p 'Plan the implementation for GitHub issue #<n> in the current repository. If the /gemini:plan command is available, run it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view <n> --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.'
   ```

3. Capture stdout and summarize the plan to the user.
4. If the user wants revisions, invoke Gemini again with their feedback appended.
5. Do NOT post the plan as a comment yourself — the user owns that step.
