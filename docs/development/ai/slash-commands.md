---
title: Slash Commands and Workflows
description: Reference for the slash commands and dual-agent workflow this template ships with
audience:
  - contributors
  - ai-agents
tags:
  - ai
  - workflow
  - slash-commands
---

# Slash Commands and Workflows

## Purpose

This page documents the slash commands this template ships under `.claude/commands/` and `.gemini/commands/`, and the single-agent and dual-agent workflows built on top of them. It is written for contributors who want to understand or extend the workflow, and for AI agents that need to know which command to run at each stage of the issue lifecycle.

## Workflows

### Single-agent workflow

The default Claude flow takes an issue from unplanned to closed. Each step produces an artifact the next step expects.

1. **`/plan-issue <n>`** — Claude enters plan mode in the main conversation, reads project rules, explores the codebase, drafts a plan, and iterates with the user until approved. On approval the plan is posted as a comment on issue `#n` with the header `## Implementation Plan for #<n>: <title>`. The next step expects this comment to exist.
2. **User review of the plan** — read the comment, discuss revisions in chat, re-run `/plan-issue` if needed.
3. **`/implement <n>`** — Claude verifies the plan comment exists, creates a branch (`<type>/<n>-<short-description>`) off fresh `main`, then spawns a subagent (Task tool) that reads `AGENTS.md`, fetches the plan, implements files and tests, and runs `doit check`. The main context receives only the summary. The artifact is an uncommitted working tree on the feature branch.
4. **User review of the changes** — inspect the diff and discuss fixes directly in chat; no command is needed for fix-ups.
5. **`/finalize`** — Claude detects the branch and issue, spawns a finalization subagent that updates docs/ADRs as needed, runs `doit check`, and drafts a commit message and PR body. The main context presents the drafts and waits for explicit user approval before staging, committing, and creating the PR via `doit pr`. The artifact is an open PR referencing `Addresses #<n>`.
6. **User-driven merge** — the user reviews the PR, adds the `ready-to-merge` label, and merges via `doit pr_merge` (or the web UI). This step is never automated.
7. **`/close-issue <n>`** — Claude verifies a merged PR addresses `#n`, updates task checkboxes in the issue body, posts `Addressed in PR #<pr>`, closes the issue, and scans the PR for related issues to optionally close as well.

### Dual-agent workflow

The dual-agent flow replaces the planning and (optionally) review steps with orchestrated calls that spawn Claude and Gemini in **isolated contexts**. The design intent is that neither agent can bias the other: each generates its output without seeing the other's work, and the orchestrating Claude agent in the main conversation posts both raw outputs plus a synthesis.

Gemini commands under `.gemini/commands/` are **output-only**: Gemini does not post to GitHub itself. The orchestrating Claude agent captures Gemini's stdout and posts it via `gh`.

1. **`/plan-both <n>`** — replaces `/plan-issue`. Claude validates the issue, then in parallel (a) spawns a general-purpose subagent to produce a Claude plan and (b) invokes `gemini -p "/plan-issue <n>" --yolo` to produce a Gemini plan. Both are posted as separate comments on the issue, Claude synthesizes a combined plan, reviews it with the user, and posts the approved synthesized plan.
2. **`/implement <n>`** — same as the single-agent flow. The synthesized plan comment is the input.
3. **`/review-both`** — runs after a PR exists. In parallel spawns a Claude review subagent and invokes `gemini -p "/review-pr" --yolo`, posts both reviews as PR comments, and posts a combined synthesis listing consensus findings, agent-specific findings, and a combined verdict. Alternatively, **`/gemini-review`** runs only the Gemini review and posts it (useful when the user wants a second opinion without a full Claude review).
4. **`/finalize`**, merge, and **`/close-issue <n>`** — same as the single-agent flow.

### Diagnostic command

**`/where-am-i`** can be invoked at any point. It inspects the current branch, issue state, plan comment, uncommitted changes, unpushed commits, and open PRs, then reports a status summary and the suggested next command. It has no side effects.

## Command reference

Entries are alphabetical. Each one names the command, its arguments, what it does, its position in the workflow, and any design note worth knowing.

### `/close-issue <n>`

**Args:** issue number. **Source:** `.claude/commands/close-issue.md`.

Verifies a merged PR references `#n`, updates task checkboxes in the issue body, posts the closing comment `Addressed in PR #<pr-number>`, closes the issue via `gh issue close`, then scans the PR body and comments for related issue references (`Addresses`, `Part of`, `Related to`, `Closes`, `Fixes`, `References`, bare `#N`) and asks the user individually whether to close each open related issue. **Workflow position:** last step of both single-agent and dual-agent flows. **Design note:** never closes an issue without a merged PR unless the user explicitly confirms; never closes related issues without per-issue confirmation.

### `/finalize`

**Args:** none. **Source:** `.claude/commands/finalize.md`.

