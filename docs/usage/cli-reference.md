# InfraFoundry CLI Reference

## Overview

The InfraFoundry CLI (`foundry`) organizes infrastructure management into a three-tier command hierarchy. Each command group owns a distinct domain, keeping concerns separated and making it clear where to look for a given operation.

## Command Domain Model

InfraFoundry commands are organized into five domain groups plus two top-level utilities:

| Domain | Command Group | Responsibility |
|--------|--------------|----------------|
| **System** | `foundry doctor` | Binary dependency checks (Terraform, Ansible, SOPS, Age) |
| **Shell** | `foundry completion` | Shell autocompletion setup |
| **Configuration** | `foundry config` | Config repo management: environments, schemas, diffs, health checks, blueprints, exports, migrations |
| **Infrastructure** | `foundry infra` | Day-2 operations: plan, apply, destroy, drift, rollback, security, testing, analysis |
| **State** | `foundry state` | State database management: init, backup, resources, backend migration, audit trail |
| **Secrets** | `foundry secrets` | SOPS/age secret lifecycle: init, encrypt, decrypt, rotate |
| **Policy** | `foundry policy` | Policy listing and enforcement |

**The three-tier doctor pattern** illustrates the hierarchy:

- `foundry doctor` -- checks system-level binary dependencies
- `foundry config doctor` -- checks config repo structure and health
- `foundry infra doctor --env <env>` -- validates against live provider APIs

## Audience and Prerequisites

- **Audience:** Operators and CI systems running InfraFoundry workflows.
- **Prerequisites:** Config repo available (`--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`), `foundry` installed via `uv`, and provider credentials/secrets configured.

## Quick Reference

**"I want to..."**

| Goal | Command |
|------|---------|
| Check if tools are installed | `foundry doctor` |
| Check config repo health | `foundry config doctor [--deep]` |
| Validate against provider APIs | `foundry infra doctor --env <env>` |
| List environments | `foundry config envs` |
| Compare two environments | `foundry config diff --env-a dev --env-b prod` |
| Show resolved config | `foundry config show --env <env>` |
| Create a new environment | `foundry config create <name>` |
| Create from a blueprint | `foundry config new create <blueprint> <dir>` |
| Export Proxmox config to YAML | `foundry provider proxmox export --env <env> --output <dir>` |
| Dump raw Proxmox API state | `foundry provider proxmox dump --env <env> --output <file>.json` |
| Generate JSON schemas for IDE | `foundry config schema export` |
| Migrate existing infra to config | `foundry config migrate --env <env> --provider opnsense --component <comp>` |
| Plan changes | `foundry infra plan --env <env>` |
| Apply changes | `foundry infra apply --env <env>` |
| Destroy infrastructure | `foundry infra destroy --env <env>` |
| Detect drift | `foundry infra drift detect --env <env>` |
| Auto-remediate drift | `foundry infra drift remediate --env <env> --auto-approve` |
| View drift history | `foundry infra drift history` |
| Show deployment status | `foundry infra deployed --env <env>` |
| View deployment history | `foundry infra history --env <env>` |
| List packages in an environment | `foundry infra list --env <env>` |
| Move a package between envs | `foundry infra move-package --env <src> --package <pkg> --to-env <dst>` |
| Analyze dependencies | `foundry infra analyze dependencies --env <env>` |
| Analyze change impact | `foundry infra analyze impact --env <env> --resource <name>` |
| Visualize dependency graph | `foundry infra analyze graph --env <env> --format mermaid` |
| Rollback to previous deployment | `foundry infra rollback to <deployment-id>` |
| List rollback points | `foundry infra rollback list --env <env>` |
| Run security scan | `foundry infra security --env <env>` |
| Run infrastructure tests | `foundry infra test --env <env>` |
| Show infrastructure status | `foundry infra status --env <env>` |
| Reset a provider component | `foundry infra reset --env <env> --provider opnsense --component <comp>` |
| Manage deployment locks | `foundry infra unlock --list` |
| Initialize state database | `foundry state init` |
| List resources in state | `foundry state list --env <env>` |
| List tracked resources | `foundry state resources` |
| Backup state database | `foundry state backup` |
| Validate backend config | `foundry state backend validate --env <env>` |
| Migrate backend | `foundry state backend migrate --env <env>` |
| View audit trail | `foundry state audit list` |
| Export audit entries | `foundry state audit export --output <file>` |
| Verify audit integrity | `foundry state audit verify <entry-id>` |
| Initialize secrets | `foundry secrets init` |
| Encrypt a file | `foundry secrets encrypt <file>` |
| Decrypt a file | `foundry secrets decrypt <file>` |
| Rotate encryption keys | `foundry secrets rotate --env <env> --generate-new-key` |
| List policies | `foundry policy list` |
| Install shell completion | `foundry completion bash` |

