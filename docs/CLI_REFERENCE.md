# InfraFoundry CLI Reference

Complete reference for all InfraFoundry CLI commands.

## Global Options

- `--config-dir / -c PATH` – Override `INFRAFOUNDRY_CONFIG_REPO` for configs.
- `--strict-mode / --no-strict-mode` – Toggle strict mode (fails on missing secrets/snippets).
- `--fail-on-missing-secrets / --allow-missing-secrets` – Control behavior when secrets files are missing.
- `--fail-on-missing-snippets / --allow-missing-snippets` – Control behavior when cloud-init snippets are missing.

Environment equivalents:

- `INFRAFOUNDRY_STRICT_MODE`
- `INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS`
- `INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS`

When strict mode is enabled, both snippet and secret warnings become errors automatically.

## Core Commands

### `infra init`
Initialize InfraFoundry state database.

```bash
infra init
```

Creates `~/.infrafoundry/state.db` (SQLite) for tracking deployments and resources.

---

### `infra envs`
List available environments.

```bash
infra envs
```

Shows all environments found in the configuration directory.

---

### `infra plan`
Generate infrastructure configurations (Terraform + Ansible).

```bash
# Plan entire environment
infra plan --env dev

# Plan specific resources
infra plan --env dev --resource vm-01 --resource vm-02

# Dry-run (validate only, no file generation)
infra plan --env dev --dry-run
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--resource`, `-r` - Target specific resources (multiple allowed)
- `--dry-run` - Validate without generating files

---

### `infra apply`
Apply infrastructure changes (generate + execute Terraform/Ansible).

```bash
# Apply entire environment
infra apply --env dev

# Apply specific resources
infra apply --env dev --resource vm-01

# Auto-approve (skip confirmation)
infra apply --env dev --auto-approve
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--resource`, `-r` - Target specific resources (multiple allowed)
- `--auto-approve` - Skip confirmation prompts

**What it does:**
1. Generates Terraform `.tf` files
2. Generates Ansible playbooks
3. Runs `terraform init` (first time)
4. Runs `terraform apply`
5. Runs `ansible-playbook`
6. Tracks deployment in state database

---

### `infra destroy`
Destroy infrastructure resources.

```bash
# Destroy entire environment
infra destroy --env dev

# Destroy specific resources
infra destroy --env dev --resource vm-01

# Auto-approve (skip confirmation)
infra destroy --env dev --auto-approve
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--resource`, `-r` - Target specific resources (multiple allowed)
- `--auto-approve` - Skip confirmation prompts

---

### `infra status`
Show deployment status for an environment.

```bash
infra status --env prod
```

Shows current state of all resources in the environment.

---

### `infra list`
List resources in an environment.

```bash
# List all resources
infra list --env dev

# Filter by provider
infra list --env dev --provider proxmox

# Filter by resource type
infra list --env dev --type vms

# Combine filters
infra list --env dev --provider proxmox --type vms
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--provider` - Filter by provider (proxmox, opnsense, kubernetes)
- `--type` - Filter by resource type (vms, networks, firewall_rules, etc.)

---

### `infra history`
View deployment history.

```bash
# All deployments
infra history

# Filter by environment
infra history --env prod

# Limit results
infra history --limit 20
```

**Options:**
- `--env`, `-e` - Filter by environment
- `--limit`, `-l` - Limit number of results (default: 50)

Shows:
- Deployment ID
- Environment
- Command (plan/apply/destroy)
- Status (completed/failed/in_progress)
- Timestamp
- User

---

## Advanced Operations

### `infra drift`
Detect infrastructure drift from declared configuration.

```bash
infra drift --env prod
```

**What it checks:**
- Resources modified outside InfraFoundry
- Resources manually added
- Resources unexpectedly deleted
- Configuration changes not in YAML

**Output:**
- Per-provider drift summary
- Count of resources to add/change/destroy
- Detailed change descriptions

---

### `infra impact`
Analyze impact of changing a resource.

```bash
infra impact --env prod --resource db-template
```

