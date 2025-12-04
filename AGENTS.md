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

## Commit Guidelines

### Commit Message Format
All commits must follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <subject> [(<merges PR #XX, closes #YY>)]
```

**Commit Types:**
- `feat`: New feature or capability
- `fix`: Bug fix
- `refactor`: Code restructuring without behavior change
- `docs`: Documentation updates
- `test`: Adding or updating tests
- `chore`: Dependency updates, tooling changes
- `ci`: CI/CD configuration changes
- `perf`: Performance improvements

**Format Rules:**
- Subject must be lowercase and concise (no period at end)
- Use imperative mood ("add feature" not "added feature")
- Separate commits for refactoring, docs, tests, cleanup, dependencies
- Use markdown formatting for detailed commit bodies (optional)

### PR Merge Commit Format

**When PR has an associated issue:**
```
<type>: <subject> (merges PR #XX, closes #YY)
```

**When PR has no associated issue (legacy/docs-only):**
```
<type>: <subject> (merges PR #XX)
```

**Examples - Correct Format:**
- `feat: add PyInfra runner support and configurable execution order (merges PR #18)`
- `refactor: normalize OPNsense interface data (merges PR #63, closes #56)`
- `docs: comprehensive documentation overhaul with testing report and templates (merges PR #29)`
- `fix: handle None ctx.obj in migrate command (merges PR #64, closes #57)`

**Examples - Incorrect Format:**
- ❌ `Merge pull request #18 from endavis/feat/pyinfra-support`
- ❌ `feat: Add PyInfra Support` (capitalized subject)
- ❌ `added pyinfra support` (wrong tense, missing type)
- ❌ `refactor: normalize OPNsense interface data (#56)` (missing PR reference)

### Development Workflow
**Rule:** All *code* changes must originate from a GitHub Issue. Documentation updates are exempt from this rule.
1.  **Issue:** Ensure a GitHub Issue exists for the code task (e.g., "Refactor BaseRunner").
2.  **Branch:** Create a branch linked to the issue (format: `issue/<number>-<short-desc>` or `feat/<number>-<desc>`).
3.  **Commit:** Use Conventional Commits format as described above.
4.  **Pull Request:** Submit a PR from your branch to `main` (or `dev` if active), referencing the issue (e.g., "Closes #123").
5.  **PR Merge:** When merging, ensure the merge commit follows the format: `<type>: <subject> (merges PR #XX, closes #YY)`

## Pull Request Guidelines

### PR Title Format
Follow the same format as commit messages:
```
<type>: <subject>
```

**Examples:**
- `feat: add PyInfra runner support and configurable execution order`
- `refactor: normalize OPNsense interface data`
- `docs: add comprehensive commit message format guidelines`

### PR Description Template
```markdown
## Summary
Brief overview of changes (2-3 sentences)

## Changes
- Bullet point list of specific changes
- Include file paths for major changes

## Related Issues
Closes #123

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests passing
- [ ] Manual testing completed

## Breaking Changes
List any breaking changes or "None"

## Documentation
- [ ] Updated relevant documentation
- [ ] Added/updated docstrings
```

### Code Review Checklist

**Reviewers should verify:**
- [ ] Code follows project conventions (imports, docstrings, type hints)
- [ ] Tests added/updated with adequate coverage
- [ ] No security vulnerabilities (secrets, injection, path traversal)
- [ ] Error handling with proper logging
- [ ] Breaking changes properly documented
- [ ] CI checks passing (tests, lint, type checking)
- [ ] Commit messages follow format guidelines
- [ ] PR title follows format guidelines
- [ ] Documentation updated

**Authors should:**
- Self-review code before submitting
- Ensure all CI checks pass
- Respond to review comments promptly
- Keep PRs focused (one feature/fix per PR)
- Update PR if main has advanced

## Issue Creation Guidelines

### Issue Title Format
Use clear, actionable titles with type prefix:
```
<type>: <brief description>
```

**Examples:**
- `feat: Add state locking for concurrent operations`
- `bug: Silent failures in policy evaluator`
- `refactor: Extract Kea CRUD duplication into helper`
- `docs: Document provider 3-layer architecture`

### Issue Description Template
```markdown
## Description
Clear description of the issue/feature

## Current Behavior
What currently happens (for bugs/refactors)

## Expected Behavior
What should happen

## Proposed Solution
High-level approach (optional)

## Complexity
Estimated complexity: X/10

## Priority
CRITICAL / HIGH / MEDIUM / LOW

## Related Issues
Links to related issues (if any)
```

### When to Create an Issue
- **Always** for code changes (features, bugs, refactors)
- **Optional** for documentation-only changes
- **Before** starting work on a task
- **Link** to related issues or PRs

## Breaking Changes Policy

### What Constitutes a Breaking Change
- Changes to public CLI signatures
- Changes to BaseManager/BaseProvider APIs
- Changes to state schema without migration
- Changes to event enum values (non-additive)
- Changes to configuration file formats
- Removal of public functions/classes

### How to Handle Breaking Changes
1. **Document in CHANGELOG.md**: List all breaking changes with migration guide
2. **Update version**: Follow semantic versioning (major version bump)
3. **Provide migration path**: Include scripts or clear instructions
4. **Deprecation period**: Deprecate first if possible, remove in next major version
5. **PR description**: Clearly mark as `BREAKING CHANGE` in description
6. **Commit body**: Include `BREAKING CHANGE:` footer in commit message

**Example commit with breaking change:**
```
refactor: change BaseProvider API to use async/await

Migrate all providers to use async/await pattern for better
concurrency handling.

BREAKING CHANGE: BaseProvider.generate() is now async and must
be awaited. Update all custom providers to use async def.
```

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
