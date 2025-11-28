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
- **Terraform State:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`
- **InfraFoundry State DB:** `~/.infrafoundry/state.db` (SQLite or PostgreSQL)
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

## State & Generated Artifacts
- **Terraform state:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (local by default; remote backends configurable).
- **InfraFoundry state:** SQLite database at `~/.infrafoundry/state.db` (or PostgreSQL via `INFRAFOUNDRY_STATE_BACKEND` / `INFRAFOUNDRY_STATE_CONNECTION`) tracking deployments, resources, dependencies, and events.
- **Generated configs:** `generated/{env}/{terraform|ansible}/{provider}/`—always reproducible from YAML; keep out of version control.

## Development & Testing
- **Use `uv` for Python package management**
- **Run tests:** `just test` or `uv run pytest`
- **Format/lint:** `just format`, `just lint`
- **Coverage:** `just coverage`
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
- Python 3.12+ type hints, `@override` decorator
- Black formatting, ruff linting, max line length 100
- Snake_case for Python, kebab-case for YAML resource names
- Use singular resource type names

## Coding Standards & Best Practices
- **Read-before-edit**: inspect files before modifying; maintain backward-compatible public APIs.
- Follow BaseManager/PathBasedManager, provider mixins, and 3-layer architecture conventions—new managers/providers must integrate cleanly.
- Python style: full type hints with modern syntax (`list[str]`, `X | None`), `@override` on abstract implementations, max line 100, Google-style docstrings.
- Error handling: raise specific exceptions with contextual logging; never catch `KeyboardInterrupt`/`SystemExit`. Prefer early returns over deep nesting.
- Avoid duplication in validators/templates; consider mixins or helpers before copying logic.
- Do not modify public CLI signatures, BaseManager APIs, provider plugin contracts, state schema (introduce migrations instead), or event enums except additive changes.

## Commit Guidelines
- Use Conventional Commits: `feat`, `fix`, `refactor`, `docs`, etc.
- Markdown formatting for detailed commits
- Separate commits for refactoring, docs, tests, cleanup, dependencies

### Branching Strategy
- **General Fixes:** For minor bug fixes and small improvements, directly branch from and target the `dev` branch.
- **Refactors & Feature Additions:** For larger changes, refactorings, or new features, create a dedicated branch (e.g., `feat/my-new-feature`, `refactor/api-cleanup`) branched off `dev`. These branches should be merged into `main` via a Pull Request once completed and reviewed.

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
- Repository docs: `docs/`
- Example configs: `example-config/`
- Policies: `policies/`
- Issues/roadmap: GitHub issues referenced in `AGENTS.md`
- Contact: Use repo discussion/issues per AGENTS guidance.

---
This file unifies essential agent instructions for InfraFoundry. For coding/development specifics, see dedicated documentation files.
