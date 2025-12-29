# InfraFoundry – AI Agent Unified Instructions

## Overview
InfraFoundry generates Terraform `.tf` files and Ansible playbooks from YAML configurations, then optionally orchestrates their execution. It uses a strict separation between the framework repository and user configuration repositories. Providers, runners, validators, and policies are fully pluggable. State and secret management are robust and event-driven orchestration is used throughout.

## Repository & Architecture
- **Framework Repo:** Core code, provider plugins, templates
- **Config Repo:** User infrastructure configs, secrets (separate)
- **Managers:** Inherit from `BaseManager` or `PathBasedManager` for logging, error handling, and path utilities
- **Provider Mixins:** Use `TemplateRendererMixin`, `ResourceGrouperMixin` for Jinja2 templating and resource grouping
- **Provider 3-Layer Stack:** Provider → Component Manager → Service Layer for complex API workflows
- **Pluggable Runners:** Terraform, Ansible, etc., extend `BaseRunner`
- **Event System:** Pub/sub hooks for orchestration lifecycle (e.g., DRIFT_*, POLICY_*, PLAN/APPLY events)

## State, Data Flow, and Artifacts
- **Terraform State:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (local by default; remote backends configurable)
- **InfraFoundry State DB:** `~/.infrafoundry/state.db` (SQLite) or PostgreSQL via `INFRAFOUNDRY_STATE_BACKEND` / `INFRAFOUNDRY_STATE_CONNECTION`, tracking deployments, resources, dependencies, and events
- **Generated Configs:** `generated/{env}/{terraform|ansible}/{provider}/` (reproducible, git-ignored)
- **Data Flow:** YAML configs → ConfigManager → Orchestrator → Providers/Templates → generated files → optional execution

## Configuration & Secrets
- Two-repo approach: framework repo (this) + configuration repo set via `INFRAFOUNDRY_CONFIG_REPO` or `infra --config-dir`. CLI precedence: explicit flag > env var > local `./envs`.
- **Config Formats:**
  - Provider-centric: `envs/{env}/{provider}/{resource_type}.yaml`
  - Resource-centric: `envs/{env}/resources/*.yaml` (recommended for multi-provider)
  - Both formats may coexist; providers are auto-discovered
- **Secrets:** Managed with SOPS + age, per-environment keys; decrypted data shared with Terraform `.tfvars` and Ansible vars
- **Environment Variables:** Use `INFRAFOUNDRY_*` for framework, standard names for providers

## Development & Testing
- **Use `uv` for Python package management**
- **Run tests:** `doit test` or `uv run pytest`
- **Format/lint:** `doit format`, `doit lint`
- **Coverage:** `doit coverage`
- **Add dependencies:** `uv pip install <package>`
- **Temporary files:** Use `tmp/` (git-ignored); keep root directory clean

## CLI & Operations
- Key commands (`infra` via `uv run infra …` or equivalent):
  - `infra envs` – list configured environments.
  - `infra plan --env <name>` – generate files only (use `--dry-run` when applicable).
  - `infra apply --env <name>` – generate and execute Terraform/Ansible.
  - `infra destroy --env <name>` – tear down infrastructure.
  - `infra drift --env <name>` – detect drift.
  - `infra history --env <name>` – inspect past deployments.
  - `infra secrets <init|encrypt|decrypt>` – manage SOPS secrets.
- Generated artifacts should be reviewed (and optionally validated with native Terraform/Ansible tools) from the `generated/` directory hierarchy.

## Code Style & Conventions

### Python Style
- Python 3.12+ type hints with modern syntax: `list[str]`, `dict[str, Any]`, `X | None`
- `@override` decorator on all abstract method implementations
- Black formatting, ruff linting, max line length 100
- Snake_case for Python, kebab-case for YAML resource names
- Use singular resource type names

### Import Organization
Organize imports in this order (separated by blank lines):
1. **Standard library imports** (alphabetical)
2. **Third-party imports** (alphabetical)
3. **Local application imports** (alphabetical)

