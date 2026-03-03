# Plan Issue (Gemini)

Create an implementation plan for GitHub issue #$ARGUMENTS.

## Instructions

You are being invoked to provide a planning perspective. Your plan will be posted
to the GitHub issue by the orchestrating agent (Claude). Output clean markdown to
stdout — do NOT post to GitHub directly.

### Step 1: Fetch the issue details

```bash
gh issue view $ARGUMENTS --json title,body,labels,assignees
```

- Parse the issue body to understand what needs to be done
- Check if the issue has the `needs-adr` label

### Step 2: Read the project standards

- Read `AGENTS.md` — understand workflow, conventions, and patterns
- Identify relevant coding standards and testing requirements

### Step 3: Explore the codebase

- Identify which files, modules, and tests are relevant
- Understand existing patterns and conventions in the affected areas
- Check for related ADRs in `docs/decisions/`

### Step 4: Output the implementation plan

Output the plan in this exact format:

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
*Plan by: Gemini* | *Date: <today's date>*
```

### Important

- Output ONLY the plan markdown — no preamble, no conversational text
- Be specific about file paths and function names
- Include concrete test cases, not vague descriptions
- Note any risks or alternative approaches worth considering