## Global Options

```
foundry [OPTIONS] COMMAND [ARGS]...

Options:
  --version                              Show version and exit
  --debug                                Enable debug mode (full tracebacks)
  -c, --config-dir DIRECTORY             Path to config repo (overrides INFRAFOUNDRY_CONFIG_REPO)
  --strict-mode / --no-strict-mode       Fail on missing secrets/snippets
  --fail-on-missing-secrets / --allow-missing-secrets
  --fail-on-missing-snippets / --allow-missing-snippets
```

**Environment variables:** `INFRAFOUNDRY_CONFIG_REPO`, `INFRAFOUNDRY_STRICT_MODE`, `INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS`, `INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS`.

## Top-Level Commands

### `foundry doctor`

Check system dependencies (Terraform, OpenTofu, Ansible, SOPS, Age).

```bash
foundry doctor                  # text output
foundry doctor --format json    # JSON for scripting
```

**Options:** `--format [text|json]`

### `foundry completion`

Install or remove shell completion.

```bash
foundry completion bash         # install for bash
foundry completion zsh          # install for zsh
foundry completion fish         # install for fish
foundry completion uninstall    # remove completion
```

---

## Config Group (`foundry config`)

Configuration repo management: environments, schemas, diffs, health, blueprints, exports, and migrations.

### `config doctor`

Check configuration repository health: repo structure, environments, state backend, SOPS keys, state/filesystem consistency, blueprint validation.

```bash
foundry config doctor                 # basic health check
foundry config doctor --deep          # include per-environment resource counts
foundry config doctor --format json   # JSON output for CI
```

**Options:** `--format [text|json]`, `--deep`

### `config envs`

List available environments with sync status (OK, FS-ONLY, DB-ONLY).

```bash
foundry config envs
foundry config envs --format json
```

**Options:** `--format [text|json]`

### `config diff`

Compare configurations between two environments.

```bash
foundry config diff --env-a dev --env-b prod
foundry config diff --env-a dev --env-b prod --provider proxmox
foundry config diff --env-a dev --env-b prod --verbose
```

**Options:** `--env-a TEXT` (required), `--env-b TEXT` (required), `-p/--provider TEXT`, `-v/--verbose`

### `config show`

Show resolved configuration for an environment after variable substitution.

```bash
foundry config show --env dev
foundry config show --env dev --provider proxmox
foundry config show --env dev --resource my-vm
foundry config show --env dev --format yaml
foundry config show --env dev --settings-only
```

**Options:** `-e/--env TEXT` (required), `-p/--provider TEXT`, `-t/--resource-type TEXT`, `-r/--resource TEXT`, `--format [table|yaml|json]`, `--settings-only`

### `config create`

Create a new environment. Optionally scaffold from an existing environment.
SOPS-encrypted settings.yaml files are handled transparently.

```bash
foundry config create staging
foundry config create staging --from dev
foundry config create prod --from staging -d "Production environment"
```

**Options:** `--from TEXT`, `-d/--description TEXT`, `-f/--force`

### `config new`

Create infrastructure from blueprints.

```bash
foundry config new create basic-vm ./my-new-vm
```

**Subcommands:** `create <blueprint-name> <target-dir>`

### `config migrate`

Migrate existing infrastructure to InfraFoundry configuration by reading from provider APIs.

