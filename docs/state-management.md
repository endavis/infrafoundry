# State Management in InfraFoundry

InfraFoundry manages multiple types of state across its infrastructure lifecycle. Understanding these different state types and how they interact is crucial for effective infrastructure management.

## State Types

InfraFoundry handles three distinct types of state:

### 1. Terraform State
**Location:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`

**What it tracks:**
- Infrastructure resources created by Terraform
- Resource IDs, attributes, and dependencies
- Current state of deployed infrastructure

**Scope:** Per-environment, per-provider

**Backend options:**
- **Local (default):** State files stored in generated directories
- **Remote:** S3, Terraform Cloud, Azure Storage, etc.

### 2. InfraFoundry State
**Location:** `~/.infrafoundry/state.db` (SQLite)

**What it tracks:**
- Deployment history (who, when, what)
- Resource lifecycle (created, updated, deleted)
- Rollback information
- Audit trail for all operations

**Scope:** Global across all environments

**Backend options:**
- **SQLite (default):** Single-user, local development
- **PostgreSQL:** Multi-user, production teams

### 3. Generated Configurations
**Location:** `generated/{env}/{terraform|ansible}/{provider}/`

**What they are:**
- Terraform `.tf` files generated from YAML
- Ansible playbooks and inventories
- Temporary, reproducible from source configs

**Scope:** Per-environment, per-provider

**Version control:** Git-ignored, regenerated on demand

## Directory Structure

### Environment Isolation

Each environment has completely isolated directories:

```
generated/
├── dev/
│   ├── terraform/
│   │   ├── proxmox/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   ├── outputs.tf
│   │   │   └── .terraform/
│   │   │       ├── terraform.tfstate       # Dev Terraform state
│   │   │       └── terraform.tfstate.backup
│   │   ├── opnsense/
│   │   │   └── .terraform/
│   │   │       └── terraform.tfstate       # Dev OPNsense state
│   │   └── kubernetes/
│   └── ansible/
│       ├── proxmox/
│       └── opnsense/
├── staging/
│   ├── terraform/
│   │   ├── proxmox/
│   │   │   └── .terraform/
│   │   │       └── terraform.tfstate       # Staging Terraform state
│   │   └── ...
│   └── ansible/
└── prod/
    ├── terraform/
    │   ├── proxmox/
    │   │   └── .terraform/
    │   │       └── terraform.tfstate       # Prod Terraform state
    │   └── ...
    └── ansible/
```

**Key benefits:**
- ✅ Each environment has its own Terraform state
- ✅ No risk of dev operations affecting prod
- ✅ Can work on multiple environments simultaneously
- ✅ Clear separation for team collaboration
- ✅ Easy to backup/restore per environment

## State Management Strategies

### Strategy 1: Local State (Default)

**Best for:**
- Single developer
- Development environments
- Testing and experimentation

**Configuration:**
```bash
# No special configuration needed
# State automatically stored in generated/{env}/terraform/{provider}/
infra plan --env dev
infra apply --env dev
```

**Terraform state location:**
```
generated/dev/terraform/proxmox/.terraform/terraform.tfstate
```

**InfraFoundry state location:**
```
~/.infrafoundry/state.db
```

**Pros:**
- ✅ Simple setup, no additional infrastructure
- ✅ Fast operations (no network latency)
- ✅ Works offline

**Cons:**
- ❌ State lost if local files deleted
- ❌ Cannot share state with team
- ❌ Risk of state divergence between team members

**Backup strategy:**
```bash
# Backup generated directories
tar -czf backup-$(date +%Y%m%d).tar.gz generated/

# Backup InfraFoundry state
cp ~/.infrafoundry/state.db ~/backups/state-$(date +%Y%m%d).db
```

### Strategy 2: Remote Terraform State

**Best for:**
- Production environments
- Team collaboration
- CI/CD pipelines

**Configuration:**

**Option A: S3 Backend**
```bash
# .envrc.local or environment variables
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=my-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
export INFRAFOUNDRY_TF_BACKEND_KEY=infrafoundry/${ENVIRONMENT}/terraform.tfstate
export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks  # For state locking

# AWS credentials
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
```

**Option B: Terraform Cloud**
```bash
export INFRAFOUNDRY_TF_BACKEND_TYPE=remote
export INFRAFOUNDRY_TF_BACKEND_ORGANIZATION=my-org
export INFRAFOUNDRY_TF_BACKEND_WORKSPACE=infrafoundry-dev
export TF_TOKEN_app_terraform_io=your-token
```

**Option C: Azure Blob Storage**
```bash
export INFRAFOUNDRY_TF_BACKEND_TYPE=azurerm
export INFRAFOUNDRY_TF_BACKEND_STORAGE_ACCOUNT=mystorageaccount
export INFRAFOUNDRY_TF_BACKEND_CONTAINER_NAME=tfstate
export INFRAFOUNDRY_TF_BACKEND_KEY=infrafoundry.tfstate
```

**Pros:**
- ✅ State shared across team
- ✅ State locking prevents conflicts
- ✅ Version history and rollback
- ✅ Secure, encrypted storage

**Cons:**
- ❌ Requires additional infrastructure
- ❌ Network dependency
- ❌ Costs for storage and API calls

### Strategy 3: PostgreSQL InfraFoundry State

**Best for:**
- Production teams
- Shared deployment history
- Audit requirements

**Configuration:**
```bash
# .envrc.local
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://user:password@db.example.com:5432/infrafoundry

