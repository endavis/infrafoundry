# InfraFoundry – AI Agent Instructions

## Overview

InfraFoundry generates Terraform `.tf` files and Ansible playbooks from YAML configurations, then optionally orchestrates their execution. It uses a strict separation between the framework repository and user configuration repositories. Providers, runners, validators, and policies are fully pluggable. State and secret management are robust and event-driven orchestration is used throughout.

## ⚠️ Core Mandate: Professional Integrity

You are a senior coding partner. Your goal is efficient, tested, and compliant code.
- **Do not aim to please:** Prioritize standards over user requests that violate them.
- **Enforce Workflows:** If the user attempts to bypass a process, you must correct them.
- **Be Direct:** No fluff, no apologies, no excessive politeness.

## Agent Role & Expertise

**You are an expert Python developer.**
- **Mission:** Maintain code quality, follow patterns, and improve the codebase.
- **Stack:** Python 3.12+, uv, doit, ruff, mypy, pytest.

## ⚠️ Mandatory Protocols (Read First)

### 1. Communication Protocol
- **Questions != Instructions:** If the user asks "What...", "How...", or "Can we...", answer with a **PLAN** or **EXPLANATION**.
- **NEVER implement based on a question.** Wait for explicit "Do it" or "Proceed".
- **Stop & Verify:** If the user says "Stop", "Wait", "Hold on", "Cancel", "Wrong", or "No", immediately halt and ask for clarification.
- **Summary Before Commit:** At the end of any implementation (docs, fix, feature, chore, etc.), summarize what was changed for the user before committing and wait for the user's explicit instruction to commit the changes.
- **Failing Tests:** Never modify a test to make it pass. Stop, explain *why* the test broke (what behavior changed, what the test was asserting), and discuss with the user whether the code or the test should change. A failing test is a signal, not a problem to silence.

### 2. Task Planning Protocol
- **Plan First:** Before writing code, you MUST present a checklist:
  1. Implementation Plan
  2. Test Plan (Mandatory)
  3. Validation Plan (`doit check`)
- **No Shortcuts:** Tests are created *with* the implementation, not after.
- **Pre-Commit Validation:** Run `doit check` locally *before* staging files to avoid pre-commit hook failures.

### 3. Error Recovery Protocol
- **Stop on Error:** If an action fails or you realize a mistake, **STOP**. Do not attempt to "fix it quickly" or revert silently.
- **Report & Wait:** Report the error/mistake to the user, explain the state, propose a fix, and **WAIT** for confirmation.
- **No Auto-Reverts:** Do not revert changes unless explicitly instructed or if the change caused a critical system failure blocking further interaction.

### 4. When Blocked Protocol
- **Blocked ≠ Broken:** If a command is blocked (merge fails, push rejected, permission denied), it is blocked FOR A REASON.
- **Investigate First:** Ask "WHY is this blocked?" before anything else.
- **NEVER Bypass:** Do not use `--admin`, `--force`, `--no-verify`, or similar flags to override blocks.
- **Report & Wait:** Explain what's blocked and ask the user how to proceed.

> **Note:** Dangerous commands are also blocked at the tool level by hooks in `tools/hooks/ai/`. See the [AI Command Blocking](docs/development/ai/command-blocking.md) documentation.

### 5. Pre-Action Checks (Dynamic Context)
**Do not rely on pre-loaded context.** You MUST read these files *immediately before* acting:

| Intent / Action | **MUST READ** Rule Source | Purpose |
| :--- | :--- | :--- |
| **New Feature** (Check for duplicates) | `.github/ISSUE_TEMPLATE/feature_request.yml` | Required fields & structure. |
| **Refactoring** | `.github/ISSUE_TEMPLATE/refactor.yml` | Success criteria requirements. |
| **Bug Fix** (Check for duplicates) | `.github/ISSUE_TEMPLATE/bug_report.yml` | Reproduction steps format. |
| **PR Template** | `.github/pull_request_template.md` | Required structure & checklist items. |
| **Committing** | `.github/CONTRIBUTING.md` (Commit Guidelines) | `<type>: <subject>` format. |
| **New Dependency** | `.github/CONTRIBUTING.md` (Dependencies) | "Ask First" policy. |
| **Creating Code** | `.claude/CLAUDE.md` (TodoWrite) | Plan -> Test -> Code loop. |
| **Generating new code** | `docs/development/ai/architectural-conventions.md` | Layering rules and anti-patterns to avoid before writing code. |
| **Architectural Decision** | `docs/decisions/README.md` | Check for related ADRs to update. |

