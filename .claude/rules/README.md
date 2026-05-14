# Per-Stack Rule Files

## Purpose

Rule files in this directory capture **narrow, recurring footguns** that an AI agent keeps getting
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

Uncomment the `@./rules/*.md` line in `.claude/CLAUDE.md`:

```
@../AGENTS.md
<!-- Uncomment when you add rule files. See .claude/rules/README.md for the pattern. -->
<!-- @./rules/*.md -->
```

becomes:

```
@../AGENTS.md
@./rules/*.md
```

Note: the line stays commented out in this template repository. Downstream consumers uncomment it
after authoring their first rule file.

## Discipline: build from observed failures, not generic best-practices

The central rule of this pattern is that rule files must be derived from documented failures, not
from intuition or generic advice. A checklist written in advance of any failure will drift into
noise — the model will pattern-match the checklist language and satisfy it superficially. A
checklist written because a specific PR broke a specific invariant three times is sharp enough to
change behavior. If you cannot fill in the `Observed failures:` footer with real links, the rule
file is not ready to be written yet.

## Worked example

The following sketch illustrates what a `codegen.md` rule file might look like for a downstream
project (`pynetappfoundry`) that generates typed Python from a YANG schema and has an ADR
(ADR-0008) documenting a round-trip invariant. **This example is illustrative only** — actual rule
files belong in downstream repos, not in this template.

```
Skill: codegen

Self-check before committing generated code:
1. Run `make roundtrip` and confirm exit 0 — the generated types must deserialize
   what the serializer produces without loss (ADR-0008).
2. Confirm no hand-edited lines remain in `src/generated/` — regenerate from schema
   if any exist.
3. Confirm the schema version in `src/generated/_version.py` matches the YANG source
   revision header.

Observed failures: endavis/pynetappfoundry#104, endavis/pynetappfoundry#117
```

## What NOT to put in a rule file

- **Broad workflow rules** — things like "never commit to main" or "always run `doit check`"
  belong in `AGENTS.md`, not here. Rule files are for stack-specific self-checks, not universal
  workflow.
- **Generic best-practices** — "prefer composition over inheritance", "write type annotations" —
  these are noise. They drift into checklists the model satisfies by rote without changing
  behavior.
- **Anything not tied to an observed failure** — if you cannot cite a PR or issue where the rule
  was violated, the rule file is not ready to be written.
