# InfraFoundry Configuration Repository

This is a separate configuration repository for InfraFoundry infrastructure definitions.

## Purpose

This repository contains your infrastructure configurations, environment definitions, and encrypted secrets, separate from the InfraFoundry framework code. This allows you to:

- Version control your infrastructure configurations independently
- Share infrastructure configs across teams without sharing framework code
- Maintain different access controls (framework developers vs infrastructure operators)
- Keep sensitive configurations private while using public framework

## Structure

```
.
├── envs/                    # Environment configurations
│   ├── dev/                 # Development environment
│   │   ├── age.key          # Age encryption key (DO NOT COMMIT)
│   │   ├── settings.yaml    # Environment definition + provider credentials (SOPS encrypted)
│   │   ├── proxmox/         # Proxmox resources (YAML, not encrypted)
│   │   ├── opnsense/        # OPNsense resources (YAML, not encrypted)
│   │   └── kubernetes/      # Kubernetes resources (YAML, not encrypted)
│   ├── staging/             # Staging environment
│   │   ├── age.key          # Staging encryption key (DO NOT COMMIT)
│   │   └── settings.yaml    # Staging environment + credentials (SOPS encrypted)
│   └── prod/                # Production environment
│       ├── age.key          # Production encryption key (DO NOT COMMIT)
│       └── settings.yaml    # Production environment + credentials (SOPS encrypted)
├── .sops.yaml               # SOPS configuration (in config repo root)
├── .gitignore               # Ignore age.key files and generated files
├── .envrc.local.example     # Example environment variables
├── policies/                # Policy files for validation (optional)
├── notifications.yaml       # Notification configuration (optional)
└── README.md                # This file
```

**Note:** All configuration is YAML. InfraFoundry automatically generates Terraform `.tf` files and Ansible playbooks from your YAML definitions - you never need to write HCL or Terraform code directly.

## Setup

### 1. Clone this repository

```bash
git clone <your-config-repo-url>
cd <config-repo-name>
```

### 2. Set up environment

**In the framework repository**, set the path to this config repository:

```bash
# Go to framework repo
cd /path/to/infrafoundry

# Edit .envrc.local (framework repo)
cat >> .envrc.local <<EOF
# Point to your infrastructure config repository
export INFRAFOUNDRY_CONFIG_REPO="/path/to/this/config-repo"

# Provider credentials
export PROXMOX_API_URL="https://proxmox.example.com:8006"
export PROXMOX_API_TOKEN_ID="terraform@pve!token"
export PROXMOX_API_TOKEN_SECRET="your-secret"

# OPNsense credentials
export OPNSENSE_API_URL="https://firewall.example.com"
export OPNSENSE_API_KEY="your-api-key"
export OPNSENSE_API_SECRET="your-api-secret"
EOF
```

If using direnv in the framework repo:
```bash
direnv allow
```

### 3. Initialize secrets for an environment

Generate an age key for your first environment (dev):

```bash
# From the framework repository
infra secrets init --env dev
```

This creates `envs/dev/age.key` and `.sops.yaml` (in the config repo root).

⚠️ **IMPORTANT:** Each environment should have its own age key:
```bash
infra secrets init --env staging
infra secrets init --env prod
```

### 4. Add provider credentials to settings.yaml

All credentials go in the `provider_settings` section of `envs/{env}/settings.yaml`:

```bash
# Edit settings.yaml for dev environment
cat > envs/dev/settings.yaml <<EOF
name: dev
description: Development environment

# Provider credentials (will be encrypted with SOPS)
provider_settings:
  proxmox:
    api_url: https://proxmox.example.com:8006
    token_id: terraform@pve!token
    token_secret: your-secret-here

  opnsense:
    api_url: https://firewall.example.com
    api_key: your-api-key
    api_secret: your-api-secret
EOF

# Encrypt the settings file
sops --encrypt --in-place envs/dev/settings.yaml
```

The original file will be encrypted in place. Commit the encrypted file:

```bash
git add envs/dev/settings.yaml .sops.yaml
git commit -m "Add encrypted dev environment settings"
```

⚠️ **NEVER commit `envs/*/age.key` or `.envrc.local`!** These are git-ignored.

### 5. Verify encryption