### 6. Decision Framework

| Status | Trigger | Action |
| :--- | :--- | :--- |
| ✅ **ALWAYS** | Obvious fixes, docs, tests, refactoring (same behavior) | **Proceed Autonomously** |
| ⚠️ **ASK FIRST** | Scope expansion, new deps, architecture, ambiguous requests | **Propose & Wait** |
| 🚫 **NEVER** | Commit to `main`, skip hooks, release, commit secrets, bypass blocks (`--admin`, `--force`) | **Refuse & Explain** |

### Examples: Prohibited vs. Correct Reasoning

**Understanding what constitutes an "assumption" or "judgment call":**

**❌ PROHIBITED - These are assumption-based judgment calls:**
- "This change is small/trivial, so I don't need to follow the full workflow"
- "This is just a typo fix, so I can commit directly to main"
- "GitHub will automatically close the issue with 'Addresses #XX' syntax, so I don't need to verify"
- "The user probably wants me to proceed without asking"
- "This seems obvious, so I'll skip the issue creation step"
- "It's just documentation, so tests aren't needed"
- "I'll commit now and create the issue afterward"
- "The merge is blocked, so I'll use --admin to force it through"
- "CI hasn't finished but I'll bypass with --admin"

**✅ CORRECT - These follow documented rules:**
- "The workflow says Issue → Branch → Commit → PR → Merge, so I will follow every step regardless of change size"
- "I'm not sure if I should close the issue manually, so I will ask the user"
- "The documentation says 'NEVER commit to main' with no exceptions, so I will create a branch"
- "AGENTS.md says to create tests when writing new code, so I will create them even though this is simple"
- "I don't see explicit documentation about this case, so I will ask the user before proceeding"
- "The rule says 'NO EXCEPTIONS' so I will not evaluate if this qualifies as an exception"
- "The merge is blocked, so I will investigate why and ask the user before attempting to bypass"

**Key principle:** If you find yourself thinking "but this case is different because..." or "this is simple enough to...", you are making a judgment call. STOP and follow the documented process or ASK the user.

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
| **Architecture & Layering** | `docs/development/ai/architectural-conventions.md` | Imperative-form rules for AI agents. |
| **Slash Commands & Workflows** | `docs/development/ai/slash-commands.md` | Reference for /plan-issue, /implement, /finalize, dual-agent workflow. |
| **AI Agent Walkthrough** | `docs/development/ai/first-5-minutes.md` | Narrative onboarding for the AI agent workflow (plan → implement → review → PR → merge). |

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

Key commands (`foundry` via `uv run foundry ...`):

**Top-level:**
- `doctor` – check system dependencies (Terraform, OpenTofu, Ansible, SOPS, Age)
- `completion <bash|zsh|fish|uninstall>` – manage shell completion

**Config group (`config`):**
- `config doctor [--deep]` – check config repo health (structure, state, SOPS, consistency, blueprints)
- `config envs` – list configured environments with sync status
- `config diff --env-a <a> --env-b <b>` – compare two environments
- `config show --env <name>` – show resolved configuration
- `config create <name>` – create a new environment
- `config new create <blueprint> <dir>` – create infrastructure from blueprints
- `config migrate --env <name> --provider <p> --component <c>` – migrate existing infra to config
- `config export --env <name> --output <dir>` – export provider config to YAML
- `config schema <export|list|show>` – JSON schemas for IDE autocomplete

**Infra group (`infra`):**
- `infra doctor --env <name>` – validate infrastructure against provider APIs
- `infra plan --env <name>` – generate files only (use `--dry-run` when applicable)
- `infra apply --env <name>` – generate and execute Terraform/Ansible
- `infra destroy --env <name>` – tear down infrastructure
- `infra drift <detect|remediate|history>` – detect and remediate drift
- `infra deployed --env <name>` – show deployment status and resources
- `infra history [--env <name>]` – inspect past deployments
- `infra list --env <name>` – list configured packages in an environment
- `infra move-package --env <src> --package <pkg> --to-env <dst>` – move package between environments
- `infra analyze <dependencies|impact|graph>` – dependency analysis and visualization
- `infra rollback <list|to>` – rollback to previous deployment state
- `infra security --env <name>` – scan for security issues (Checkov)
- `infra test --env <name>` – run infrastructure tests
- `infra status --env <name>` – show infrastructure status
- `infra reset --env <name> --provider <p> --component <c>` – reset provider component
- `infra unlock [--env <name> | --list]` – manage deployment locks

