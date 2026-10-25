---
name: copilot-implement
description: Use when implementing an approved plan for a GitHub issue from a Copilot CLI session. Verifies the plan comment, creates or resumes the feature branch, implements the changes inline with tests, and runs `doit check`.
---

# Implement Issue (Copilot)

Implement the plan for a GitHub issue in this repository.

## When to use

Use this skill when the user wants Copilot to implement an approved plan. This is Copilot's self-action equivalent of `/claude:implement` / `$codex-implement`.

Expected prompt shape:

- `/copilot-implement 399`
- `/copilot-implement implement issue 399`

If the issue number is missing, ask for it before continuing.

## Instructions

This skill performs the implementation of an approved plan for the specified issue. Copilot executes the implementation steps directly within the main conversation context.

### Step 1: Validate preconditions

1. **Verify the issue exists and is open:**
   ```bash
   gh issue view <issue-number> --json number,title,state,labels
   ```
   - If the issue does not exist or is closed, tell the user and stop.

2. **Verify a plan comment exists:**
   Fetch all comments and search for the plan header:
   ```bash
   gh api repos/{owner}/{repo}/issues/<issue-number>/comments --jq '.[].body' | grep -E "^#+ Implementation Plan for"
   ```
   - If no plan comment is found, tell the user:
     > "No implementation plan found for issue #<n>. Run `/copilot-plan <n>` first."
   - Stop and wait for the user.

3. **Check current branch state:**
   ```bash
   git branch --show-current
   git status --short
   ```
   - If already on a branch matching `*/<n>-*` (e.g., `feat/<n>-description`):
     - Tell the user you're resuming work on the existing branch
     - Skip branch creation (Step 2)
     - If there are uncommitted changes, warn the user and ask how to proceed
   - If on `main` or a different branch: proceed to Step 2

### Step 2: Create the branch

Only if not already on the correct branch:

1. Fetch the issue to determine the branch type:
   ```bash
   gh issue view <issue-number> --json title,labels
   ```
2. Determine branch type from labels:
   - `enhancement` → `feat`
   - `bug` → `fix`
   - `refactor` → `refactor`
   - `documentation` → `docs`
   - `chore` → `chore`
   - Default → `issue`
3. Create and switch to branch:
   ```bash
   git checkout main && git pull
   git checkout -b <type>/<n>-<short-description>
   ```

### Step 3: Implementation

Execute the implementation directly in the current context:

1. **Read the plan:** Fetch the plan comment again and use it as your implementation guide.
2. **Read project rules:**
   - Read `AGENTS.md` — understand workflow, conventions, and patterns.
   - Read `.github/CONTRIBUTING.md` — understand commit format.
3. **Explore the codebase:** Identify relevant files, modules, and tests if not already known from the planning phase.
4. **Implement changes:**
   - Create or modify the files as specified in the plan.
   - Follow existing patterns and conventions.
   - **Always include tests:** Add or update test files to verify your changes.

### Step 4: Run validation

1. Run `doit check` and iterate on any failures until they are resolved.

### Step 5: Present changes to user

Show the user:
- Summary of what was implemented
- Files changed
- Test results
- Any issues or deviations from the plan

Tell the user:
- Review the changes and test as needed
- Discuss any fixes directly in conversation
- When satisfied, use `/ghi-finalize` to commit and create a PR
