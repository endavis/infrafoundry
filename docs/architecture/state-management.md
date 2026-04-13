# State Management in InfraFoundry

## Overview

InfraFoundry manages three artifacts: Terraform state, the InfraFoundry state database, and generated configs. Keeping them isolated per environment/provider and backing them up correctly prevents cross-env drift and data loss.

## Audience and Prerequisites

- **Audience:** Operators and platform engineers running plan/apply across multiple environments.
- **Prereqs:** Access to config and generated directories, Terraform/Ansible CLIs for inspection, and (optionally) a PostgreSQL instance for shared InfraFoundry state.

## When to Use This

- Deciding between local vs remote Terraform state backends.
- Migrating InfraFoundry state from SQLite to PostgreSQL for multi-user teams.
- Auditing, backing up, or restoring state artifacts.

## Quick Start

1. Use default local state for dev:
   ```bash
   infra plan --env dev
   infra apply --env dev
   ```
   Terraform state is in `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`; InfraFoundry state is `~/.infrafoundry/state.db`.
2. Configure remote backends (example S3 + DynamoDB locking):
   ```bash
   export INFRAFOUNDRY_TF_BACKEND=s3
   export INFRAFOUNDRY_TF_BACKEND_BUCKET=my-tf-state
   export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
   export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks
   ```
3. Use PostgreSQL for InfraFoundry state (multi-user):
   ```bash
   export INFRAFOUNDRY_STATE_BACKEND=postgresql
   export INFRAFOUNDRY_STATE_CONNECTION=postgresql://user:password@db.example.com:5432/infrafoundry
   ```

## Configuration Details

- **Terraform state:**
  - Path: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (local backend).
  - Scope: per-environment, per-provider.
  - Backends: local (default) or remote (S3, GCS, Azure, PostgreSQL, Terraform Cloud). Configure via `backend` field in `settings.yaml`.
- **InfraFoundry state DB:**
  - Path: `~/.infrafoundry/state.db` (SQLite default).
  - Custom location: set `INFRAFOUNDRY_STATE_HOME=/custom/path` to override default state directory.
  - Scope: global across environments.
  - Backend: set `INFRAFOUNDRY_STATE_BACKEND=postgresql` and `INFRAFOUNDRY_STATE_CONNECTION=<DSN>` for team/shared use.
- **Generated configs:**
  - Path: `generated/{env}/{terraform|ansible}/{provider}/`.
  - Git-ignored, reproducible from YAML; clean up safely between runs if needed.
- **Environment isolation:** Each env has its own `generated/{env}` subtree to avoid cross-env collisions.
- **Locking:** Use remote backends with locking (e.g., S3 + DynamoDB) for concurrent access; local state is single-writer.

## Deployment and Resource Lifecycle

InfraFoundry tracks deployments and resources through well-defined state transitions:

### Deployment Status

**DeploymentStatus** - Tracks the overall status of a deployment operation:

| Status | Description | Transitions From |
|--------|-------------|-----------------|
| `PLANNED` | Deployment plan created, not yet started | Initial state |
| `IN_PROGRESS` | Deployment actively running | PLANNED |
| `COMPLETED` | Deployment finished successfully | IN_PROGRESS |
| `FAILED` | Deployment encountered errors | IN_PROGRESS |
| `ROLLED_BACK` | Deployment was rolled back to previous state | COMPLETED, FAILED |

**Typical flow:** `PLANNED` → `IN_PROGRESS` → `COMPLETED` or `FAILED` → (optionally) `ROLLED_BACK`

### Resource State

**ResourceState** - Tracks individual resource lifecycle:

| State | Description | Transitions From |
|-------|-------------|-----------------|
| `PLANNED` | Resource planned but not yet created | Initial state |
| `CREATING` | Resource actively being provisioned | PLANNED |
| `ACTIVE` | Resource successfully created and operational | CREATING, UPDATING |
| `UPDATING` | Resource being modified | ACTIVE |
| `DELETING` | Resource being destroyed | ACTIVE, ERROR |
| `DELETED` | Resource successfully removed | DELETING |
| `ERROR` | Resource operation failed | CREATING, UPDATING, DELETING |

**Typical flows:**
- **Creation:** `PLANNED` → `CREATING` → `ACTIVE`
- **Update:** `ACTIVE` → `UPDATING` → `ACTIVE`
- **Deletion:** `ACTIVE` → `DELETING` → `DELETED`
- **Error recovery:** Any state → `ERROR` → (manual intervention) → resumed state

### Querying State

```bash
# View deployment status and history
infra history --env prod
infra status --env dev

# View resource states from database
infra resources --env prod --state ACTIVE
infra resources --env prod --state ERROR
```

## Backend Configuration