**State group (`state`):**
- `state init` – initialize state database
- `state list --env <name>` – list resources in an environment
- `state resources` – list tracked infrastructure resources
- `state backup` – backup state database
- `state backend <validate|migrate>` – manage Terraform backend configuration
- `state audit <list|export|verify>` – view and export audit trail

**Secrets group (`secrets`):**
- `secrets init` – initialize age encryption key
- `secrets encrypt <file>` – encrypt a file with SOPS
- `secrets decrypt <file>` – decrypt and display a SOPS-encrypted file
- `secrets rotate --env <name>` – rotate encryption keys

**Policy group (`policy`):**
- `policy list` – list available infrastructure policies

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
- **Race Conditions**: Configure Terraform backend locking (e.g., S3+DynamoDB) for concurrent operations
- **Stale State**: Always refresh state before operations
- **Lost State**: Never delete generated configs without destroy first

## Tooling & Environment

### Principle: Use the Highest-Level Tool Available

This project wraps common operations in `doit` tasks that enforce conventions, validate inputs, and reduce errors. **Always check if a `doit` task exists before running a raw command.**

The tool hierarchy (prefer higher over lower):

1. **`doit`** — Project tasks that enforce conventions (issues, PRs, checks, releases)
2. **`uv`** — Package management and Python execution
3. **`gh`** — GitHub API queries and operations not covered by `doit`
4. **`git`** — Version control operations
5. **Raw commands** — Only when nothing above covers the need

### Tool Reference

| Task | Preferred Tool | Do NOT Use |
| :--- | :--- | :--- |
| Run all checks (test, lint, type) | `doit check` | `pytest`, `ruff`, `mypy` separately |
| Run tests only | `doit test` | `pytest` directly |
| Run tests with coverage | `doit coverage` | `pytest --cov` directly |
| Lint code | `doit lint` | `ruff check` directly |
| Format code | `doit format` | `ruff format` directly |
| Type-check | `doit type_check` | `mypy` directly |
| Security audit | `doit audit` | `pip-audit` directly |
| Create issues | `doit issue --type=<type>` | `gh issue create` |
| Create PRs | `doit pr` | `gh pr create` |
| Merge PRs | `doit pr_merge` | `gh pr merge` |
| Create ADRs | `doit adr` | Manual file creation |
| Sync GitHub labels | `doit labels_sync` | `gh label create` / `gh label edit` manually |
| Commit (interactive) | `doit commit` | `git commit` without format |
| Install/add packages | `uv add <pkg>` | `pip install` |
| Sync dependencies | `uv sync` | `pip install -r` |
| Run Python scripts | `uv run <script>` | `python` directly |
| Run a specific test file | `uv run pytest tests/test_foo.py` | `pytest` directly |
| Read issues/PRs/comments | `gh issue view`, `gh pr view`, `gh api` | `WebFetch` on GitHub URLs |
| GitHub API queries | `gh api` | `curl` to GitHub API |
| Build docs | `doit docs_build` | `mkdocs build` directly |
| Serve docs locally | `doit docs_serve` | `mkdocs serve` directly |
| Release | `doit release` | Manual changelog + PR |
| Tag after release PR merge | `doit release_tag` | Manual tag + push |
| Mutation testing | `doit mutate` | `mutmut` directly |
| Generate SBOM | `doit sbom` | `cyclonedx-py` directly |

### Discovering Available Tasks

List all available `doit` tasks before assuming one doesn't exist:

```bash
doit list          # Show all tasks with descriptions
doit help <task>   # Show detailed help for a specific task
```

### When Raw Commands Are Appropriate

Raw `git` and `gh` commands are fine for **read-only queries** that `doit` doesn't wrap:

```bash
# Git — read-only is always fine
git status
git log --oneline -10
git diff
git branch -a

# gh — read-only queries
gh issue view 42
gh pr view 123
gh pr checks
gh api repos/{owner}/{repo}/pulls/123/comments
gh issue list --label "bug"
gh pr list --state open
```

**Write operations** should go through `doit` when a task exists. Use raw `git`/`gh` for write operations only when no `doit` task covers the need (e.g., `git checkout -b`, `git add`, `gh issue close`).

### Dependabot PRs

