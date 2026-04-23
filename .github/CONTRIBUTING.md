# Contributing to InfraFoundry

Thank you for your interest in contributing to this project! We welcome contributions from everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

## Code of Conduct

This project adheres to the Contributor Covenant [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your changes
5. Make your changes
6. Run tests and checks
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [direnv](https://direnv.net/) - Automatic environment management (recommended)

### Initial Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/infrafoundry.git
cd infrafoundry

# Set up direnv
direnv allow
# Optional: Create .envrc.local for personal settings
cp .envrc.local.example .envrc.local

# Install dependencies (creates venv automatically)
uv sync --all-extras

# Install pre-commit hooks
doit pre_commit_install
```

### Available Commands

View all available development tasks:
```bash
doit list
```

Common commands:
```bash
doit test          # Run tests
doit coverage      # Run tests with coverage
doit lint          # Run linting
doit format        # Format code
doit type_check    # Run type checking
doit check         # Run all checks
doit benchmark     # Run performance benchmarks
doit cleanup       # Clean build artifacts
```

## How to Contribute

### Types of Contributions

We welcome many types of contributions:

- **Bug fixes** - Fix issues in the codebase
- **New features** - Add new functionality
- **Documentation** - Improve docs, docstrings, examples
- **Tests** - Add or improve test coverage
- **Refactoring** - Improve code quality without changing behavior
- **Performance** - Optimize performance

### Before You Start

1. **Check existing issues** - See if someone is already working on it
2. **Open an issue** - Discuss your proposed changes before starting work
3. **Get feedback** - Especially for large changes or new features

## Coding Standards

### Python Style

- **Python version:** 3.12+ with modern type hints
- **Line length:** Max 100 characters
- **Docstrings:** Google-style for all public APIs
- **Type hints:** Required for all public functions/methods
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **File I/O:** Always pass `encoding="utf-8"` to `Path.read_text()`,
  `Path.write_text()`, text-mode `open()`, and `tempfile.NamedTemporaryFile()`.
  Omitting the kwarg falls back to `locale.getpreferredencoding()`, which is
  `cp1252` on Windows and breaks silently on non-ASCII content. Binary-mode
  calls (`"rb"`, `"wb"`, `"ab"`) and `tarfile.open(...)` do not take an
  encoding kwarg. Enforced by ruff's `PLW1514` rule.

### Type Hints

Use modern type hint syntax:
```python
# Good
def process_items(items: list[str]) -> dict[str, int]:
    pass

# Bad
from typing import List, Dict
def process_items(items: List[str]) -> Dict[str, int]:
    pass
```

### Docstrings

Use Google-style docstrings. These are automatically extracted into the
[API Reference](../docs/reference/api.md) documentation using mkdocstrings.

```python
def example_function(param1: str, param2: int = 10) -> bool:
    """Short description of the function.

    Longer description if needed, explaining the purpose,
    behavior, and any important details.

    Args:
        param1: Description of param1.
        param2: Description of param2. Defaults to 10.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param2 is negative.

    Examples:
        >>> example_function("test", 5)
        True
        >>> example_function("", 10)
        False
    """
```

**Key points:**

- Type hints go in signatures, not duplicated in docstrings
- End descriptions with periods for consistency
- Include `Examples` section for complex functions (used by doctests)
- Document all public functions, classes, and methods
- Module-level docstrings describe the module's purpose

### Code Organization

Organize imports in three groups:
```python
# Standard library
import os
from pathlib import Path

# Third-party
import click
import pytest

# Local
from infrafoundry import module
```

## Testing Guidelines

### Writing Tests

- Write tests for all new functionality
- Maintain or improve test coverage (target: ≥80%)
- Use descriptive test names: `test_function_does_something_when_condition`
- Use fixtures for common setup
- Test edge cases and error conditions

### Running Tests

```bash
# Run all tests
doit test

# Run with coverage
doit coverage

# Run specific test file
uv run pytest tests/test_example.py

# Run specific test
uv run pytest tests/test_example.py::test_specific_function -v
```

### Test Structure

```python
import pytest

def test_feature_works_correctly():
    """Test that feature produces expected output."""
    # Arrange
    input_data = "test input"

    # Act
    result = function_to_test(input_data)

    # Assert
    assert result == expected_output


@pytest.mark.parametrize("input_value,expected", [
    ("value1", "expected1"),
    ("value2", "expected2"),
])
def test_feature_with_multiple_inputs(input_value, expected):
    """Test feature with various inputs."""
    assert function_to_test(input_value) == expected
```

## Commit Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/):

### Commit Format

```
<type>: <subject>

[optional body]

[optional footer]
```

### Commit Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Formatting, whitespace (no code change)
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks (deps, tooling)
- `ci`: CI/CD changes
- `revert`: Reverting previous commits

### Examples

```bash
feat: add support for async operations

fix: handle None values in data processor

docs: update installation instructions

test: add tests for edge cases in parser
```

### Breaking Changes

For breaking changes, include `BREAKING CHANGE:` in the footer:

```
refactor: change API to use async/await

BREAKING CHANGE: All public methods are now async.
Update calling code to use `await`.
```

### Exceptions

**Dependabot commits** are exempt from the full merge commit format. Dependabot automatically generates commits with:

```
chore(deps): bump <package> from X to Y (#PR)
```

This is acceptable because:
- Dependabot creates commit messages before the PR exists (cannot reference PR number)
- Automated dependency updates don't have linked issues
- The `chore(deps):` format follows conventional commits with a scope

## Pull Request Process

### Before Submitting

1. **Run all checks locally:**
   ```bash
   doit check
   ```

2. **Use conventional commit messages** - Your commit messages (`feat:`, `fix:`, etc.) automatically become changelog entries during release. See [Commit Guidelines](#commit-guidelines).

3. **Update documentation** (if needed)

4. **Update related ADRs** (if implementing an architectural decision) - Add your issue link to the Related section

5. **Self-review your code**

### PR Title

Use the same format as commits: `<type>: <subject>`

Examples:
- `feat: add support for custom validators`
- `fix: handle edge case in data parsing`
- `docs: improve API documentation`

### PR Description

Fill out the PR template (`.github/pull_request_template.md`):
- Provide a clear summary
- List specific changes
- Reference related issues
- Describe testing performed
- Note any breaking changes

### PR Review Process

1. **Automated checks** - CI must pass (tests, lint, type-check)
2. **Code review** - At least one maintainer approval required
3. **Address feedback** - Respond to review comments
4. **Add `ready-to-merge` label** - When PR is approved and CI passes (see below)
5. **Merge** - Maintainer will merge when approved

### Merge Gate and `ready-to-merge` Label

This repository uses a **merge gate** workflow to prevent premature merges:

**Why this exists:**
- Ensures full CI matrix (all OS/Python versions) completes before merge
- Prevents merging while tests are still running
- Provides explicit "ready" signal after review

**How it works:**
1. Open a PR - initial CI checks run
2. Get code review and address feedback
3. Wait for **all** CI checks to pass (including full OS matrix)
4. Add the `ready-to-merge` label to signal the PR is ready
5. The merge gate check passes, allowing merge

**Important:**
- The `ready-to-merge` label should only be added after:
  - All CI checks have passed (including full OS matrix)
  - Code review is complete and approved
  - All feedback has been addressed
- Adding the label prematurely doesn't bypass CI - the merge gate waits for CI completion
- The label works alongside GitHub's approval requirement - both must be satisfied

**With approval workflows enabled:**

If your repository requires PR approvals (branch protection → "Require approvals"), the merge flow becomes:

1. CI checks pass
2. Reviewer approves the PR
3. Add `ready-to-merge` label (final "ship it" signal)
4. Merge allowed

The label and approval are independent checks - both must pass. The label serves as an explicit final confirmation after review and CI are complete.

### After Merge

- Delete your branch
- Update your fork with the latest changes
- Close any related issues with comment "Addressed in PR #XXX"

## Release Process

This section documents how to publish releases to TestPyPI and PyPI.

> **Note:** Releases can only be performed by maintainers with push access to the repository and appropriate PyPI/TestPyPI permissions.

### How Versioning Works

This project uses **semantic versioning** derived automatically from git tags via [hatch-vcs](https://github.com/ofek/hatch-vcs):

- **No manual version editing** - Version is determined by git tags
- **Tag format:** `v<major>.<minor>.<patch>` (e.g., `v1.2.3`)
- **Pre-release format:** PEP440 `v<version><type><n>` (e.g., `v1.2.3a0`, `v1.2.3b1`, `v1.2.3rc0`, `v1.2.3.dev0`) — emitted by commitizen via `doit release --prerelease=...`

Version bumping is handled by [commitizen](https://commitizen-tools.github.io/commitizen/) based on conventional commit history:

| Commit Type | Version Bump |
|-------------|--------------|
| `fix:` | Patch (1.0.0 → 1.0.1) |
| `feat:` | Minor (1.0.0 → 1.1.0) |
| `BREAKING CHANGE:` | Major (1.0.0 → 2.0.0) |

### Release Workflow

All releases — production and pre-release — go through a pull request.
`doit release` opens the release PR; a reviewer merges it; `doit release_tag`
then tags `main` and triggers the publish workflow. Direct-to-`main` release
commands are not supported.

```bash
# Step 1: open a release PR
doit release                       # auto-detect next version from commits
doit release --increment=major     # force MAJOR (1.0.0 → 2.0.0)
doit release --increment=minor     # force MINOR
doit release --increment=patch     # force PATCH
doit release --prerelease=alpha    # open a pre-release PR (1.0.0 → 1.0.1a0)
doit release --prerelease=beta
doit release --prerelease=rc

# --> reviewer merges the PR --

# Step 2: tag main and trigger publish
git checkout main
git pull
doit release_tag
```

`--increment` and `--prerelease` can be combined to force a pre-release of a
specific bump type (e.g. `--prerelease=alpha --increment=minor` → `1.1.0a0`).
See [issue #475](https://github.com/endavis/pyproject-template/issues/475).

**What `doit release` does:**

1. Verifies you're on `main` with a clean working tree
2. Validates `--prerelease` (must be empty, `alpha`, `beta`, or `rc`)
3. Pulls latest changes from remote
4. Validates merge commit format (governance check)
5. Validates issue links in commits
6. Runs all checks (`doit check`)
7. Determines the next version using commitizen (`cz bump --get-next`)
8. Creates a `release/vX.Y.Z` branch and updates `CHANGELOG.md`
9. Commits the changelog, pushes the branch, and opens PR `release: vX.Y.Z`

**What `doit release_tag` does:**

1. Verifies you're on `main`, pulls latest changes
2. Finds the most recently merged `release: vX.Y.Z` PR
3. Extracts the version from the PR title (falls back to the branch name)
4. Creates the git tag `vX.Y.Z` on `main`
5. Pushes the tag
6. **Triggers:** `.github/workflows/release.yml` (production) or
   `.github/workflows/testpypi.yml` (pre-release)
7. **Publishes to:** TestPyPI first, then PyPI for production tags; TestPyPI
   only for pre-release tags

**Testing a pre-release from TestPyPI:**

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ infrafoundry==1.0.1a0
```

### Workflow Triggers

| Workflow | Trigger | Destination |
|----------|---------|-------------|
| `testpypi.yml` | PEP440 pre-release tags: `v*a[0-9]*`, `v*b[0-9]*`, `v*rc[0-9]*`, `v*.dev[0-9]*` (e.g., `v1.0.0a0`) | TestPyPI only |
| `release.yml` | Tag matching `v[0-9]+.[0-9]+.[0-9]+` (e.g., `v1.0.0`) | TestPyPI → PyPI |

### Setting Up Release Permissions

`doit release_tag` pushes the version tag directly to `main`. If your branch
protection rules cover tag pushes, configure a bypass for the tagging step.
The release PR itself is reviewed and merged through the normal PR flow, so
no bypass is required for the commit and changelog changes.

#### Organization Repositories: GitHub App (Recommended)

Create a dedicated GitHub App that can bypass branch protection:

**1. Create the GitHub App:**

1. Go to **GitHub Settings** → **Developer Settings** → **GitHub Apps**
2. Click **New GitHub App**
3. Fill in:
   - **Name:** `<your-org>-release-bot` (must be globally unique)
   - **Homepage URL:** Your repository URL
   - **Webhook:** Uncheck "Active" (not needed)
4. Set **Repository Permissions:**
   - **Contents:** Read and write (to push commits/tags)
   - **Metadata:** Read-only (required)
   - **Pull requests:** Write (required for the dependabot auto-merge
     workflow to apply the `ready-to-merge` label via the App — see
     [Dependabot Auto-merge → Required GitHub App configuration](../docs/development/dependabot-automerge.md#required-github-app-configuration))
5. Click **Create GitHub App**
6. Note the **App ID** displayed on the app page
7. Scroll down → **Generate a private key** → saves a `.pem` file

**2. Install the App:**

1. On the App page, click **Install App** (left sidebar)
2. Select your organization
3. Choose **Only select repositories** → select your repo
4. Click **Install**

**3. Add to Ruleset Bypass:**

1. Go to **Repo Settings** → **Rules** → **Rulesets** → select your main branch ruleset
2. Under **Bypass list**, click **Add bypass**
3. Select your release app from the list
4. Save the ruleset

**4. Store Secrets:**

In your repo **Settings** → **Secrets and variables** → **Actions**:

- Add **Secret:** `RELEASE_APP_PRIVATE_KEY` = contents of the `.pem` file
- Add **Variable:** `RELEASE_APP_ID` = the App ID from step 1

**5. Update Workflows (if using CI-based releases):**

```yaml
- name: Generate release token
  id: app-token
  uses: actions/create-github-app-token@v3
  with:
    app-id: ${{ vars.RELEASE_APP_ID }}
    private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}

- name: Checkout with token
  uses: actions/checkout@v4
  with:
    token: ${{ steps.app-token.outputs.token }}
    fetch-depth: 0
```

#### Personal Repositories: Personal Access Token (PAT)

For personal (non-organization) repositories, use a fine-grained PAT:

**1. Create a Fine-Grained PAT:**

1. Go to **GitHub Settings** → **Developer Settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click **Generate new token**
3. Fill in:
   - **Name:** `release-token`
   - **Expiration:** Set appropriate expiration
   - **Repository access:** Select your repository
4. Set **Repository Permissions:**
   - **Contents:** Read and write
   - **Metadata:** Read-only
5. Click **Generate token** and copy it immediately

**2. Configure Git to Use the Token:**

For local releases, configure git to use the token:

```bash
# Option 1: Use credential helper (recommended)
git config --global credential.helper store
# Then git will prompt for credentials on first push

# Option 2: Include token in remote URL (less secure)
git remote set-url origin https://<token>@github.com/username/repo.git
```

**3. Store as Secret (for CI-based releases):**

In your repo **Settings** → **Secrets and variables** → **Actions**:

- Add **Secret:** `RELEASE_PAT` = your PAT

**4. Update Workflows:**

```yaml
- name: Checkout with PAT
  uses: actions/checkout@v4
  with:
    token: ${{ secrets.RELEASE_PAT }}
    fetch-depth: 0
```

### Release Checklist

Before opening a release PR:

- [ ] All CI checks pass on `main`
- [ ] CHANGELOG.md is up to date (or will be auto-generated)
- [ ] No uncommitted changes on your working tree
- [ ] You have push access to the repository
- [ ] PyPI/TestPyPI environments are configured in GitHub

After the release PR is merged:

- [ ] `git checkout main && git pull`
- [ ] `doit release_tag`
- [ ] Monitor the publish workflow in GitHub Actions
- [ ] Verify the new version on TestPyPI (pre-release) or PyPI (production)

### Typical Release Cycle

1. **Development:** Features merged to `main` via PRs
2. **Alpha testing:** `doit release --prerelease=alpha` → merge PR → `doit release_tag` → Test on TestPyPI
3. **Beta testing:** `doit release --prerelease=beta` → merge PR → `doit release_tag` → Wider testing
4. **Release candidate:** `doit release --prerelease=rc` → merge PR → `doit release_tag` → Final testing
5. **Production:** `doit release` → merge PR → `doit release_tag` → Publish to PyPI

### Troubleshooting

**"Uncommitted changes detected"**
- Commit or stash your changes before releasing

**"Not on main branch"**
- Switch to main: `git checkout main && git pull`

**"Pre-release checks failed"**
- Run `doit check` and fix any issues before retrying

**"commitizen bump failed"**
- Ensure commits follow conventional format
- Check that there are commits since the last tag

**PyPI publish fails**
- Verify GitHub environment secrets are configured
- Check that the version doesn't already exist on PyPI

## Reporting Bugs

Use the bug report template (`.github/ISSUE_TEMPLATE/bug_report.yml`):

1. Go to **Issues** → **New Issue** → **Bug Report**
2. Fill out all sections:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, package version)
   - Error messages or logs
3. Add relevant labels
4. Be responsive to follow-up questions

## Requesting Features

Use the feature request template (`.github/ISSUE_TEMPLATE/feature_request.yml`):

1. Go to **Issues** → **New Issue** → **Feature Request**
2. Fill out all sections:
   - Problem statement
   - Proposed solution
   - Alternative solutions considered
   - Use cases
   - Benefits
3. Be open to discussion and feedback
4. Be willing to implement it yourself (or help)

## Development Workflow

**MANDATORY RULE:** All changes must originate from a GitHub Issue.

### Issue-Driven Development

Every code change must be linked to a GitHub Issue. This ensures:
- **Traceability:** Every change is linked to a documented need
- **Context:** Issues capture the "why" behind changes
- **Planning:** Better project management and prioritization
- **History:** Searchable record of decisions and rationale
- **Collaboration:** Clear communication about work in progress

### Workflow Steps

#### 1. **Issue:** Ensure GitHub Issue Exists

**Create issue using doit (recommended):**
```bash
# Interactive: Opens $EDITOR with template
doit issue --type=feature    # For new features
doit issue --type=bug        # For bugs and defects
doit issue --type=refactor   # For code refactoring
doit issue --type=docs       # For documentation
doit issue --type=chore      # For maintenance tasks

# Non-interactive: For AI agents or scripts
doit issue --type=feature --title="Add export" --body-file=issue.md
doit issue --type=docs --title="Add guide" --body="## Description\n..."
```

**Or use gh CLI directly:**
```bash
gh issue create --title "<description>" --label "enhancement" --body "..."
```

**Issue types auto-apply labels:**
- `feature` → `enhancement, needs-triage`
- `bug` → `bug, needs-triage`
- `refactor` → `refactor, needs-triage`
- `docs` → `documentation, needs-triage`
- `chore` → `chore, needs-triage`

**Required fields ensure complete information** - Fill all fields to provide context.

#### 2. **Branch:** Create Branch Linked to Issue

**Branch Format:** `<type>/<number>-<description>`

**Allowed Types:**
- `issue`, `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`, `hotfix`
- Special: `release/<version>` (no issue number required)

**Examples:**
```bash
feat/42-user-authentication
fix/123-handle-null-values
docs/41-update-guidelines
refactor/55-simplify-parser
```

**Create and link branch:**
```bash
# Option 1: GitHub CLI (auto-links)
gh issue develop <issue-number> --checkout

# Option 2: Manual (include issue number in name)
git checkout -b feat/42-add-feature
```

**Branch naming is enforced by pre-commit hooks.**

#### 3. **Commit:** Use Conventional Commits

**Format:** `<type>: <subject>`

Use `doit commit` for interactive commit creation with commitizen.

**Enforced by:**
- Pre-commit hooks (locally)
- CI checks (on PR)

#### 4. **Pull Request:** Submit PR from Branch to `main`

**Create PR using doit (recommended):**
```bash
# Interactive: Opens $EDITOR with template
doit pr

# Non-interactive: For AI agents or scripts
doit pr --title="feat: add export" --body-file=pr.md
doit pr --title="feat: add export" --body="## Description\n..."

# Create as draft
doit pr --draft
```

Features:
- Auto-detects issue number from branch name (e.g., `feat/42-description` → `Addresses #42`)
- Pre-fills the PR template with detected issue
- Validates required fields before creating

**PR Title:**
- Must follow conventional commit format: `<type>: <subject>`
- PR title becomes the merge commit message
- Examples: ✅ `feat: add validators`, ❌ `Add validators`

**PR Description Requirements (enforced by CI):**
- Minimum 50 characters
- Reference related issue: "Addresses #42"
- Describe what changed and why
- Include testing information

#### 5. **Merge:** Format Must Include PR and Issue Numbers

**Merge commit format:**
```
<type>: <subject> (merges PR #XX, addresses #YY)
```

**Examples - Correct:**
```
feat: add user authentication (merges PR #18, addresses #42)
fix: handle None values (merges PR #23, addresses #19)
docs: update installation guide (merges PR #29, addresses #25)
```

**Examples - Incorrect:**
```
❌ Merge pull request #18 from user/branch
❌ feat: Add Feature (capitalized subject)
❌ added feature (missing type)
❌ feat: add feature (missing PR reference)
```

**Using `doit pr_merge`:**

The `doit pr_merge` task enforces this format automatically:

```bash
# Merge PR for current branch
doit pr_merge

# Merge specific PR
doit pr_merge --pr=123

# Keep branch after merge (default deletes it)
doit pr_merge --delete-branch=false
```

The task:
- Fetches PR title, number, and linked issues from GitHub
- Validates PR title follows conventional commit format
- Constructs the merge commit subject automatically
- Uses squash merge with the formatted subject

### Architecture Decision Records (ADRs)

When your PR implements or relates to an architectural decision, update the relevant ADR:

**When to update an ADR:**
- Your PR implements a decision documented in an existing ADR
- Your PR changes behavior described in an ADR
- Your issue is related to an architectural decision

**How to update:**
1. Find related ADRs in `docs/decisions/`
2. Add your issue to the "Related Issues" section: `- Issue #XX: Brief description`
3. Add links to implementation docs in "Related Documentation" section
4. Include the ADR update in your PR

**When to create a new ADR:**
- Introducing a new tool, framework, or library
- Changing development workflow or processes
- Making decisions that affect project architecture
- Decisions that future contributors should understand

**Which issue types may need ADRs:**
- **Feature**: Often - new features may introduce architectural decisions
- **Refactor**: Often - refactoring may change architecture or patterns
- **Bug**: Rarely - only if the fix reveals a significant design decision
- **Doc/Chore**: No - documentation and maintenance don't need ADRs

**The `needs-adr` label:**
Use the `needs-adr` label on issues that require an ADR. This signals that:
- The issue involves an architectural decision
- An ADR should be created as part of the PR
- The PR should not be merged without the ADR

**Create a new ADR:**
```bash
# Interactive (opens editor)
doit adr --title="Use Redis for caching"

# Non-interactive (for scripts/AI)
doit adr --title="Use Redis" --body-file=adr.md
doit adr --title="Use Redis" --body="## Status\nAccepted\n..."
```

**ADR requirements:**
- Every ADR must link to the GitHub Issues where the decision was discussed
- Every ADR must link to documentation in `docs/` that describes the implementation
- If no documentation exists, create it as part of the PR

ADRs provide context for why decisions were made, helping future contributors understand the project's evolution.

### Edge Cases

**Issue needs to be split during work:**
- Create new issues for discovered separate concerns
- Update original issue to reference the new issues
- Continue work on current branch or create new branches

**Issue is obsolete or duplicate:**
- Comment explaining why it's obsolete/duplicate
- Link to the duplicate issue if applicable
- Close with appropriate label (duplicate, wontfix)
- Delete branch if no work committed

**Work spans multiple sessions:**
- Update issue with progress comments
- Document decisions and approaches tried
- Push commits regularly
- Keep PR description updated

### Keeping Your Fork Updated

```bash
# Add upstream remote (one-time setup)
git remote add upstream https://github.com/original-owner/infrafoundry.git

# Fetch and merge upstream changes
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

## Questions?

If you have questions:

1. Check the [README.md](README.md) and [AGENTS.md](AGENTS.md)
2. Search existing [Issues](https://github.com/endavis/infrafoundry/issues)
3. Open a new issue with the "question" label
4. Join our discussions (if available)

## Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort!

---

For more detailed information, see:
- [README.md](../README.md) - Project overview
- [AGENTS.md](../AGENTS.md) - Development guide for AI agents
- [Architecture Decision Records](../docs/decisions/README.md) - Documented architectural decisions
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community guidelines
- [SECURITY.md](SECURITY.md) - Security policy
