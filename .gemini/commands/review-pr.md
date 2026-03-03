# Review PR (Gemini)

Review the pull request for the current branch.

## Instructions

You are being invoked to provide a code review perspective. Your review will be
posted to the PR by the orchestrating agent (Claude). Output clean markdown to
stdout — do NOT post to GitHub directly.

### Step 1: Identify the PR

```bash
gh pr view --json number,title,body,baseRefName,headRefName
```

If no PR exists for the current branch, output an error message and stop.

### Step 2: Identify the Issue
Scan the PR for "Addresses #XXX" for the issue number
```bash
gh issue view {issue number} --json body,comments
```

### Step 3: Read the project standards

- Read `AGENTS.md` — understand code style, testing requirements, and conventions
- Read `.github/CONTRIBUTING.md` — understand contribution guidelines

### Step 4: Get the changes

```bash
gh pr diff
```

Review the full diff carefully.

### Step 5: Analyze the changes

Review the code for:

1. **Issue and Plan** - Does it fulfil the issue and plan?
2. **Correctness** — Does the logic work? Are there bugs or edge cases?
3. **Code Style** — Does it follow project conventions from AGENTS.md?
4. **Testing** — Are tests adequate? Are edge cases covered?
5. **Security** — Any OWASP top 10 vulnerabilities? Command injection, path traversal, etc.?
6. **Documentation** — Are docstrings/comments appropriate? Does behavior change need doc updates?
7. **Architecture** — Does it follow existing patterns? Is there tight coupling?
8. **Breaking Changes** — Does this change public APIs or default behavior?

If the diff alone is insufficient to evaluate a pattern or convention, read the
relevant source file for context. Do not read every touched file upfront — only
when a specific finding requires it.

### Step 6: Output the review

Output the review in this exact format:

```
## PR Review: #<number> — <title>

### Summary
Brief assessment of the changes (1-2 sentences).

### Findings

#### Critical
- [ ] Description of critical issue (if any)

#### Suggestions
- [ ] Description of suggested improvement (if any)

#### Positive
- Notable good practices or well-implemented aspects

### Verdict
One of: **Approve**, **Request Changes**, or **Comment**

Brief justification for the verdict.

---
*Review by: Gemini* | *Date: <today's date>*
```

### Important

- Output ONLY the review markdown — no preamble, no conversational text
- Be specific: reference file paths and line ranges
- Distinguish between critical issues (must fix) and suggestions (nice to have)
- If the code looks good, say so — don't invent issues to fill space
