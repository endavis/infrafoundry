# Dual-Agent PR Review

Both Claude and Gemini independently review the current branch's pull request
in separate contexts, then the user discusses the synthesized findings with
Claude in the current conversation.

## Instructions

### Step 1: Verify the PR exists

```bash
gh pr view --json number,title,body,headRefName
```

- If no PR exists for the current branch, tell the user and stop.
- Save the PR number for later use.

### Step 2: Generate both reviews in parallel (separate contexts)

Both reviews MUST be generated in isolated contexts so neither influences the other.

**Claude's review** — use the Task tool to spawn a subagent:

Prompt the subagent with:
> Read AGENTS.md and .github/CONTRIBUTING.md for project standards.
> Get the PR details via `gh pr view --json number,title,body,headRefName`.
> Get the diff via `gh pr diff`.
> Review the code for: correctness, code style, testing, security,
> documentation, architecture, and breaking changes.
> Create a review in this exact format:
>
> ## PR Review: #<number> — <title>
> ### Summary
> ### Findings
> #### Critical
> #### Suggestions
> #### Positive
> ### Verdict
> Approve, Request Changes, or Comment with justification.
>
> End with: `---` followed by `*Review by: Claude* | *Date: <today's date>*`
>
> Output ONLY the review markdown.

Save the subagent's output as Claude's review.

**Gemini's review** — invoke Gemini CLI non-interactively:

```bash
gemini -p "/review-pr" --yolo 2>/dev/null
```

Capture the stdout output as Gemini's review.

Run both in parallel if possible. If either fails or produces empty output,
report the error and ask the user if they want to continue with the other
agent's review only or retry.

### Step 3: Post both reviews to the PR

Post each review as a separate comment on the PR:

```bash
gh pr comment <PR_NUMBER> --body "<claude review>"
gh pr comment <PR_NUMBER> --body "<gemini review>"
```

### Step 4: Synthesize the findings

Read both reviews and create a synthesis that:
- Lists issues both agents flagged (highest priority — both caught it)
- Lists issues only one agent flagged (worth investigating)
- Notes disagreements in verdicts if any
- Provides a combined verdict with justification

Format:

```
## Combined Review Summary

### Consensus Findings (both agents flagged)
- Description of shared finding

### Claude-Only Findings
- Description of finding only Claude caught

### Gemini-Only Findings
- Description of finding only Gemini caught

### Combined Verdict
**Approve / Request Changes / Comment** — justification

---
*Synthesized Review by: Claude (from Claude + Gemini input)* | *Date: <today's date>*
```

### Step 5: Post and discuss

Post the synthesis to the PR:

```bash
gh pr comment <PR_NUMBER> --body "<synthesis>"
```

Present the synthesis to the user and highlight any areas that need attention.