```python
# Standard library
import os
from pathlib import Path
from typing import Any

# Third-party
import click
from jinja2 import Environment

# Local
from infrafoundry.core.base_manager import BaseManager
from infrafoundry.providers.base_provider import BaseProvider
```

### Docstring Requirements
- **Public APIs** (classes, functions, methods): Required
- **Private functions/methods** (prefixed with `_`): Optional, use when complex
- **Module-level docstrings**: Required for all modules
- **Format**: Google-style docstrings
- **Content**: Brief description, Args, Returns, Raises (when applicable)

```python
def generate_terraform(self, resources: list[dict[str, Any]]) -> Path:
    """Generate Terraform configuration from resource definitions.

    Args:
        resources: List of resource definitions to convert

    Returns:
        Path to the generated Terraform file

    Raises:
        ValidationError: If resource validation fails
        TemplateError: If template rendering fails
    """
```

## Coding Standards & Best Practices
- **Read-before-edit**: inspect files before modifying; maintain backward-compatible public APIs.
- Follow BaseManager/PathBasedManager, provider mixins, and 3-layer architecture conventions—new managers/providers must integrate cleanly.
- Python style: full type hints with modern syntax (`list[str]`, `X | None`), `@override` on abstract implementations, max line 100, Google-style docstrings.
- Error handling: raise specific exceptions with contextual logging; never catch `KeyboardInterrupt`/`SystemExit`. Prefer early returns over deep nesting.
- Avoid duplication in validators/templates; consider mixins or helpers before copying logic.
- Do not modify public CLI signatures, BaseManager APIs, provider plugin contracts, state schema (introduce migrations instead), or event enums except additive changes.

## Common Patterns

### Manager Pattern
- **BaseManager**: Base class for all managers; provides logging, error handling
- **PathBasedManager**: Extends BaseManager with path utilities for file operations
- Use managers for orchestration logic, not business logic

### Provider Pattern
- **TemplateRendererMixin**: Jinja2 template rendering for providers
- **ResourceGrouperMixin**: Group resources by type or dependency
- **3-Layer Architecture**: Provider → Component Manager → Service Layer
  - Provider: High-level interface, config parsing
  - Component Manager: Resource-specific logic
  - Service Layer: API/direct interaction

### Pluggable Runners
- Extend `BaseRunner` for new execution engines (Terraform, Ansible, PyInfra)
- Implement required methods: `plan()`, `apply()`, `destroy()`
- Use dependency injection for testability

### Event-Driven Orchestration
- Subscribe to events: `DRIFT_DETECTED`, `POLICY_VIOLATED`, `PLAN_COMPLETE`, `APPLY_COMPLETE`
- Publish events when state changes
- Keep event handlers focused and side-effect free

## Common Pitfalls

### Anti-Patterns to Avoid
- **God Classes**: Don't put all logic in Orchestrator; use managers and providers
- **Tight Coupling**: Always use dependency injection, avoid importing concrete implementations
- **Silent Failures**: Always log errors and raise exceptions with context
- **Mutable Defaults**: Never use mutable default arguments (`def foo(items=[])` ❌)
- **String Concatenation for Paths**: Use `Path` objects, not string concatenation
- **Blocking I/O in Loops**: Batch operations when possible
- **Ignoring Type Hints**: Type hints are enforced by mypy in CI

### Security Pitfalls
- **Never log secrets**: Scrub sensitive data before logging
- **Command Injection**: Always use subprocess with list args, not shell=True
- **Path Traversal**: Validate all user-provided paths
- **YAML Unsafe Loading**: Always use `yaml.safe_load()`, never `yaml.load()`

### State Management Pitfalls
- **Race Conditions**: Use state locking for concurrent operations
- **Stale State**: Always refresh state before operations
- **Lost State**: Never delete generated configs without destroy first

## Development Workflow

**Rule:** All *code* changes must originate from a GitHub Issue. Documentation updates are exempt from this rule.

### Issue-Driven Development Flow

1. **Issue:** Ensure a GitHub Issue exists for the code task (e.g., "Add PyInfra runner support").
   - Use YAML issue forms to create structured, validated issues
   - Required fields ensure all necessary information is captured
   - Auto-labeling helps with project management and triage

