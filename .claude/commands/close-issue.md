# Close Issue

Close GitHub issue #$ARGUMENTS after verifying its PR has been merged, and handle related issues.

## Instructions

### Step 1: Verify the PR is merged

1. **Find PRs that reference this issue:**
   ```bash
   gh pr list --state merged --search "$ARGUMENTS" --json number,title,body,mergedAt
   ```
   Also check:
   ```bash
   gh pr list --state merged --search "Addresses #$ARGUMENTS" --json number,title,body,mergedAt
   ```

2. **If no merged PR is found:**
   - Tell the user no merged PR was found for issue #$ARGUMENTS
   - Ask if they want to proceed anyway or check the PR status
   - Do NOT close the issue without a merged PR unless the user explicitly confirms

### Step 2: Update issue task checkboxes

1. **Fetch the current issue body:**
   ```bash
   gh issue view $ARGUMENTS --json body
   ```

2. **Check for task checkboxes** (`- [ ]` items) in the issue body.

3. **If task checkboxes exist:**
   - Review each task against the merged PR changes
   - Mark completed tasks as `- [x]`
   - Update the issue body with checked-off tasks:
     ```bash
     gh issue edit $ARGUMENTS --body "<updated body>"
     ```
   - Tell the user which tasks were marked complete and which remain unchecked (if any)

4. **If unchecked tasks remain**, ask the user:
   > "Some tasks in issue #$ARGUMENTS are not yet complete: <list>. Close anyway?"
   - Wait for user confirmation before proceeding

### Step 3: Close the primary issue

1. **Add a closing comment:**
   ```bash
   gh issue comment $ARGUMENTS --body "Addressed in PR #<pr-number>"
   ```

2. **Close the issue:**
   ```bash
   gh issue close $ARGUMENTS
   ```

3. **Confirm** to the user that issue #$ARGUMENTS has been closed.

### Step 4: Find and handle related issues

1. **Scan all merged PRs** for this issue to find referenced issues:
   ```bash
   gh pr view <pr-number> --json body,comments
   ```
   Search the PR body and comments for patterns like:
   - `Addresses #N`
   - `Part of #N`
   - `Related to #N`
   - `Closes #N`
   - `Fixes #N`
   - `References #N`
   - `#N` (bare issue references)

   Exclude the primary issue (#$ARGUMENTS) from this list.

2. **For each related issue found:**
   - Fetch its current state: `gh issue view <N> --json state,title`
   - Skip issues that are already closed
   - For each **open** related issue, ask the user:
     > "Issue #N: <title> is still open and was referenced in PR #<pr>. Would you like to close it?"
   - If the user says yes, close it with comment "Addressed in PR #<pr-number>"
   - If the user says no, move to the next one

3. **Summary:** After processing all related issues, show the user a summary:
   - Issues closed in this session
   - Issues left open