**Shows:**
- All resources that depend on the specified resource
- Risk level (LOW, MEDIUM, HIGH, CRITICAL)
- Total number of dependent resources
- Suggested actions

**Risk Levels:**
- **LOW**: 0 dependents
- **MEDIUM**: 1-5 dependents
- **HIGH**: 6-20 dependents
- **CRITICAL**: 21+ dependents

---

### `infra validate`
Validate infrastructure configuration before deployment.

```bash
# Validate entire environment
infra validate --env test

# Validate specific resources
infra validate --env test --resource vm-01 --resource vm-02

# Show detailed output
infra validate --env test --verbose
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--resource`, `-r` - Validate specific resources (multiple allowed)
- `--verbose`, `-v` - Show detailed validation including passing checks

**Validation Checks:**
- ✅ API connectivity to all providers
- ✅ Nodes/hosts exist and are online
- ✅ Storage pools exist and are active
- ✅ Network bridges are configured
- ✅ Templates/images exist for cloning
- ✅ VMIDs/resource IDs are available
- ✅ No MAC address conflicts
- ✅ Referenced resources exist

---

### `infra policies`
Manage and check infrastructure policies.

```bash
# List available policies
infra policies list

# Check resources against policies
infra policies check --env prod

# Enforce policies (block on errors)
infra policies check --env prod --enforce
```

**Policy Types:**
- Resource limits (CPU, memory, disk)
- Naming conventions
- Security requirements
- Compliance rules

**Policy Levels:**
- **ERROR**: Blocks deployment
- **WARNING**: Shows warning but allows deployment
- **INFO**: Informational only

---

### `infra rollback`
Rollback to a previous deployment.

```bash
# List available rollback points
infra rollback-points --env prod

# Rollback to specific deployment
infra rollback --env prod --to-deployment 42

# Rollback to previous deployment
infra rollback --env prod --to-previous

# Auto-approve
infra rollback --env prod --to-previous --auto-approve
```

**Options:**
- `--env`, `-e` - Environment name (required)
- `--to-deployment` - Specific deployment ID to rollback to
- `--to-previous` - Rollback to previous deployment
- `--auto-approve` - Skip confirmation

---

## Secret Management

### `infra secrets init`
Initialize age encryption for secrets.

```bash
infra secrets init
```

Creates age encryption keys for each environment:
- `envs/dev/age.key`
- `envs/prod/age.key`
- `.sops.yaml` configuration

---

### `infra secrets encrypt`
Encrypt a secrets file with SOPS.

```bash
infra secrets encrypt envs/dev/settings.yaml
```

Encrypts the file in-place using age encryption.

---

### `infra secrets decrypt`
Decrypt and view a secrets file.

```bash
infra secrets decrypt envs/dev/settings.yaml
```

Displays decrypted contents (does not modify file).

---

## Provider-Specific Commands

### `infra reset`
Reset (wipe) specific infrastructure components.

```bash
# Reset Kea DHCPv4 configuration
infra reset --env prod --provider opnsense --component kea/dhcpv4

# Reset Kea DHCPv6 configuration
infra reset --env prod --provider opnsense --component kea/dhcpv6

# Reset both DHCPv4 and DHCPv6
infra reset --env prod --provider opnsense --component kea/dhcp

# Auto-approve
infra reset --env prod --provider opnsense --component kea/dhcp --auto-approve
```

**Use Cases:**
- Clear existing DHCP config before applying InfraFoundry-managed configuration
- Resolve configuration drift by wiping and reapplying
- Clean slate for testing configuration changes

---

### `infra migrate`
Migrate existing infrastructure to InfraFoundry YAML.

```bash
# Migrate existing Kea DHCP configuration
infra migrate --env prod --provider opnsense --component kea/dhcp

# Migrate legacy ISC DHCP to Kea DHCP format
infra migrate --env prod --provider opnsense --component isc-to-kea

# Migrate specific interfaces only
infra migrate --env prod --provider opnsense --component isc-to-kea -i lan -i wan

# Preview migration without writing files
infra migrate --env prod --provider opnsense --component isc-to-kea --dry-run

# Custom output location
infra migrate --env prod --provider opnsense --component isc-to-kea \
    -o custom/path/dhcp-config.yaml
```

