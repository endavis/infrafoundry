---
title: "Doit Tasks Reference"
description: "Every doit task in the project and what it does"
audience:
  - contributors
tags:
  - development
---

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
| [GitHub Workflow](#github-workflow-tasks) | `issue`, `pr`, `pr_merge`, `adr`, `labels_sync`, `delegation_context`, `env_create`, `env_list`, `publish_setup` | Issue, PR, and environment management |
| [Release](#release-tasks) | `release`, `release_tag`, `publish` | Version and release management |
| [Setup](#setup-tasks) | `pre_commit_install`, `completions`, `install_direnv`, `install_jq`, `worktree` | Development environment |
| [Maintenance](#maintenance-tasks) | `cleanup` | Project cleanup |

---

## Testing Tasks

### `test`

Run pytest with parallel execution.

```bash
doit test
```

Runs `pytest -n auto -v` using all available CPU cores. Depends on `env_check` first, which warns (without failing) if `uv.lock` has drifted (endavis/pyproject-template#1033).

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

Introduces small changes (mutations) to source code and runs the tests that exercise `src/` (the list in `[tool.mutmut]` in `pyproject.toml`) against each one, then lists the mutations the tests did not kill. Results are stored in `tmp/mutmut/`. See [Mutation Testing](ci-cd-testing.md#mutation-testing) for details.

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

Saves results to `tmp/benchmarks/`. Each run saves a new numbered baseline (`0001_baseline`, `0002_baseline`, ...); `benchmark_compare` compares against the latest one.

### `benchmark_compare`

Run benchmarks and compare against the latest saved baseline.

```bash
doit benchmark_compare
```

Shows performance regressions or improvements against the most recent baseline saved by `benchmark_save`. With no saved baseline, pytest-benchmark warns `Can't compare` and the run still passes.

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

Runs `mypy src/ tools/ tests/ bootstrap.py` with the strict settings in `[tool.mypy]`. The pre-commit mypy hook uses the same scope.

### `check`

Run all quality checks in sequence.

```bash
doit check
```

Warns, without failing, if the environment has drifted from `uv.lock` (`env_check`), then runs format check, lint, blueprint lint, type check, dead code (`deadcode`), security, audit, spelling, a wheel smoke test (`wheel_check`), a strict docs build (`docs_build`), and tests. Stops on first failure.

### `env_check`

Warn, without failing, when the installed environment has drifted from `uv.lock`.

```bash
doit env_check
```

Runs `uv sync --all-extras --dev --check`. If it exits non-zero, prints `uv.lock changed — run: doit install_dev` and returns — it never fails the task and never runs `uv sync` itself. It replaces the `uv-sync-on-pull`/`uv-sync-on-checkout` pre-commit hooks, which auto-ran `uv sync` on `git pull`/`git checkout` before anyone had reviewed the branch (endavis/pyproject-template#1033). `check` and `test` both depend on it, so the reminder runs only when a developer runs `doit` on a branch they have already decided to trust.

### `wheel_check`

Install the built wheel into a throwaway venv and smoke-test it, so a packaging regression (missing module, broken entry point, missing `py.typed`) fails before it ships. Part of `doit check`.

```bash
doit wheel_check              # Build a fresh wheel and check it
doit wheel_check --dist=dist  # Check the single *.whl already in dist/
```

Builds the wheel from a temporary clone of the working tree (uncommitted changes included, so `src/` `_version.py` is not rewritten), confirms `py.typed` is in it, installs it into an isolated venv, imports the package from there, and runs every `[project.scripts]` entry with `--help`. `--dist` fails if the directory has zero or more than one `*.whl`. The release and TestPyPI workflows run it with `--dist=dist` on the wheel they upload.

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

Scans the `paths` in `[tool.vulture]` (`src`, `tests`, `tools`) and is part of `doit check`. Each `ignore_names` entry carries a comment naming the reference vulture cannot see.

---

## Security Tasks

All security tasks need the `security` extra, which `doit install_dev` installs.

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

Equivalent command:

```bash
uv sync
```

Uninstalls the `dev` and `security` extras. Use it where you only run the program; to develop, use `install_dev`.

### `install_dev`

Install package with development dependencies.

```bash
doit install_dev
```

Runs `uv sync --all-extras --dev`, including the `dev` and `security` extras. The task does not install the pre-commit hooks; run `doit pre_commit_install` for those.

It also marks `src/infrafoundry/_version.py` as assume-unchanged so the version file regenerated by setuptools-scm does not appear as modified in `git status`.

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
doit pr --base=feat/42-add-parser   # Open against the unmerged branch this work builds on
```

- `--base`: Open the PR against this branch instead of `main`. The up-to-date check then compares with `origin/<branch>`. After that branch merges, rebase onto `main` and retarget the PR (`gh pr edit <number> --base main`) before `doit pr_merge` accepts it.
- `--no-push`: Abort instead of pushing a branch that has no upstream.
- `--no-update-check`: Skip the check that aborts when the branch is behind `origin/main` (or `origin/<branch>` with `--base`).

### `pr_merge`

Merge a pull request with properly formatted commit message.

```bash
doit pr_merge            # Merge PR for current branch
doit pr_merge --pr=123   # Merge specific PR
```

Stops before merging or closing anything if the PR is not open, targets a branch other than the default branch, or has a non-conventional title. The task does not check approvals or CI itself; branch protection enforces them. PRs in a GitHub native stack are not supported: unstack them with `gh stack unstack`, then merge bottom first.

If a linked worktree has the PR's branch checked out, the task merges without `--delete-branch`, then deletes the remote branch, removes the worktree if it is under `worktrees/` (kept, with the files listed, when it has modified, untracked, or non-rebuildable ignored files such as `.envrc.local`), deletes the local branch if it still points at the merged commit, and removes empty directories under `worktrees/`. Run it from the main checkout with `--pr`. Run from the PR's base branch, it fast-forwards that branch with `git pull --ff-only`; a pull that cannot fast-forward is reported, not fatal.

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

The ADR starts with the template's frontmatter, with the title and date filled in. A body that starts with its own frontmatter keeps it, and `doit adr` sets its title. If the description is still the template's placeholder, it says so; write one sentence that says what was decided, because `docs/TABLE_OF_CONTENTS.md` lists it next to the title.

---

## Release Tasks

Releases follow a single PR-based flow: `doit release` opens a release PR,
and `doit release_tag` tags `main` once the PR is merged.

### `release`

Open a release PR with the version bump and changelog updates.

```bash
# Auto-detect the next version from conventional commits
doit release

# Force a specific increment
doit release --increment=major   # 1.0.0 → 2.0.0
doit release --increment=minor
doit release --increment=patch

# Cut a pre-release PR (TestPyPI)
doit release --prerelease=alpha  # 1.0.0 → 1.0.1a0
doit release --prerelease=beta
doit release --prerelease=rc

# Force a pre-release of a specific bump type (see issue #475)
doit release --prerelease=alpha --increment=minor  # 1.0.0 → 1.1.0a0
```

**What it does:**
1. Verifies you're on `main`
2. Validates `--prerelease` (must be empty, `alpha`, `beta`, or `rc`), `--issue` (must be empty or a number) and `--increment` (must be empty, `MAJOR`, `MINOR` or `PATCH`, in any case)
3. Checks for uncommitted changes
4. Pulls latest changes
5. Runs governance validations (merge commit format, issue links)
6. Runs all quality checks (`doit check`)
7. Asks commitizen for the next version (`cz bump --get-next`)
8. Creates a `release/vX.Y.Z` branch and updates `CHANGELOG.md`
9. Commits the changelog, pushes the branch, and opens PR `release: vX.Y.Z`

A project with a static version or a hand-written changelog gets two more
steps here — see [Release Automation — Downstream opt-ins](release-and-automation.md#downstream-opt-ins-static-version-and-hand-written-changelog).

**Options:**
- `--increment`: Force `MAJOR`, `MINOR`, or `PATCH` bump (auto-detects if empty).
- `--prerelease`: `alpha`, `beta`, or `rc`. Empty means a production release.
  Can be combined with `--increment` to force a pre-release of a specific
  bump type (see [issue #475](https://github.com/endavis/pyproject-template/issues/475)).
- `--issue`: Release issue number. Writes `Addresses #N` into the PR body, so `doit pr_merge`
  records it in the merge commit.

**Requirements:**
- Must be on `main` branch
- No uncommitted changes
- All checks must pass
- `--prerelease` additionally requires a baseline `v*` tag so commitizen
  has an anchor to bump from. Existing projects that predate the bootstrap
  auto-seed should seed one manually — see
  [Before your first pre-release](release-and-automation.md#before-your-first-pre-release).

See [Release Automation](release-and-automation.md) for the full flow.

### `release_tag`

Tag `main` after the release PR is merged, and — if `.github/workflows/release.yml`
exists — trigger the publish workflow it defines.

```bash
git checkout main
git pull
doit release_tag
```

**What it does:**
1. Verifies you're on `main`
2. Pulls latest changes
3. Finds the most recently merged `release: vX.Y.Z` PR
4. Extracts the version from the PR title (falls back to the branch name)
5. Creates the git tag `vX.Y.Z` on `main`
6. Pushes the tag. If `.github/workflows/release.yml` exists, it triggers the
   publish workflow and the printed next steps point at GitHub Actions and
   PyPI/TestPyPI. Otherwise nothing builds or publishes from the tag, and the
   task says so instead — the tag is the release (#993).

---

## GitHub Environments

### `labels_sync`

Reconcile GitHub labels with `.github/labels.yml` (idempotent).

```bash
doit labels_sync --dry-run      # Preview changes
doit labels_sync                # Create missing / update drift
doit labels_sync --prune        # Also delete labels absent from the file
```

### `delegation_context`

Fetch the GitHub data a delegated agent needs and write it to files, so the delegated agent reads them instead of calling `gh` itself. The host CLI runs it before delegating (`/multi-*`, `implement-issue`, the Codex bridge skills).

```bash
doit delegation_context --kind=issue --n=985 --out=tmp/agents/claude/multi-plan-985  # issue.json + comments.json
doit delegation_context --kind=pr --n=42 --out=tmp/agents/claude/multi-review-42      # pr.json + diff.txt
```

All three options are required. A missing or inaccessible issue or PR aborts with exit code 1, never an empty file. The calling skill deletes the directory when done. See [Cross-Agent Delegation Matrix](ai/cross-agent-delegation.md).

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

Install every hook type declared by `default_install_hook_types` in `.pre-commit-config.yaml`:
`pre-commit` and `commit-msg`. Also uninstalls `post-checkout` and `post-merge` if a previous run
installed them (`pre-commit uninstall -t post-checkout -t post-merge`; a no-op if they were never
installed).

```bash
doit pre_commit_install
```

**Why `commit-msg` matters:** it carries conventional-commit validation and the check that a
commit's issue reference matches its branch. A clone that installed hooks *before* that type was
declared does not have it, and neither check runs — silently, because a hook that was never
installed cannot fail. Run this task again to pick it up, then confirm with `ls .git/hooks/`.

**Why `post-checkout`/`post-merge` are uninstalled, not fixed (endavis/pyproject-template#1033):**
`pre-commit` reads `.pre-commit-config.yaml` from whatever is checked out, so a hook of either type
— ours, or one an untrusted branch supplies in its own copy of the file — runs before anyone has
reviewed that branch. Only not installing the type closes that. `doit check` and `doit test` warn
instead, via `env_check`, when `uv.lock` has drifted from the installed environment.

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

### `install_jq`

Install jq, which the Claude and agy statusline scripts depend on.

```bash
doit install_jq
```

Installs `jq` into `~/.local/bin` from the `jqlang/jq` GitHub releases if it is not already on `PATH`. Without it, the statusline scripts print `statusline: jq not installed (run: doit install_jq)` instead of rendering.

### `commit`

Interactive commit with commitizen.

```bash
doit commit
```

### `worktree`

Create a git worktree with its own environment, for working on a branch while the main checkout holds other work.

```bash
doit worktree --branch=feat/42-add-export
```

Checks the branch name, fetches `origin/main`, creates `worktrees/<branch>` on a new branch with no upstream (so `doit pr` pushes it), and runs `uv sync --all-extras --dev` there with `VIRTUAL_ENV` unset so the worktree gets its own `.venv`.

- Run everything through `uv run` in the worktree; the shell's `VIRTUAL_ENV` and `PATH` still point at the main checkout. Never pass `--active` to `uv`.
- Merge its PR from the main checkout with `uv run doit pr_merge --pr=<number>`, which removes the worktree and its branch. To remove it without merging, run `git worktree remove worktrees/<branch>`.
- `worktrees/` is gitignored and skipped by the repository-wide test walkers. Worktrees do not go under `tmp/`, which [`cleanup`](#cleanup) empties.

---

## Pre-commit Hooks

The following hooks run automatically on `git commit`:

| Hook | Purpose |
|------|---------|
| `ruff` | Lint and auto-fix Python code |
| `ruff-format` | Format Python code |
| `mypy` | Type checking |
| `bandit` | Security scanning (if installed) |
| `codespell` | Spell checking |
| `check-branch-name` | Enforce branch naming convention |
| `generate-doc-toc` | Update documentation TOC |
| `no-commit-to-main` | Prevent direct commits to main |
| `no-local-config` | Prevent committing local config files |
| `protect-dynamic-version` | Protect version configuration |
| `uv-lock-check` | Validate `uv.lock` is in sync with `pyproject.toml` when `pyproject.toml` is staged |
| `conventional-pre-commit` | Enforce conventional commit format |

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
