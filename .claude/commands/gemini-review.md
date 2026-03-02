# Gemini PR Review

Invoke Gemini CLI to review the current branch's pull request and post findings to the PR.

## Instructions

This command runs in the main conversation context. It invokes Gemini CLI
non-interactively to get a code review, then posts the findings to the PR.

### Step 1: Verify the PR exists

```bash
gh pr view --json number,title,headRefName
```

- If no PR exists for the current branch, tell the user and stop.
- Save the PR number for later use.

### Step 2: Invoke Gemini CLI

Run Gemini in non-interactive mode:

```bash
gemini -p "/review-pr" --yolo 2>/dev/null
```

- Capture the stdout output — this is Gemini's review in markdown format.
- If Gemini fails or produces empty output, report the error and stop.

### Step 3: Post the review to the PR

Post Gemini's review as a PR comment:

```bash
gh pr comment <PR_NUMBER> --body "<gemini review output>"
```

### Step 4: Report to user

Tell the user:
- Gemini's review has been posted to PR #<number>
- Provide a brief summary of Gemini's findings (verdict, critical issues if any)
