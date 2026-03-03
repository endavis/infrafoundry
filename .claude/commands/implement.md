# Implement Issue

Implement the plan for GitHub issue #$ARGUMENTS.

## Instructions

**CRITICAL: Do NOT enter plan mode. Do NOT use EnterPlanMode. This command executes code directly — plan mode will block the implementation agent from writing files.**

You MUST delegate the implementation to an agent (Task tool) to keep the main conversation context clean. The agent does all the coding. You receive the summary for user review.

### Step 1: Validate preconditions

1. **Verify the issue exists and is open:**
   ```bash
   gh issue view $ARGUMENTS --json number,title,state,labels
   ```
   - If the issue does not exist or is closed, tell the user and stop.

2. **Verify a plan comment exists:**
   Fetch all comments and search for the plan header:
   ```bash
   gh api repos/{owner}/{repo}/issues/$ARGUMENTS/comments --jq '.[].body' | grep "## Implementation Plan for"
   ```
   - If no plan comment is found, tell the user:
     > "No implementation plan found for issue #$ARGUMENTS. Run `/plan-issue $ARGUMENTS` first."
   - Stop and wait for the user.

3. **Check current branch state:**
   ```bash
   git branch --show-current
   git status --short
   ```
   - If already on a branch matching `*/$ARGUMENTS-*` (e.g., `feat/$ARGUMENTS-description`):
     - Tell the user you're resuming work on the existing branch
     - Skip branch creation (Step 2)
     - If there are uncommitted changes, warn the user and ask how to proceed
   - If on `main` or a different branch: proceed to Step 2

### Step 2: Create the branch

Only if not already on the correct branch:

1. Fetch the issue to determine the branch type:
   ```bash
   gh issue view $ARGUMENTS --json title,labels
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
   git checkout -b <type>/$ARGUMENTS-<short-description>
   ```

### Step 3: Spawn an implementation agent

Use the Task tool with `subagent_type: "general-purpose"` and provide it with the issue number and branch name. The agent should:

1. **Read the project rules:**
   - Read `AGENTS.md` — understand workflow, conventions, code style, testing guidelines
   - Read `.claude/CLAUDE.md` — understand TodoWrite requirements

2. **Fetch the implementation plan:**
   Retrieve all comments and find the one containing `## Implementation Plan for`:
   ```bash
   gh api repos/{owner}/{repo}/issues/$ARGUMENTS/comments --jq '.[] | select(.body | contains("## Implementation Plan for")) | .body'
   ```
   - If multiple plan comments exist, use the most recent one
   - Parse the plan to extract the file list and test plan

3. **Implement the plan:**
   - Follow the plan step by step
   - Create implementation files
   - Create test files — this is MANDATORY, never skip tests
   - Follow existing code patterns and conventions

4. **Run validation:**
   - Run: `doit check`
   - If checks fail, fix the issues and re-run
   - Do NOT give up after first failure — investigate and fix

5. **Return a summary** of all changes made:
   - Files created/modified with brief descriptions
   - Test results (pass/fail counts)
   - Any deviations from the plan and why

### Step 4: Present changes to user

After the agent returns, show the user:
- Summary of what was implemented
- Files changed
- Test results
- Any issues or deviations from the plan

Tell the user:
- Review the changes and test as needed
- Discuss any fixes directly in conversation (no command needed)
- When satisfied, use `/finalize` to commit and create a PR
