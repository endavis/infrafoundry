# InfraFoundry CLI Reference

## Overview

`infra` drives environment discovery, generation, validation, apply/destroy flows, and policy/secrets management. Use this reference to run common workflows and explore command options.

## Audience and Prerequisites

- **Audience:** Operators and CI systems running InfraFoundry workflows.
- **Prereqs:** Config repo available (`--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`), `uv run infra` installed, and provider credentials/secrets configured.

## When to Use This

- Running plan/apply/destroy for environments or specific resources.
- Inspecting environments, state, history, or drift.
- Managing secrets, policies, blueprints, and helpers.

## Quick Start

```bash
# List environments
infra envs

# Validate + plan
infra validate --env dev --check-api --check-refs
infra plan --env dev

# Apply/destroy
infra apply --env dev
infra destroy --env dev --auto-approve
```

## Configuration Details

- **Global options:**
  - `--config-dir/-c PATH` (overrides `INFRAFOUNDRY_CONFIG_REPO`)
  - `--strict-mode/--no-strict-mode`
  - `--fail-on-missing-secrets | --allow-missing-secrets`
  - `--fail-on-missing-snippets | --allow-missing-snippets`
  - Environment equivalents: `INFRAFOUNDRY_STRICT_MODE`, `INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS`, `INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS`.
- **State:** InfraFoundry DB at `~/.infrafoundry/state.db` (unless overridden); Terraform state under `generated/{env}/terraform/{provider}`.
- **Generated artifacts:** `generated/{env}/{terraform|ansible}/{provider}`; always reproducible from YAML.

## Commands and Examples

- **Initialization**
  - `infra init` — create state DB (SQLite by default).
- **Blueprints**
  - `infra new list` — list blueprints.
  - `infra new create <blueprint> <path>` — scaffold from blueprint.
- **Environment introspection**
  - `infra envs` — list environments.
  - `infra list --env <env> [--provider ... --type ...]` — list resources from YAML.
  - `infra resources [--env ... --provider ... --type ... --state ...]` — list tracked resources from state DB.
  - `infra status --env <env>` — show deployment status.
  - `infra history [--env <env>]` — view deployment history.
- **Plan/Apply/Destroy**
  - `infra plan --env <env> [--resource ...] [--dry-run]`
  - `infra apply --env <env> [--resource ...] [--auto-approve]`
  - `infra destroy --env <env> [--resource ...] [--auto-approve]`
- **Validation and Drift**
  - `infra validate --env <env> [--check-api] [--check-refs]`
  - `infra drift --env <env>`
- **Policies**
  - `infra policies check --env <env> [--enforce]`
- **Secrets**
  - `infra secrets init|encrypt|decrypt`
- **Graphing**
  - `infra graph --env <env> --format mermaid|dot`
- **Migrations/Helpers**
  - `infra isc-to-kea ...` — migrate ISC DHCP to Kea format.
  - `infra download-template ...` — fetch templates where supported.

## Validation and Checks

- Prefer `infra validate --env <env> --check-api --check-refs` before `plan`/`apply`.
- Use `--strict-mode` to treat missing secrets/snippets as errors.
- Inspect generated files under `generated/` if behavior is unexpected.

## Examples

- **Target specific resources:**
  ```bash
  infra plan --env dev --resource vm-01 --resource vm-02
  infra apply --env dev --resource vm-01 --auto-approve
  ```
- **Policy enforcement in CI:**
  ```bash
  infra policies check --env prod --enforce
  ```
- **Drift detection:**
  ```bash
  infra drift --env prod
  ```
- **Graph dependencies:**
  ```bash
  infra graph --env dev --format mermaid > graph.mmd
  ```

## Related Documentation

- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](validation.md)
- [Policy Configuration Guide](../configuration/policy-configuration.md)
- [State Management](../architecture/state-management.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)

## Troubleshooting

- **Symptom:** Missing configs. **Fix:** Set `--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`; ensure `envs/{env}` exists.
- **Symptom:** Commands fail due to missing secrets/snippets. **Fix:** Enable `--strict-mode` to surface early, or allow missing during development; ensure SOPS keys are available.
- **Symptom:** Unexpected resource lists. **Fix:** Use `infra list` (YAML view) vs `infra resources` (state DB view) to differentiate declared vs tracked resources.

---

Last updated: 2025-11-29 14:27 GMT
