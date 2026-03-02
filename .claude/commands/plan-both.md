# Dual-Agent Plan

Both Claude and Gemini independently create implementation plans for GitHub issue
#$ARGUMENTS in separate contexts, then the user discusses the synthesized plan
with Claude in the current conversation.

## Instructions

### Step 1: Validate the issue

```bash
gh issue view $ARGUMENTS --json number,title,state,labels
```

- If the issue does not exist, tell the user and stop.
- If the issue is closed, tell the user and ask if they want to reopen it or stop.

### Step 2: Check for existing plans

```bash
gh issue view $ARGUMENTS --json comments --jq '.comments[].body' | grep -l "## Implementation Plan for"
```

- If plan comments already exist, warn the user:
  > "Issue #$ARGUMENTS already has implementation plan comments. Continuing will post new ones. Proceed?"
- Wait for user confirmation before continuing.

### Step 3: Generate both plans in parallel (separate contexts)

Both plans MUST be generated in isolated contexts so neither influences the other.

**Claude's plan** — use the Task tool to spawn a subagent:

Prompt the subagent with:
> Read AGENTS.md and .claude/CLAUDE.md for project standards.
> Fetch issue #$ARGUMENTS via `gh issue view $ARGUMENTS --json title,body,labels,assignees`.
> Explore the codebase to understand relevant files, patterns, and tests.
> Create an implementation plan in this exact format:
>
> ## Implementation Plan for #<number>: <title>
> ### Overview
> ### Files to Create/Modify
> ### Test Plan
> ### Documentation
> ### Validation
> ### Risks and Considerations
>
> End with: `---` followed by `*Plan by: Claude* | *Date: <today's date>*`
>
> Output ONLY the plan markdown.

Save the subagent's output as Claude's plan.

**Gemini's plan** — invoke Gemini CLI non-interactively:

```bash
gemini -p "/plan-issue $ARGUMENTS" --yolo 2>/dev/null
```

Capture the stdout output as Gemini's plan.

Run both in parallel if possible. If either fails or produces empty output,
report the error and ask the user if they want to continue with the other
agent's plan only or retry.

### Step 4: Post both plans to the issue

Post each plan as a separate comment on the issue:

```bash
gh issue comment $ARGUMENTS --body "<claude plan>"
gh issue comment $ARGUMENTS --body "<gemini plan>"
```

### Step 5: Synthesize the final plan

Read both plans and create a synthesized final plan that:
- Combines the best elements from both plans
- Resolves any conflicts or contradictions between them
- Notes where the plans agreed (higher confidence)
- Notes where they diverged (needs discussion)
- Preserves the standard plan format (Overview, Files, Test Plan, Documentation, Validation)

Add the signature:
```
---
*Synthesized Plan by: Claude (from Claude + Gemini input)* | *Date: <today's date>*
```

### Step 6: Review with user

Present the synthesized plan to the user for discussion:
- Highlight areas where the two agents disagreed
- Ask for feedback and iterate as needed
- Do NOT post the synthesized plan until the user approves it

### Step 7: Post the approved synthesized plan

Only after the user approves:

```bash
gh issue comment $ARGUMENTS --body "<synthesized plan>"
```

Tell the user:
- All three plans (Claude, Gemini, Synthesized) have been posted to issue #$ARGUMENTS
- When ready, use `/implement $ARGUMENTS` to start implementation