2. **Branch:** Create a branch linked to the issue
   - Format: `issue/<number>-<short-desc>`, `feat/<number>-<desc>`, or `fix/<number>-<desc>`
   - Examples:
     - `issue/42-add-cloudflare-provider`
     - `feat/42-cloudflare-provider`
     - `fix/123-handle-null-values`
   - Branch naming is enforced by pre-commit hooks

3. **Commit:** Use Conventional Commits format for all commits
   - Format: `<type>: <subject>`
   - Enforced by pre-commit hooks locally and PR checks in CI
   - Use `uv run cz commit` for interactive commit message creation (if commitizen is installed)

4. **Pull Request:** Submit a PR from your branch to `main` (or `develop` if active)
   - Reference the issue in PR description (e.g., "Closes #42")
   - PR title must follow conventional commit format
   - Automated checks validate:
     - PR title format
     - Issue link presence (except docs-only PRs)
     - PR description completeness
     - Breaking change documentation

5. **PR Merge:** When merging, ensure the merge commit follows the format:
   - `<type>: <subject> (merges PR #XX, closes #YY)` - when PR has associated issue
   - `<type>: <subject> (merges PR #XX)` - when PR has no issue (docs-only)

**Examples - Correct Merge Commit Format:**
```
feat: add PyInfra runner support and configurable execution order (merges PR #18, closes #42)
fix: handle None values in OPNsense provider (merges PR #23, closes #19)
docs: update provider implementation guide (merges PR #29)
refactor: extract common validation logic (merges PR #31, closes #28)
```

**Examples - Incorrect Format:**
```
❌ Merge pull request #18 from endavis/feat/pyinfra-support
❌ feat: Add PyInfra Support (capitalized subject)
❌ added pyinfra support (missing type)
❌ feat: add pyinfra support (missing PR reference)
```

### Why Issue-Driven Development?

- **Traceability:** Every code change is linked to a documented need
- **Context:** Issues capture the "why" behind changes
- **Planning:** Better project management and prioritization
- **History:** Searchable record of decisions and rationale
- **Collaboration:** Clear communication about work in progress

## Commit Guidelines

### Commit Message Format
Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <subject>

[optional body]

[optional footer]
```

**Commit Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring without behavior change
- `docs`: Documentation updates
- `test`: Adding or updating tests
- `chore`: Dependency updates, tooling changes
- `ci`: CI/CD configuration changes
- `perf`: Performance improvements

**Rules:**
- Subject must be lowercase, concise (no period at end)
- Use imperative mood ("add feature" not "added feature")
- Separate concerns: one commit per logical change
- Write clear, descriptive messages

**Examples:**
```
feat: add support for CloudFlare DNS provider

fix: handle None values in OPNsense interface parsing

refactor: extract common provider validation logic

docs: update provider implementation guide with new patterns

test: add tests for edge cases in state manager

