# Doit Tasks Reference

Complete reference for all available `doit` tasks in InfraFoundry.

## Quick Reference

```bash
# List all available tasks
doit list

# Get help for a specific task
doit help <task_name>

# Run a task
doit <task_name>
```

## Task Categories

| Category | Tasks | Description |
|----------|-------|-------------|
| [Testing](#testing-tasks) | `test`, `coverage`, `mutate`, `mutate_html` | Run tests, coverage, and mutation testing |
| [Benchmarking](#benchmarking-tasks) | `benchmark`, `benchmark_save`, `benchmark_compare` | Performance benchmarks |
| [Code Quality](#code-quality-tasks) | `format`, `lint`, `type_check`, `check` | Code formatting and linting |
| [Code Analysis](#code-analysis-tasks) | `complexity`, `maintainability`, `deadcode` | Code metrics and analysis |
| [Security](#security-tasks) | `security`, `audit`, `licenses`, `sbom` | Security scanning and SBOM |
| [Documentation](#documentation-tasks) | `docs_serve`, `docs_build`, `docs_deploy`, `docs_toc` | Documentation management |
| [Dependencies](#dependency-tasks) | `install`, `install_dev`, `update_deps` | Package management |
| [GitHub Workflow](#github-workflow-tasks) | `issue`, `pr`, `pr_merge`, `adr`, `labels_sync`, `env_create`, `env_list`, `publish_setup` | Issue, PR, and environment management |
| [Release](#release-tasks) | `release`, `release_tag`, `publish` | Version and release management |
| [Setup](#setup-tasks) | `pre_commit_install`, `completions`, `install_direnv` | Development environment |
| [Maintenance](#maintenance-tasks) | `cleanup` | Project cleanup |

---

## Testing Tasks

### `test`

Run pytest with parallel execution.

```bash
doit test
```

Runs `pytest -n auto -v` using all available CPU cores.

### `coverage`

Run tests with coverage reporting.

```bash
doit coverage
```

Generates terminal, HTML (`tmp/htmlcov/`), and XML (`tmp/coverage.xml`) coverage reports.

### `mutate`

Run mutation testing with mutmut.

```bash
doit mutate
```

Introduces small changes (mutations) to source code and checks whether tests detect them. Results are stored in `tmp/mutmut/`. See [Mutation Testing](ci-cd-testing.md#mutation-testing) for details.

### `mutate_html`

Generate an HTML report from mutation testing results.

```bash
doit mutate_html
```

Requires `doit mutate` first. Report saved to `tmp/mutmut/index.html`.

---

## Benchmarking Tasks

### `benchmark`

Run performance benchmarks.

```bash
doit benchmark
```

Runs pytest on `tests/benchmarks/` with `--benchmark-enable --benchmark-only`. Benchmarks are disabled by default during normal test runs.

### `benchmark_save`

Run benchmarks and save results as a baseline.

```bash
doit benchmark_save
```

Saves results to `tmp/benchmarks/` for comparison with `benchmark_compare`.

### `benchmark_compare`

Run benchmarks and compare against a saved baseline.

```bash
doit benchmark_compare
```

Shows performance regressions or improvements against the saved baseline.

---

## Code Quality Tasks

### `format`

Format code with ruff.

```bash
doit format
```

Runs `ruff format` and `ruff check --fix` to format and auto-fix Python code.

### `lint`

Run ruff linting checks.

```bash
doit lint
```

### `type_check`

Run mypy type checking.

```bash
doit type_check
```

### `check`

Run all quality checks in sequence.

```bash
doit check
```

Runs format check, lint, type check, security, spelling, and tests. Stops on first failure.

### `spell_check`

Check spelling in code and documentation.

```bash
doit spell_check
```

---

## Code Analysis Tasks

### `complexity`

Analyze cyclomatic complexity with radon.

```bash
doit complexity
```

### `maintainability`

Analyze maintainability index with radon.

```bash
doit maintainability
```

### `deadcode`

Detect unused code with vulture.

```bash
doit deadcode
```

---

## Security Tasks

### `security`

Run static security analysis with bandit.

```bash
doit security
```

### `audit`

Run dependency vulnerability audit with pip-audit.

```bash
doit audit
```

### `licenses`

Check licenses of all dependencies.

```bash
doit licenses
```

### `sbom`

Generate a Software Bill of Materials (SBOM) in CycloneDX format.

```bash
doit sbom
```

Produces `tmp/sbom.json` (JSON) and `tmp/sbom.xml` (XML). See [SBOM Generation](release-and-automation.md#sbom-generation) for details.

---

## Documentation Tasks

### `docs_serve`

Serve documentation locally with live reload at http://127.0.0.1:8000.

```bash
doit docs_serve
```

### `docs_build`

Build static documentation site.

```bash
doit docs_build
```

### `docs_deploy`

Deploy documentation to GitHub Pages.

```bash
doit docs_deploy
```

### `docs_toc`

Generate documentation table of contents.

```bash
doit docs_toc
```

---

## Dependency Tasks

### `install`

Install package with dependencies.

```bash
doit install
```

### `install_dev`

Install package with development dependencies.

```bash
doit install_dev
```

Also marks `src/infrafoundry/_version.py` as assume-unchanged so the version file regenerated by setuptools-scm does not appear as modified in `git status`.

### `update_deps`

Update dependencies and verify with tests.

```bash
doit update_deps
```

---

## GitHub Workflow Tasks

### `issue`

Create a GitHub issue from a template.

```bash
doit issue --type=feature --title="Add feature" --body="## Problem\n..."
doit issue --type=bug --title="Fix bug" --body-file=issue.md
```

Issue types: `feature`, `bug`, `refactor`, `doc`, `chore`.

### `pr`

Create a pull request.

```bash
doit pr --title="feat: add feature" --body="## Description\n..."
```

### `pr_merge`

Merge a pull request with properly formatted commit message.

```bash
doit pr_merge            # Merge PR for current branch
doit pr_merge --pr=123   # Merge specific PR
```

### `adr`

Create an Architecture Decision Record.

```bash
doit adr --title="Use Redis for caching" --body="## Status\nAccepted\n..."
doit adr --title="Template-meta ADR" --template  # Creates a 9XXX-series template ADR
```

**Options:**
- `--title`: ADR title (required)
- `--body`: ADR body (non-interactive)
- `--body-file`: File containing ADR body
- `--template`: Create a template-meta ADR (9XXX series) instead of a project-level ADR

---

## Release Tasks

### `release`

Create a production release with full governance validation.

```bash
doit release
```

### `release_tag`

Tag `main` after a release PR is merged.

```bash
doit release_tag
```

**What it does:**
1. Verifies you are on `main` and pulls the latest changes.
2. Finds the most recently merged `release: vX.Y.Z` PR.
3. Extracts the version from the PR title (falls back to the branch name).
4. Creates the git tag `vX.Y.Z` on `main` and pushes it.
5. The tag push triggers `.github/workflows/release.yml` (production) or
   `.github/workflows/testpypi.yml` (pre-release).

**Pre-releases:** Open a pre-release PR with `doit release --prerelease=alpha`
(or `beta` / `rc`). After merge, run `doit release_tag` — the PEP440 tag format
(`v1.2.3a0`, `v1.2.3b0`, `v1.2.3rc0`, `v1.2.3.dev0`) is picked up by
`testpypi.yml` and publishes to TestPyPI only.

---

## GitHub Environments

### `labels_sync`

Reconcile GitHub labels with `.github/labels.yml` (idempotent).

```bash
doit labels_sync --dry-run      # Preview changes
doit labels_sync                # Create missing / update drift
doit labels_sync --prune        # Also delete labels absent from the file
```

### `env_create`

Create a GitHub environment by name (idempotent).

```bash
doit env_create --name=pypi
doit env_create --name=testpypi
```

### `env_list`

List GitHub environments for the current repository.

```bash
doit env_list
```

### `publish_setup`

Bootstrap GitHub environments (`testpypi`, `pypi`) for PyPI trusted publishing.

```bash
doit publish_setup
```

---

## Setup Tasks

### `pre_commit_install`

Install pre-commit hooks (including post-merge and post-checkout).

```bash
doit pre_commit_install
```

### `completions`

Generate shell completion scripts for doit.

```bash
doit completions
```

### `install_direnv`

Install direnv for automatic environment loading.

```bash
doit install_direnv
```

### `commit`

Interactive commit with commitizen.

```bash
doit commit
```

---

## Maintenance Tasks

### `cleanup`

Clean build and cache artifacts.

```bash
doit cleanup
```

Removes `build/`, `dist/`, `__pycache__/`, `tmp/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`.

---

## See Also

- [CI/CD Testing](ci-cd-testing.md) - Continuous integration
- [Release Automation](release-and-automation.md) - Release process
- [Coding Standards](coding-standards.md) - Code quality guidelines
