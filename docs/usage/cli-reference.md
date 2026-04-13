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
# Check system dependencies
foundry doctor

# Check config repo health
foundry config doctor

# Validate against provider APIs
foundry infra doctor --env dev

# List environments
infra envs

# Plan + apply
infra plan --env dev
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

- **Health Checks (doctor commands)**
  - `foundry doctor [--format text|json]` — check system dependencies (Terraform, OpenTofu, Ansible, SOPS, Age).
  - `foundry config doctor [--format text|json] [--deep]` — check config repo health: config repo structure, environments, state backend, SOPS keys, state/filesystem consistency, blueprint validation.
  - `foundry infra doctor --env <env> [--resource <name>]... [--verbose]` — validate infrastructure against provider APIs (connectivity, nodes, storage, networks, templates, etc.).
- **Initialization**
  - `infra init` — create state DB (SQLite by default).
- **Blueprints**
  - `infra new list` — list blueprints.
  - `infra new create <blueprint> <path>` — scaffold from blueprint.
- **Environment introspection**
  - `infra envs` — list environments with sync status (OK/FS-ONLY/DB-ONLY) showing consistency between filesystem and state database.
  - `infra list --env <env> [--provider ... --type ...]` — list resources from YAML.
  - `infra resources [--env ... --provider ... --type ... --state ...]` — list tracked resources from state DB.
  - `infra status --env <env>` — show deployment status.
  - `infra history [--env <env>]` — view deployment history.
  - `infra diff --env-a <env1> --env-b <env2> [--provider ...] [--verbose]` — compare configurations between two environments.
- **Plan/Apply/Destroy**
  - `infra plan --env <env> [--resource ...] [--package <name>] [--dry-run]`
  - `infra apply --env <env> [--resource ...] [--package <name>] [--auto-approve] [--lock-timeout <seconds>] [--lock-ttl <seconds>]`
  - `infra destroy --env <env> [--resource ...] [--package <name>] [--auto-approve] [--lock-timeout <seconds>] [--lock-ttl <seconds>]`
  - `infra reset --env <env> --provider <provider> --component <component> [--auto-approve]` — completely remove component configuration from provider for clean reapply.
  - **Lock options on apply/destroy:**
    - `--lock-timeout <seconds>` — how long to wait for an existing lock before failing. Default `0` (fail fast).
    - `--lock-ttl <seconds>` — how long the acquired lock is valid before it is considered stale. The lock is auto-extended every `ttl / 3` seconds while the process runs, so this only governs stale-lock recovery after a crash. Default `600` (10 minutes).
- **Locking**
  - `infra unlock --env <env>` — release an expired lock for the environment (refuses to release active locks).
  - `infra unlock --env <env> --force [--yes]` — force-release an active lock; prompts for confirmation unless `--yes` is supplied.
  - `infra unlock --list` — list all current deployment locks across environments.
  - Set `INFRAFOUNDRY_SKIP_LOCK=1` to bypass locking entirely (emergency use only — emits a loud warning).
- **Rollback and Recovery**
  - `infra rollback-points --env <env> [--limit <n>]` — list available rollback points for an environment.
  - `infra rollback --deployment-id <id> [--auto-approve]` — rollback infrastructure to a previous deployment state.
- **State Management**
  - `infra state backup [--output-dir <dir>] [--include-generated]` — create timestamped backup of state database and optionally the generated/ directory.
- **Validation and Drift**
  - `infra doctor --env <env> [--resource <name>]... [--verbose]` — pre-flight validation against provider APIs.
  - `infra drift --env <env>`
- **Policies**
  - `infra policies check --env <env> [--enforce]`
- **Secrets**
  - `infra secrets init|encrypt|decrypt`
- **Dependency Analysis** (under `infra analyze`)
  - `infra analyze dependencies --env <env> [--resource <provider:name>] [--format list|mermaid]` — show dependency graph or analyze specific resource dependencies.
  - `infra analyze impact --env <env> --resource <name>` — analyze the impact of changes to a resource and show what depends on it.
  - `infra analyze graph --env <env> --format mermaid|dot` — generate visual topology graph.
- **Configuration Export**
  - `config export --env <env> --output <dir> [--provider proxmox] [--node ...] [--resource-type ...]` — export provider configuration to InfraFoundry YAML.
- **Schema Management** (under `config schema`)
  - `config schema export [--output <dir>]` — export all JSON schemas for IDE autocomplete.
  - `config schema list` — list available schemas.
  - `config schema show <name> [--format json|yaml]` — show a specific schema.
- **Audit Trail** (under `state audit`)
  - `state audit list [--env ... --user ... --action ... --limit ... --since ...]` — list audit entries.
  - `state audit export --output <file> [--format json|csv] [--env ... --since ...]` — export audit entries.
  - `state audit verify <ENTRY_ID>` — verify integrity of an audit entry.

## Validation and Checks

- Prefer `infra doctor --env <env>` before `plan`/`apply` to catch configuration errors early.
- Use `--strict-mode` to treat missing secrets/snippets as errors.
- Inspect generated files under `generated/` if behavior is unexpected.

## Examples

- **Target specific resources:**
  ```bash
  infra plan --env dev --resource vm-01 --resource vm-02
  infra apply --env dev --resource vm-01 --auto-approve
  ```
