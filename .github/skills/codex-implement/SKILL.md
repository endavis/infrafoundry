---
name: codex-implement
description: Use to delegate implementation of a GitHub issue from a Copilot CLI session to Codex CLI via `codex -a never --dangerously-bypass-hook-trust exec`. Captures the resulting summary; does not push or open a PR.
---

# Delegate Implement to Codex (from Copilot)

Hand off implementation work for a GitHub issue to Codex CLI via shell.

## When to use

Use this skill when the user explicitly wants implementation done by Codex (not by Copilot). This is the Copilot-host bridge equivalent of Codex's `$codex-implement`.

Expected prompt shape:

- `/codex-implement 399`
- `/codex-implement delegate implementation of #399 to Codex`

If the issue number is missing, ask for it before continuing.

## Instructions

1. Confirm the issue number from the user's request.
2. Run Codex non-interactively. Hybrid C: prefer the existing `$codex-implement` skill if available, otherwise inline workflow.

   ```bash
   codex -a never --dangerously-bypass-hook-trust exec 'Implement GitHub issue #<n> in the current repository. If the $codex-implement skill is available, activate it for this issue. Otherwise, follow this workflow: 1) Read the plan comment from issue #<n> via `gh issue view <n> --json comments`. 2) Read AGENTS.md for branch naming and commit conventions. 3) Create or check out the branch `<type>/<n>-<slug>` (do not commit to main). 4) Implement the changes per the plan. 5) Run `doit check` to validate. Do NOT push the branch or open a PR — the user reviews first.'
   ```

3. After Codex returns:
   - Summarize what was implemented and the `doit check` result.
   - Show the user the changed files (`git status`, `git diff --stat`) so they can review.
   - Do not push or open a PR yourself.
