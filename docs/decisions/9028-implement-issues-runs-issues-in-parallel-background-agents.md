---
title: "ADR-9028: implement-issues runs issues in parallel background agents"
description: implement-issues runs implement-issue for several issues at once, one worktree and one nested-capable background agent each, capped at 2 by default
date: 2026-10-30
audience:
  - contributors
tags:
  - adr
---

# ADR-9028: implement-issues runs issues in parallel background agents

## Status

Accepted

## Decision

1. **Nested background agents.** The `implement-issues` skill starts one `general-purpose` subagent per issue with `run_in_background: true`. Each runs `implement-issue` in its own worktree and starts the Planner (`implement-planner`, Opus) and Coder (`implement-worker`) as nested subagents. Probes on Claude Code 2.1.314 showed a background subagent has the Agent tool and a nested `implement-planner` ran on `claude-opus-5-5`.
2. **Concurrency cap.** Default 2, override with `--max=N`. `doit test` runs `pytest -n auto`, so one `doit check` already uses every core.
3. **Host scope.** Parallel mode is Claude Code only. The skill stays one shared source in `.agents/skills/`; other hosts run `implement-issue` for each issue in sequence, because nested agents were not verified there.
4. **Plain background agents, not the Workflow tool.** A Workflow needs its own opt-in, nesting under it was not verified, and an ask-first stop needs an agent that reasons. An issue agent cannot ask the user, so it returns `ASK-FIRST: <trigger> — <detail>`, which stops that issue only.

The skill never applies `ready-to-merge`, merges or closes an issue.

## Rationale

Several issues were run by starting one session per issue (#1095, ADR-9027). One session could not run them together (#1097).

## Documentation

- [Slash Commands and Workflows — implement issues A, B](../development/ai/slash-commands.md#implement-issues-a-b)
- [Cross-Agent Delegation — Parallel issues](../development/ai/cross-agent-delegation.md#parallel-issues-implement-issues)

Issue: #1097. Builds on ADR-9027.