chore: update dependencies to latest versions
```

### Breaking Changes Policy

**What Constitutes a Breaking Change:**
- Changes to public function/method signatures
- Removal of public functions, classes, or modules
- Changes to CLI command syntax or options
- Changes to configuration file formats
- Changes to default behavior that affects existing code
- Changes to exception types or error handling
- Removal of deprecated features

**How to Handle Breaking Changes:**

1. **Document in Commit Message:**
   ```
   refactor: change provider API to use async/await

   Migrate to async for better concurrency handling.

   BREAKING CHANGE: All provider methods are now async and must be awaited.
   Update custom providers to use async def for generate(), validate(), etc.
   See docs/migration.md for detailed migration guide.
   ```

2. **Document in PR Description:**
   - Add "BREAKING CHANGE" section to PR description
   - Explain what changed and why
   - Provide migration guide with before/after examples
   - List affected APIs or features

3. **Update CHANGELOG.md:**
   - Add breaking changes to "Breaking Changes" section
   - Include migration instructions
   - Provide code examples showing the change

4. **Version Bump:**
   - Breaking changes require a major version bump (e.g., 1.x.x → 2.0.0)
   - Follow semantic versioning principles

5. **Consider Deprecation Period:**
   - For widely-used features, consider deprecating first (with warnings)
   - Remove in next major version
   - Gives users time to migrate

**Automated Detection:**
- PR checks will scan for potential breaking changes
- Comments will be added to PRs highlighting concerns
- CI will fail if breaking changes are not documented

## Issue Creation Guidelines

### Issue Title Format
Use clear, actionable titles with type prefix matching conventional commits:

```
<type>: <brief description>
```

**Examples:**
- `feat: add support for CloudFlare DNS provider`
- `bug: infrafoundry crashes when processing OPNsense config`
- `refactor: extract duplicate provider validation logic`
- `docs: add examples for custom provider implementation`

### Issue Templates

The project uses GitHub YAML issue forms with required fields:

**Bug Reports (bug_report.yml):**
- Required: title, description, steps to reproduce, expected/actual behavior
- Dropdowns: Python version, OS, priority (CRITICAL/HIGH/MEDIUM/LOW)
- Optional: error output, additional context, possible solution
- Auto-labels: `bug`, `needs-triage`

**Feature Requests (feature_request.yml):**
- Required: title, problem statement, proposed solution, use cases
- Dropdowns: complexity (1-10 scale), priority
- Optional: alternatives, implementation ideas, benefits
- Checkbox: breaking changes flag
- Auto-labels: `enhancement`, `needs-triage`

**Refactor Requests (refactor.yml):**
- Required: title, current situation, proposed improvement, technical debt impact
- Dropdowns: complexity, priority
- Optional: affected areas, benefits
- Checkboxes: breaking changes, test updates, doc updates, API impact
- Auto-labels: `refactor`, `needs-triage`

### When to Create an Issue

**Always create an issue for:**
- New features or enhancements
- Bug fixes
- Refactoring work
- Performance improvements
- Security updates

**Optional for:**
- Documentation-only changes (can PR directly)
- Typo fixes in comments
- Minor README updates

**Before starting work:**
- Check if an issue already exists
- Create the issue first, then the branch
- Link the branch to the issue number

### Issue Best Practices

- **Be specific:** Clear, concise descriptions
- **Be complete:** Fill all required fields
- **Add context:** Include examples, screenshots, or code snippets
- **Estimate complexity:** Helps with prioritization and planning
- **Set priority:** CRITICAL for blockers, HIGH for important work, MEDIUM/LOW otherwise
- **Link related issues:** Reference related issues or PRs
- **Update as needed:** Add information as you learn more

## Pull Request Guidelines

### PR Title Format
Same as commit messages: `<type>: <subject>`

**The PR title becomes the merge commit message, so make it clear and descriptive.**

**Examples:**
- ✅ `feat: add CloudFlare DNS provider`
- ✅ `fix: handle None values in OPNsense interface parsing`
- ✅ `docs: update provider implementation guide`
- ❌ `Add CloudFlare provider` (missing type)
- ❌ `Feat: Add CloudFlare Provider` (capitalization wrong)

### PR Description Requirements

**Minimum requirements (enforced by CI):**
- At least 50 characters
- Include reference to related issue (except docs-only PRs)
- Describe what changed and why
- Include testing information

**Complete PR template includes:**
- **Summary:** 2-3 sentence overview of changes
- **Changes:** Bullet list of specific changes with file paths
- **Related Issues:** "Closes #123" or "Fixes #123"
- **Testing:** How changes were tested
- **Breaking Changes:** Document any breaking changes
- **Documentation:** List doc updates

### Automated PR Checks

All PRs are automatically validated for:

✅ **PR Title Format** - Must follow conventional commits
✅ **Issue Link** - Must reference an issue (code changes only)
✅ **Description Length** - Minimum 50 characters
✅ **Breaking Changes** - Detects and requires documentation
✅ **Tests** - All tests must pass
✅ **Coverage** - Must maintain ≥69% coverage
✅ **Linting** - Ruff checks must pass
✅ **Type Checking** - Mypy must pass
✅ **Format** - Code must be formatted with ruff

**Docs-only PRs are exempt from issue linking requirement.**

### Code Review Checklist

**Before submitting:**
- [ ] Created and linked GitHub Issue (for code changes)
- [ ] Branch name follows convention (`feat/123-description`)
- [ ] Self-reviewed code
- [ ] All CI checks passing locally (`doit check coverage`)
- [ ] Tests added/updated with ≥69% coverage
- [ ] Documentation updated (README, docstrings, guides)
- [ ] CHANGELOG.md updated (for notable changes)
- [ ] Breaking changes documented (if applicable)

**Reviewers verify:**
- [ ] Code follows project conventions (style, patterns, architecture)
- [ ] Tests adequate and passing
- [ ] No security vulnerabilities (injection, secrets, path traversal)
- [ ] Error handling appropriate with clear messages
- [ ] Documentation clear and accurate
- [ ] Breaking changes properly documented
- [ ] Issue is fully addressed

### Merge Process

1. **All CI checks must pass** - No exceptions
2. **At least one approval required** - From code owner or maintainer
3. **Merge commit format** - Must include PR and issue numbers:
   - `<type>: <subject> (merges PR #XX, closes #YY)`
   - PR title is automatically used as merge commit message
4. **Squash and merge** - Preferred for clean history (multiple commits → one)
5. **Delete branch** - After successful merge

## CI/CD Requirements

### Required Checks (must pass before merge)
- **Tests**: All pytest tests pass, ≥69% coverage maintained
- **Lint**: ruff checks pass with no errors
- **Type checking**: mypy passes with no type errors
- **Format**: ruff formatting applied
- **Pre-commit hooks**: All hooks pass

### Running CI Checks Locally
```bash
# Run all checks
doit check coverage

# Individual checks
doit lint
doit format
doit coverage
```

### CI Workflow
1. Push to branch triggers GitHub Actions
2. All checks must pass (tests, lint, type checking)
3. Coverage report posted to PR
4. Reviewer approval required
5. Merge to main triggers deployment (if applicable)

## AI Agent Guidelines

### When to Ask for User Input
AI agents (like Claude) should ask the user when:
- **Ambiguous requirements**: Multiple valid implementation approaches exist
- **Architectural decisions**: Choosing between patterns or libraries
- **Breaking changes**: User impact needs to be understood
- **Missing information**: Config values, credentials, or preferences needed
- **Trade-offs**: Performance vs. simplicity, etc.
- **Scope clarification**: Feature boundaries unclear

### When to Proceed Autonomously
Agents can proceed without asking when:
- **Clear conventions exist**: Follow existing patterns in codebase
- **Obvious fixes**: Clear bugs with single correct solution
- **Documentation tasks**: Adding docstrings, comments, README updates
- **Refactoring**: Improving code structure without behavior change
- **Tests**: Adding missing test coverage for existing code

### Best Practices for AI Agents
- **Read before editing**: Always read files before modifying them
- **Follow patterns**: Match existing code style and patterns
- **Run tests**: Execute tests after changes to verify correctness
- **Commit incrementally**: Make focused commits, not large batch changes
- **Explain changes**: Provide clear commit messages and PR descriptions
- **Check CI**: Ensure all CI checks pass before considering work complete
- **Link issues**: Always reference related issue numbers

## Testing Expectations
- Maintain ≥69% coverage
- Add/update tests when refactoring or adding features; use fixtures and mocks
- Typical commands:
  - `uv run pytest`
  - `uv run pytest --cov=src/infrafoundry/<module>.py tests/`

## Troubleshooting
- Use CLI commands to check config loading, state, and secrets
- Inspect files with `cat -pp` or `batcat -pp` for consistent output

## Help & Resources
- **Documentation Index:** [Table of Contents](docs/TABLE_OF_CONTENTS.md)
- **Getting Started:** `docs/getting-started/`
- **Configuration:** `docs/configuration/`
- **Architecture:** `docs/architecture/`
- **Development:** `docs/development/`
- **Example Configs:** `example-config/`
- **Roadmap & TODOs:** [docs/TODO.md](docs/TODO.md)

---
This file unifies essential agent instructions for InfraFoundry. For coding/development specifics, see dedicated documentation files.
