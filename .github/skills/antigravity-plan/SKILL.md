---
name: antigravity-plan
description: Use to delegate planning for a GitHub issue from a Copilot CLI session to Antigravity CLI (agy) via `agy -p`. Captures the plan from stdout and returns it to the user; does not post to GitHub itself.
---

# Delegate Plan to Antigravity (from Copilot)

Hand off planning work for a GitHub issue to Antigravity CLI (`agy`) via shell.

## When to use

Use this skill when the user explicitly wants planning done by Antigravity (not by Copilot). This is the Copilot-host bridge to Antigravity.

Expected prompt shape:

- `/antigravity-plan 399`
- `/antigravity-plan delegate planning for #399 to Antigravity`

If the issue number is missing, ask for it before continuing.

## Instructions

1. Confirm the issue number from the user's request.
2. Run Antigravity non-interactively. `agy` needs `--add-dir` pointed at the repo root so it loads the workspace (and the shared dangerous-command hook); `--dangerously-skip-permissions` auto-approves routine tools while that hook still hard-blocks unsafe ones.

   ```bash
   agy -p 'Plan the implementation for GitHub issue #<n> in the current repository. If an Antigravity planning skill (antigravity-plan) is available, use it for this issue. Otherwise, follow this workflow: 1) Run `gh issue view <n> --json title,body,labels` to read the issue. 2) Read AGENTS.md to understand the workflow and conventions. 3) Explore the relevant files. 4) Draft a plan with three sections: Implementation Plan, Test Plan, Validation Plan. 5) Print the full plan to stdout. Do NOT post a comment to the issue — the user reviews and posts.' --dangerously-skip-permissions --add-dir "$(git rev-parse --show-toplevel)"
   ```

3. Capture stdout and summarize the plan to the user.
4. If the user wants revisions, invoke Antigravity again with their feedback appended.
5. Do NOT post the plan as a comment yourself — the user owns that step.