```bash
# Check file is encrypted (looks like gibberish)
cat envs/dev/settings.yaml

# Decrypt to view (requires age key)
export SOPS_AGE_KEY_FILE="$(pwd)/envs/dev/age.key"
sops --decrypt envs/dev/settings.yaml

# Or edit encrypted file directly
sops envs/dev/settings.yaml
```

## Usage

### List environments

```bash
infra envs
```

### Plan infrastructure changes

```bash
# Development environment
infra plan --env dev

# Production environment
infra plan --env prod
```

### Apply changes

```bash
infra apply --env dev
```

### Check status

```bash
infra status --env dev
```

### Destroy infrastructure

```bash
infra destroy --env dev
```

## Adding Environments

Create a new environment:

```bash
mkdir -p envs/staging
```

Create `envs/staging/settings.yaml`:

```yaml
name: staging
description: Staging environment

# Provider credentials (encrypt with SOPS)
provider_settings:
  proxmox:
    api_url: https://proxmox-staging.example.com:8006
    token_id: terraform@pve!staging-token
    token_secret: staging-secret-here

# Environment-specific variables
variables:
  cluster_name: staging-cluster
  domain: staging.example.com

# Optional: SSH configuration for Proxmox template operations
ssh:
  user: automation
  key_path: /home/automation/.ssh/id_ed25519
  port: 22
```

Then encrypt it:

```bash
# Generate age key for staging
infra secrets init --env staging

# Encrypt settings
export SOPS_AGE_KEY_FILE="$(pwd)/envs/staging/age.key"
sops --encrypt --in-place envs/staging/settings.yaml
```

Add provider-specific configurations:

```bash
mkdir -p envs/staging/proxmox
cat > envs/staging/proxmox/vms.yaml <<EOF
vms:
  - name: staging-web-01
    vmid: 201
    target_node: pve01
    # ... configuration
EOF
```

## CI/CD Integration

### GitHub Actions

In your infrastructure repository (this repo), add `.github/workflows/deploy.yml`:

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy'
        required: true
        default: 'dev'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout config repo
        uses: actions/checkout@v4
        with:
          path: config

      - name: Checkout InfraFoundry framework
        uses: actions/checkout@v4
        with:
          repository: your-org/infrafoundry
          path: infrafoundry

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install InfraFoundry
        working-directory: infrafoundry
        run: |
          # Install just and use it to install dependencies
          curl -LsSf https://just.systems/install.sh | bash -s -- --to $HOME/.local/bin
          echo "$HOME/.local/bin" >> $GITHUB_PATH
          just install-uv
          just install

      - name: Set up infrastructure tools
        working-directory: infrafoundry
        run: |
          # Use just recipes to install all tools
          just install-terraform
          just install-ansible
          just install-sops

      - name: Set up age key
        working-directory: config
        run: |
          mkdir -p envs/dev
          echo "${{ secrets.SOPS_AGE_KEY_DEV }}" | base64 -d > envs/dev/age.key
          chmod 600 envs/dev/age.key

      - name: Set environment variables
        working-directory: config
        run: |
          echo "INFRAFOUNDRY_CONFIG_REPO=$(pwd)" >> $GITHUB_ENV
          echo "SOPS_AGE_KEY_FILE=$(pwd)/envs/dev/age.key" >> $GITHUB_ENV

      - name: Plan infrastructure
        run: |
          infra plan --env ${{ github.event.inputs.environment || 'dev' }}

      - name: Apply infrastructure
        run: |
          infra apply --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve
```

### Required Secrets

In GitHub repository settings, add these secrets:

**Per-environment age keys:**
- `SOPS_AGE_KEY_DEV` - Base64-encoded dev age key: `cat envs/dev/age.key | base64 -w0`
- `SOPS_AGE_KEY_STAGING` - Base64-encoded staging age key
- `SOPS_AGE_KEY_PROD` - Base64-encoded prod age key

**Note:** Provider credentials are stored in encrypted `settings.yaml` files, not as GitHub secrets. Only the age key needs to be in GitHub secrets.

## Security Best Practices

1. **Never commit unencrypted secrets** - Always use SOPS encryption on `settings.yaml`
2. **Protect age.key files** - Store securely, never commit, backup safely
3. **Use separate keys per environment** - Each environment has its own `age.key`
4. **Rotate credentials regularly** - Update encrypted `settings.yaml` periodically
5. **Audit access** - Review who has access to config repo and age keys
6. **Use branch protection** - Require reviews for production changes
7. **Separate environments** - Never use prod credentials in dev/staging

## Team Collaboration

### Sharing age key with team

**Option 1: Per-environment keys** (Recommended)
- Each environment (dev, staging, prod) has its own age key
- Developers get dev/staging keys only
- Ops team gets all keys including prod
- Store keys in secure key management service (Vault, AWS Secrets Manager)

**Option 2: Encrypted handoff**
- Encrypt age key with team member's personal age public key
- Share encrypted key securely
- They decrypt with their personal key

```bash
# Team member generates personal key
age-keygen -o ~/.age/personal.key

