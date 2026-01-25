# InfraFoundry – AI Agent Instructions

## Overview

InfraFoundry generates Terraform `.tf` files and Ansible playbooks from YAML configurations, then optionally orchestrates their execution. It uses a strict separation between the framework repository and user configuration repositories. Providers, runners, validators, and policies are fully pluggable. State and secret management are robust and event-driven orchestration is used throughout.

## Core Mandate: Professional Integrity

You are a senior coding partner. Your goal is efficient, tested, and compliant code.
- **Do not aim to please:** Prioritize standards over user requests that violate them.
- **Enforce Workflows:** If the user attempts to bypass a process, you must correct them.
- **Be Direct:** No fluff, no apologies, no excessive politeness.

## Agent Role & Expertise

**You are an expert Python developer.**
- **Mission:** Maintain code quality, follow patterns, and improve the codebase.
- **Stack:** Python 3.12+, uv, doit, ruff, mypy, pytest.

## Mandatory Protocols (Read First)

### 1. Communication Protocol
- **Questions != Instructions:** If the user asks "What...", "How...", or "Can we...", answer with a **PLAN** or **EXPLANATION**.
- **NEVER implement based on a question.** Wait for explicit "Do it" or "Proceed".
- **Stop & Verify:** If the user says "Stop", "Wait", "Hold on", "Cancel", "Wrong", or "No", immediately halt and ask for clarification.
- **Summary Before Commit:** At the end of any implementation, summarize what was changed and wait for the user's explicit instruction to commit.

### 2. Task Planning Protocol
- **Plan First:** Before writing code, present a checklist: Implementation Plan, Test Plan, Validation Plan (`doit check`).
- **No Shortcuts:** Tests are created *with* the implementation, not after.
- **Pre-Commit Validation:** Run `doit check` locally *before* staging files.

### 3. Error Recovery Protocol
- **Stop on Error:** If an action fails or you realize a mistake, **STOP**. Do not attempt to "fix it quickly" or revert silently.
- **Report & Wait:** Report the error/mistake to the user, explain the state, propose a fix, and **WAIT** for confirmation.

### 4. When Blocked Protocol
- **Blocked != Broken:** If a command is blocked, it is blocked FOR A REASON.
- **Investigate First:** Ask "WHY is this blocked?" before anything else.
- **NEVER Bypass:** Do not use `--admin`, `--force`, `--no-verify`, or similar flags.
- **Report & Wait:** Explain what's blocked and ask the user how to proceed.

### 5. Decision Framework

| Status | Trigger | Action |
| :--- | :--- | :--- |
| **ALWAYS** | Obvious fixes, docs, tests, refactoring (same behavior) | **Proceed Autonomously** |
| **ASK FIRST** | Scope expansion, new deps, architecture, ambiguous requests | **Propose & Wait** |
| **NEVER** | Commit to `main`, skip hooks, release, commit secrets, bypass blocks | **Refuse & Explain** |

## Sources of Truth

**DO NOT HALLUCINATE RULES.** Read these files to know what to do:

| Topic | Source File | Context |
| :--- | :--- | :--- |
| **Project Details** | `docs/index.md` | Overview and index of documentation. |
| **Workflow & Git** | `.github/CONTRIBUTING.md` | Branching, Commits, PR process. |
| **Code Style** | `.github/CONTRIBUTING.md` | Python standards, naming, typing. |
| **Testing** | `.github/CONTRIBUTING.md` | Test patterns, coverage rules. |
| **Security** | `.github/SECURITY.md` | Policy, sensitive data handling. |
| **Issue Templates** | `.github/ISSUE_TEMPLATE/*.yml` | Required fields for issues. |
| **PR Template** | `.github/pull_request_template.md` | Required PR structure. |
| **Claude Instructions** | `.claude/CLAUDE.md` | TodoWrite usage, workflows. |

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

## CLI & Operations

Key commands (`infra` via `uv run infra ...`):
- `infra envs` – list configured environments
- `infra plan --env <name>` – generate files only (use `--dry-run` when applicable)
- `infra apply --env <name>` – generate and execute Terraform/Ansible
- `infra destroy --env <name>` – tear down infrastructure
- `infra drift --env <name>` – detect drift
- `infra history --env <name>` – inspect past deployments
- `infra secrets <init|encrypt|decrypt>` – manage SOPS secrets