- **Target an entire package:**
  ```bash
  infra plan --env dev --package ontap-cluster
  infra apply --env dev -p ontap-cluster --auto-approve
  infra destroy --env dev -p ontap-cluster
  ```
  Note: `--package` (`-p`) and `--resource` (`-r`) are mutually exclusive.
- **Rollback to previous deployment:**
  ```bash
  # View deployment history to find deployment ID
  infra history --env prod

  # Rollback to deployment ID 42
  infra rollback --deployment-id 42

  # Rollback without confirmation prompt (use with caution)
  infra rollback --deployment-id 42 --auto-approve
  ```
- **Backup state and generated files:**
  ```bash
  # Backup state database only
  infra state backup --output-dir ./backups

  # Backup state database and generated/ directory
  infra state backup --output-dir ./backups --include-generated

  # Creates timestamped files:
  # - infrafoundry_state_20250127_143022.db
  # - infrafoundry_generated_20250127_143022.tar.gz (if --include-generated)
  ```
- **Compare environments:**
  ```bash
  # Compare dev and prod configurations
  infra diff --env-a dev --env-b prod

  # Compare specific provider configurations
  infra diff --env-a dev --env-b prod --provider proxmox

  # Show detailed differences for changed resources
  infra diff --env-a dev --env-b prod --verbose
  ```
- **Analyze dependencies and impact:**
  ```bash
  # Show full dependency graph for environment
  infra analyze dependencies --env prod --format mermaid > deps.mmd

  # Analyze dependencies for specific resource
  infra analyze dependencies --env prod --resource proxmox:vm-web-01

  # Analyze impact of changing a resource
  infra analyze impact --env prod --resource vm-database-01
  # Shows: What resources depend on vm-database-01 and risk level
  ```
- **Reset component configuration:**
  ```bash
  # Reset Kea DHCPv4 configuration on OPNsense
  infra reset --env prod --provider opnsense --component kea/dhcpv4

  # Reset both DHCPv4 and DHCPv6 (without confirmation)
  infra reset --env prod --provider opnsense --component kea/dhcp --auto-approve
  ```
- **Export provider configuration:**
  ```bash
  # Export all Proxmox resources to YAML
  config export --env prod --output ./exported --provider proxmox

  # Export only VMs from specific node
  config export --env prod --output ./exported --provider proxmox --node pve01 --resource-type vm

  # Export network configurations
  config export --env prod --output ./exported --provider proxmox --resource-type network
  ```
- **List rollback points:**
  ```bash
  # List all available rollback points
  infra rollback-points --env prod

  # List only last 5 rollback points
  infra rollback-points --env prod --limit 5
  ```
- **Check configuration health:**
  ```bash
  # Full config repo health check
  config doctor

  # Detailed check with resource counts per environment
  config doctor --deep

  # JSON output for scripting or CI pipelines
  config doctor --format json
  ```
- **Policy enforcement in CI:**
  ```bash
  infra policies check --env prod --enforce
  ```
- **Drift detection:**
  ```bash
  infra drift --env prod
  ```
- **Manage deployment locks:**
  ```bash
  # Wait up to 5 minutes for an active lock before failing
  infra apply --env prod --lock-timeout 300

  # Use a longer TTL as a safety net (the lock is auto-extended while the
  # process runs; this only matters for recovering from a crashed holder).
  infra apply --env prod --lock-ttl 1800

  # Inspect current locks
  infra unlock --list

  # Release an expired lock
  infra unlock --env prod

  # Force-release an active lock (use with caution)
  infra unlock --env prod --force --yes
  ```
- **Graph dependencies:**
  ```bash
  infra analyze graph --env dev --format mermaid > graph.mmd
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
- **Symptom:** `infra envs` shows FS-ONLY or DB-ONLY for some environments. **Fix:** Run `config doctor --deep` for a detailed consistency report. FS-ONLY means the environment directory exists but is not tracked in the state database (run `infra plan` to populate). DB-ONLY means the state database has records for an environment whose config directory has been removed.
- **Symptom:** Rollback fails with "deployment not found". **Fix:** Use `infra history` or `infra rollback-points --env <env>` to verify deployment ID exists and has rollback data available.
- **Symptom:** State backup skips database file. **Fix:** Ensure using SQLite backend (default); PostgreSQL and other remote databases cannot be backed up via file copy.
- **Symptom:** `diff` shows no differences but configs look different. **Fix:** Check if provider filtering is hiding changes; remove `--provider` flag to see all differences.
- **Symptom:** `infra analyze dependencies` or `infra analyze impact` shows unexpected results. **Fix:** Ensure resources are loaded from YAML; check `get_dependencies()` implementation in provider.
- **Symptom:** `reset` command fails or doesn't clean properly. **Fix:** Verify provider and component names are correct; currently only supports OPNsense Kea components (kea/dhcpv4, kea/dhcpv6, kea/dhcp).
- **Symptom:** `config export` fails to connect. **Fix:** Verify environment credentials in `settings.yaml`; ensure provider API is accessible and credentials have read permissions.

---

Last updated: 2026-04-13 GMT


---
[Back to Table of Contents](../index.md)
