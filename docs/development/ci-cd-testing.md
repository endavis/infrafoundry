# CI/CD Testing Guide

## Overview

CI runs lint/format, tests, coverage, and integration checks to guard regressions. GitHub Actions pipelines target multiple Python versions and publish coverage artifacts/comments.

## Audience and Prerequisites

- **Audience:** Contributors and reviewers ensuring CI health.
- **Prereqs:** GitHub Actions access; local tools (`uv`, `doit`, pytest, ruff, mypy) to replicate checks.

## When to Use This

- Before opening/merging PRs to mirror CI locally.
- Understanding pipeline stages and coverage expectations.
- Expanding integration tests or adjusting thresholds.

## Quick Start

Local commands:
```bash
doit format && doit lint
uv run pytest
doit coverage
```

## Pipeline Details (GitHub Actions)

- **Workflow:** `.github/workflows/tests.yml`
- **Triggers:** Push to main/dev/develop; PR to main/dev; manual dispatch.
- **Jobs:**
  - `test`: Python 3.12, installs via `uv pip install -e ".[dev]"`; runs ruff (non-blocking), `pytest --cov=src/infrafoundry --cov-fail-under=69`; uploads coverage artifacts and Codecov.
  - `test-matrix`: Python 3.12 and 3.13 without coverage to ensure compatibility.
  - `integration-test`: After `test`; installs Terraform 1.6.0, Ansible; runs `pytest tests/integration/`.
  - `code-quality`: `ruff format` (blocking), `ruff check` (blocking), `mypy` (non-blocking via `continue-on-error`).
- **Coverage:** Threshold 69% (rounds to ~70%); artifacts `tmp/htmlcov/`, `tmp/coverage.xml`.
- **PR comments:** Coverage comment via `python-coverage-comment-action`; badge thresholds green ≥80, orange ≥70.

## Validation and Checks

- Replicate CI locally with `doit format && doit lint && uv run pytest`.
- For coverage gates, run `doit coverage` or `pytest --cov=src/infrafoundry --cov-fail-under=69`.
- Ensure Terraform/Ansible present if touching integration tests.

## Examples

- **Run specific tests:**
  ```bash
  pytest tests/unit/test_config.py::TestConfigManager::test_load_environment -v
  ```
- **Open HTML coverage:**
  ```bash
  xdg-open tmp/htmlcov/index.html
  ```
- **Matrix check locally (Python 3.13):**
  ```bash
  pyenv local 3.13 && uv run pytest
  ```

## Related Documentation

- [Coding Standards](coding-standards.md)
- [Manager Patterns](manager-patterns.md)
- [Plugin Development](plugin-development.md)

## Troubleshooting

- **Symptom:** Coverage below threshold. **Fix:** Add tests for new/changed code paths; re-run coverage.
- **Symptom:** Ruff/mypy failures. **Fix:** Run `doit format` and address lint/type errors; for non-blocking mypy, still fix issues proactively.
- **Symptom:** Integration tests fail locally. **Fix:** Ensure Terraform/Ansible versions match CI and required binaries are installed.

---

Last updated: 2025-11-29 14:27 GMT