```bash
foundry config migrate --env prod --provider opnsense --component kea/dhcp
foundry config migrate --env prod --provider opnsense --component isc-to-kea
foundry config migrate --env prod --provider opnsense --component isc-to-kea -i lan -i wan
foundry config migrate --env prod --provider opnsense --component isc-to-kea --dry-run
```

**Options:** `-e/--env TEXT` (required), `-p/--provider [opnsense]` (required), `-c/--component [kea/dhcp|isc-to-kea]` (required), `-i/--interfaces TEXT` (repeatable), `-o/--output TEXT`, `--dry-run`

### `config schema`

Export JSON schemas for IDE autocomplete.

```bash
foundry config schema export                    # export to .schemas/
foundry config schema export --output ./schemas # export to custom dir
foundry config schema list                      # list available schemas
foundry config schema show settings             # show a schema
foundry config schema show resources --format yaml
```

**Subcommands:** `export [--output PATH]`, `list`, `show <name> [--format json|yaml]`

Available schemas: `settings`, `resources`, `backend`, `hooks`, `resource`.

---

## Provider Group (`foundry provider`)

Provider-specific commands. Subcommands are registered dynamically by
each provider package's plugin entry point (see
[ADR 0005](../decisions/0005-provider-cli-extensibility.md)).

!!! warning "Breaking change"
    `foundry config export --provider proxmox` was removed. Use
    `foundry provider proxmox export` instead.

### `provider proxmox dump`

Dump raw Proxmox cluster API state as a JSON snapshot. Captures
everything the PVE API returns for cluster, access, pools, storage, every
node, and every VM/container. Writes atomically and incrementally so an
interrupted dump leaves valid JSON on disk. Per-call failures are
captured inline as `{"__timeout__": true, "path": ...}` or
`{"__error__": "...", "path": ...}`.

```bash
foundry provider proxmox dump --env prod --output pve-state.json
foundry provider proxmox dump --env prod --output pve-state.json --timeout 60
```

**Options:** `-e/--env TEXT` (required), `-o/--output FILE` (required),
`--timeout INTEGER` (default: 20).

### `provider proxmox export`

Export existing Proxmox VMs, bridge networks, and storage pools to
InfraFoundry YAML. Useful when adopting an existing cluster.

```bash
foundry provider proxmox export --env prod --output ./exported
foundry provider proxmox export --env prod --output ./exported --node pve01
foundry provider proxmox export --env prod --output ./exported --resource-type vm
```

**Options:** `-e/--env TEXT` (required), `-o/--output DIRECTORY`
(required), `--node TEXT`, `--resource-type [vm|network|storage]`.

See [the Proxmox provider guide](../providers/proxmox.md) for the
dump-vs-export decision tree and credential setup.

---

## Infra Group (`foundry infra`)

Day-2 infrastructure operations: plan, apply, destroy, drift, rollback, security, testing, and analysis.

### `infra doctor`

Validate infrastructure against provider APIs (connectivity, nodes, storage, networks, templates, resource IDs, MAC conflicts).

```bash
foundry infra doctor --env dev
foundry infra doctor --env dev --resource vm-01 --resource vm-02
foundry infra doctor --env dev --verbose
```

**Options:** `-e/--env TEXT` (required), `-r/--resource TEXT` (repeatable), `-v/--verbose`

### `infra plan`

Generate Terraform/Ansible files for an environment.

```bash
foundry infra plan --env dev
foundry infra plan --env dev --dry-run
foundry infra plan --env dev --resource vm-01 --resource vm-02
foundry infra plan --env dev --package ontap-cluster
foundry infra plan --env dev --enforce-policies
```

**Options:** `-e/--env TEXT` (required), `--dry-run`, `-r/--resource TEXT` (repeatable), `-p/--package TEXT`, `--enforce-policies`

Note: `--resource` and `--package` are mutually exclusive.

### `infra apply`

Deploy infrastructure changes.

```bash
foundry infra apply --env dev
foundry infra apply --env dev --auto-approve
foundry infra apply --env dev --package ontap-cluster --auto-approve
foundry infra apply --env dev --parallel --max-workers 8
foundry infra apply --env dev --lock-timeout 300 --lock-ttl 1800
```

