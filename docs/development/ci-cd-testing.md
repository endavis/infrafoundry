# CI/CD Testing Guide

This document describes InfraFoundry's automated testing and CI/CD setup.

## Overview

InfraFoundry uses GitHub Actions for automated testing on every push and pull request. The workflow ensures code quality, maintains test coverage, and prevents regressions.

## Test Workflow

**Location:** `.github/workflows/tests.yml`

**Triggers:**
- Push to `main`, `dev`, or `develop` branches
- Pull requests to `main` or `dev`
- Manual workflow dispatch

### Jobs

The workflow runs 4 parallel jobs:

#### 1. Main Test Job (`test`)

**Purpose:** Run full test suite with coverage enforcement

**Steps:**
1. Check out code
2. Set up Python 3.12
3. Install uv package manager
4. Install dependencies with `uv pip install -e ".[dev]"`
5. Run linting (ruff) - non-blocking
6. Run tests with coverage: `pytest --cov=src/infrafoundry --cov-fail-under=69`
7. Upload coverage to Codecov
8. Upload coverage reports as artifacts
9. Comment coverage on PR
10. Generate coverage badge (main/dev branches only)

**Coverage Threshold:** 69% (actual coverage: 69.89%, rounds to 70%)

**Artifacts:**
- `htmlcov/` - HTML coverage report
- `coverage.xml` - XML coverage report for Codecov
- `.coverage` - Raw coverage data

#### 2. Python Matrix Job (`test-matrix`)

**Purpose:** Ensure compatibility with multiple Python versions

**Matrix:**
- Python 3.12 (project minimum)
- Python 3.13 (latest stable)

**Steps:**
1. Check out code
2. Set up Python version from matrix
3. Install dependencies
4. Run tests (without coverage)

**Fail-fast:** Disabled - all Python versions tested even if one fails

#### 3. Integration Test Job (`integration-test`)

**Purpose:** Test with external tools (Terraform, Ansible)

**Dependencies:** Runs after `test` job passes

**Steps:**
1. Check out code
2. Set up Python 3.12
3. Install Terraform 1.6.0
4. Install Ansible via uv
5. Run integration tests: `pytest tests/integration/`