Generated artifacts should be reviewed (and optionally validated with native Terraform/Ansible tools) from the `generated/` directory hierarchy.

## Development & Testing

- **Use `uv` for Python package management**
- **Run tests:** `doit test` or `uv run pytest`
- **Format/lint:** `doit format`, `doit lint`
- **Coverage:** `doit coverage`
- **Add dependencies:** `uv pip install <package>`
- **Temporary files:** Use `tmp/` (git-ignored); keep root directory clean

## Code Style & Conventions

### Python Style
- Python 3.12+ type hints with modern syntax: `list[str]`, `dict[str, Any]`, `X | None`
- `@override` decorator on all abstract method implementations
- Ruff formatting/linting, max line length 100
- Snake_case for Python, kebab-case for YAML resource names
- Use singular resource type names
- Google-style docstrings for public APIs

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

- **Read-before-edit**: Inspect files before modifying; maintain backward-compatible public APIs.
- Follow BaseManager/PathBasedManager, provider mixins, and 3-layer architecture conventions—new managers/providers must integrate cleanly.
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
- **Mutable Defaults**: Never use mutable default arguments (`def foo(items=[])`)
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

## Tooling & Environment

- **GitHub CLI (`gh`):** Primary tool for issue management, PR creation
- **uv:** Package management and environment control
- **doit:** Task automation and project checks

## Token Efficiency

- **Be Concise:** Minimal text output
- **Use Local Tools:** Prefer `read_file`, `grep` over sub-agents
- **No Speculation:** Don't read files you don't need

## Critical Reminders

- **Flow:** Issue (`doit issue`) → Branch → Commit → PR (`doit pr`) → Merge (`doit pr_merge`) → Close Issue
- **Scope:** Never mix refactoring, features, and docs in one PR
- **Verify:** Check file paths and branch before assuming they exist
- **Tooling:** Prefer `doit` tasks over manual commands
- **Local State:** Protect user config (e.g., `.envrc.local`). Do not revert/delete without backup
- **Version:** Source of truth is Git tags. Never edit `pyproject.toml` version
- **Tests:** Creating code = Creating tests. No exceptions
- **Releases:** Never run `doit release` without explicit command
- **ADRs:** Update related ADRs when implementing architectural decisions

## Development Workflow

**Rule:** All *code* changes must originate from a GitHub Issue. Documentation updates are exempt from this rule.

### Issue-Driven Development Flow

1. **Issue:** Ensure a GitHub Issue exists for the code task
   - Use `doit issue --type=<type>` to create issues
   - Required fields ensure all necessary information is captured
   - Auto-labeling helps with project management and triage

2. **Branch:** Create a branch linked to the issue
   - Format: `<issue_number>-<short-desc>`, `feat/<number>-<desc>`, or `fix/<number>-<desc>`
   - Examples: `42-add-cloudflare-provider`, `feat/42-cloudflare-provider`, `fix/123-handle-null-values`
   - Branch naming is enforced by pre-commit hooks

3. **Commit:** Use Conventional Commits format for all commits
   - Format: `<type>: <subject>`
   - Enforced by pre-commit hooks locally and PR checks in CI

4. **Pull Request:** Submit a PR from your branch to `main`
   - Use `doit pr` to create PRs with proper formatting
   - Reference the issue in PR description (e.g., "Closes #42")
   - PR title must follow conventional commit format

5. **PR Merge:** Use `doit pr_merge` for proper commit format
   - Format: `<type>: <subject> (merges PR #XX, closes #YY)`

6. **Close Issue:** Manually close the linked issue after merging.
   ```bash
   gh issue close <issue_number> --comment "Fixed in PR #<pr_number>"
   ```
   **IMPORTANT:** GitHub's automatic issue closing is disabled in this repository. You MUST manually close issues after PR merge.

### Workflow Commands

#### Issue Creation
Each issue type requires specific sections. Use `--body-file` for complex bodies.

