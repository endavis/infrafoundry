# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the project.

## What is an ADR?

An ADR documents an architectural decision: what was decided and why. The detailed discussion and specification lives in the GitHub Issue; the ADR provides a summary with links.

## Two Series

All ADRs live in this single directory, but they follow a two-series numbering convention:

| Series | Prefix | Scope |
|--------|--------|-------|
| **Template-meta** | `9XXX` | Decisions about the template itself — tooling choices, workflows, and conventions inherited by every downstream project. Created with `doit adr --template`. |
| **Project-level** | `0001+` | Decisions made by this repository's owner about this project. Created with `doit adr`. |

Downstream projects spawned from `pyproject-template` inherit the 9XXX template ADRs via the clone. A downstream project can keep, delete, or supersede any template ADR with its own 0001-series ADR.

## ADR Format

ADRs use a simplified format:

```markdown
# ADR-NNNN: Title

## Status
Accepted

## Decision
Brief summary of what was decided.

## Rationale
Why this decision was made.

## Related Issues
- Issue #XX: Description

## Related Documentation
- [Relevant Doc](../path/to/doc.md)
```

See [adr-template.md](adr-template.md) for the template.

## Creating a New ADR

```bash
# Project-level ADR (0001-series) — interactive
doit adr --title="Your decision title"

# Project-level ADR — non-interactive
doit adr --title="Use Redis" --body="## Status\nAccepted\n..."
doit adr --title="Use Redis" --body-file=adr.md

# Template-meta ADR (9XXX-series) — add --template
doit adr --title="Use some tool" --template
doit adr --title="Use some tool" --template --body-file=adr.md
```

Use `--template` when the decision is about the template's own tooling, workflow, or conventions (something every downstream project will inherit). Use the default (project-level) for decisions specific to this project.

## When to Create an ADR

Create an ADR when:
- Introducing a new tool, framework, or library
- Changing development workflow or processes
- Making decisions that affect project architecture

The Issue contains the full discussion; the ADR summarizes the outcome.

## ADR Statuses

- **Accepted**: Decision is in effect
- **Deprecated**: No longer relevant (kept for history)
- **Superseded**: Replaced by a newer ADR

## Index

### Template-meta ADRs (9XXX)

| ADR | Title | Status |
|-----|-------|--------|
| [9001](9001-use-uv-for-package-management.md) | Use uv for package management | Accepted |
| [9002](9002-use-doit-for-task-automation.md) | Use doit for task automation | Accepted |
| [9003](9003-use-ruff-for-linting-and-formatting.md) | Use ruff for linting and formatting | Accepted |
| [9004](9004-auto-discover-doit-tasks.md) | Auto-discover doit tasks from modules | Accepted |
| [9005](9005-ai-agent-command-restrictions.md) | AI agent command restrictions via hooks | Accepted |
| [9006](9006-merge-gate-workflow.md) | Merge-gate workflow requiring ready-to-merge label | Accepted |
| [9007](9007-use-mypy-for-type-checking.md) | Use mypy for static type checking | Accepted |
| [9008](9008-pr-based-development-workflow.md) | PR-based development workflow | Accepted |
| [9009](9009-use-pre-commit-hooks-for-quality-gates.md) | Use pre-commit hooks for quality gates | Accepted |
| [9010](9010-use-conventional-commits-format.md) | Use conventional commits format | Accepted |
| [9011](9011-use-pytest-for-testing.md) | Use pytest for testing | Accepted |
| [9012](9012-use-mkdocs-with-material-theme-for-documentation.md) | Use mkdocs with Material theme for documentation | Accepted |
| [9013](9013-python-version-support-policy.md) | Python version support policy with bookend CI strategy | Accepted |
| [9014](9014-use-click-for-application-cli.md) | Use click for application CLI | Accepted |
| [9015](9015-install-tools-framework-archive-extraction-and-custom-urls.md) | install_tools framework: archive extraction and custom URLs | Accepted |
| [9016](9016-unify-adr-directories.md) | Unify ADR directories under docs/decisions | Accepted |

### Project-level ADRs (0001+)

| ADR | Title | Status |
|-----|-------|--------|

_(No project-level ADRs yet.)_
