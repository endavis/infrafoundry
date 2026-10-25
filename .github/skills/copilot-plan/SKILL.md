---
name: copilot-plan
description: Use when planning work for a GitHub issue in this repository from a Copilot CLI session. Drafts an implementation plan, iterates with the user, and posts the approved plan as a comment with the repo's required header format.
---

# Plan Issue (Copilot)

Plan the implementation for a GitHub issue in this repository.

## When to use

Use this skill when the user wants Copilot to plan a GitHub issue. This is Copilot's self-action equivalent of `/claude:plan` / `$codex-plan`.

Expected prompt shape:

- `/copilot-plan 399`
- `/copilot-plan plan issue 399`

If the issue number is missing, ask for it before continuing.

## Instructions

This skill runs inline in the active Copilot session so the user can ask questions, discuss tradeoffs, and refine the plan interactively. After the user approves it, the plan is posted to the issue as a comment.

### Step 1: Validate the issue

1. **Verify the issue exists and is open:**
   ```bash
   gh issue view <issue-number> --json number,title,state,labels
   ```
   - If the issue does not exist, tell the user and stop.
   - If the issue is closed, tell the user and ask if they want to reopen it or stop.

2. **Check for an existing plan comment:**
   ```bash
   gh issue view <issue-number> --json comments --jq '.comments[].body' | grep -lE "^#+ Implementation Plan for"
   ```
   - If a plan comment already exists, warn the user:
     > "Issue #<n> already has an implementation plan comment. Continuing will post a new one. Proceed?"
   - Wait for user confirmation before continuing.

### Step 2: Read the project rules

- Read `AGENTS.md` — understand workflow, conventions, and commit guidelines.
- Identify relevant coding standards and testing requirements.

### Step 3: Fetch the issue details

```bash
gh issue view <issue-number> --json title,body,labels,assignees
```

- Parse the issue body to understand what needs to be done.
- Check if the issue has the `needs-adr` label.

### Step 4: Explore the codebase

- Identify which files, modules, and tests are relevant.
- Understand existing patterns and conventions in the affected areas.
- Check for related ADRs in `docs/decisions/`.
- If anything is ambiguous or there are multiple valid approaches, **ask the user** before deciding.

### Step 5: Draft the plan and iterate with the user

Draft the plan in this exact format and present it to the user:

```
## Implementation Plan for #<number>: <title>

### Overview
Brief description of what will be done.

### Files to Create/Modify
- [ ] `path/to/file.py` — description of changes
- [ ] `tests/test_file.py` — description of test coverage

### Test Plan
- [ ] Test case 1: description
- [ ] Test case 2: description

### Documentation
- [ ] Any docs that need updating
- [ ] ADR needed: yes/no (if yes, brief description)

### Validation
- [ ] `doit check` passes
- [ ] Manual verification steps

### Risks and Considerations
- Any potential issues, edge cases, or trade-offs to consider

---
*Plan by: Copilot* | *Date: <today's date>*
```

Then:

1. Ask the user for feedback on the plan.
2. Discuss alternatives, answer questions, and adjust the plan as the user requests.
3. Keep iterating until the user explicitly says the plan is approved.
4. Do NOT post the plan until the user confirms approval.

### Step 6: Post the approved plan to the issue

Only after the user explicitly approves the plan, post it as a comment:

```bash
gh issue comment <issue-number> --body "<approved plan>"
```

Tell the user:
- The plan has been posted as a comment on issue #<n>.
- When ready, use `/copilot-implement <n>` to start implementation.