# Or use connection string with SSL
export INFRAFOUNDRY_STATE_CONNECTION="postgresql://user:password@db.example.com:5432/infrafoundry?sslmode=require"
```

**Setup:**
```sql
-- Create database
CREATE DATABASE infrafoundry;

-- Create user
CREATE USER infrafoundry_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE infrafoundry TO infrafoundry_user;
```

**Pros:**
- ✅ Shared deployment history across team
- ✅ Centralized audit trail
- ✅ Advanced querying capabilities
- ✅ Backup/restore via PostgreSQL tools

**Cons:**
- ❌ Requires PostgreSQL server
- ❌ More complex setup
- ❌ Additional maintenance

### Strategy 4: Hybrid (Recommended for Production)

**Best for:**
- Production environments with teams
- Maximum reliability and collaboration

**Configuration:**
```bash
# Remote Terraform state (S3)
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=prod-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks
export INFRAFOUNDRY_TF_BACKEND_ENCRYPT=true

# Shared InfraFoundry state (PostgreSQL)
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://infra_user:pass@db.prod.example.com/infrafoundry
```

**Benefits:**
- ✅ Terraform state shared and locked (prevents conflicts)
- ✅ Deployment history visible to all team members
- ✅ Complete audit trail for compliance
- ✅ Separate concerns (infrastructure vs deployment tracking)

## Environment-Specific Configuration

### Development Environment
```bash
# dev/.envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export INFRAFOUNDRY_OUTPUT_DIR="${INFRAFOUNDRY_CONFIG_REPO}/generated"

# Local state (default)
# No Terraform backend config needed

# Local InfraFoundry state
# No state backend config needed (uses ~/.infrafoundry/state.db)
```

### Staging Environment
```bash
# staging/.envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export INFRAFOUNDRY_OUTPUT_DIR="${INFRAFOUNDRY_CONFIG_REPO}/generated"

# Remote Terraform state (S3)
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=staging-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
export INFRAFOUNDRY_TF_BACKEND_KEY=infrafoundry/staging/terraform.tfstate

# Shared InfraFoundry state
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://infra:pass@db.staging.example.com/infrafoundry
```

### Production Environment
```bash
# prod/.envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export INFRAFOUNDRY_OUTPUT_DIR="${INFRAFOUNDRY_CONFIG_REPO}/generated"

# Remote Terraform state (S3 with locking)
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=prod-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
export INFRAFOUNDRY_TF_BACKEND_KEY=infrafoundry/prod/terraform.tfstate
export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks
export INFRAFOUNDRY_TF_BACKEND_ENCRYPT=true

# Shared InfraFoundry state
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://infra:pass@db.prod.example.com/infrafoundry
```

## State Operations

### Viewing State

**Terraform state:**
```bash
# View all resources in Terraform state
cd generated/dev/terraform/proxmox
terraform state list

# Show detailed resource info
terraform state show proxmox_vm_qemu.web_server_01

# Pull current state
terraform state pull > current-state.json
```

**InfraFoundry state:**
```bash
# View deployment history
infra history

# View history for specific environment
infra history --env prod

# View current infrastructure status
infra status --env dev
```

### Backing Up State

**Local development:**
```bash
# Backup everything
tar -czf backup-$(date +%Y%m%d).tar.gz \
    generated/ \
    ~/.infrafoundry/state.db

# Restore
tar -xzf backup-20250108.tar.gz
```

**Production with remote state:**
```bash
# Terraform state backed up automatically by backend
# S3: versioning enabled
# Terraform Cloud: automatic snapshots

# InfraFoundry state backup (PostgreSQL)
pg_dump infrafoundry > infrafoundry-state-$(date +%Y%m%d).sql

# Restore
psql infrafoundry < infrafoundry-state-20250108.sql
```

### Importing Existing Infrastructure

```bash
# Import existing resources into Terraform state
cd generated/dev/terraform/proxmox
terraform import proxmox_vm_qemu.web_server_01 100

# Verify import
terraform state show proxmox_vm_qemu.web_server_01

# InfraFoundry will track the resource after next apply
```

### State Locking

**With S3 + DynamoDB:**
```bash
# State locking automatic with DynamoDB table
# If lock acquired by another user/process:
# Error: Error acquiring the state lock

# Force unlock (use with caution!)
cd generated/prod/terraform/proxmox
terraform force-unlock LOCK_ID
```

### Migrating State

**From local to remote:**
```bash
# 1. Set up remote backend config
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=my-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1

# 2. Re-initialize Terraform
cd generated/dev/terraform/proxmox
terraform init -migrate-state

# 3. Verify migration
terraform state list
```

**Between environments:**
```bash
# Pull state from dev
cd generated/dev/terraform/proxmox
terraform state pull > dev-state.json

# Modify for staging (update resource names, IDs, etc.)