**Supported Migrations:**
- **kea/dhcp**: Export existing Kea DHCP configuration to YAML
- **isc-to-kea**: Convert legacy ISC DHCP to Kea DHCP format

**ISC to Kea Migration:**
- Converts both DHCPv4 and DHCPv6 configurations
- Preserves all settings: subnets, pools, DNS, gateway, NTP, static reservations
- Generates InfraFoundry YAML ready for deployment

---

## Global Options

All commands support these global options:

- `--config-dir` - Override configuration directory (default: `$INFRAFOUNDRY_CONFIG_REPO` or `./example-config`)
- `--help` - Show help for command

**Examples:**

```bash
# Use custom config directory
infra --config-dir /path/to/config plan --env dev

# Show help for any command
infra plan --help
infra apply --help
```

---

## Environment Variables

These environment variables affect CLI behavior:

- `INFRAFOUNDRY_CONFIG_REPO` - Configuration repository path
- `INFRAFOUNDRY_OUTPUT_DIR` - Generated files output directory (default: `generated/`)
- `INFRAFOUNDRY_STATE_BACKEND` - State backend type (`sqlite` or `postgresql`)
- `INFRAFOUNDRY_STATE_CONNECTION` - Custom state database connection string
- `INFRAFOUNDRY_STATE_HOME` - Override directory for the local SQLite state database
- `INFRAFOUNDRY_LOG_LEVEL` - Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `SOPS_AGE_KEY_FILE` - Path to age encryption key for SOPS

**Example `.envrc.local`:**

```bash
# Configuration
export INFRAFOUNDRY_CONFIG_REPO="/path/to/my-infra-config"
export INFRAFOUNDRY_OUTPUT_DIR="${INFRAFOUNDRY_CONFIG_REPO}/generated"

# State backend (optional - defaults to local SQLite)
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://user:pass@localhost/infrafoundry

# Logging (optional)
export INFRAFOUNDRY_LOG_LEVEL=INFO

# SOPS (if using encryption)
export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/envs/dev/age.key"
```

---

## Command Workflow Examples

### Basic Deployment Workflow

```bash
# 1. List environments
infra envs

# 2. Validate configuration
infra validate --env dev

# 3. Preview changes
infra plan --env dev

# 4. Check for drift
infra drift --env dev

# 5. Apply changes
infra apply --env dev

# 6. Check status
infra status --env dev

# 7. View deployment history
infra history --env dev
```

---

### Production Deployment Workflow

```bash
# 1. Validate configuration
infra validate --env prod --verbose

# 2. Check policies
infra policies check --env prod --enforce

# 3. Analyze impact of critical changes
infra impact --env prod --resource db-template

# 4. Preview changes
infra plan --env prod

# 5. Apply with auto-approve (in CI/CD)
infra apply --env prod --auto-approve

# 6. Verify no drift
infra drift --env prod
```

---

### Troubleshooting Workflow

```bash
# 1. Check deployment history
infra history --env prod --limit 10

# 2. Detect drift
infra drift --env prod

# 3. Validate current configuration
infra validate --env prod --verbose

# 4. List available rollback points
infra rollback-points --env prod

# 5. Rollback if needed
infra rollback --env prod --to-previous
```

---

## Exit Codes

InfraFoundry commands use standard exit codes:

- `0` - Success
- `1` - General error (configuration, validation, execution)
- `2` - Command-line usage error

**Example in scripts:**

```bash
#!/bin/bash
infra validate --env prod
if [ $? -ne 0 ]; then
    echo "Validation failed!"
    exit 1
fi

infra apply --env prod --auto-approve
if [ $? -ne 0 ]; then
    echo "Deployment failed!"
    exit 1
fi
```

---

## Related Documentation

- [Setup Guide](SETUP_GUIDE.md) - Initial configuration and setup
- [State Management](state-management.md) - Understanding state types and backends
- [ISC to Kea Migration](isc-to-kea-migration.md) - DHCP migration guide
- [Architecture](architecture/ARCHITECTURE.md) - System architecture and design