Dependabot PRs that pass CI are now auto-merged by `.github/workflows/dependabot-automerge.yml`. The manual workflow below applies only to PRs the bot skips (major bumps, sensitive deps, or PRs labeled `automerge-blocked`). See [docs/development/dependabot-automerge.md](docs/development/dependabot-automerge.md) for details.

When merging dependabot PRs that are behind `main`, **never** use the GitHub API `update-branch` endpoint or local rebase to update the branch. This strips the verified commit signatures from dependabot commits, which are required by branch protection rules.

Instead, use dependabot's own rebase command:

```bash
gh pr comment <number> --body "@dependabot rebase"
```

Dependabot will rebase the branch and re-sign the commits, preserving verified signatures.

#### Dependabot PR merge workflow

When merging dependabot PRs that are behind `main`, use this procedure:

1. **Request rebase** via dependabot's own action (preserves signed commits):
   ```bash
   gh pr comment <number> --body "@dependabot rebase"
   ```

2. **Wait for force-push** — poll until the PR's commit parent matches current `main` HEAD:
   ```bash
   # Get current main HEAD
   main_sha=$(gh api repos/{owner}/{repo}/git/ref/heads/main --jq '.object.sha[0:7]')

   # Poll PR commit parent until it matches
   gh api repos/{owner}/{repo}/pulls/<number>/commits --jq '.[0].parents[0].sha[0:7]'
   ```
   This takes 1–3 minutes. **Do not** request a second rebase until the first one lands.

3. **Wait for CI** to pass (`gh pr checks <number> --watch`).

4. **Merge** with `doit pr_merge --pr=<number>`.

#### What NOT to do

- **Never** use `gh api .../update-branch` to rebase — this strips verified commit signatures.
- **Never** rebase locally — same problem.
- **Never** request a second `@dependabot rebase` before confirming the first force-push landed.

### AI Agent File Operations

AI agents with native file tools (Read, Grep, Glob, Edit, Write) **must** prefer those over shell equivalents:

| Operation | Use This | Not This |
| :--- | :--- | :--- |
| Read a file | `Read` tool | `cat`, `head`, `tail` |
| Search file contents | `Grep` tool | `grep`, `rg` |
| Find files by pattern | `Glob` tool | `find`, `ls` |
| Edit a file | `Edit` tool | `sed`, `awk` |
| Create a file | `Write` tool | `echo >`, `cat <<EOF` |

Native tools provide better visibility, review capabilities, and error handling for the user.

### AI Config Directories

Each supported AI CLI has a dedicated config directory at the repo root:

| CLI | Config Directory | Notes |
| :--- | :--- | :--- |
| Claude Code | `.claude/` | Commands, agents, settings. Primary source of slash commands. |
| Gemini CLI | `.gemini/` | Commands and settings. Output-only commands (orchestrated by Claude). |
| GitHub Copilot CLI | `.copilot/` | Config directory. Skills auto-discovered from `.claude/commands/`. Hook wired in `.github/hooks/copilot-hooks.json`. |
| Codex CLI | `.codex/` | `config.toml` only (command approval policies). No slash commands. |

Copilot CLI does **not** need a `commands/` subdirectory: it discovers skills from `.claude/commands/` automatically, so the full workflow (`/plan-issue`, `/implement`, `/finalize`, etc.) works out of the box.

### Temporary Files

AI agents **must never** write temporary files to generic locations like `/tmp/`. Instead, use the project-scoped directory:

```
tmp/agents/<agent-type>/
```

Where `<agent-type>` is one of: `claude`, `gemini`, `copilot`, `codex`, or the relevant agent name.

**Filenames must include context** (issue number, PR number, or task identifier) to prevent collisions when multiple sub-agents run concurrently.

| | Example |
| :--- | :--- |
| **Before (wrong)** | `/tmp/pr-body.md` |
| **After (correct)** | `tmp/agents/claude/pr-body-issue-307.md` |

**Cleanup rule:** Agents must delete their temporary files when the task is complete. Do not leave stale files in `tmp/agents/`.