InfraFoundry supports multiple Terraform backend types for state storage and locking. Configure backends per-environment in `settings.yaml` to enable team collaboration and state locking.

### Supported Backend Types

| Backend | Locking | Use Case | Configuration Complexity |
|---------|---------|----------|-------------------------|
| **Local** | ❌ No | Single-user, development | Simple (default) |
| **AWS S3** | ✅ Yes (DynamoDB) | Team collaboration, AWS environments | Medium |
| **Google Cloud Storage** | ✅ Yes (native) | Team collaboration, GCP environments | Medium |
| **Azure Blob Storage** | ✅ Yes (native) | Team collaboration, Azure environments | Medium |
| **PostgreSQL** | ✅ Yes (native) | Team collaboration, any environment | Medium |
| **Terraform Cloud** | ✅ Yes (native) | Team collaboration, managed service | Low |

### Backend Configuration Structure

Add the `backend` field to your environment's `settings.yaml`:

```yaml
# envs/prod/settings.yaml
backend:
  type: s3  # or gcs, azurerm, postgres, remote, local
  s3:       # Backend-specific configuration
    bucket: my-terraform-state
    key: prod/terraform.tfstate
    region: us-east-1
    dynamodb_table: terraform-locks  # Required for locking
    encrypt: true
```

### Backend-Specific Configuration

**AWS S3 Backend:**
```yaml
backend:
  type: s3
  s3:
    bucket: my-terraform-state           # Required
    key: terraform.tfstate                # Default: terraform.tfstate
    region: us-east-1                     # Required
    dynamodb_table: terraform-locks       # Optional but recommended for locking
    encrypt: true                         # Default: true
    kms_key_id: arn:aws:kms:...          # Optional
    profile: production                   # Optional
    role_arn: arn:aws:iam:...            # Optional
```

**Google Cloud Storage Backend:**
```yaml
backend:
  type: gcs
  gcs:
    bucket: my-tf-state-bucket           # Required
    prefix: terraform/state               # Default: terraform/state
    credentials: /path/to/key.json       # Optional (uses default credentials if omitted)
    encryption_key: base64-key           # Optional
```

**Azure Blob Storage Backend:**
```yaml
backend:
  type: azurerm
  azurerm:
    resource_group_name: my-rg           # Required
    storage_account_name: mystorageacct  # Required
    container_name: tfstate              # Required
    key: terraform.tfstate                # Default: terraform.tfstate
    access_key: secret-key               # Optional
    sas_token: sas-token                 # Optional
    use_azuread_auth: false              # Default: false
```

**PostgreSQL Backend:**
```yaml
backend:
  type: postgres
  postgres:
    conn_str: postgres://user:pass@db.example.com:5432/terraform  # Required
    schema_name: terraform_remote_state                            # Default: terraform_remote_state
    skip_schema_creation: false                                    # Default: false
```

**Terraform Cloud Backend:**
```yaml
backend:
  type: remote
  remote:
    organization: my-org                 # Required
    hostname: app.terraform.io           # Optional (for Terraform Enterprise)
    token: terraform-cloud-token         # Optional (can use TF_TOKEN_* env var)
    workspaces:
      name: prod-infrastructure          # Use 'name' for single workspace
      # OR
      prefix: prod-                      # Use 'prefix' for multiple workspaces
```

### Generated Backend Configuration

When backend is configured, InfraFoundry generates `backend.tf` for each provider:

```hcl
# generated/prod/terraform/proxmox/backend.tf
# Terraform Backend Configuration
# Generated by InfraFoundry
# Backend Type: s3
# State Locking: Enabled

terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

### Backend Reconfiguration

InfraFoundry automatically detects backend configuration changes and triggers reconfiguration:

1. **Change Detection:** Compares `backend.tf` with `.terraform/terraform.tfstate`
2. **Automatic Reconfiguration:** Runs `terraform init -reconfigure` when backend type changes
3. **Manual Migration:** Use `infra backend migrate --env <env>` to migrate state between backends

### State Locking

State locking happens at **two** layers in InfraFoundry. Both are needed for
correctness; one does not replace the other.

#### 1. Terraform backend locking

**Why Locking Matters:**
- Prevents concurrent modifications to infrastructure state
- Avoids race conditions in team environments
- Essential for CI/CD pipelines running parallel deployments

**Locking by Backend:**
- **S3:** Requires DynamoDB table; configure `dynamodb_table` field
- **GCS, Azure, PostgreSQL, Terraform Cloud:** Built-in locking (no additional configuration)
- **Local:** No locking support (single-user only)

**Verifying Locking:**
```bash
# Backend validation shows locking status
infra backend validate --env prod