**Options:** `-e/--env TEXT` (required), `--auto-approve`, `-r/--resource TEXT` (repeatable), `-p/--package TEXT`, `--parallel`, `--max-workers INTEGER` (default: 4), `--lock-timeout INTEGER` (default: 0), `--lock-ttl INTEGER` (default: 600)

**Lock options:** `--lock-timeout` sets how long to wait for an existing lock before failing. `--lock-ttl` sets how long the lock is valid before considered stale (auto-extended every `ttl / 3` while running).

### `infra destroy`

Tear down infrastructure.

```bash
foundry infra destroy --env dev --auto-approve
foundry infra destroy --env dev --package ontap-cluster
foundry infra destroy --env dev --resource vm-01
```

**Options:** `-e/--env TEXT` (required), `--auto-approve`, `-r/--resource TEXT` (repeatable), `-p/--package TEXT`, `--lock-timeout INTEGER`, `--lock-ttl INTEGER`

### `infra drift`

Detect and remediate infrastructure drift. This is a command group with three subcommands.

```bash
# Detect drift
foundry infra drift detect --env dev

# Auto-remediate within configured thresholds
foundry infra drift remediate --env dev --auto-approve
foundry infra drift remediate --env dev --dry-run
foundry infra drift remediate --env dev --auto-approve --max-changes 10
foundry infra drift remediate --env dev --auto-approve --max-add 5 --max-change 3 --max-destroy 0

# View remediation history
foundry infra drift history
foundry infra drift history --env dev --limit 20
```

**Subcommands:**

- `detect` -- `-e/--env TEXT` (required)
- `remediate` -- `-e/--env TEXT` (required), `--auto-approve`, `--dry-run`, `--max-changes INTEGER`, `--max-add INTEGER`, `--max-change INTEGER`, `--max-destroy INTEGER`
- `history` -- `-e/--env TEXT`, `-n/--limit INTEGER` (default: 10)

### `infra deployed`

Show deployment status and resources for an environment.

```bash
foundry infra deployed --env prod
foundry infra deployed --env prod --format json
```

**Options:** `-e/--env TEXT` (required), `--format [text|json]`

### `infra history`

Show deployment history with optional filters.

```bash
foundry infra history --env prod
foundry infra history --env prod --command apply --status completed
foundry infra history --limit 20
foundry infra history --exclude-dry-runs --format json
```

**Options:** `-e/--env TEXT`, `-c/--command [plan|apply|destroy]`, `-s/--status [completed|failed|in_progress|planned]`, `-n/--limit INTEGER`, `--exclude-dry-runs`, `--format [text|json]`

### `infra list`

List configured packages in an environment (from YAML configuration).

```bash
foundry infra list --env dev
foundry infra list --env dev --format json
```

**Options:** `-e/--env TEXT` (required), `--format [text|json]`

### `infra move-package`

Move a package from one environment to another. Relocates the config directory, copies Terraform state, removes moved resources from source state, and updates the InfraFoundry state database.

```bash
foundry infra move-package --env dev --package my-app --to-env staging
foundry infra move-package --env dev --package my-app --to-env staging --create-env
foundry infra move-package --env dev --package my-app --to-env staging --dry-run
```

**Options:** `-e/--env TEXT` (required), `-p/--package TEXT` (required), `--to-env TEXT` (required), `--create-env`, `--dry-run`

### `infra analyze`

Analysis and visualization command group.

```bash
# Show dependency graph
foundry infra analyze dependencies --env prod --format mermaid > deps.mmd
foundry infra analyze dependencies --env prod --resource proxmox:vm-web-01

# Analyze change impact
foundry infra analyze impact --env prod --resource vm-database-01

# Generate visual topology
foundry infra analyze graph --env dev --format mermaid > graph.mmd
```

**Subcommands:**

- `dependencies` -- `-e/--env TEXT` (required), `-r/--resource TEXT`, `--format [list|mermaid]` (default: list)
- `impact` -- `-e/--env TEXT` (required), `-r/--resource TEXT` (required)
- `graph` -- `-e/--env TEXT` (required), `-f/--format [mermaid]`

### `infra rollback`

Rollback infrastructure to a previous deployment state. This is a command group with two subcommands.

