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

## Python Version Support Policy

### Active Support

Only the **last 3 major Python versions** are actively supported. This means:
- Bug fixes and new features are tested against these versions
- CI runs these versions on every PR (using bookend strategy - oldest + newest)
- Documentation and examples target these versions

**Current active versions:** Python 3.12, 3.13, 3.14

### Passive Compatibility

Older Python versions may continue to work but are not actively maintained:
- We continue testing previous versions in CI via the `full-matrix` label
- Once a version fails CI tests, it is removed from the matrix and marked incompatible
- Users on older Python versions can use version-tagged releases (e.g., `v1.2.3-py310-final`)

### Version Lifecycle

| Stage | Description | CI Testing |
|-------|-------------|------------|
| **Active** | Last 3 major versions | Every PR (bookend strategy) |
| **Passive** | Older versions still passing | On-demand (`full-matrix` label) |
| **Deprecated** | Fails CI tests | Removed from matrix |

### CI Matrix Strategy

To balance test coverage with CI efficiency:

| PR State | Python Versions Tested | Jobs |
|----------|----------------------|------|
| Default | Bookends only (oldest + newest) × 3 OSes | 6 |
| `full-matrix` label | Middle versions only × 3 OSes | 3 per middle version |

The **bookend strategy** tests the oldest and newest supported versions. If both pass, intermediate versions are assumed compatible. Use the `full-matrix` label when:
- Making changes that might affect version compatibility
- Preparing a release
- Investigating compatibility issues

### Configuration

Python versions are configured in `.github/python-versions.json`:

```json
{
  "oldest": "3.12",
  "newest": "3.14"
}
```

The CI workflow automatically derives:
- **Bookends**: oldest + newest (tested on every PR)
- **Middle versions**: everything between (tested when `full-matrix` label is added)

When updating supported versions, edit this config file - no workflow changes needed.

### Deprecation Process

When a Python version starts failing CI:

1. **Assess**: Determine if the failure is fixable without significant effort
2. **Decide**: Fix compatibility or deprecate the version
3. **Tag**: If deprecating, tag the last compatible release (e.g., `v1.2.3-py310-final`)
4. **Update**: Remove version from CI matrix and update `pyproject.toml` classifiers
5. **Document**: Update this documentation and release notes

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

### Pre-commit Integration

The template includes pre-commit hooks that run automatically:

```bash
# Install hooks
doit pre_commit_install

# Run manually on all files
doit pre_commit_run

# Update hook versions
uv run pre-commit autoupdate
```

**Hook stages in `.pre-commit-config.yaml`:**

**Pre-commit stage** (runs on every `git commit`):

| Hook | Purpose |
|------|---------|
| `trailing-whitespace` | Remove trailing whitespace |
| `end-of-file-fixer` | Ensure files end with a newline |
| `check-yaml` | Validate YAML syntax |
| `check-added-large-files` | Prevent large files from being committed |
| `check-toml` | Validate TOML syntax |
| `check-merge-conflict` | Detect merge conflict markers |
| `detect-private-key` | Prevent private keys from being committed |
| `ruff` | Lint and auto-fix Python code |
| `ruff-format` | Format Python code |
| `mypy` | Type checking (strict mode, `src/` only) |
| `bandit` | Security scanning (skipped if not installed) |
| `codespell` | Spell checking |
| `actionlint` | Lint GitHub Actions workflow files (extra runner labels in `.github/actionlint.yaml`) |
| `check-branch-name` | Enforce branch naming convention |
| `generate-doc-toc` | Update documentation TOC when docs change |
| `no-commit-to-main` | Prevent direct commits to main branch |
| `no-local-config` | Prevent committing local config files |
| `protect-dynamic-version` | Protect `dynamic = ["version"]` in `pyproject.toml` |
| `uv-lock-check` | Validate `uv.lock` is in sync with `pyproject.toml` when `pyproject.toml` is staged |

**Commit-msg stage** (validates commit messages):

| Hook | Purpose |
|------|---------|
| `conventional-pre-commit` | Enforce conventional commit format |

**Post-merge / Post-checkout stage** (automatic dependency sync):

| Hook | Purpose |
|------|---------|
| `uv-sync-on-pull` | Runs `uv sync --all-extras --dev` when `uv.lock` changes after `git pull` |
| `uv-sync-on-checkout` | Runs `uv sync --all-extras --dev` when `uv.lock` changes after branch switch |

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

## Property-Based Testing

### What Is Property-Based Testing?

Property-based testing verifies *invariant properties* of your code by feeding it hundreds of randomly generated inputs rather than a handful of hand-picked examples. If a property holds for every input the framework can dream up, you gain much higher confidence than example-based tests alone.

