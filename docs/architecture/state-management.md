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
  - Path: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`.
  - Scope: per-environment, per-provider.
  - Backends: local (default) or remote (S3, Terraform Cloud, Azure Storage, etc.). Configure via `INFRAFOUNDRY_TF_BACKEND_*` vars.
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

## Validation and Checks

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
  ```bash
  cd generated/dev/terraform/proxmox
  terraform import proxmox_vm_qemu.web_server_01 100
  terraform state show proxmox_vm_qemu.web_server_01
  ```
- **Remote backend (S3) env vars:**
  ```bash
  export INFRAFOUNDRY_TF_BACKEND=s3
  export INFRAFOUNDRY_TF_BACKEND_BUCKET=my-tf-state
  export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
  export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks
  export INFRAFOUNDRY_TF_BACKEND_ENCRYPT=true
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

---

Last updated: 2025-12-27 13:50 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