```bash
# List available rollback points
foundry infra rollback list --env prod
foundry infra rollback list --env prod --limit 5

# Rollback to a specific deployment
foundry infra rollback to 42
foundry infra rollback to 42 --auto-approve
```

**Subcommands:**

- `list` -- `-e/--env TEXT` (required), `-l/--limit INTEGER`
- `to <deployment-id>` -- `--auto-approve`

### `infra security`

Scan infrastructure configurations for security issues using Checkov.

```bash
foundry infra security --env prod
foundry infra security --env dev --severity medium
foundry infra security --env staging --skip-check CKV_AWS_1 --skip-check CKV_AWS_2
foundry infra security --env prod --output json
```

**Options:** `-e/--env TEXT` (required), `-s/--severity [critical|high|medium|low|info]` (default: high), `--skip-check TEXT` (repeatable), `-o/--output [table|json]`, `--timeout INTEGER` (default: 300)

### `infra test`

Run infrastructure tests against configurations.

```bash
foundry infra test --env prod
foundry infra test --env dev --verbose
foundry infra test --env staging --test no_duplicate_names
foundry infra test --env prod --output json
```

**Options:** `-e/--env TEXT` (required), `-t/--test TEXT` (repeatable), `-o/--output [table|json]`, `-v/--verbose`

### `infra status`

Show infrastructure status for an environment.

```bash
foundry infra status --env prod
```

**Options:** `-e/--env TEXT` (required)

### `infra reset`

Reset (wipe) infrastructure components for a clean reapply. Currently supports OPNsense Kea components.

```bash
foundry infra reset --env prod --provider opnsense --component kea/dhcpv4
foundry infra reset --env prod --provider opnsense --component kea/dhcp --auto-approve
```

**Options:** `-e/--env TEXT` (required), `-p/--provider [opnsense]` (required), `-c/--component [kea/dhcpv4|kea/dhcpv6|kea/dhcp]` (required), `--auto-approve`

### `infra unlock`

Release or inspect deployment locks.

```bash
foundry infra unlock --list                    # list all locks
foundry infra unlock --env prod                # release expired lock
foundry infra unlock --env prod --force --yes  # force-release active lock
```

**Options:** `-e/--env TEXT` (required unless `--list`), `--force`, `--yes`, `--list`

Set `INFRAFOUNDRY_SKIP_LOCK=1` to bypass locking entirely (emergency use only).

---

## State Group (`foundry state`)

State database management: initialization, backup, resource tracking, backend migration, and audit trail.

### `state init`

Initialize the InfraFoundry state database (SQLite by default).

```bash
foundry state init
```

### `state list`

List all resources in an environment from the state database.

```bash
foundry state list --env prod
foundry state list --env prod --provider proxmox --type vms
foundry state list --env prod --format json
```

**Options:** `-e/--env TEXT` (required), `-p/--provider TEXT`, `-t/--type TEXT`, `--format [text|json]`

### `state resources`

List tracked infrastructure resources from the state database.

```bash
foundry state resources
foundry state resources --env prod --state ACTIVE
foundry state resources --provider proxmox --type vm
```

**Options:** `-e/--env TEXT`, `-p/--provider TEXT`, `-t/--type TEXT`, `-s/--state [PLANNED|CREATING|ACTIVE|DELETING|DELETED|FAILED]`

### `state backup`

Create a timestamped backup of the state database. Optionally includes the `generated/` directory.

```bash
foundry state backup
foundry state backup --output-dir ./backups
foundry state backup --output-dir ./backups --include-generated
```

**Options:** `-o/--output-dir DIRECTORY`, `-g/--include-generated`

### `state backend`

Manage Terraform backend configuration.

```bash
# Validate backend configuration
foundry state backend validate --env prod

# Migrate state between backends
foundry state backend migrate --env prod
foundry state backend migrate --env prod --from local --to s3
foundry state backend migrate --env prod --auto-approve
```

**Subcommands:**

- `validate` -- `-e/--env TEXT` (required)
- `migrate` -- `-e/--env TEXT` (required), `--from [local|s3|gcs|azurerm|postgres|remote]`, `--to [local|s3|gcs|azurerm|postgres|remote]`, `--auto-approve`

