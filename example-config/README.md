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
│   │   ├── environment.yaml # Environment definition
│   │   ├── proxmox/         # Proxmox resources
│   │   ├── opnsense/        # OPNsense resources
│   │   └── kubernetes/      # Kubernetes resources
│   ├── staging/             # Staging environment
│   └── prod/                # Production environment
├── secrets/                 # Encrypted secrets (SOPS + age)
│   ├── age.key              # Age encryption key (DO NOT COMMIT)
│   ├── .sops.yaml           # SOPS configuration
│   └── *.yaml               # Encrypted secret files
├── .gitignore               # Ignore secrets and generated files
└── README.md                # This file
```

**Note:** Credentials and environment-specific settings are configured in the **framework repository's** `.envrc.local` file, not in this config repository.

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

### 3. Initialize secrets

From the framework repository:

```bash
infra secrets init
```

This creates `secrets/age.key` and `secrets/.sops.yaml` in this config repository. The age key is automatically set up for decryption.

### 4. Add encrypted secrets

Create a secrets file and encrypt it:

```bash
# Create secrets file (in config repo)
cat > secrets/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox.example.com:8006
proxmox_token_id: terraform@pve!token
proxmox_token_secret: your-secret-here
EOF

# Encrypt it
infra secrets encrypt secrets/proxmox.yaml
```

The original file will be encrypted in place. Commit the encrypted file:

```bash
git add secrets/proxmox.yaml secrets/.sops.yaml
git commit -m "Add encrypted Proxmox credentials"
```

⚠️ **NEVER commit `secrets/age.key` or `.envrc.local`!** These are git-ignored.

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

Create `envs/staging/environment.yaml`:

```yaml
name: staging
description: Staging environment
providers:
  - proxmox
  - kubernetes
variables:
  cluster_name: staging-cluster
  domain: staging.example.com
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
          pip install uv
          uv pip install -e .

      - name: Set up infrastructure tools
        run: |
          # Install Terraform
          wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
          echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
          sudo apt update && sudo apt install terraform

          # Install Ansible
          pip install ansible

          # Install SOPS
          wget https://github.com/getsops/sops/releases/latest/download/sops-latest.linux.amd64
          sudo mv sops-latest.linux.amd64 /usr/local/bin/sops
          sudo chmod +x /usr/local/bin/sops

      - name: Set up age key
        working-directory: config
        run: |
          mkdir -p secrets
          echo "${{ secrets.SOPS_AGE_KEY }}" | base64 -d > secrets/age.key
          chmod 600 secrets/age.key

      - name: Set environment variables
        working-directory: config
        run: |
          echo "INFRAFOUNDRY_CONFIG_REPO=$(pwd)" >> $GITHUB_ENV
          echo "SOPS_AGE_KEY_FILE=$(pwd)/secrets/age.key" >> $GITHUB_ENV
          echo "PROXMOX_API_URL=${{ secrets.PROXMOX_API_URL }}" >> $GITHUB_ENV
          echo "PROXMOX_API_TOKEN_ID=${{ secrets.PROXMOX_API_TOKEN_ID }}" >> $GITHUB_ENV
          echo "PROXMOX_API_TOKEN_SECRET=${{ secrets.PROXMOX_API_TOKEN_SECRET }}" >> $GITHUB_ENV

      - name: Plan infrastructure
        run: |
          infra plan --env ${{ github.event.inputs.environment || 'dev' }}

      - name: Apply infrastructure
        run: |
          infra apply --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve
```

### Required Secrets

In GitHub repository settings, add these secrets:
- `SOPS_AGE_KEY` - Base64-encoded age key: `cat secrets/age.key | base64 -w0`
- `PROXMOX_API_URL` - Proxmox API URL
- `PROXMOX_API_TOKEN_ID` - Proxmox token ID
- `PROXMOX_API_TOKEN_SECRET` - Proxmox token secret
- (Similar for other providers)

## Security Best Practices

1. **Never commit unencrypted secrets** - Always use SOPS encryption
2. **Protect age.key** - Store securely, never commit, backup safely
3. **Use separate credentials per environment** - Different keys for dev/staging/prod
4. **Rotate credentials regularly** - Update encrypted secrets periodically
5. **Audit access** - Review who has access to config repo and age key
6. **Use branch protection** - Require reviews for production changes

## Team Collaboration

### Sharing age key with team

**Option 1: Secure key management service** (Recommended)
- Store age key in HashiCorp Vault, AWS Secrets Manager, or similar
- Team members retrieve key from secure service

**Option 2: Encrypted handoff**
- Encrypt age key with team member's personal age public key
- Share encrypted key securely
- They decrypt with their personal key

```bash
# Team member generates personal key
age-keygen -o ~/.age/personal.key

# Admin encrypts shared key
age -r <team-member-public-key> -o age.key.encrypted secrets/age.key

# Team member decrypts
age -d -i ~/.age/personal.key age.key.encrypted > secrets/age.key
```

**Option 3: Per-user SOPS setup** (Most secure)
- Each team member has their own age key
- Add all public keys to `.sops.yaml`
- SOPS encrypts for all keys

Edit `secrets/.sops.yaml`:
```yaml
creation_rules:
  - path_regex: .*\.yaml$
    age: >-
      age1public1...,
      age1public2...,
      age1public3...
```

## Troubleshooting

### Config repo not found
```bash
export INFRAFOUNDRY_CONFIG_REPO="/path/to/config/repo"
```

### Decryption fails
- Check `SOPS_AGE_KEY_FILE` points to correct key
- Verify age.key is readable: `ls -l $SOPS_AGE_KEY_FILE`
- Test manually: `sops -d secrets/proxmox.yaml`

### Environment not found
- Check directory structure: `ls envs/`
- Verify `environment.yaml` exists in environment directory
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
- `secrets/age.key` - Encryption key (store securely offline)
- `secrets/.sops.yaml` - SOPS configuration
- `.envrc.local` - Local environment settings (keep private)

## Related Documentation

- [InfraFoundry Framework](https://github.com/your-org/infrafoundry)
- [Provider Documentation](https://github.com/your-org/infrafoundry/tree/main/docs)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)