# Check generated backend.tf
cat generated/prod/terraform/proxmox/backend.tf
```

#### 2. InfraFoundry-level locking

Terraform backend locks only protect the `.tfstate` file. InfraFoundry's own
state DB, event log, and multi-runner workflow sit *outside* that lock, so
concurrent `foundry infra apply --env prod` runs can corrupt the deployment
history, duplicate resource tracking rows, and race on runner execution even
when the Terraform backend is locking correctly.

InfraFoundry therefore wraps `apply` and `destroy` in a second lock, stored in
the `deployment_locks` table in the state DB. The unique constraint on
`environment` is the atomic primitive - exactly one writer wins.

Key behavior:

- **`plan` is not locked.** Preview jobs never queue behind an apply.
- **Fail fast by default.** `foundry infra apply --env prod` rejects
  immediately if another run holds the lock. Pass `--lock-timeout <seconds>`
  to wait instead.
- **TTL-based stale recovery.** Locks carry an `expires_at` (default 10
  minutes, tunable via `--lock-ttl <seconds>`). A crashed run stops blocking
  new runs once its lock expires. Live runs are kept alive past the TTL by
  the heartbeat (see below).
- **Holder identity.** Each lock records `user@host:pid` in `locked_by` and a
  timestamp in `acquired_at`.
- **Event emission.** `LOCK_ACQUIRED`, `LOCK_RELEASED`, `LOCK_TIMEOUT`, and
  `LOCK_HEARTBEAT_FAILED` events flow through the existing `EventManager` for
  auditing and notifications.

##### Heartbeat

While `apply` or `destroy` is running, a background daemon thread
auto-extends the lock every `ttl / 3` seconds. With the default TTL of 600 s
the heartbeat fires every ~200 s, giving three chances to refresh before
expiry. This decouples "how long can an apply run" from "how long is a
crashed holder considered dead":

- Long applies (hours) keep their lock indefinitely while the process is
  alive — there is no need to guess a TTL upfront.
- Crashed holders free the lock within the TTL window instead of within an
  hour, so the next run recovers quickly.

If the heartbeat cannot extend the lock (DB hiccup, row taken over after a
previous expiry, etc.), it logs the failure and emits a
`LOCK_HEARTBEAT_FAILED` event, then **continues looping**. The in-flight
apply is deliberately **not** aborted — aborting on a transient DB failure
is strictly worse than letting the apply finish under a still-ticking TTL.

If you see `LOCK_HEARTBEAT_FAILED` events in your logs, investigate the
state DB connectivity. The apply itself is unaffected as long as it finishes
before the TTL elapses; if it does not, another process may take over the
stale row. There is no knob to disable or reconfigure the heartbeat — the
interval is always `ttl / 3`.

Managing locks from the CLI:

```bash
# List all currently held locks (shows active vs. expired)
foundry infra unlock --list

# Release an expired lock (safe — refuses active locks)
foundry infra unlock --env prod