This project uses [Hypothesis](https://hypothesis.readthedocs.io/) for property-based testing.

### When to Use Property-Based Tests

| Good fit | Not a good fit |
|----------|----------------|
| Pure functions with clear contracts (validators, formatters, parsers) | Tests that require complex external state (databases, APIs) |
| Functions whose output must satisfy invariants (e.g., "always lowercase") | Behaviour that depends on side effects or ordering |
| Edge-case-heavy logic (string processing, numeric conversions) | Simple CRUD with no transformation logic |

### Writing Property Tests

```python
import pytest
from hypothesis import given, example
from hypothesis import strategies as st

@pytest.mark.property
@given(name=st.text(min_size=1))
@example("edge-case-value")
def test_output_is_always_lowercase(name: str) -> None:
    result = normalize(name)
    assert result == result.lower()
```

### Hypothesis Profiles

Two profiles are configured in `tests/conftest.py`:

| Profile | `max_examples` | `deadline` | Used when |
|---------|---------------|------------|-----------|
| `default` | 200 | Hypothesis default | Local development |
| `ci` | 50 | 500 ms | GitHub Actions CI |

The CI workflow sets `HYPOTHESIS_PROFILE: ci` so property tests run faster in pipelines.

### Running Property Tests

```bash
# Run only property tests
uv run pytest -m property -v

# Run with a specific seed for reproducibility
uv run pytest -m property --hypothesis-seed=12345
```

## Mutation Testing

### What Is Mutation Testing?

Mutation testing evaluates the effectiveness of your test suite by introducing small changes (mutations) to your source code and checking whether the tests detect them. Each mutation represents a potential bug -- if your tests catch it (a "killed" mutant), that area is well tested. If they don't (a "survived" mutant), your tests may have a gap.

This project uses [mutmut](https://mutmut.readthedocs.io/) for mutation testing.

### Running Locally

```bash
# Run mutation testing (generates results and prints summary)
doit mutate

# Generate an HTML report for detailed review
doit mutate_html

# Open the report in a browser
xdg-open tmp/mutmut/index.html
```

### Which Tests Run

mutmut does not run all of `tests/`. It copies `src/`, `tests/`, `pyproject.toml` and `uv.lock` into `mutants/` (git-ignored) and runs the tests there. A test that imports `tools` or reads any other file in the repository fails in that copy. mutmut passes `-x` to pytest, so the first such failure stops the run before any mutant is checked (pyproject-template#873).

`pytest_add_cli_args_test_selection` in `[tool.mutmut]` therefore lists only the tests that exercise `src/`. When you add a test file that imports the package, add it to that list. `tests/test_mutmut_config.py` fails until you do. It also fails if a listed file imports a module that mutmut does not copy, or no longer exists. The benchmarks in `tests/benchmarks/` are left out on purpose: they time the package and assert nothing, so they cannot kill a mutant.

### Interpreting Results

| Term | Meaning |
|------|---------|
| **Killed** | A mutation was detected by the test suite -- good coverage |
| **Survived** | A mutation was NOT detected -- potential test gap |
| **Timeout** | The mutation caused the tests to hang -- typically counted as killed |
| **Suspicious** | The mutation caused an unexpected result -- review manually |

The **mutation score** is the percentage of mutants killed out of total mutants generated. There is no enforced threshold -- use the score as a guide to identify areas that need better test coverage.

### CI Schedule

Mutation testing runs weekly in CI (Sunday midnight UTC) via the `.github/workflows/mutation.yml` workflow. It is informational only and does not block merges.

## Benchmark Tracking

### Overview

Benchmark results are tracked historically using [benchmark-action/github-action-benchmark](https://github.com/benchmark-action/github-action-benchmark). This enables performance trend visualization and automatic regression detection across commits.

### How It Works

| Trigger | Behavior |
|---------|----------|
| **Push to `main`** | Runs benchmarks and commits results to the `gh-benchmarks` data branch |
| **Pull request** | Runs benchmarks and posts a comparison comment on the PR |
| **Manual dispatch** | Runs benchmarks and uploads artifact only |

### The `gh-benchmarks` Branch

Benchmark data is stored in a dedicated `gh-benchmarks` branch, separate from the main codebase. This branch is auto-created by the benchmark action on the first push to `main` after the workflow is enabled.

### PR Comments

On every pull request, the benchmark action posts a comment comparing the PR's benchmark results against the latest stored baseline from `main`.

### Alert Threshold

The alert threshold is set to `110%` -- the workflow flags a warning if any benchmark is more than 10% slower than the baseline. Adjust in `.github/workflows/benchmark.yml`.

## Related Documentation

- [Coding Standards](coding-standards.md)
- [Doit Tasks Reference](doit-tasks-reference.md)
- [Manager Patterns](manager-patterns.md)
- [Implementing Providers](implementing-providers.md)

## Troubleshooting

- **Symptom:** Coverage below threshold. **Fix:** Add tests for new/changed code paths; re-run coverage.
- **Symptom:** Ruff/mypy failures. **Fix:** Run `doit format` and address lint/type errors; for non-blocking mypy, still fix issues proactively.
- **Symptom:** Integration tests fail locally. **Fix:** Ensure Terraform/Ansible versions match CI and required binaries are installed.

---
[Back to Table of Contents](../index.md)
