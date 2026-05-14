# Per-Stack Rule Files (Gemini)

## Purpose

Rule files in this directory capture **narrow, recurring footguns** that Gemini CLI keeps getting
wrong for a specific stack or domain. They are not a second copy of `AGENTS.md`. `AGENTS.md` carries
broad workflow and architectural rules for the whole project. A rule file carries three to ten
numbered self-checks for one specific failure mode — small enough to survive a context window, sharp
enough to change behavior.

The pattern works because a short, skill-gated checklist is more likely to be honored late in a
session than a paragraph buried in a large reference file.

## When to author a rule file

Write a rule file when all three conditions hold:

1. The same mistake has recurred in at least two separate sessions or PRs.
2. The failure can be expressed as a numbered checklist a model can self-check before acting.
3. The scope is narrow enough to belong to a single skill gate (e.g., `codegen`, `db-migrations`,
   `api-contracts`).

If the rule is broad (applies everywhere) or is not tied to an observed failure, put it in
`AGENTS.md` instead — or leave it out entirely.

## File structure

Each rule file must have three parts:

```
Skill: <name>

Self-check before <action>:
1. <First check — concrete and verifiable>
2. <Second check>
3. <Third check>
...

Observed failures: <PR or issue URL>, <PR or issue URL>
```

- **`Skill: <name>`** — the first line, no heading. Names the capability gate so the model can
  self-identify when to apply the file.
- **Numbered self-check list** — imperative, specific. Each item must be falsifiable: the model
  should be able to answer "yes" or "no".
- **`Observed failures:` footer** — links to the PRs or issues where the failure was documented.
  This is mandatory. A rule with no observed-failure link is a guess, not a discipline.

Target: **30 lines or fewer** per rule file. If a file grows past 30 lines, split it.

## How to load

When you author a rule file (e.g., `codegen.md`), add a literal `@`-import for it to `GEMINI.md`:

```markdown
@./AGENTS.md
@./.gemini/rules/codegen.md

# Gemini CLI Instructions
...
```

Add one line per rule file. Do **not** use a glob like `@./.gemini/rules/*.md` — Gemini CLI's
[Memory Import Processor](https://geminicli.com/docs/reference/memport/) only supports literal
relative or absolute paths to specific files. Globs work in practice via undocumented behavior but
emit a spurious `[ERROR] [ImportProcessor] Failed to import .../*.md: ENOENT` log on every run
(the processor calls `access()` on the literal pattern before expanding it).

This is the inverse of Claude Code's `.claude/CLAUDE.md`, which does support glob imports — the two
CLIs differ here despite using the same `@`-import syntax.

Note: this template ships with no import line in `GEMINI.md`. Add the first line when you author
your first rule file.

## Discipline: build from observed failures, not generic best-practices

The central rule of this pattern is that rule files must be derived from documented failures, not
from intuition or generic advice. A checklist written in advance of any failure will drift into
noise — the model will pattern-match the checklist language and satisfy it superficially. A
checklist written because a specific PR broke a specific invariant three times is sharp enough to
change behavior. If you cannot fill in the `Observed failures:` footer with real links, the rule
file is not ready to be written yet.

## What NOT to put in a rule file

- **Broad workflow rules** — things like "never commit to main" or "always run `doit check`"
  belong in `AGENTS.md`, not here. Rule files are for stack-specific self-checks, not universal
  workflow.
- **Generic best-practices** — "prefer composition over inheritance", "write type annotations" —
  these are noise. They drift into checklists the model satisfies by rote without changing
  behavior.
- **Anything not tied to an observed failure** — if you cannot cite a PR or issue where the rule
  was violated, the rule file is not ready to be written.
