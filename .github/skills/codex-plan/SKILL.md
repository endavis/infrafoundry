---
name: codex-plan
description: Use to delegate planning for a GitHub issue from a Copilot CLI session to Codex CLI via `codex -a never --dangerously-bypass-hook-trust exec`. Captures the plan from stdout and returns it to the user; does not post to GitHub itself.
---

# Delegate Plan to Codex (from Copilot)

Hand off planning work for a GitHub issue to Codex CLI via shell.

## When to use

Use this skill when the user explicitly wants planning done by Codex (not by Copilot). This is the Copilot-host bridge equivalent of Codex's `$codex-plan`.

Expected prompt shape:

- `/codex-plan 399`
- `/codex-plan delegate planning for #399 to Codex`

If the issue number is missing, ask for it before continuing.

## Instructions

1. Confirm the issue number from the user's request.
2. Run Codex non-interactively. Hybrid C: prefer the existing `$codex-plan` skill if available, otherwise inline workflow. Single-quote the prompt so the literal `$codex-plan` reaches Codex (not the shell).

   ```bash
   codex -a never --dangerously-bypass-hook-trust exec 'Plan the implementation for GitHub issue #<n> in the current repository. If the $codex-plan skill is available, activate it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view <n> --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.'
   ```

3. Capture stdout and summarize the plan to the user.
4. If the user wants revisions, invoke Codex again with their feedback appended.
5. Do NOT post the plan as a comment yourself — the user owns that step.