# Force-release an active lock after confirming the holder is dead
foundry infra unlock --env prod --force           # prompts for confirmation
foundry infra unlock --env prod --force --yes     # skip the prompt (scripts)
```

Emergency escape hatch: set `INFRAFOUNDRY_SKIP_LOCK=1` to bypass locking
entirely. A loud warning is logged. Only use this when the state DB itself is
inaccessible — it defeats the correctness guarantee that this feature exists
to provide.

See [ADR-0002: State locking via deployment_locks table](../decisions/0002-state-locking.md)
for the full rationale and trade-offs.

## Validation and Checks

- **Filesystem / state DB consistency:**
  ```bash
  # List environments with sync status (OK, FS-ONLY, DB-ONLY)
  foundry config envs

  # Detailed consistency check (exits 1 on divergence)
  foundry config check --deep
  ```
  `FS-ONLY` means an environment directory exists on disk but has no state DB records. `DB-ONLY` means the state DB tracks an environment whose config directory is missing.
- Inspect Terraform state:
  ```bash
  cd generated/dev/terraform/proxmox
  terraform state list
  terraform state show proxmox_vm_qemu.web_server_01
  ```
- Inspect InfraFoundry state/history:
  ```bash
  infra history
  infra history --env prod
  infra status --env dev
  ```
- Verify backend configuration by ensuring state files/DB entries update after `infra plan/apply`.

## Examples

- **Local backup/restore:**
  ```bash
  tar -czf backup-$(date +%Y%m%d).tar.gz generated/ ~/.infrafoundry/state.db
  tar -xzf backup-20250108.tar.gz
  ```
- **PostgreSQL state backup:**
  ```bash
  pg_dump infrafoundry > infrafoundry-state-$(date +%Y%m%d).sql
  psql infrafoundry < infrafoundry-state-20250108.sql
  ```
- **Import existing resource into Terraform state:**
  The preferred approach is to add `import_id` to the resource definition in YAML.
  InfraFoundry generates Terraform `import` blocks automatically:
  ```yaml
  # Resource-centric example
  resources:
    - provider: proxmox
      type: vm
      name: web-server-01
      import_id: "100"
      config:
        target_node: pve1
  ```
  For manual imports (e.g., one-off operations), you can still use the CLI:
  ```bash
  cd generated/dev/terraform/proxmox
  terraform import proxmox_vm_qemu.web_server_01 100
  terraform state show proxmox_vm_qemu.web_server_01
  ```
- **Configure S3 backend with DynamoDB locking:**
  ```yaml
  # envs/prod/settings.yaml
  backend:
    type: s3
    s3:
      bucket: my-terraform-state
      key: prod/terraform.tfstate
      region: us-east-1
      dynamodb_table: terraform-locks
      encrypt: true
  ```
  Then run `infra plan --env prod` to generate backend.tf.

- **Migrate from local to S3 backend:**
  ```bash
  # 1. Add backend config to settings.yaml (as shown above)
  # 2. Run plan to generate backend.tf
  infra plan --env prod

  # 3. Terraform will prompt to migrate state
  # Or use manual migration command
  infra backend migrate --env prod --from local --to s3
  ```

- **Validate backend configuration:**
  ```bash
  # Check backend configuration and locking support
  infra backend validate --env prod

  # View generated backend.tf
  cat generated/prod/terraform/proxmox/backend.tf
  ```

- **Custom state directory location:**
  ```bash
  # Override default ~/.infrafoundry location
  export INFRAFOUNDRY_STATE_HOME=/mnt/shared/infrafoundry-state
  infra init
  # State will be created at /mnt/shared/infrafoundry-state/state.db

  # Useful for shared network storage or custom backup locations
  ```

## Related Documentation

- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Configuration Guide](../configuration/overview.md)
- [Separate Config Repo](../configuration/separate-config-repo.md)
- [State Management Architecture](orchestrator-architecture.md)

## Troubleshooting

- **Symptom:** State collisions or locks. **Fix:** Use remote backend with locking (S3 + DynamoDB) and avoid sharing local state directories.
- **Symptom:** Missing history entries. **Fix:** Confirm InfraFoundry state backend is reachable (SQLite file present or PostgreSQL DSN correct); check `INFRAFOUNDRY_STATE_HOME` if using custom location.
- **Symptom:** Drift between YAML and deployed infra. **Fix:** Re-run `infra plan --env <env>` and inspect generated configs and Terraform state; import existing resources if needed.
- **Symptom:** Permission errors on state paths. **Fix:** Check filesystem permissions for `generated/` and state database location (default `~/.infrafoundry/state.db` or custom via `INFRAFOUNDRY_STATE_HOME`); ensure CI containers persist writable paths.
- **Symptom:** State database not found after setting custom location. **Fix:** Ensure `INFRAFOUNDRY_STATE_HOME` is set in environment and directory exists with write permissions; run `infra init` to create state database in custom location.
- **Symptom:** Resources stuck in ERROR state. **Fix:** Review deployment logs to identify cause; manually fix underlying issue (network, credentials, provider API); re-run `infra apply` to resume from ERROR state.
- **Symptom:** Deployment status shows IN_PROGRESS but no activity. **Fix:** Check if process was killed or terminated; deployment may need manual intervention to move to FAILED or COMPLETED state in database.
- **Symptom:** Backend configuration invalid error. **Fix:** Run `infra backend validate --env <env>` to check configuration; ensure all required fields for backend type are present in `settings.yaml`.
- **Symptom:** Terraform fails to initialize with backend error. **Fix:** Verify credentials for backend (AWS credentials for S3, GCP credentials for GCS, etc.); check network connectivity to backend service; ensure backend resources exist (S3 bucket, DynamoDB table, etc.).
- **Symptom:** State locking timeout. **Fix:** Check if another process holds the lock; verify DynamoDB table exists for S3 backend; ensure locking is supported for backend type; manually break lock if process crashed: `cd generated/{env}/terraform/{provider} && terraform force-unlock <lock-id>`.
- **Symptom:** Backend reconfiguration loop. **Fix:** Check if backend configuration in `settings.yaml` matches generated `backend.tf`; remove `.terraform/` directory and re-run `infra plan --env <env>`; verify no conflicting backend configurations.
- **Symptom:** State migration fails between backends. **Fix:** Use `infra backend migrate --env <env> --from <old> --to <new>` with `--auto-approve` for non-interactive migration; ensure both old and new backends are accessible; backup state before migration.

---

Last updated: 2025-12-27 15:15 GMT


---
[Back to Table of Contents](../index.md)