### `state audit`

View and export audit trail for compliance.

```bash
# List audit entries
foundry state audit list --env prod
foundry state audit list --user admin --since 2024-01-01
foundry state audit list --action apply_completed --limit 100

# Export for compliance reporting
foundry state audit export --output audit.json
foundry state audit export --format csv --output report.csv --env prod --since 2024-01-01

# Verify integrity
foundry state audit verify 123
```

**Subcommands:**

- `list` -- `-e/--env TEXT`, `-u/--user TEXT`, `-a/--action TEXT`, `--since TEXT`, `--until TEXT`, `-n/--limit INTEGER` (default: 50), `--format [text|json]`
- `export` -- `-o/--output FILE` (required), `-f/--format [json|csv]`, `-e/--env TEXT`, `-u/--user TEXT`, `-a/--action TEXT`, `--since TEXT`, `--until TEXT`
- `verify <entry-id>`

---

## Secrets Group (`foundry secrets`)

SOPS/age secret lifecycle management.

### `secrets init`

Initialize secrets with a new age key.

```bash
foundry secrets init
foundry secrets init --key-file /path/to/age.key
```

**Options:** `--key-file TEXT`

### `secrets encrypt`

Encrypt a file with SOPS.

```bash
foundry secrets encrypt envs/dev/secrets.yaml
```

### `secrets decrypt`

Decrypt and display a SOPS-encrypted file.

```bash
foundry secrets decrypt envs/dev/secrets.yaml
```

### `secrets rotate`

Rotate secrets with a new age encryption key. Re-encrypts all secrets with a new key, with automatic rollback on failure.

```bash
foundry secrets rotate --env dev --generate-new-key
foundry secrets rotate --env prod --new-key-file /path/to/new_age.key
foundry secrets rotate --env dev --generate-new-key --files proxmox.yaml --files opnsense.yaml
foundry secrets rotate --env dev --generate-new-key --dry-run
```

**Options:** `-e/--env TEXT` (required), `--new-key-file PATH`, `--generate-new-key`, `--files TEXT` (repeatable), `--no-verify`, `--no-backup`, `--dry-run`

---

## Policy Group (`foundry policy`)

### `policy list`

List available infrastructure policies.

```bash
foundry policy list
foundry policy list --env prod
```

**Options:** `-e/--env TEXT`

---

## Configuration Details

- **State:** InfraFoundry DB at `~/.infrafoundry/state.db` (unless overridden); Terraform state under `generated/{env}/terraform/{provider}`.
- **Generated artifacts:** `generated/{env}/{terraform|ansible}/{provider}`; always reproducible from YAML.

## Full Command Tree

