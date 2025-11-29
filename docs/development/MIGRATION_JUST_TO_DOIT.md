# Migration from Just to Doit

**Date:** 2025-11-29
**Branch:** `refactor/migrate-to-pydoit`
**Status:** ✅ Complete

## Overview

InfraFoundry has migrated from the [just](https://github.com/casey/just) task runner to [doit](https://pydoit.org/) (pydoit). This change provides better Python integration, cross-platform compatibility, and more powerful task management capabilities.

## What Changed

### Build System
- **Before:** `justfile` with shell-based tasks
- **After:** `dodo.py` with Python-based tasks
- **Benefits:**
  - Better error handling and reporting
  - Cross-platform compatibility (Windows/Mac/Linux)
  - Python integration (can use Python libraries in tasks)
  - Built-in dependency tracking
  - More flexible task definitions

### Command Changes

All commands remain the same, just replace `just` with `doit`:

| Old Command | New Command | Description |
|-------------|-------------|-------------|
| `just install` | `doit install` | Install dependencies with uv |
| `just dev` | `doit dev` | Install with dev dependencies |
| `just test` | `doit test` | Run pytest |
| `just lint` | `doit lint` | Run ruff linter |
| `just format` | `doit format` | Format code with ruff |
| `just coverage` | `doit coverage` | Run tests with coverage |
| `just check` | `doit check` | Run all checks (lint + type check) |
| `just cleanup` | `doit cleanup` | Remove build artifacts and caches |
| `just --list` | `doit list` | List available tasks |

### Infrastructure Commands

| Old Command | New Command | Description |
|-------------|-------------|-------------|
| `just plan` | `doit plan` | Generate and plan infrastructure (dry-run) |
| `just apply` | `doit apply` | Apply infrastructure changes |
| `just destroy` | `doit destroy` | Destroy infrastructure |

### Installation Tasks

These tasks install external dependencies (terraform, ansible, sops, age, direnv):

| Old Command | New Command | Description |
|-------------|-------------|-------------|
| `just install-deps` | `doit install_deps` | Install all system dependencies |
| `just install-terraform` | `doit install_terraform` | Install Terraform |
| `just install-ansible` | `doit install_ansible` | Install Ansible via uv |
| `just install-sops` | `doit install_sops` | Install SOPS secrets manager |
| `just install-age` | `doit install_age` | Install age encryption tool |
| `just install-direnv` | `doit install_direnv` | Install direnv |

## Technical Changes

### 1. Dependencies
- `doit>=0.36.0` added as a base dependency in `pyproject.toml` (not dev)
- This ensures `uv run doit` works without requiring dev dependencies

### 2. Task Definitions
- Tasks defined as Python functions in `dodo.py`
- Each task function returns a dictionary with `actions`, `params`, `title`, etc.
- Better error handling with Python exceptions vs shell exit codes

### 3. Virtual Environment Detection
- `install_ansible` task automatically detects if running in a virtual environment
- Uses `--system` flag for `uv pip install` when not in a venv
- Fixes CI compatibility where `--system` is required

### 4. GitHub API Rate Limiting
- `_get_latest_github_release()` function uses `GITHUB_TOKEN` when available
- Avoids GitHub API rate limits in CI (60/hr unauthenticated → 5000/hr authenticated)
- Automatically uses `${{ secrets.GITHUB_TOKEN }}` in GitHub Actions workflows

### 5. CI/CD Updates
- `.github/workflows/tests.yml` updated to use `doit` commands
- `GITHUB_TOKEN` environment variable passed to installation steps
- All jobs now passing with new build system

## Migration Guide for Users

If you have existing scripts or workflows using `just`:

### 1. Update Scripts
Replace `just` commands with `doit`:

```bash
# Before
just install
just test
just lint

# After
doit install
doit test
doit lint
```

### 2. Update CI/CD Pipelines
If you have custom CI/CD pipelines using InfraFoundry:

```yaml
# Before
- name: Run tests
  run: just test

# After
- name: Run tests
  run: doit test
```

### 3. Update Documentation
Update any custom documentation or runbooks that reference `just` commands.

### 4. Shell Aliases (Optional)
If you want shorter commands, create aliases:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias d='doit'
alias dt='doit test'
alias dl='doit lint'
```

## Features & Benefits

### Python Integration
Tasks can now use Python libraries and have better error handling:

```python
def task_mytest():
    """Run custom tests."""
    def run_tests():
        import subprocess
        result = subprocess.run(['pytest', 'tests/'], capture_output=True)
        if result.returncode != 0:
            raise Exception(f"Tests failed: {result.stderr.decode()}")

    return {
        'actions': [run_tests],
        'verbosity': 2,
    }
```

### Cross-Platform
`doit` works identically on Windows, macOS, and Linux without shell-specific commands.

### Task Dependencies
Built-in dependency tracking:

```python
def task_test():
    return {
        'actions': ['pytest tests/'],
        'file_dep': ['src/**/*.py', 'tests/**/*.py'],  # Only run if files changed
        'task_dep': ['lint'],  # Run lint first
    }
```

### Better Help
Each task can have detailed help text:

```bash
$ doit list --all
apply               Apply infrastructure changes.
check               Run all checks (lint + type check).
cleanup             Remove build artifacts and caches.
coverage            Run tests with full coverage report.
```

## Troubleshooting

### "doit: command not found"

Make sure you've installed InfraFoundry with dependencies:

```bash
uv pip install -e ".[dev]"
# or
uv run doit install
```

### "No tasks found"

Make sure you're in the InfraFoundry root directory where `dodo.py` exists:

```bash
cd /path/to/infrafoundry
doit list
```

### CI Failures with GitHub API Rate Limits

Make sure `GITHUB_TOKEN` is passed to installation steps:

```yaml
- name: Install dependencies
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    doit install_deps
```

## Rollback (If Needed)

If you need to temporarily use the old `just` system:

```bash
# Checkout the commit before the migration
git checkout <commit-before-migration>

# Install just
cargo install just

# Use just commands
just install
just test
```

## References

- [doit Documentation](https://pydoit.org/)
- [Migration Commits](https://github.com/endavis/infrafoundry/compare/main...refactor/migrate-to-pydoit)
- [GitHub Actions Changes](.github/workflows/tests.yml)
- [dodo.py Task Definitions](../../dodo.py)

## Questions?

If you encounter issues with the migration, please open an issue on GitHub with:
- Your operating system
- Python version (`python --version`)
- Full error message
- Steps to reproduce