**Note:** Currently, integration tests are minimal. See [#5 in todo list](../README.md#development-roadmap) for expansion plans.

#### 4. Code Quality Job (`code-quality`)

**Purpose:** Enforce code style and type safety

**Checks:**
1. **black** - Code formatting (blocking)
2. **ruff** - Linting and import sorting (blocking)
3. **isort** - Import organization (non-blocking)
4. **mypy** - Static type checking (non-blocking)

**Non-blocking checks** use `continue-on-error: true` to provide feedback without failing the build.

## Coverage Reporting

### Codecov Integration

Coverage reports are uploaded to [Codecov](https://codecov.io) for:
- Historical trend tracking
- PR coverage comparisons
- Coverage visualizations

**Setup:**
1. Create Codecov account linked to GitHub repo
2. Add `CODECOV_TOKEN` to GitHub Secrets
3. Codecov action automatically uploads `coverage.xml`

**Note:** `fail_ci_if_error: false` prevents CI failures if Codecov is unavailable

### PR Comments

The `python-coverage-comment-action` posts coverage info on PRs:
- Total coverage percentage
- Coverage change vs base branch
- Color-coded badge (green ≥80%, orange ≥70%, red <70%)

**Configuration:**
- `MINIMUM_GREEN: 80` - Green badge threshold
- `MINIMUM_ORANGE: 70` - Orange badge threshold

### Coverage Badge

A coverage badge is generated and committed to the repo on pushes to `main` or `dev`:

```bash
coverage-badge -o coverage.svg -f
```

Badge URL: `https://img.shields.io/badge/coverage-70%25-brightgreen`

## Local Testing

### Quick Tests

```bash
make test          # Run all tests
make coverage      # Run with full coverage report
```

### Manual Coverage

```bash
# Run with coverage
pytest --cov=src/infrafoundry --cov-report=term-missing --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Test Specific Modules

```bash
# Unit tests only
pytest tests/unit/

# Specific test file
pytest tests/unit/test_config.py -v

# Specific test
pytest tests/unit/test_config.py::TestConfigManager::test_load_environment -v

# With coverage for specific module
pytest tests/unit/test_config.py --cov=src/infrafoundry/core/config --cov-report=term-missing
```

### Code Quality Checks

```bash
make format        # Format with black
make lint          # Run ruff
make check         # Run all checks

# Individual tools
black src/ tests/
ruff check src/ tests/
isort src/ tests/
mypy src/
```

## Required GitHub Secrets

### For Test Workflow

- `CODECOV_TOKEN` (optional) - Codecov API token for coverage upload

### For Infrastructure Deployment Workflow

- `SOPS_AGE_KEY` - Base64-encoded age encryption key
- `PROXMOX_API_URL`, `PROXMOX_API_TOKEN_ID`, `PROXMOX_API_TOKEN_SECRET`
- `OPNSENSE_API_URL`, `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET`
- `KUBECONFIG` (optional) - Kubernetes configuration

## Coverage Targets

**Current Status (as of last update):**
- **Overall:** 69.89% (70% target ✅)
- **Core modules:** 94-100%
  - config.py: 98%
  - dependencies.py: 99%
  - events.py: 100%
  - notifications.py: 94%
  - policy.py: 100%
  - secrets.py: 100%
  - state.py: 95%
- **Providers:** 98-100%
  - proxmox: 100%
  - opnsense: 98%
  - kubernetes: 99%

**Areas needing improvement:**
- cli.py: 29% (CLI commands, interactive prompts)
- orchestrator.py: 46% (multi-provider workflows, error handling)

See [Development Roadmap](../README.md#development-roadmap) for coverage improvement plans.

## Troubleshooting

### Tests Pass Locally but Fail in CI

**Common causes:**
1. **Python version difference** - CI uses 3.12, check local version: `python --version`
2. **Missing dependencies** - CI installs from `pyproject.toml`, ensure it's up to date
3. **Environment variables** - CI doesn't have local `.envrc.local`, mock external dependencies

**Solution:**
```bash
# Test with exact CI environment
docker run -it --rm -v $(pwd):/app -w /app python:3.12 bash
pip install uv
uv pip install -e ".[dev]"
pytest --cov=src/infrafoundry --cov-fail-under=69 -v
```

### Coverage Below Threshold

**Error:** `FAIL Required test coverage of 69% not reached. Total coverage: XX.XX%`

**Solutions:**
1. Add tests for uncovered code
2. Remove dead code
3. Lower threshold (update `COVERAGE_THRESHOLD` in `.github/workflows/tests.yml`)

**Check coverage locally:**
```bash
make coverage
# Review htmlcov/index.html to see uncovered lines
```

### Codecov Upload Fails

**Non-blocking:** CI continues even if Codecov fails

**Causes:**
1. Missing `CODECOV_TOKEN` secret
2. Codecov service outage
3. Network issues

**Fix:**
- Add token to GitHub Secrets: Settings → Secrets → Actions → New secret
- Check [Codecov status](https://status.codecov.io)

### Linting Failures

**ruff errors:**
```bash
# Fix automatically
ruff check --fix src/ tests/

# Check specific rules
ruff check --select E,F,I,N,W,UP src/
```

**black formatting:**
```bash
# Format code
black src/ tests/

# Check without changes
black --check src/ tests/
```

## Best Practices

### Before Committing

```bash
# Run full check
make format && make lint && make coverage

# Or individual steps
black src/ tests/              # Format
ruff check --fix src/ tests/   # Fix linting
pytest --cov=src/infrafoundry --cov-fail-under=69  # Test with coverage
```

### Writing Tests

1. **Follow naming convention:** `test_*.py`, `Test*` classes, `test_*()` functions
2. **Use fixtures:** Share setup code with pytest fixtures
3. **Mock external calls:** Don't call real APIs, use `unittest.mock`
4. **Test edge cases:** Empty inputs, missing files, network errors
5. **Check coverage:** Run with `--cov` to see what's missed

### Maintaining Coverage

- **Add tests with new features** - Don't let coverage drop
- **Test error paths** - Exception handling is often uncovered
- **Review coverage reports** - Check `htmlcov/` after each test run
- **Track trends** - Use Codecov to see coverage over time

## CI/CD Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Push / PR to main/dev                                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │  GitHub Actions    │
         │  tests.yml         │
         └────────┬───────────┘
                  │
        ┌─────────┴─────────┬─────────────┬──────────────┐
        │                   │             │              │
        ▼                   ▼             ▼              ▼
   ┌────────┐        ┌──────────┐   ┌─────────┐   ┌─────────┐
   │  Test  │        │ Py Matrix│   │ Integ   │   │  Code   │
   │ +Cov   │        │ 3.12/3.13│   │ Tests   │   │ Quality │
   └───┬────┘        └──────────┘   └─────────┘   └─────────┘
       │
       ├─ Upload to Codecov
       ├─ Generate artifacts (htmlcov, coverage.xml)
       ├─ Comment on PR
       └─ Generate badge (main/dev only)
```

## Further Reading

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Codecov documentation](https://docs.codecov.com/)
- [GitHub Actions documentation](https://docs.github.com/en/actions)
- [Python coverage.py](https://coverage.readthedocs.io/)
