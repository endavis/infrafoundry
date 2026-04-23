# InfraFoundry

[![CI](https://github.com/endavis/infrafoundry/actions/workflows/ci.yml/badge.svg)](https://github.com/endavis/infrafoundry/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/endavis/infrafoundry/branch/main/graph/badge.svg)](https://codecov.io/gh/endavis/infrafoundry)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A pluggable infrastructure code generator and orchestration framework that turns YAML into Terraform/Ansible, with optional execution, state tracking, policies, and notifications.

## Audience and Prerequisites

- **Audience:** Platform/infrastructure engineers and contributors building or operating InfraFoundry.
- **Prereqs:** Python 3.12+, `uv`, Terraform ≥1.6 or OpenTofu ≥1.6, Ansible ≥2.15, SOPS + age, direnv (optional), and access to a config repo (`INFRAFOUNDRY_CONFIG_REPO` or `--config-dir`).

## When to Use This

- You want YAML-only definitions that generate Terraform/Ansible for multi-provider environments.
- You need reproducible, policy-enforced plans/applies with state/history and notifications.
- You prefer separating framework and configuration repositories.

## Features

- Pluggable providers (Proxmox, OPNsense, Kubernetes; extensible)
- Secrets management via SOPS/age (pluggable backends planned — see #419)
- YAML-only configuration; generated Terraform/Ansible artifacts
- Separate config repos; CI/CD-ready with GitHub/GitLab examples
- State/history tracking (SQLite/PostgreSQL)
- Event system + notifications; policy enforcement; drift detection; dependency graphing
- Modern tooling: `uv` for deps, `ruff` for format/lint, `mypy` in strict mode
- CI/CD ready: GitHub Actions for checks, coverage upload, and releases
- Release automation: hatch-vcs + commitizen-driven tagging and changelog

## Quick Start

```bash
git clone https://github.com/endavis/infrafoundry.git
cd infrafoundry
./scripts/setup-dependencies.sh
./scripts/setup-config.sh
foundry doctor
foundry infra plan --env dev
foundry infra apply --env dev
```

## Documentation

Full documentation is available in the [docs/](docs/) directory.

Build and view locally:

```bash
doit docs_serve  # Opens at http://127.0.0.1:8000
```

For a comprehensive overview of all documentation, including getting started guides, configuration details, architectural insights, development practices, and more, please refer to the [documentation index](docs/index.md).

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — Fast Python package installer
- [direnv](https://direnv.net/) — Automatic environment variable loading (optional but recommended)

### Initial Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/endavis/infrafoundry.git
cd infrafoundry

# Create virtual environment and install dependencies
uv sync --all-extras --dev

# Install pre-commit hooks
doit pre_commit_install

# Optional: install direnv via the doit helper on Linux
doit install_direnv

# Hook direnv into your shell (one-time setup)
# Bash:
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
# Zsh:
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc

# Allow direnv to load .envrc
direnv allow

# Optional: create .envrc.local for personal overrides
cp .envrc.local.example .envrc.local
```

## Versioning & Releases

This project uses automated versioning and releases powered by `commitizen` and `hatch-vcs`.

- **Single Source of Truth:** The Git tag is the definitive version. `pyproject.toml` and `_version.py` are generated at build time from tags (no manual edits).
- **Versioning Scheme:**
    - **Production:** Standard SemVer (e.g., `v1.0.0`).
    - **Development:** PEP440 pre-release tags (e.g., `v1.0.0a0`, `v1.0.0b0`, `v1.0.0rc0`, `v1.0.0.dev0`).

### Creating a Release

All releases go through a pull request. `doit release` opens the release PR; after a reviewer merges it, `doit release_tag` tags `main` and triggers the publish workflow.

```bash
# Step 1: open a release PR
doit release                     # auto-detect next version from commits
doit release --increment=major   # force MAJOR
doit release --increment=minor   # force MINOR
doit release --increment=patch   # force PATCH
doit release --prerelease=alpha  # pre-release (1.0.0 → 1.0.1a0)

# Step 2 (after PR is merged):
git checkout main && git pull
doit release_tag                  # tags main and triggers the publish workflow
```

See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md#release-process) for the full release process including workflow triggers, bypass-permission setup, and troubleshooting.

### Environment Variables

This project uses direnv for automatic environment management. After setup:

- `.envrc` (committed) contains project defaults and is loaded automatically
- `.envrc.local` (git-ignored) is for personal overrides and credentials
- Environment variables are set automatically when you enter the project directory
- Virtual environment is activated automatically

### Manual Setup (without direnv)

```bash
# Create virtual environment and activate it
uv venv
source .venv/bin/activate

# Set environment variables manually
export UV_CACHE_DIR="$(pwd)/tmp/.uv_cache"

# Install dependencies
uv sync --all-extras --dev
```

## Available Tasks

View all available tasks:

```bash
doit list
```

### Quick Commands

```bash
# Testing
doit test          # Run tests (parallel execution with pytest-xdist)
doit coverage      # Run tests with coverage report

# Code Quality
doit format        # Format code with ruff
doit lint          # Run linting
doit type_check    # Run type checking with mypy
doit check         # Run ALL checks (format, lint, type check, test)

# Security
doit security      # Run security scan with bandit
doit audit         # Run dependency vulnerability audit
doit spell_check   # Check for typos with codespell
doit licenses      # Check licenses of dependencies

# Version Management
doit commit        # Interactive commit with conventional format
doit release       # Open release PR (commitizen-driven)
doit release_tag   # Tag main after release PR merges

# Documentation
doit docs_serve    # Serve docs locally with live reload
doit docs_build    # Build documentation site
doit docs_deploy   # Deploy docs to GitHub Pages

# Maintenance
doit cleanup       # Clean build artifacts and caches
doit update_deps   # Update dependencies and run tests
```

## Running Tests

```bash
# Run all tests (parallel execution)
doit test

# Run with coverage
doit coverage

# View coverage report
open tmp/htmlcov/index.html

# Run a specific test
uv run pytest tests/test_example.py::test_version -v
```

## Code Quality

This project includes comprehensive tooling:

### Core Tools

- **uv** — Fast Python package installer and dependency manager
- **ruff** — Extremely fast Python linter and formatter
- **mypy** — Static type checker with strict mode
- **pytest** — Testing framework with parallel execution (pytest-xdist)

### Quality & Security

- **bandit** — Security vulnerability scanner
- **codespell** — Spell checker for code and documentation
- **pip-audit** — Dependency vulnerability auditor
- **pip-licenses** — License compliance checker
- **pre-commit** — Git hooks for automated quality checks
- **pyproject-fmt** — Keep pyproject.toml formatted and organized
- **commitizen** — Enforce conventional commit message standards

### Documentation

- **MkDocs** — Documentation site generator
- **mkdocs-material** — Material Design theme for MkDocs

Run all quality checks:

```bash
doit check
```

### Pre-commit Hooks

Install hooks to run checks automatically before each commit:

```bash
doit pre_commit_install
```

Hooks include:

- Code formatting (ruff)
- Type checking (mypy)
- Security scanning (bandit)
- Spell checking (codespell)
- YAML/TOML validation
- Trailing whitespace removal
- Private key detection
- Branch-naming enforcement
- Blueprint linter (InfraFoundry-specific)

## AI Agent Support

InfraFoundry is designed primarily for **Claude Code**, which ships the full slash-command workflow (plan → implement → finalize → close-issue). **Gemini CLI** is supported as a second-opinion planner/reviewer inside Claude-orchestrated dual-agent commands, and **Codex CLI** is supported as a standalone alternative without slash commands.

### Requirements

> **Important:** [GitHub CLI (`gh`)](https://cli.github.com/) is **required** for AI-assisted workflows.
>
> Many `doit` tasks use `gh` for issue creation, PR management, and repository operations.
> Install and authenticate before using AI agents:
>
> ```bash
> # Install (macOS)
> brew install gh
>
> # Install (Linux) — see https://github.com/cli/cli/blob/trunk/docs/install_linux.md
>
> # Authenticate
> gh auth login
> ```

### Features

- **AGENTS.md** — Instructions and protocols for AI agents
- **Dangerous command blocking** — Hooks prevent destructive operations (force push to main, branch deletion, etc.)
- **Workflow automation** — `doit issue` and `doit pr` for GitHub operations

See [AGENTS.md](AGENTS.md) and [docs/development/](docs/development/) for more details.

## Contributing

- Use Conventional Commits; maintain ≥69% coverage.
- Run locally: `doit check` (runs format, lint, type-check, tests).
- See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) for the full workflow.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Support

- Issues/Discussions: [github.com/endavis/infrafoundry](https://github.com/endavis/infrafoundry)
- Docs: [docs/](docs/index.md) in repo

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