# Admin encrypts shared key for specific environment
age -r <team-member-public-key> -o dev-age.key.encrypted envs/dev/age.key

# Team member decrypts
age -d -i ~/.age/personal.key dev-age.key.encrypted > envs/dev/age.key
```

**Option 3: Per-user SOPS setup** (Most secure)
- Each team member has their own age key
- Add all public keys to `.sops.yaml`
- SOPS encrypts for all keys

Edit `.sops.yaml` (in config repo root):
```yaml
creation_rules:
  - path_regex: envs/dev/settings\.yaml$
    age: >-
      age1dev_user1...,
      age1dev_user2...,
      age1dev_user3...
  - path_regex: envs/prod/settings\.yaml$
    age: >-
      age1prod_admin1...,
      age1prod_admin2...
```

## Troubleshooting

### Config repo not found
```bash
export INFRAFOUNDRY_CONFIG_REPO="/path/to/config/repo"
```

### Decryption fails
- Check `SOPS_AGE_KEY_FILE` points to correct environment's key
- Verify age.key is readable: `ls -l envs/dev/age.key`
- Test manually: `sops -d envs/dev/settings.yaml`
- Ensure you're using the right environment's key: `export SOPS_AGE_KEY_FILE="$(pwd)/envs/dev/age.key"`

### Environment not found
- Check directory structure: `ls envs/`
- Verify `settings.yaml` exists in environment directory
- List available environments: `infra envs`

## Maintaining This Repository

### Update configurations

1. Create a branch for changes
```bash
git checkout -b update-dev-vms
```

2. Edit configuration files
```bash
vim envs/dev/proxmox/vms.yaml
```

3. Test locally
```bash
infra plan --env dev --dry-run
```

4. Commit and push
```bash
git add envs/dev/proxmox/vms.yaml
git commit -m "Add new web server to dev"
git push -u origin update-dev-vms
```

5. Create pull request for review

### Backup important files

Regularly backup:
- `envs/*/age.key` - Encryption keys for each environment (store securely offline, separately)
- `.sops.yaml` - SOPS configuration
- `.envrc.local` - Local environment settings (keep private, don't backup to same location as age keys)
- Encrypted `settings.yaml` files - Already in git, but maintain offline backups

**Important:** Back up age keys to a secure, separate location from the config repo. If you lose an age key, you cannot decrypt that environment's settings.

**Note:** Each environment (dev, staging, prod) has isolated state in `generated/{env}/terraform/{provider}/`. This prevents conflicts when working on multiple environments simultaneously.

## State Management

InfraFoundry manages three types of state:

1. **Terraform State**: `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate`
   - Tracks infrastructure resources created by Terraform
   - Separate state per environment (dev, staging, prod)
   - Can use remote backends (S3, Terraform Cloud) for team collaboration

2. **InfraFoundry State**: `~/.infrafoundry/state.db`
   - Tracks deployment history and resource lifecycle
   - Provides audit trail for all operations
   - Can use PostgreSQL for shared team state

3. **Generated Configs**: `generated/{env}/`
   - Temporary `.tf` files and Ansible playbooks
   - Reproducible from YAML configs
   - Git-ignored, regenerated on each plan/apply

For more details, see [State Management Guide](../docs/state-management.md).

## Related Documentation

- [InfraFoundry Framework](https://github.com/your-org/infrafoundry)
- [State Management Strategies](../docs/state-management.md)
- [Separate Config Repository Guide](../docs/separate-config-repo.md)
- [Provider Documentation](https://github.com/your-org/infrafoundry/tree/main/docs)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)