Operates on the current feature branch, assuming implementation and review are complete. In the main context it detects the branch, extracts the issue number from the branch name, fetches issue details, and checks for uncommitted changes. It then spawns a general-purpose subagent that reads `AGENTS.md`, `.github/CONTRIBUTING.md`, and `.github/pull_request_template.md`, reviews changed files for doc/ADR updates, runs `doit check`, and drafts a commit message plus a PR body written to a temp file. The main context then presents the drafts to the user, waits for explicit approval, stages files, commits, and creates the PR via `doit pr --title=... --body-file=...`. **Workflow position:** after implementation and review. **Design note:** will not commit or create the PR without explicit user confirmation; stops if run on `main`.

### `/gemini-review`

**Args:** none. **Source:** `.claude/commands/gemini-review.md`.

Runs in the main conversation context. Verifies a PR exists for the current branch, invokes `gemini -p "/review-pr" --yolo` to get a Gemini-authored review as stdout markdown, and posts the output as a comment on the PR via `gh pr comment`, then reports a brief summary to the user. **Workflow position:** optional second-opinion review on an open PR. **Design note:** Gemini does not post to GitHub itself — the orchestrating Claude agent posts the captured stdout.

### `/implement <n>`

**Args:** issue number. **Source:** `.claude/commands/implement.md`.

Validates that the issue is open and that a plan comment exists (otherwise instructs the user to run `/plan-issue <n>` first). Checks the current branch: if already on `<type>/<n>-*` it resumes work on that branch, otherwise it checks out `main`, pulls, and creates a new branch whose type is derived from the issue's labels (`enhancement`→`feat`, `bug`→`fix`, `refactor`→`refactor`, `documentation`→`docs`, `chore`→`chore`, else `issue`). It then spawns the custom `implement-worker` subagent (defined in `.claude/agents/implement-worker.md`) that reads `AGENTS.md` and `.claude/CLAUDE.md`, fetches the plan via `gh api`, implements files and tests, and runs `doit check`, fixing failures rather than giving up. The main context receives only the summary. **Workflow position:** after plan exists, before `/finalize`. **Design note:** the subagent pattern keeps the main conversation context clean. The command now spawns `implement-worker` rather than the built-in `general-purpose` subagent. The custom subagent has `permissionMode: default` in its YAML frontmatter — per Claude Code's documented sub-agent precedence rules, this should escape parent plan mode because plan mode is not in the parent-overrides-child list. The status-line preamble warning (telling the user to check for "plan mode" before running) is retained as belt-and-suspenders while the override is empirically validated; it can be removed in a follow-up once confirmed on the shipping Claude Code version.


### `/plan-both <n>`

**Args:** issue number. **Source:** `.claude/commands/plan-both.md`.

Dual-agent replacement for `/plan-issue`. Validates the issue, warns if plan comments already exist, then generates two plans in isolated contexts — a Claude plan via a spawned subagent and a Gemini plan via `gemini -p "/plan-issue <n>" --yolo` — posts both as separate issue comments, synthesizes a combined plan that highlights agreements and divergences, reviews the synthesis with the user, and only posts the synthesized plan after explicit approval. **Workflow position:** first step of the dual-agent workflow. **Design note:** isolated contexts are mandatory so neither agent can see the other's output while drafting; Claude is the orchestrator and the only agent that writes to GitHub.

### `/plan-issue <n>`

**Args:** issue number. **Source:** `.claude/commands/plan-issue.md`.

Runs in the main conversation context (not a subagent) so the user can ask questions and refine the plan interactively. Enters plan mode, validates the issue, warns if a plan comment already exists, reads `AGENTS.md` and `.claude/CLAUDE.md`, fetches issue details, explores the codebase, and drafts a plan with the standard sections (Overview, Files to Create/Modify, Test Plan, Documentation, Validation). It iterates inside plan mode with `AskUserQuestion` until the user approves, then exits plan mode and posts the approved plan as an issue comment. **Workflow position:** first step of the single-agent workflow. **Design note:** plan mode is preserved throughout iteration; exiting plan mode means "post the approved plan", nothing more.

### `/review-both`

**Args:** none. **Source:** `.claude/commands/review-both.md`.

Dual-agent PR review. Verifies a PR exists for the current branch, then in parallel spawns a general-purpose Claude review subagent and invokes `gemini -p "/review-pr" --yolo`, posts both reviews as separate PR comments, and posts a synthesis listing consensus findings (both agents flagged), Claude-only findings, Gemini-only findings, and a combined verdict. **Workflow position:** after `/implement`, before `/finalize`, in the dual-agent workflow. **Design note:** same isolation guarantee as `/plan-both` — neither reviewer sees the other's output; the synthesis is posted after both raw reviews so readers can audit the synthesis against the sources.

### `/where-am-i`

**Args:** none. **Source:** `.claude/commands/where-am-i.md`.

Inspects the current git state (branch, uncommitted changes, recent log), extracts the issue number from the branch name if on a feature branch, checks for a plan comment, unpushed commits, and open PRs, then reports a status summary and suggests the next command to run. **Workflow position:** any time. **Design note:** read-only and side-effect-free — safe to run whenever the user is unsure where they are in the lifecycle.

