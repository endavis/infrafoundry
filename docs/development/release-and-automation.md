# Release Automation & Security

This guide covers the automated versioning, release management, governance validation, and security tooling available in InfraFoundry.

## Table of Contents
- [Automated Versioning](#automated-versioning)
- [Release Management](#release-management)
- [Release Notes](#release-notes)
- [Security & Quality Tasks](#security--quality-tasks)
- [SBOM Generation](#sbom-generation)
- [Governance Validation](#governance-validation)
- [Environment Configuration](#environment-configuration)

## Automated Versioning

InfraFoundry uses **hatch-vcs** for automated, git tag-based versioning. Version numbers are derived from git tags - no manual edits to `pyproject.toml` or `_version.py` are required.

### How It Works

- **Git Tags**: Version source of truth (e.g., `v0.1.0`, `v1.0.0`)
- **Automatic Generation**: The `_version.py` file is auto-generated during builds
- **Dynamic Versioning**: Version is set to `dynamic = ["version"]` in `pyproject.toml`

### Version Formats

```bash
# Production releases
v1.0.0         # Major release
v1.1.0         # Minor release (new features)
v1.1.1         # Patch release (bug fixes)

# Pre-releases (for TestPyPI)
v1.0.0-alpha.1   # Alpha release
v1.0.0-beta.1    # Beta release
v1.0.0-rc.1      # Release candidate
```

### Checking Current Version

```bash
# From installed package
uv run python -c "from importlib.metadata import version; print(version('infrafoundry'))"

# Development version (shows git-based dev version)
# Example output: 0.0.1.dev519+g295cc7b6b.d20251229
```

## Release Management

InfraFoundry provides two automated release workflows powered by **commitizen**:

### 1. Production Release (`doit release`)

Creates a stable release for PyPI with full governance validation.

```bash
uv run doit release
```

**What it does:**
1. ✅ Verifies you're on the `main` branch
2. ✅ Checks for uncommitted changes
3. ✅ Pulls latest changes from remote
4. ✅ **Runs governance validations** (merge commit format, issue links)
5. ✅ Runs all quality checks (`doit check`)
6. ✅ Uses commitizen to:
   - Analyze conventional commits since last tag
   - Determine next version number (MAJOR, MINOR, PATCH)
   - Update CHANGELOG.md (merges pre-release entries)
   - Create git tag
7. ✅ Pushes commits and tags to GitHub
8. ✅ Triggers CI/CD to build and publish to PyPI

**Example Output:**
```
======================================================================
Starting automated release process...
======================================================================

Pulling latest changes...
✓ Git pull successful.

Running governance validations...

Validating merge commit format...
✓ All merge commits follow required format.

Validating issue links in commits...
✓ All non-docs commits reference issues.

✓ Governance validations complete.

Running all pre-release checks...
✓ All checks passed.

Bumping version and generating CHANGELOG with commitizen...
✓ Version bumped and CHANGELOG updated (merged pre-releases).

Pushing commits and tags to GitHub...
✓ Pushed new commits and tags to GitHub.

======================================================================
✓ Automated release 1.0.0 complete!
======================================================================

Next steps:
1. Monitor GitHub Actions for build and publish.
2. Check PyPI: https://pypi.org/project/infrafoundry/
3. Verify the updated CHANGELOG.md in the repository.
```

### 2. Pre-release (`doit release_dev`)

Creates alpha/beta/rc releases for TestPyPI testing.

```bash
# Create alpha pre-release (default)
uv run doit release_dev

# Create beta pre-release
uv run doit release_dev --type=beta

# Create release candidate
uv run doit release_dev --type=rc
```

**What it does:**
1. ✅ Verifies you're on the `main` branch (with warning option to continue)
2. ✅ Checks for uncommitted changes
3. ✅ Pulls latest changes
4. ✅ Runs all quality checks
5. ✅ Uses commitizen to create pre-release tag
6. ✅ Pushes tag to trigger TestPyPI publish

**No governance validation** - this is for testing only.

### Release Workflow Best Practices

```bash
# 1. Develop features with conventional commits
git commit -m "feat: add new provider support"
git commit -m "fix: resolve configuration parsing issue"

# 2. Create alpha for testing
uv run doit release_dev --type=alpha
# --> Creates v0.2.0-alpha.1, publishes to TestPyPI

# 3. Test the alpha release
pip install --index-url https://test.pypi.org/simple/ infrafoundry==0.2.0a1

# 4. Fix issues, create beta
git commit -m "fix: address alpha feedback"
uv run doit release_dev --type=beta
# --> Creates v0.2.0-beta.1

# 5. Final testing, then production release
uv run doit release
# --> Creates v0.2.0, updates CHANGELOG, publishes to PyPI
```

## Release Notes

Release notes are automatically generated from merged pull requests when a GitHub release is created. The release workflow creates a GitHub release with auto-generated notes after publishing to PyPI.

### How It Works

1. When a version tag (e.g., `v1.0.0`) is pushed, the release workflow runs
2. After the package is published to PyPI, the `github-release` job creates a GitHub release
3. GitHub generates release notes by categorizing merged PRs since the last release
4. SBOM files are attached to the release as downloadable assets

### Category Configuration

PR labels and conventional commit prefixes are mapped to release note sections in `.github/release.yml`:

| Section | Labels |
|---------|--------|
| **Breaking Changes** | `breaking` |
| **New Features** | `enhancement`, `feat` |
| **Bug Fixes** | `bug`, `fix` |
| **Documentation** | `documentation`, `docs` |
| **Performance** | `performance`, `perf` |
| **Other Changes** | Everything else |

PRs with the `dependencies` or `needs-triage` labels are excluded from release notes.

## Security & Quality Tasks

InfraFoundry includes comprehensive security scanning and code quality tools.

### Security Tasks

```bash
# Run dependency vulnerability audit (pip-audit)
uv run doit audit

# Run static security analysis (bandit)
uv run doit security

# Check all dependency licenses
uv run doit licenses
```

**Installing Security Tools:**
```bash
# Security tools are optional to keep dev environment lean
uv sync --extra security
```

### Quality Tasks

```bash
# Check spelling in code and docs (codespell)
uv run doit spell_check

# Format pyproject.toml (pyproject-fmt)
uv run doit fmt_pyproject
```

### Task Details

#### `doit audit`
- **Tool**: pip-audit
- **Purpose**: Scans dependencies for known CVE vulnerabilities
- **When**: Run before releases, periodically in CI
- **Example**:
  ```bash
  $ uv run doit audit
  No known vulnerabilities found
  ```

#### `doit security`
- **Tool**: bandit
- **Purpose**: Static security analysis of Python code
- **Configuration**: See `[tool.bandit]` in `pyproject.toml`
- **Excludes**: tests/, tmp/, .venv/
- **Example**:
  ```bash
  $ uv run doit security
  [main]  INFO    profile include tests: None
  [main]  INFO    profile exclude tests: None
  [main]  INFO    running on Python 3.12.0
  Run started
  ...
  Code scanned:
          Total lines of code: 5234
          Total lines skipped: 123
  ```

#### `doit spell_check`
- **Tool**: codespell
- **Purpose**: Catches typos in code, tests, docs, README
- **Configuration**: See `[tool.codespell]` in `pyproject.toml`
- **Example**:
  ```bash
  $ uv run doit spell_check
  docs/README.md:42: receive ==> receive
  ```

#### `doit fmt_pyproject`
- **Tool**: pyproject-fmt
- **Purpose**: Formats and validates pyproject.toml structure
- **Auto-fixes**: Sorts dependencies, standardizes formatting
- **Example**:
  ```bash
  $ uv run doit fmt_pyproject
  Formatted pyproject.toml
  ```

#### `doit licenses`
- **Tool**: pip-licenses
- **Purpose**: Lists all dependency licenses for compliance
- **Output**: Markdown table by license type
- **Example**:
  ```bash
  $ uv run doit licenses
  | Name         | Version | License     |
  |--------------|---------|-------------|
  | click        | 8.1.7   | BSD-3-Clause|
  | pydantic     | 2.5.0   | MIT         |
  ```

#### `doit sbom`
- **Tool**: cyclonedx-py
- **Purpose**: Generates a Software Bill of Materials (SBOM) in CycloneDX format
- **Output**: `tmp/sbom.json` (JSON) and `tmp/sbom.xml` (XML)
- **Example**:
  ```bash
  $ uv run doit sbom
  # Generates tmp/sbom.json and tmp/sbom.xml
  ```

### SBOM Generation

A **Software Bill of Materials (SBOM)** is a machine-readable inventory of all software components and dependencies in a project. SBOMs are increasingly required for regulatory compliance and are essential for security auditing and supply chain transparency.

#### Why SBOM Matters

- **Compliance**: Many organizations and government agencies require SBOMs for software procurement
- **Security Auditing**: Enables automated vulnerability scanning across all dependencies
- **Supply Chain Transparency**: Provides a complete picture of third-party components
- **Incident Response**: Quickly determine if a newly discovered vulnerability affects your software

#### Local Usage

```bash
# Install security extras (if not already installed)
uv sync --extra security

# Generate SBOM files
doit sbom
```

This produces two files in the `tmp/` directory:

- `tmp/sbom.json` -- CycloneDX JSON format
- `tmp/sbom.xml` -- CycloneDX XML format

#### Release Integration

SBOMs are automatically generated and attached to every GitHub release:

1. During the **build** job, `cyclonedx-py` generates both JSON and XML SBOMs
2. The SBOM files are included in the `dist/` artifact alongside wheel and sdist packages
3. After publishing to PyPI, the **github-release** job creates a GitHub release with auto-generated notes and attaches the SBOMs as release assets

#### Using SBOMs for Vulnerability Scanning

```bash
# Using grype (https://github.com/anchore/grype)
grype sbom:tmp/sbom.json

# Using trivy (https://github.com/aquasecurity/trivy)
trivy sbom tmp/sbom.json

# Using osv-scanner (https://github.com/google/osv-scanner)
osv-scanner --sbom=tmp/sbom.json
```

### Integrating into CI

Add security checks to your CI pipeline:

```yaml
# .github/workflows/security.yml
name: Security Scan

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v1
      - name: Run security audit
        run: uv run doit audit
      - name: Run bandit scan
        run: uv run doit security
```

## Governance Validation

InfraFoundry enforces governance rules to ensure code quality and traceability.

### Validation Functions

#### 1. Merge Commit Format Validation

**Purpose**: Ensures all merge commits follow conventional format with PR/issue links.

**Required Format**:
```
<type>: <subject> (merges PR #XX, addresses #YY)
<type>: <subject> (merges PR #XX)
```

**Examples**:
```
✅ feat: add CloudFlare provider (merges PR #102, addresses #99)
✅ fix: resolve state parsing issue (merges PR #103, addresses #100)
✅ docs: update installation guide (merges PR #104)

❌ Add new feature                    # Missing type
❌ feat: add feature                  # Missing PR reference
❌ feat: add feature (PR #102)        # Wrong format
```

**Valid Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `perf`

**When It Runs**: During `doit release` (blocks on failure)

#### 2. Issue Link Validation

**Purpose**: Encourages linking commits to issues for better tracking.

**Checks**: All non-docs, non-merge commits should reference an issue (`#123`)

**Examples**:
```
✅ feat: add new provider (#99)
✅ fix: resolve bug addresses #100
✅ docs: update README                # Docs exempt

⚠️ feat: add new feature             # Warning only
```

**When It Runs**: During `doit release` (warning only, doesn't block)

### Pre-commit Hooks

The repository includes pre-commit hooks that run on every commit:

```yaml
# .pre-commit-config.yaml
hooks:
  - ruff-format: Auto-format Python code
  - ruff-check: Lint and auto-fix issues
  - mypy: Type checking (strict mode)
  - tests: Run test suite
  - check-branch-name: Enforce branch naming convention
```

**Branch Naming Convention**:
```
✅ issue/99-hatch-vcs-versioning
✅ feat/102-add-provider
✅ fix/103-resolve-bug
✅ docs/installation-guide
✅ hotfix/critical-security-fix
✅ release/v1.0.0
✅ main
✅ develop

❌ my-feature-branch
❌ fix-bug
❌ random-name
```

### Conventional Commits

All commits should follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

**Format**:
```
<type>[(scope)]: <subject>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature (triggers MINOR version bump)
- `fix`: Bug fix (triggers PATCH version bump)
- `refactor`: Code refactoring (triggers PATCH version bump)
- `perf`: Performance improvement (triggers PATCH version bump)
- `docs`: Documentation only
- `test`: Adding/updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

**Breaking Changes** (triggers MAJOR version bump):
```
feat!: redesign provider API

BREAKING CHANGE: Provider interface has changed. See migration guide.
```

**Examples**:
```bash
# Feature commit
git commit -m "feat: add CloudFlare provider support (#99)"

# Bug fix commit
git commit -m "fix: resolve state file parsing issue (#100)"

# Documentation commit
git commit -m "docs: add release automation guide"

# Breaking change
git commit -m "feat!: redesign plugin system

BREAKING CHANGE: Plugin registration API has changed.
Plugins must now implement the new PluginProtocol interface.
See docs/migration.md for upgrade instructions."
```

## Environment Configuration

### Using direnv (Recommended)

InfraFoundry supports `direnv` for automatic environment management:

```bash
# Install direnv
uv run doit install_direnv

# Hook into your shell (one-time)
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
source ~/.bashrc

# Allow direnv in this directory
direnv allow
```

Once configured, direnv automatically:
- Activates the virtual environment
- Sets cache directories (UV_CACHE_DIR, RUFF_CACHE_DIR, etc.)
- Loads project-specific environment variables
- Creates tmp/ directory structure

### Manual Environment Setup

Without direnv:

```bash
# Activate virtual environment
source .venv/bin/activate

# Set cache directories (optional but recommended)
export UV_CACHE_DIR="$(pwd)/tmp/.uv_cache"
export RUFF_CACHE_DIR="$(pwd)/tmp/.ruff_cache"
export MYPY_CACHE_DIR="$(pwd)/tmp/.mypy_cache"
export COVERAGE_FILE="$(pwd)/tmp/.coverage"

# Create tmp directory
mkdir -p tmp
```

### Cache Management

All cache files are stored in `tmp/` to keep the project root clean:

```
tmp/
├── .uv_cache/         # uv package cache
├── .ruff_cache/       # ruff linter cache
├── .mypy_cache/       # mypy type checker cache
├── .coverage          # coverage data
└── htmlcov/           # coverage HTML reports
```

The `tmp/` directory is gitignored and can be safely deleted:

```bash
# Clean all caches
rm -rf tmp/
doit cleanup  # Also removes build artifacts
```

## Quick Reference

### Common Tasks

```bash
# Development
uv run doit format          # Format code
uv run doit lint            # Run linter
uv run doit type_check      # Run mypy
uv run doit test            # Run tests
uv run doit check           # Run all checks

# Security & Quality
uv run doit audit           # Vulnerability scan
uv run doit security        # Security analysis
uv run doit spell_check     # Spell checking
uv run doit licenses        # License compliance

# Releases
uv run doit release_dev     # Create pre-release (TestPyPI)
uv run doit release         # Create production release (PyPI)
```

### Installation Options

```bash
# Standard development setup
uv sync --dev

# Include security tools
uv sync --dev --extra security

# Include all extras
uv sync --dev --all-extras
```

### Pre-commit

```bash
# Install hooks
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files

# Skip hooks (emergency only)
git commit --no-verify
```

## Troubleshooting

### Release Fails: "Not on main branch"

**Problem**: `doit release` requires main branch

**Solution**:
```bash
git checkout main
git pull
uv run doit release
```

### Release Fails: "Uncommitted changes"

**Problem**: Working directory has uncommitted changes

**Solution**:
```bash
git status
git add .
git commit -m "feat: finalize changes before release"
uv run doit release
```

### Governance Validation Fails

**Problem**: Merge commit format doesn't match required pattern

**Solution**: Update the merge commit message:
```bash
# When merging PR #102 that addresses issue #99
git merge --no-ff feat/99-feature -m "feat: add new feature (merges PR #102, addresses #99)"
```

### Security Task Fails: "pip-audit not installed"

**Problem**: Security tools are optional dependencies

**Solution**:
```bash
uv sync --extra security
uv run doit audit
```

### Spell Check Finds False Positives

**Problem**: Technical terms flagged as typos

**Solution**: Add to ignore list in `pyproject.toml`:
```toml
[tool.codespell]
ignore-words-list = "crate,kubernetes,terraform"
```

## See Also

- [Coding Standards](coding-standards.md) - Code style guidelines
- [CI/CD Testing](ci-cd-testing.md) - Continuous integration setup
- [AGENTS.md](../AGENTS.md) - Issue-driven development workflow
