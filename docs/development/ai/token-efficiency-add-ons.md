---
title: AI Agent Token-Efficiency Add-Ons
description: Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
audience:
  - contributors
  - ai-agents
  - operators
tags:
  - ai
  - token-efficiency
  - add-ons
---

# AI Agent Token-Efficiency Add-Ons

## Purpose

This page is an **opt-in menu** for operators of larger downstream projects who hit token-cost or
session-length pain points. The baseline defaults (env-var settings, autocompact threshold) are
already on for everyone — see [AI Agent Setup: Environment Variables](../AI_SETUP.md#environment-variables).
Add-ons here are additional investments: each has setup cost, operational burden, and in some cases
a trust trade-off. Read the tipping-point guidance before adopting any of them.

Most projects built on this template do not need these. The audience is operators running
multi-hour sessions against large codebases where the baseline defaults are not enough.

## When to consider an add-on

Adopt an add-on when one or more of the following apply:

- Sessions end in autocompact more than once per workday.
- Shell command output (test runs, `find` output, diff blobs) dominates context billing.
- AGENTS.md rules drift noticeably in long sessions — the agent ignores a documented rule late
  in a conversation that it respected at the start.
- You are running concurrent agents on a shared API key and token-rate costs are measurable.
- You are working in a regulated environment and want auditable compression before tokens leave
  the machine.

## RTK (Rust Token Killer)

**Repo:** [github.com/rtk-ai/rtk](https://github.com/rtk-ai/rtk)

RTK is a shell-output compressor. It intercepts the stdout of commands you run through the
Claude Code terminal, strips redundant whitespace and repeated lines, and injects a compact
representation into the context instead of the raw output. It is written in Rust for low-overhead
interception and ships as a standalone binary as well as bundled inside Headroom (see below).

**Tipping-point:** adopt RTK when test-suite output, build logs, or `find`/`grep` results are a
visible fraction of your context bills. If `pytest` output is 200 lines per run and you run tests
frequently in a session, RTK compresses that cost significantly.

**Per-CLI applicability:**

| CLI | Works? |
| :--- | :--- |
| Claude Code | Yes |
| Gemini CLI | Yes (shell interception is CLI-agnostic) |
| GitHub Copilot CLI | Yes |
| Codex CLI | Yes |

**Install (standalone):**

```bash
# Install the Rust binary
cargo install rtk

# Wrap your shell session
rtk -- bash
```

Once the shell is wrapped, every command Claude Code (or you) runs through the terminal has its
output compressed automatically. No changes to `.claude/settings.local.json` are required.

**Trust caveat:** RTK operates entirely on your machine and does not proxy the API — it rewrites
the text that ends up in the context, but it never reads or forwards your API key. No significant
trust concern beyond normal Rust binary installation hygiene.

## Headroom

**Repo:** [github.com/chopratejas/headroom](https://github.com/chopratejas/headroom)

Headroom is a local proxy that sits between Claude Code and the Anthropic API. It intercepts
outbound API requests and compresses conversation history, system prompts, `CLAUDE.md` content,
and tool-call outputs **before they leave the machine**, reducing the token count sent upstream.
It also ships RTK as a bundled dependency so you get both tools in one install.

**Tipping-point:** adopt Headroom when context bills are high across the board — not just shell
output but also system prompts and conversation history. It is the most aggressive compression
option and gives you the broadest reduction.

> **Trust caveat:** Headroom is a **MITM proxy** in your API path. All requests to the Anthropic
> API, including your API key and full conversation content, pass through Headroom's local process.
> **Read the source before adopting Headroom on shared or employer-owned codebases.** Confirm that
> the binary you run matches the source at the tagged version and that no network forwarding is
> configured. This is not a warning against Headroom itself — it is a standard due-diligence step
> for any tool that sits in the API path.

**Per-CLI applicability:**

| CLI | Works? |
| :--- | :--- |
| Claude Code | Yes |
| Gemini CLI | No (Gemini API endpoint differs; not tested) |
| GitHub Copilot CLI | No (uses GitHub's Copilot endpoint, not Anthropic) |
| Codex CLI | No (uses OpenAI endpoint) |

**Install:**

```bash
# Install Headroom (bundles RTK)
cargo install headroom

# Start the local proxy (default port 8082)
headroom proxy

# Configure Claude Code to route through it
```

**`.claude/settings.local.json` snippet:**

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8082"
  }
}
```

This is a **local-only** settings file (not committed). The
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` env var documented in
[AI Agent Setup: Environment Variables](../AI_SETUP.md#environment-variables) continues to work alongside Headroom —
Headroom compresses tokens in flight while autocompact still triggers at your configured threshold.

## Caveman

**Repo:** [github.com/JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)

Caveman is a Claude Code plugin that injects terse-style instructions at `SessionStart` and on
**every `UserPromptSubmit` event**. It tells the model to prefer brevity: shorter responses,
minimal prose, table-first formatting. Because it fires every turn, injected style survives
autocompact and context drift — the model is reminded on each prompt, not just at session start.

**Tipping-point:** adopt Caveman when you observe that Claude's response verbosity increases over
a long session, or when you want a consistent terse baseline across all sessions without relying
on ad-hoc prompting.

**Caveman is complementary to `AGENTS.md`, not a replacement.** `AGENTS.md` is rich
project-specific content (workflows, architecture, tooling rules) that is auto-loaded once per
session. Caveman injects narrow style instructions on every turn. They target different things.
Stacking is reasonable — but read the intensity trade-off table below before choosing a level.

### Intensity levels

| Level | What it enforces | Risk with project rules |
| :--- | :--- | :--- |
| `lite` | Terse phrasing, concise bullet points | Low — plays well with AGENTS.md; prose in issue bodies and PR descriptions is unaffected |
| `full` | Short answers, table-first, minimal explanation | Medium — may shorten ADR rationale, PR descriptions, commit messages below template minimums |
| `ultra` | Extreme brevity, single-sentence answers | High — likely to conflict with rules requiring structured long-form artefacts (issue bodies, ADR decisions) |

**Recommendation: start with `lite`.** It reduces verbosity in conversational turns without
clashing with template rules that require structured prose in artefacts. Move to `full` only
after confirming your workload does not produce artefacts that need to meet a length standard.

**Per-CLI applicability:**

| CLI | Works? |
| :--- | :--- |
| Claude Code | Yes (native plugin system) |
| Gemini CLI | No |
| GitHub Copilot CLI | No |
| Codex CLI | No |

**Install and enable:**

Follow the installation steps in the Caveman repo. Once installed, enable it at `lite` intensity
in your local Claude Code settings:

**`.claude/settings.local.json` snippet:**

```json
{
  "plugins": {
    "caveman": {
      "intensity": "lite"
    }
  }
}
```

This is a **local-only** file (not committed). Do not commit Caveman plugin config — intensity
preference varies by operator and can conflict with other contributors' expectations.

## Session-survival of project rules

This section documents the **pattern** that Caveman uses, so you can apply it to any narrow rule
that needs to survive long sessions — not just terse style.

### The two injection mechanisms

Claude Code offers two ways to get instructions in front of the model:

| | Auto-load (`CLAUDE.md` / `AGENTS.md`) | Per-turn injection (`UserPromptSubmit` hook) |
| :--- | :--- | :--- |
| Loaded | Once at session start | Every user message |
| Survives autocompact / context drift | No | Yes |
| Best for | Rich, project-specific content | Narrow rules that "the model knows but forgets" |

**Auto-load** is how this template ships `AGENTS.md` — comprehensive project context loaded once
per session. It works well for the bulk of project rules. **The failure mode is drift**: after an
autocompact event, or deep in a long conversation, the model may stop honoring a specific rule
even though `AGENTS.md` is still nominally in context.

**Per-turn injection** fires on every `UserPromptSubmit` event. It adds a small amount of text to
every message, but that text is always present, always current, and always wins against drift.
Caveman uses this mechanism for terse style.

### When to use this pattern yourself

The `UserPromptSubmit` hook is a reusable technique. If you have a narrow rule that you observe
the model forgetting mid-session, wrapping it in a `UserPromptSubmit` hook is often more reliable
than repeating it in `AGENTS.md`. Good candidates:

- A naming convention the model tends to ignore late in sessions.
- A formatting rule for a specific artefact type.
- A reminder to use `doit` instead of raw `git`/`gh` for a particular class of operation.

The hook lives in `.claude/settings.json` (committed) or `.claude/settings.local.json`
(local-only). Keep injected text short — per-turn injection costs tokens on every message, so
verbosity here works against the goal.

## Related primitives in this template

These are not add-ons (they ship with the template) but they interact with the tools above:

- **`/checkpoint` and `/restore`** — session-state preservation commands. When a session is
  about to hit its context limit, `/checkpoint` writes a portable state file and `/restore`
  reconstructs context in a new session. Complements all three add-ons above. See
  [Slash Commands and Workflows](slash-commands.md).
- **Env-var defaults** — `ENABLE_PROMPT_CACHING_1H`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, and
  `CLAUDE_CODE_SUBAGENT_MODEL` are already set via `.claude/settings.json`. Headroom and Caveman
  layer on top of these defaults, not instead of them. See
  [AI Agent Setup: Environment Variables](../AI_SETUP.md#environment-variables).
- **PreCompact handoff hook** — `tools/hooks/ai/precompact-checkpoint.py` (shipped in PR #828).
  Autocompact events serialize session state via the hook, so the post-compact continuation
  rehydrates more context automatically — reducing the frequency of sessions that need
  `/checkpoint` or Headroom.

## Out of scope

- No code is shipped here. All three tools are external; install them from their respective repos.
- Equivalent add-ons for Gemini CLI, Codex CLI, and GitHub Copilot CLI. Most of these tools are
  Claude Code-specific. If equivalents exist for other CLIs, that is a separate doc.
- Shipping tool configuration in this template's committed files. All snippets above go into
  `.claude/settings.local.json` (not committed) to keep individual operator preferences local.