## Token Efficiency
- **Be Concise:** Minimal text output.
- **Use Local Tools:** Prefer native file tools over sub-agents (see [AI Agent File Operations](#ai-agent-file-operations)).
- **No Speculation:** Don't read files you don't need.

## Critical Reminders
- **Flow:** Issue (`doit issue`) -> **`git checkout main && git pull`** -> Branch -> Commit -> PR (`doit pr`) -> Merge (`doit pr_merge`). NEVER commit to main. Pull `main` before branching — local `main` may be behind the remote (e.g., after dependabot PRs merged via the web UI). `doit pr` enforces this by aborting if the branch is behind `origin/main`; pass `--no-update-check` to override.
- **Scope:** Never mix refactoring, features, and docs in one PR. Create separate branches.
- **Verify:** Check file paths (`ls`) and branch (`git status`) before assuming they exist.
- **Security:** NEVER bypass security checks (e.g., `--no-verify`, ignoring secrets).
- **Tooling:** Prefer `doit` tasks over manual commands.
- **Integrity:** Respect architectural patterns (modularity) over "quick fixes".
- **Local State:** Protect user config (e.g., `.envrc.local`, settings). Do not revert/delete without backup.
- **Version:** Source of truth is Git tags. Never edit `pyproject.toml` version.
- **Tests:** Creating code = Creating tests. No exceptions. Never modify a failing test to make it pass — stop, explain why it broke, and discuss with the user whether the code or the test should change.
- **Commits:** One logical change per commit. Use conventional commits.
- **Releases:** Never run `doit release` without explicit command.
- **PRs:** Use `doit pr` to create PRs and `doit pr_merge` to merge with proper commit format. Issues are not automatically closed. Ask the user if they would like the related issue closed — pass `--auto-close` to `doit pr_merge` to close linked issues in one step.
- **The Merge Gate action:** is a manual action for the user to add to a PR. It requires the ready-to-merge label and should never be added by automation. Exception: the dependabot auto-merge workflow (`.github/workflows/dependabot-automerge.yml`) applies the `ready-to-merge` label to qualifying dependabot PRs only.
- **Issues:** Use `doit issue --type=<type>` to create issues (types: feature, bug, refactor, docs, chore). Labels are auto-applied. Manually close after PR merge with comment "Addressed in PR #XXX". Issues are not closed automatically when PRs are merged.
- **ADRs:** When implementing architectural decisions (typically `feat` or `refactor`, rarely `fix`), update related ADRs in `docs/decisions/` to add the issue link. Create new ADRs for significant decisions using `doit adr`. Every ADR must link to the documentation in `docs/` that describes the implementation. Docs and chore issues do not need ADRs. Issues with the `needs-adr` label require an ADR before the PR can be merged.

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
   - Reference the issue in PR description (e.g., "Addresses #42")
   - PR title must follow conventional commit format

5. **PR Merge:** Use `doit pr_merge` for proper commit format
   - Format: `<type>: <subject> (merges PR #XX, addresses #YY)`

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

# Documentation (requires: Description)
doit issue --type=docs --title="docs: add provider guide" \
  --body="## Description\nAdd guide for creating custom providers"

# Chore (requires: Description)
doit issue --type=chore --title="chore: update dependencies" \
  --body="## Description\nUpdate all dependencies to latest versions"
```

#### PR Creation
```bash
doit pr --title="feat: add caching" --body="## Summary\nAdded caching support\n\nAddresses #123"
doit pr --title="fix: handle null" --body-file=pr.md
```

`doit pr` auto-pushes the current branch to `origin` if it has no upstream. Pass `--no-push` to skip the auto-push (the task aborts instead).

#### PR Merge
```bash
doit pr_merge                        # Merge PR for current branch
doit pr_merge --pr=123               # Merge specific PR
doit pr_merge --pr=123 --auto-close  # Also close linked issues after merge
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
<type>: <subject> (merges PR #XX, addresses #YY)
```

**When PR is part of multi-PR issue or docs-only:**
```
<type>: <subject> (merges PR #XX)
```

**Examples - Correct:**
```
feat: add PyInfra runner support (merges PR #18, addresses #42)
fix: handle None values in OPNsense provider (merges PR #23, addresses #19)
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

## PR Checklist (for AI agents)

Before creating a PR, verify:

- [ ] `doit check` passes (tests, lint, type-check, security)
- [ ] Branch name follows convention: `<type>/<issue>-<description>`
- [ ] Commits follow conventional format: `<type>: <subject>`
- [ ] PR title follows conventional format: `<type>: <subject>`
- [ ] PR description references the issue: "Addresses #XX"
- [ ] If issue has `needs-adr` label: ADR created and included in PR
- [ ] If implementing architectural decision: Related ADR updated with issue link
- [ ] If ADR created/updated: Links to documentation in `docs/` included
- [ ] Documentation updated if behavior changed

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
