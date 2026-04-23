# ADR-9009: Use pre-commit hooks for quality gates

## Status

Accepted

## Decision

Use the **pre-commit** framework with hooks that run quality checks (ruff, mypy, bandit, codespell) and safety checks (prevent commits to main, protect config files) before every commit.

## Rationale

Ensures bad code never enters the repository, provides fast feedback loop (seconds, not minutes), works offline without CI dependency, and catches issues before PR review. Safety checks prevent dangerous operations at the source.

## Related Issues

- Issue #184: Use project's tool versions in pre-commit hooks
- Issue #128: Align pre-commit, CI, and doit check to use consistent checks
- Issue #19: Fix resolve pre-commit hook failures in template files
- Issue #415: Add actionlint hook for GitHub Actions workflow validation

## Related Documentation

- [Coding Standards](../../development/coding-standards.md)
- [Installation Guide](../../getting-started/installation.md)