### `/plan-issue <n>` (Gemini)

**Args:** issue number. **Source:** `.gemini/commands/plan-issue.md`.

Invoked by Claude's `/plan-both` orchestration command via `gemini -p "/plan-issue <n>" --yolo`. Fetches the issue, reads `AGENTS.md`, explores the codebase, and outputs a plan in the standard format to stdout, signed `*Plan by: Gemini*`. **Workflow position:** called indirectly from `/plan-both`. **Design note:** output-only — the command explicitly instructs Gemini not to post to GitHub; the orchestrating Claude agent captures stdout and posts it.

### `/review-pr` (Gemini)

**Args:** none. **Source:** `.gemini/commands/review-pr.md`.

Invoked by Claude's `/review-both` and `/gemini-review` commands via `gemini -p "/review-pr" --yolo`. Identifies the current branch's PR, scans for `Addresses #XXX` to find the issue, reads `AGENTS.md` and `.github/CONTRIBUTING.md`, runs `gh pr diff`, reviews the changes for correctness, style, testing, security, documentation, architecture, and breaking changes, and outputs a review in the standard format to stdout, signed `*Review by: Gemini*`. **Workflow position:** called indirectly from `/review-both` or `/gemini-review`. **Design note:** output-only for the same reason as the Gemini plan command.

## Codex

The `.codex/` directory contains only `config.toml`, which configures command approval policies for the Codex CLI. No slash commands ship for Codex. The dual-agent workflow in this template targets Claude and Gemini.

## Copilot

GitHub Copilot CLI automatically discovers project skills from `.claude/commands/`. All workflow commands (`/plan-issue`, `/implement`, `/finalize`, `/close-issue`, `/where-am-i`, etc.) are available in Copilot sessions without any additional files.

**Config directory:** `.copilot/` — established as the Copilot CLI config directory for this repo, parallel to `.claude/`, `.gemini/`, and `.codex/`.

**Dangerous command hook:** Already wired in `.github/hooks/copilot-hooks.json`. It invokes `tools/hooks/ai/block-dangerous-commands.py` as a `preToolUse` hook, blocking dangerous shell commands before they execute. See [AI Command Blocking](command-blocking.md) for details.

**Implement-worker subagent:** Shared with Claude — defined in `.claude/agents/implement-worker.md`. Copilot CLI's `task` tool reads this file when `/implement` spawns the subagent.

**No parallel command files needed:** Because Copilot CLI discovers skills from `.claude/commands/` directly, you do not need to maintain a separate `.copilot/commands/` directory unless you need to override Claude-specific behavior for Copilot sessions.

## Adding a new slash command

1. **Pick the location.** Claude commands live in `.claude/commands/<name>.md` and become `/<name>` in Claude Code. Gemini commands live in `.gemini/commands/<name>.md` and become `/<name>` in Gemini CLI. Copilot CLI auto-discovers skills from `.claude/commands/` — no separate `.copilot/commands/<name>.md` is needed unless you want to override Claude-specific behaviour for Copilot sessions.
2. **Use the CLI file format** — not the `docs/` frontmatter format. Start with a top-level `# Title` heading, follow with a one-line description (which may include the `$ARGUMENTS` placeholder if the command takes arguments), then a `## Instructions` section containing the step-by-step body. **Do not add YAML frontmatter.** The CLIs expect plain markdown; frontmatter would appear verbatim in the rendered prompt.
3. **Use `$ARGUMENTS` for inputs.** When the user invokes `/<command> foo bar`, every `$ARGUMENTS` occurrence in the file is substituted with `foo bar` before the command body is sent to the model. For commands that take no arguments (like `/finalize` or `/where-am-i`), omit the placeholder.
4. **Decide: subagent or main context?** Delegate to a general-purpose subagent via the Task tool when the command does heavy codebase exploration, writes files, or runs long commands whose output would bloat the main conversation — `.claude/commands/implement.md` is the canonical example. Run in the main context when the user needs to interact step by step (plan mode, iteration, explicit approvals) — `.claude/commands/plan-issue.md` is the canonical example.
5. **Update this document** when you add or remove a command. The command reference section should list every file under `.claude/commands/` and `.gemini/commands/`.

## See also

- [First 5 Minutes with an AI Agent](first-5-minutes.md) — narrative onboarding walkthrough showing the workflow end to end.
- [AI Agent Setup Guide](../AI_SETUP.md) — per-CLI configuration and whitelists.
- [Architectural Conventions](architectural-conventions.md) — imperative rules for AI-generated code.
- [AI Enforcement Principles](enforcement-principles.md) — how this template enforces rules in code, not just instructions.
- [AI Command Blocking](command-blocking.md) — tool-level hooks that block dangerous commands.
- [AGENTS.md](../../../AGENTS.md) — universal context file and workflow reference.
