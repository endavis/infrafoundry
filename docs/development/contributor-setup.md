---
title: "Contributor Setup"
description: "Set up a development environment for working on InfraFoundry itself"
audience:
  - contributors
tags:
  - development
  - setup
---

# Contributor Setup

How to set up a checkout to work on InfraFoundry's own code. To *use* InfraFoundry, start with the
[Setup Guide](../getting-started/setup-guide.md) instead.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv), the Python package and environment manager
- [direnv](https://direnv.net/), optional but recommended, for automatic environment loading
- [GitHub CLI (`gh`)](https://cli.github.com/), required: many `doit` tasks use it for issues and PRs,
  and the AI-assisted workflows depend on it (see [AI Agent Setup](AI_SETUP.md#github-cli-gh-requirement))

## Initial Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/endavis/infrafoundry.git
cd infrafoundry

# Create the virtual environment and install all dependencies
uv sync --all-extras --dev

# Install the pre-commit hooks
uv run doit pre_commit_install

# Optional: install direnv on Linux through the doit helper
uv run doit install_direnv

# Hook direnv into your shell (one time); use the line for your shell's rc file
#   Bash: eval "$(direnv hook bash)"
#   Zsh:  eval "$(direnv hook zsh)"

# Let direnv load .envrc
direnv allow

# Optional: personal overrides
cp .envrc.local.example .envrc.local
```

`gh auth login` authenticates the GitHub CLI once it is installed.

## Environment Variables

direnv loads the environment when you enter the checkout:

- `.envrc` (committed) holds the project defaults.
- `.envrc.local` (git-ignored) holds personal overrides and credentials.
- The virtual environment is activated automatically.

See [Direnv Integration](../getting-started/direnv.md) for the full behavior and troubleshooting.

## Setup Without direnv

```bash
# Create the virtual environment and activate it
uv venv
source .venv/bin/activate

# Install dependencies
uv sync --all-extras --dev
```

Set any `INFRAFOUNDRY_*` variables you need by hand with `export`.

## Tooling

| Tool | Purpose |
| :--- | :--- |
| uv | Python package installer and dependency manager |
| ruff | Linter and formatter |
| mypy | Static type checker in strict mode |
| pytest, pytest-xdist | Test framework with parallel execution |
| bandit | Security vulnerability scanner |
| codespell | Spell checker for code and documentation |
| pip-audit | Dependency vulnerability auditor |
| pip-licenses | License compliance checker |
| pyproject-fmt | Keeps `pyproject.toml` formatted |
| commitizen | Conventional commit enforcement and release versioning |
| pre-commit | Git hooks that run these checks before each commit |
| MkDocs, mkdocs-material | Documentation site generator and theme |

`uv run doit check` runs format, lint, type check and tests together.

## Where to Go Next

- [Doit Tasks Reference](doit-tasks-reference.md): every `doit` task, including testing, code quality,
  security, documentation and maintenance.
- [CI/CD Testing](ci-cd-testing.md): running tests locally and the pre-commit hook list.
- [Release & Automation](release-and-automation.md): versioning and the release process.
- [AI Agent Setup](AI_SETUP.md): configuring Claude Code, Codex CLI, Copilot CLI and Antigravity CLI.
- [Coding Standards](coding-standards.md) and the repository's `.github/CONTRIBUTING.md`: the
  contribution workflow.
