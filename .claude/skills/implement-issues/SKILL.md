---
name: implement-issues
description: Use when the user says "implement issues A, B and C" (or "implement issues A and B", "work on issues A, B", "take issues A, B to PRs") — several issues in one request. Checks every issue is open and that their likely files do not overlap, creates one worktree per issue, runs implement-issue for each in its own background agent (default 2 at a time, --max=N overrides), and reports one PR per issue. "check only" stops after the overlap check. Never adds ready-to-merge, never merges, never closes an issue. For a single issue use implement-issue.
---

# Implement Issues

Take several open GitHub issues to one PR each, in parallel, from a single session. Each issue runs
[`implement-issue`](../implement-issue/SKILL.md) end to end in its own worktree and its own
background agent. "Implement issues A, B and C" authorizes, per issue, what "implement issue N"
authorizes: commit, push and PR creation on that issue's own branch. It is not consent to add
`ready-to-merge`, merge or close.

## Instructions

The arguments are two or more issue numbers, optionally `--max=N` (concurrency cap, default 2) and
`check only`. With a single number, tell the user to use `implement-issue` and stop. Run Steps 1 to 4
from the main checkout and never leave it.

### Step 1: Pre-flight (before any worktree exists)

For each issue:

```bash
gh issue view <n> --json number,title,state,labels,body
gh api repos/{owner}/{repo}/issues/<n>/comments --jq '.[] | select(.body | test("^#+ Implementation Plan for"; "m")) | .body'
```

- The issue must be open. If one is closed, drop it and say so.
- Determine the branch type from its labels with the mapping in
  [implement-issue Step 1.2](../implement-issue/SKILL.md#step-1-preconditions). Do not restate the
  mapping here.
- Build its likely file set from the paths named in the issue body and in the newest
  `Implementation Plan for` comment, if there is one.

Print a table with one row per issue: issue, type/branch, likely files, overlaps with other issues.
If any two sets overlap, or an issue's set is empty, ask the user before starting: drop an issue, or
run the overlapping ones one after another. Do not decide for them.

With `check only`, stop here: the table is the whole output, no worktree is created and nothing is
changed.

### Step 2: Create the worktrees, one after another

From the main checkout, for each issue in turn (never concurrently):

```bash
git worktree list --porcelain
git branch --list '<type>/<n>-*'
uv run doit worktree --branch=<type>/<n>-<short-description>
```

- An issue that already has a worktree on `<type>/<n>-*` is resumed there; do not create another.
- An issue with a local branch but no worktree stops on its own and is reported: `doit worktree` uses
  `git worktree add -b`, which fails on an existing branch. The other issues go on.
- Record each worktree's absolute path as that issue's `WORKTREE`.

### Step 3: Run one background agent per issue

Start one `general-purpose` subagent per issue with `run_in_background: true`, at most `--max=N` at a
time (default 2). `doit test` already runs `pytest -n auto`, so one `doit check` uses every core.
Issues past the cap wait in a queue; start the next when an agent returns. You, the orchestrator,
never edit files.

Prompt each agent with this, filling in the issue number and absolute `$WORKTREE`:

> Run the `implement-issue` skill for issue <n>, reading
> `<WORKTREE>/.claude/skills/implement-issue/SKILL.md`. Your worktree is `<WORKTREE>`; it is already
> created and checked out on its branch, so skip Step 1.3's creation. Edit only under it, use
> absolute paths, start every shell command with `cd "<WORKTREE>" &&`, run everything through
> `uv run` and never pass the active-environment flag, never use a bare `git stash`, and inspect the
> main checkout only with `git -C`. Run Step 3's Planner or Plan-review brief and the Coder brief as nested
> subagents (`implement-planner`, `implement-worker`), commit, push, open the PR and run the CI loop. You
> cannot ask the user. When an ask-first trigger fires, stop and make your final message start with
> `ASK-FIRST: <trigger> — <detail>`. Otherwise finish with the Step 8 report.

An `ASK-FIRST:` return stops that issue only; the others continue. Relay it to the user and never
resolve it yourself. The user resumes that issue later with "implement issue N", which resumes in
its worktree.

### Step 4: Report

Wait for every agent. For each issue report the PR URL, the CI state, any deviation from the plan,
and any stop (`ASK-FIRST:`, a branch with no worktree, a closed issue). Also report the main
checkout's branch and `git -C <main-checkout> status --short`, taken before Step 2 and again here,
so it is visible that neither moved.

Merging is unchanged: the user merges each PR through [`merge-pr`](../merge-pr/SKILL.md). Two
worktrees that change the same file still conflict at merge time; the PR that merges second needs
the rebase.

## Host support

Parallel mode is verified on Claude Code only (2.1.314): a background `general-purpose` subagent has
the Agent tool and starts `implement-planner` (Opus) and `implement-worker` nested, so the model
split from implement-issue holds. On Codex, Copilot and Antigravity, and on Claude when background
agents are unavailable, run `implement-issue` for each issue one after another in this session;
nested background agents were not verified there. See
[Cross-Agent Delegation Matrix — Parallel issues](../../../docs/development/ai/cross-agent-delegation.md#parallel-issues-implement-issues).
A headless Codex host (`codex exec -a never`) can read GitHub through `.codex/rules/gh.rules` but cannot write to it or delegate to another agent CLI — see [Headless Codex host limits](../../../docs/development/ai/cross-agent-delegation.md#headless-codex-host-limits).

## Ask-first triggers

Stop and ask the user when two issues' likely files overlap, an issue's file set is empty, or any
trigger from implement-issue fires (a new dependency, scope growth, an architecture choice, a
breaking change, a failing test that would need changing, a blocked command).

## Never

- Never apply the `ready-to-merge` label, merge a PR, or close an issue.
- Never edit files as the orchestrator, or `cd` to or switch the main checkout's branch.
- Never create worktrees concurrently, or run more agents than the cap.
- Never resolve an `ASK-FIRST:` stop on the user's behalf.