```
foundry
+-- doctor [--format text|json]
+-- completion
|   +-- bash
|   +-- zsh
|   +-- fish
|   +-- uninstall
+-- config
|   +-- doctor [--format text|json] [--deep]
|   +-- envs [--format text|json]
|   +-- diff --env-a <env1> --env-b <env2> [-p provider] [-v]
|   +-- show -e <env> [-p provider] [-t type] [-r resource] [--format] [--settings-only]
|   +-- create <name> [--from <env>] [-d desc] [-f]
|   +-- new
|   |   +-- create <blueprint> <target-dir>
|   +-- migrate -e <env> -p <provider> -c <component> [-i interfaces] [--dry-run]
|   +-- schema
|       +-- export [-o path]
|       +-- list
|       +-- show <name> [--format json|yaml]
+-- provider
|   +-- <provider-name>        (discovered via infrafoundry.providers entry points)
|       +-- ...                (subcommands contributed by each provider)
|   +-- proxmox
|       +-- dump -e <env> -o <file.json> [--timeout <seconds>]
|       +-- export -e <env> -o <dir> [--node] [--resource-type]
+-- infra
|   +-- doctor -e <env> [-r resource] [-v]
|   +-- plan -e <env> [--dry-run] [-r resource] [-p package] [--enforce-policies]
|   +-- apply -e <env> [--auto-approve] [-r resource] [-p package] [--parallel] [--max-workers] [--lock-timeout] [--lock-ttl]
|   +-- destroy -e <env> [--auto-approve] [-r resource] [-p package] [--lock-timeout] [--lock-ttl]
|   +-- drift
|   |   +-- detect -e <env>
|   |   +-- remediate -e <env> [--auto-approve] [--dry-run] [--max-changes] [--max-add] [--max-change] [--max-destroy]
|   |   +-- history [-e env] [-n limit]
|   +-- deployed -e <env> [--format text|json]
|   +-- history [-e env] [-c command] [-s status] [-n limit] [--exclude-dry-runs] [--format text|json]
|   +-- list -e <env> [--format text|json]
|   +-- move-package -e <env> -p <package> --to-env <env> [--create-env] [--dry-run]
|   +-- analyze
|   |   +-- dependencies -e <env> [-r resource] [--format list|mermaid]
|   |   +-- impact -e <env> -r <resource>
|   |   +-- graph -e <env> [-f mermaid]
|   +-- rollback
|   |   +-- list -e <env> [-l limit]
|   |   +-- to <deployment-id> [--auto-approve]
|   +-- security -e <env> [-s severity] [--skip-check] [-o table|json] [--timeout]
|   +-- test -e <env> [-t test] [-o table|json] [-v]
|   +-- status -e <env>
|   +-- reset -e <env> -p <provider> -c <component> [--auto-approve]
|   +-- unlock [-e env] [--force] [--yes] [--list]
+-- state
|   +-- init
|   +-- list -e <env> [-p provider] [-t type] [--format text|json]
|   +-- resources [-e env] [-p provider] [-t type] [-s state]
|   +-- backup [-o dir] [-g]
|   +-- backend
|   |   +-- validate -e <env>
|   |   +-- migrate -e <env> [--from backend] [--to backend] [--auto-approve]
|   +-- audit
|       +-- list [-e env] [-u user] [-a action] [--since] [--until] [-n limit] [--format text|json]
|       +-- export -o <file> [-f json|csv] [-e env] [-u user] [-a action] [--since] [--until]
|       +-- verify <entry-id>
+-- secrets
|   +-- init [--key-file]
|   +-- encrypt <file>
|   +-- decrypt <file>
|   +-- rotate -e <env> [--new-key-file | --generate-new-key] [--files] [--no-verify] [--no-backup] [--dry-run]
+-- policy
    +-- list [-e env]
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
- **Symptom:** Unexpected resource lists. **Fix:** Use `foundry infra list` (YAML-defined packages) vs `foundry state resources` (state DB tracked resources) to differentiate declared vs tracked resources.
- **Symptom:** `config envs` shows FS-ONLY or DB-ONLY. **Fix:** Run `foundry config doctor --deep` for a detailed consistency report. FS-ONLY means the environment directory exists but is not tracked in the state database (run `foundry infra plan` to populate). DB-ONLY means the state database has records for an environment whose config directory has been removed.
- **Symptom:** Rollback fails with "deployment not found". **Fix:** Use `foundry infra history` or `foundry infra rollback list --env <env>` to verify deployment ID exists and has rollback data available.
- **Symptom:** State backup skips database file. **Fix:** Ensure using SQLite backend (default); PostgreSQL and other remote databases cannot be backed up via file copy.
- **Symptom:** `config diff` shows no differences but configs look different. **Fix:** Check if provider filtering is hiding changes; remove `--provider` flag to see all differences.
- **Symptom:** `infra analyze` shows unexpected results. **Fix:** Ensure resources are loaded from YAML; check `get_dependencies()` implementation in provider.
- **Symptom:** `infra reset` fails or doesn't clean properly. **Fix:** Verify provider and component names are correct; currently only supports OPNsense Kea components (kea/dhcpv4, kea/dhcpv6, kea/dhcp).
- **Symptom:** `provider proxmox export` or `provider proxmox dump` fails to connect. **Fix:** Verify environment credentials in `settings.yaml`; ensure the PVE API is reachable and the token has read permissions. For a slow cluster, increase `--timeout` on `dump`.

---

Last updated: 2026-04-13 GMT


---
[Back to Table of Contents](../index.md)
