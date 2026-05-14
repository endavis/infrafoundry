---
name: delegate-gemini-implement
description: Delegate implementation of a GitHub issue from a Codex session to Gemini CLI. Hands implementation work to Gemini via `gemini -p` and returns the result to Codex.
---

# Delegate Implement to Gemini

Hand off implementation work for a GitHub issue to Gemini CLI from a Codex session.

## When to use

Use this skill when the user explicitly wants implementation done by Gemini (not Codex itself).

Expected prompt shape:

- `$delegate-gemini-implement implement issue 399`
- `$delegate-gemini-implement delegate implementation of #399 to Gemini`

If the issue number is missing, ask for it before continuing.

## Instructions

1. Confirm the issue number from the user's request.
2. Run Gemini CLI non-interactively. Hybrid C: prefer the existing `/gemini:implement` command if available, otherwise inline workflow.

   ```bash
   gemini -y -p 'Implement GitHub issue #<n> in the current repository. If the /gemini:implement command is available, run it for this issue. Otherwise, follow this workflow: 1) Read the plan comment from issue #<n> via `gh issue view <n> --json comments`. 2) Read AGENTS.md for branch naming and commit conventions. 3) Create or check out the branch `<type>/<n>-<slug>` (do not commit to main). 4) Implement the changes per the plan. 5) Run `doit check` to validate. Do NOT push the branch or open a PR — the user reviews first.'
   ```

3. Capture stdout and summarize what was implemented and the `doit check` result.
4. Show the user the changed files (`git status`, `git diff --stat`).
5. Do NOT push or open a PR yourself.