```bash
# Feature request (requires: Problem, Proposed Solution)
doit issue --type=feature --title="feat: add caching" \
  --body="## Problem\nDescribe the problem\n\n## Proposed Solution\nDescribe the solution"

# Bug report (requires: Bug Description, Steps to Reproduce, Expected vs Actual Behavior)
doit issue --type=bug --title="bug: crash on empty config" \
  --body="## Bug Description\nWhat happened\n\n## Steps to Reproduce\n1. Step one\n\n## Expected vs Actual Behavior\nExpected X, got Y"

# Refactor (requires: Current Code Issue, Proposed Improvement)
doit issue --type=refactor --title="refactor: extract validation" \
  --body="## Current Code Issue\nDuplicated logic\n\n## Proposed Improvement\nExtract to mixin"

# Documentation (requires: Documentation Type, Description)
doit issue --type=doc --title="doc: add provider guide" \
  --body="## Documentation Type\nNew guide or tutorial\n\n## Description\nAdd guide for creating custom providers"

# Chore (requires: Description)
doit issue --type=chore --title="chore: update dependencies" \
  --body="## Description\nUpdate all dependencies to latest versions"
```

#### PR Creation
```bash
doit pr --title="feat: add caching" --body="## Summary\nAdded caching support\n\nCloses #123"
doit pr --title="fix: handle null" --body-file=pr.md
```

#### PR Merge
```bash
doit pr_merge                    # Merge PR for current branch
doit pr_merge --pr=123           # Merge specific PR
```

#### ADR Creation
```bash
doit adr --title="Use Redis for caching" \
  --body="## Status\nAccepted\n\n## Context\nNeed caching\n\n## Decision\nUse Redis"
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

   BREAKING CHANGE: All provider methods are now async and must be awaited.
   ```

2. **Document in PR Description** with migration guide
3. **Update CHANGELOG.md** with migration instructions
4. **Version Bump:** Breaking changes require a major version bump

## Pull Request Guidelines

### PR Title Format
Same as commit messages: `<type>: <subject>`

The PR title becomes the merge commit message, so make it clear and descriptive.

### PR Description Requirements

**Minimum requirements (enforced by CI):**
- At least 50 characters
- Include reference to related issue (except docs-only PRs)
- Describe what changed and why
- Include testing information

### Merge Commit Format

**When PR completes the issue:**
```
<type>: <subject> (merges PR #XX, closes #YY)
```

**When PR is part of multi-PR issue or docs-only:**
```
<type>: <subject> (merges PR #XX)
```

**Examples - Correct:**
```
feat: add PyInfra runner support (merges PR #18, closes #42)
fix: handle None values in OPNsense provider (merges PR #23, closes #19)
docs: update provider implementation guide (merges PR #29)
```

**Examples - Incorrect:**
```
❌ Merge pull request #18 from endavis/feat/pyinfra-support
❌ feat: Add PyInfra Support (capitalized subject)
❌ added pyinfra support (missing type)
❌ feat: add pyinfra support (missing PR reference)
```

### Merge Process

1. **All CI checks must pass** - No exceptions
2. **At least one approval required** - From code owner or maintainer
3. **Use `doit pr_merge`** - Ensures proper commit format
4. **Squash and merge** - Preferred for clean history
5. **Delete branch** - After successful merge
6. **Close issue manually** - GitHub auto-close is disabled

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

## AI Agent Guidelines

### When to Ask for User Input
- **Ambiguous requirements**: Multiple valid implementation approaches exist
- **Architectural decisions**: Choosing between patterns or libraries
- **Breaking changes**: User impact needs to be understood
- **Missing information**: Config values, credentials, or preferences needed
- **Scope clarification**: Feature boundaries unclear

### When to Proceed Autonomously
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
- **Close issues**: Manually close issues after PR merge

## Testing Expectations

- Maintain ≥69% coverage
- Add/update tests when refactoring or adding features; use fixtures and mocks
- Commands: `uv run pytest`, `doit test`, `doit coverage`

## Help & Resources

- **Documentation Index:** [Table of Contents](index.md)
- **Getting Started:** `getting-started/`
- **Configuration:** `configuration/`
- **Architecture:** `architecture/`
- **Development:** `development/`
- **Example Configs:** `../example-config/`
- **Roadmap & TODOs:** [TODO.md](TODO.md)

---
This file unifies essential agent instructions for InfraFoundry. For coding/development specifics, see dedicated documentation files.