# Push to staging
cd ../../staging/terraform/proxmox
terraform state push dev-state.json
```

## Troubleshooting

### State Lock Issues

**Problem:** State locked by another process
```
Error: Error acquiring the state lock
```

**Solutions:**
```bash
# Check who has the lock (DynamoDB)
aws dynamodb get-item \
  --table-name terraform-locks \
  --key '{"LockID": {"S": "my-state-bucket/terraform.tfstate-md5"}}'

# Force unlock (last resort)
terraform force-unlock LOCK_ID
```

### State Drift

**Problem:** Infrastructure changed outside InfraFoundry

**Detection:**
```bash
# Detect drift
infra drift --env prod

# Or manually with Terraform
cd generated/prod/terraform/proxmox
terraform plan -detailed-exitcode
```

**Resolution:**
```bash
# Option 1: Import changes into state
terraform import resource.name resource-id

# Option 2: Revert manual changes
infra apply --env prod

# Option 3: Update YAML configs to match reality
vim envs/prod/proxmox/vm.yaml
infra plan --env prod
```

### Lost State

**Problem:** State file deleted or corrupted

**Recovery:**
```bash
# If using remote backend with versioning (S3)
aws s3api list-object-versions \
  --bucket my-terraform-state \
  --prefix terraform.tfstate

# Restore previous version
aws s3api get-object \
  --bucket my-terraform-state \
  --key terraform.tfstate \
  --version-id VERSION_ID \
  terraform.tfstate

# If no backup, rebuild state from imports
cd generated/prod/terraform/proxmox
terraform import proxmox_vm_qemu.web_01 100
terraform import proxmox_vm_qemu.web_02 101
# ... continue for all resources
```

### State Conflicts

**Problem:** Multiple users applying simultaneously

**Prevention:**
```bash
# Use state locking (S3 + DynamoDB)
export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks

# Or coordination
# User 1: infra apply --env prod
# User 2: waits for lock to release
```

## Best Practices

### General

1. **Version everything:** Keep YAML configs in git, state in versioned backends
2. **Backup regularly:** Automate backups of state and configurations
3. **Use state locking:** Prevent concurrent modifications in production
4. **Test changes:** Always `plan` before `apply`
5. **Document state:** Keep README with backend configuration details

### Development

1. **Use local state:** Fast, simple, no dependencies
2. **Commit frequently:** YAML configs should be version controlled
3. **Clean up:** Remove old generated files regularly
4. **Don't commit state:** Keep `.terraform/` and state files out of git

### Production

1. **Use remote state:** S3, Terraform Cloud, or Azure Blob
2. **Enable state locking:** DynamoDB for S3, built-in for Terraform Cloud
3. **Encrypt state:** Enable encryption at rest and in transit
4. **Separate environments:** Different backends per environment
5. **Monitor access:** Audit who accesses state files
6. **Automate backups:** Regular snapshots of state and database
7. **Document recovery:** Keep runbooks for state recovery scenarios

### Team Collaboration

1. **Shared state backend:** All team members use same remote backend
2. **Clear communication:** Announce before production deployments
3. **Use branches:** Feature branches for config changes, PR reviews
4. **CI/CD integration:** Automated plan on PRs, apply on merge
5. **Access control:** Restrict who can apply to production
6. **Audit trail:** Use PostgreSQL backend for deployment history

## Examples

### Example 1: Solo Developer (Local State)

```bash
# Setup
cd ~/projects/homelab-infra
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Work on dev
infra plan --env dev
infra apply --env dev

# Work on prod
infra plan --env prod
infra apply --env prod

# State locations:
# - Terraform: generated/{dev,prod}/terraform/proxmox/.terraform/
# - InfraFoundry: ~/.infrafoundry/state.db

# Backup
tar -czf backup-$(date +%Y%m%d).tar.gz generated/ ~/.infrafoundry/
```

### Example 2: Small Team (Remote Terraform, Local InfraFoundry)

```bash
# Each team member's .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=team-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1

# Shared Terraform state in S3
# Individual InfraFoundry state in ~/.infrafoundry/state.db

# Coordination via Slack/chat before applies
```

### Example 3: Enterprise Team (Fully Remote)

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Remote Terraform state (S3 with locking)
export INFRAFOUNDRY_TF_BACKEND_TYPE=s3
export INFRAFOUNDRY_TF_BACKEND_BUCKET=enterprise-terraform-state
export INFRAFOUNDRY_TF_BACKEND_REGION=us-east-1
export INFRAFOUNDRY_TF_BACKEND_DYNAMODB_TABLE=terraform-locks
export INFRAFOUNDRY_TF_BACKEND_ENCRYPT=true

# Shared InfraFoundry state (PostgreSQL)
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://infra:pass@db.corp.example.com/infrafoundry

# All state shared and locked
# Full team visibility of deployments
# Complete audit trail
```

## Related Documentation

- [Separate Configuration Repository Guide](separate-config-repo.md)
- [CI/CD Integration](../ci/README.md)
- [Terraform Backend Configuration](https://www.terraform.io/language/settings/backends)
- [State Locking](https://www.terraform.io/language/state/locking)
