# Separate Configuration Repository Pattern

This guide explains how to use InfraFoundry with a separate configuration repository, allowing you to version control your infrastructure definitions independently from the framework code.

## Benefits

**Separation of Concerns:**
- Framework developers and infrastructure operators have different responsibilities
- Framework updates don't affect your infrastructure configurations
- Infrastructure configs can be private while framework is public/shared

**Access Control:**
- Different teams/people need access to configs vs framework
- Sensitive infrastructure details stay in private repo
- Framework can be open source while configs remain private

**Version Control:**
- Independent versioning of framework and infrastructure
- Rollback infrastructure changes without framework changes
- Different CI/CD pipelines for framework vs infrastructure

**Multi-Environment:**
- Single framework, multiple config repos (dev, prod, client-specific)
- Share framework across projects/teams
- Easy to clone and adapt configs for new environments

## Architecture

```
Framework Repository (infrafoundry)     Config Repository (infrafoundry-config)
├── src/infrafoundry/                   ├── envs/
│   ├── core/                           │   ├── dev/
│   │   ├── provider.py                 │   ├── staging/
│   │   ├── config.py                   │   └── prod/
│   │   └── secrets.py                  ├── secrets/
│   └── providers/                      │   ├── age.key (ignored)
│       ├── proxmox/                    │   ├── .sops.yaml
│       ├── opnsense/                   │   └── *.yaml (encrypted)
│       └── kubernetes/                 ├── .envrc.local (ignored)
├── docs/                               ├── .gitignore
├── pyproject.toml                      └── README.md
└── example-config/
```

## Setup Methods

### Method 1: Environment Variable (Recommended)

Set `INFRAFOUNDRY_CONFIG_REPO` to point to your config repository:

**Using direnv (.envrc.local):**
```bash
# In your config repository root
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
```

**Using shell profile:**
```bash
# ~/.bashrc or ~/.zshrc
export INFRAFOUNDRY_CONFIG_REPO="$HOME/projects/infrafoundry-config"
```

**For single command:**
```bash
INFRAFOUNDRY_CONFIG_REPO=/path/to/config infra plan --env dev
```

### Method 2: CLI Option

Use `--config-dir` flag with every command:

```bash
infra --config-dir /path/to/config plan --env dev
infra --config-dir /path/to/config apply --env dev
infra --config-dir /path/to/config status --env dev
```

### Method 3: Legacy (Same Repository)

Keep configs in framework repo (original behavior):

```
infrafoundry/
├── envs/
├── secrets/
└── src/
```

This still works if you don't set `INFRAFOUNDRY_CONFIG_REPO`.

## Creating a Configuration Repository

### Step 1: Create Repository

```bash
# Create from example
cp -r /path/to/infrafoundry/example-config my-infrastructure-config
cd my-infrastructure-config

# Initialize git
git init
git add .
git commit -m "Initial infrastructure configuration"

# Add remote and push
git remote add origin <your-git-url>
git push -u origin main
```

### Step 2: Set Up Environment

```bash
# Create local environment file
cp .envrc.local.example .envrc.local

# Edit .envrc.local
vim .envrc.local
```

Add your settings:
```bash
# Point to this config repo
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# SOPS age key
export SOPS_AGE_KEY_FILE="$(pwd)/secrets/age.key"

# Provider credentials
export PROXMOX_API_URL="https://proxmox.example.com:8006"
export PROXMOX_API_TOKEN_ID="terraform@pve!token"
export PROXMOX_API_TOKEN_SECRET="your-secret"

export OPNSENSE_API_URL="https://firewall.example.com"
export OPNSENSE_API_KEY="your-api-key"
export OPNSENSE_API_SECRET="your-api-secret"

export KUBECONFIG="$(pwd)/kubeconfig"
```

### Step 3: Initialize Secrets

```bash
# Generate age encryption key
infra secrets init

# Create and encrypt secrets
cat > secrets/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox.example.com:8006
proxmox_token_id: terraform@pve!token
proxmox_token_secret: your-secret-here
EOF

infra secrets encrypt secrets/proxmox.yaml
```

### Step 4: Verify Setup

```bash
# Load environment
direnv allow  # if using direnv

# List environments
infra envs

# Test plan
infra plan --env dev --dry-run
```

## Directory Structure

### Minimal Configuration Repository

```
my-config-repo/
├── envs/
│   └── dev/
│       ├── environment.yaml
│       └── proxmox/
│           └── vms.yaml
├── secrets/
│   ├── age.key                    # Git-ignored
│   ├── .sops.yaml                 # SOPS config
│   └── proxmox.yaml               # Encrypted
├── .envrc.local                   # Git-ignored
├── .gitignore
└── README.md
```

### Full Configuration Repository

```
my-config-repo/
├── envs/
│   ├── dev/
│   │   ├── environment.yaml
│   │   ├── proxmox/
│   │   │   ├── vms.yaml
│   │   │   ├── templates.yaml
│   │   │   └── networks.yaml
│   │   ├── opnsense/
│   │   │   ├── vlans.yaml
│   │   │   ├── aliases.yaml
│   │   │   └── firewall_rules.yaml
│   │   └── kubernetes/
│   │       ├── namespaces.yaml
│   │       ├── deployments.yaml
│   │       ├── services.yaml
│   │       └── configmaps.yaml
│   ├── staging/
│   │   └── ...
│   └── prod/
│       └── ...
├── secrets/
│   ├── age.key                    # Git-ignored
│   ├── .sops.yaml
│   ├── proxmox.yaml               # Encrypted
│   ├── opnsense.yaml              # Encrypted
│   └── kubernetes.yaml            # Encrypted
├── generated/                     # Git-ignored
│   ├── terraform/
│   └── ansible/
├── docs/
│   ├── architecture.md
│   ├── runbooks/
│   └── disaster-recovery.md
├── .envrc.local                   # Git-ignored
├── .gitignore
├── README.md
└── CHANGELOG.md
```

## CI/CD Integration

### GitHub Actions

`.github/workflows/deploy.yml` in your config repository:

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]
    paths:
      - 'envs/**'
      - 'secrets/**'
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy'
        required: true
        type: choice
        options:
          - dev
          - staging
          - prod
      action:
        description: 'Action to perform'
        required: true
        type: choice
        options:
          - plan
          - apply
          - destroy

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'dev' }}

    steps:
      - name: Checkout config repository
        uses: actions/checkout@v4
        with:
          path: config

      - name: Checkout InfraFoundry framework
        uses: actions/checkout@v4
        with:
          repository: your-org/infrafoundry
          ref: v0.1.0  # Pin to specific version
          path: infrafoundry

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install InfraFoundry
        run: |
          pip install uv
          cd infrafoundry
          uv pip install --system -e .

      - name: Install infrastructure tools
        run: |
          # Terraform
          wget -O- https://apt.releases.hashicorp.com/gpg | \
            sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
          echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
            https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
            sudo tee /etc/apt/sources.list.d/hashicorp.list
          sudo apt update && sudo apt install terraform

          # Ansible
          pip install ansible

          # SOPS
          wget https://github.com/getsops/sops/releases/latest/download/sops-latest.linux.amd64
          sudo mv sops-latest.linux.amd64 /usr/local/bin/sops
          sudo chmod +x /usr/local/bin/sops

      - name: Set up age key
        run: |
          cd config
          mkdir -p secrets
          echo "${{ secrets.SOPS_AGE_KEY }}" | base64 -d > secrets/age.key
          chmod 600 secrets/age.key

      - name: Set environment variables
        run: |
          cd config
          echo "INFRAFOUNDRY_CONFIG_REPO=$(pwd)" >> $GITHUB_ENV
          echo "SOPS_AGE_KEY_FILE=$(pwd)/secrets/age.key" >> $GITHUB_ENV

          # Provider credentials from secrets
          echo "PROXMOX_API_URL=${{ secrets.PROXMOX_API_URL }}" >> $GITHUB_ENV
          echo "PROXMOX_API_TOKEN_ID=${{ secrets.PROXMOX_API_TOKEN_ID }}" >> $GITHUB_ENV
          echo "PROXMOX_API_TOKEN_SECRET=${{ secrets.PROXMOX_API_TOKEN_SECRET }}" >> $GITHUB_ENV

      - name: Validate configuration
        run: |
          infra envs
          echo "Deploying to: ${{ github.event.inputs.environment || 'dev' }}"

      - name: Plan infrastructure
        if: github.event.inputs.action == 'plan' || github.event.inputs.action == ''
        run: |
          infra plan --env ${{ github.event.inputs.environment || 'dev' }}

      - name: Apply infrastructure
        if: github.event.inputs.action == 'apply'
        run: |
          infra apply --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve

      - name: Destroy infrastructure
        if: github.event.inputs.action == 'destroy'
        run: |
          infra destroy --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve

      - name: Show status
        if: always()
        run: |
          infra status --env ${{ github.event.inputs.environment || 'dev' }} || true
```

### GitLab CI

`.gitlab-ci.yml` in your config repository:

```yaml
stages:
  - validate
  - plan
  - apply

variables:
  INFRAFOUNDRY_VERSION: "v0.1.0"
  PYTHON_VERSION: "3.11"

.setup_template: &setup
  before_script:
    # Install Python and InfraFoundry
    - apt-get update && apt-get install -y python3-pip git
    - pip install uv
    - git clone --depth 1 --branch $INFRAFOUNDRY_VERSION https://github.com/your-org/infrafoundry.git
    - cd infrafoundry && uv pip install --system -e . && cd ..

    # Install infrastructure tools
    - |
      # Terraform
      wget -O- https://apt.releases.hashicorp.com/gpg | \
        gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
      echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
        https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
        tee /etc/apt/sources.list.d/hashicorp.list
      apt update && apt install -y terraform

      # Ansible
      pip install ansible

      # SOPS
      wget https://github.com/getsops/sops/releases/latest/download/sops-latest.linux.amd64
      mv sops-latest.linux.amd64 /usr/local/bin/sops
      chmod +x /usr/local/bin/sops

    # Set up secrets
    - mkdir -p secrets
    - echo "$SOPS_AGE_KEY" | base64 -d > secrets/age.key
    - chmod 600 secrets/age.key
    - export SOPS_AGE_KEY_FILE="$(pwd)/secrets/age.key"
    - export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

validate:
  stage: validate
  <<: *setup
  script:
    - infra envs
    - echo "Validation passed"
  only:
    - merge_requests
    - main

plan:dev:
  stage: plan
  <<: *setup
  script:
    - infra plan --env dev
  artifacts:
    paths:
      - generated/
    expire_in: 1 hour
  only:
    - merge_requests
    - main

apply:dev:
  stage: apply
  <<: *setup
  script:
    - infra apply --env dev --auto-approve
  dependencies:
    - plan:dev
  only:
    - main
  when: manual

plan:prod:
  stage: plan
  <<: *setup
  script:
    - infra plan --env prod
  artifacts:
    paths:
      - generated/
    expire_in: 1 hour
  only:
    - main

apply:prod:
  stage: apply
  <<: *setup
  script:
    - infra apply --env prod --auto-approve
  dependencies:
    - plan:prod
  only:
    - main
  when: manual
  environment:
    name: production
```

## Team Collaboration

### Sharing Configuration Repository

**1. Clone and set up:**
```bash
git clone <config-repo-url>
cd <config-repo>
cp .envrc.local.example .envrc.local
```

**2. Get age key securely:**

Option A: From password manager/vault
```bash
# Store in 1Password, Vault, etc.
# Retrieve and save to secrets/age.key
```

Option B: Encrypted transfer
```bash
# Team member shares personal age public key
age-keygen -o ~/.ssh/id_age.key

# Admin encrypts shared key
age -r <team-member-public-key> -o age.key.enc secrets/age.key

# Team member decrypts
age -d -i ~/.ssh/id_age.key age.key.enc > secrets/age.key
chmod 600 secrets/age.key
```

**3. Set up provider credentials:**
```bash
# Edit .envrc.local with your credentials
vim .envrc.local

# Load environment
direnv allow
```

### Multi-User SOPS Setup

For better security, each team member can have their own age key:

1. **Each team member generates a key:**
```bash
age-keygen -o ~/.ssh/infra_age.key
# Save public key: age1xxxxxx...
```

2. **Admin updates `.sops.yaml` in config repo:**
```yaml
creation_rules:
  - path_regex: .*\.yaml$
    age: >-
      age1public_user1...,
      age1public_user2...,
      age1public_user3...
```

3. **Re-encrypt all secrets:**
```bash
for file in secrets/*.yaml; do
  sops updatekeys -y "$file"
done
```

4. **Each team member sets their key:**
```bash
# In .envrc.local
export SOPS_AGE_KEY_FILE="$HOME/.ssh/infra_age.key"
```

## Migration Guide

### From Embedded to Separate Config

If you have configs in the framework repo, migrate them:

1. **Create config repository:**
```bash
mkdir ../infrafoundry-config
cd ../infrafoundry-config
git init
```

2. **Copy configurations:**
```bash
cp -r ../infrafoundry/envs .
cp -r ../infrafoundry/secrets .
cp ../infrafoundry/.envrc.local.example .
```

3. **Set up config repository:**
```bash
# Copy gitignore from example-config
cp ../infrafoundry/example-config/.gitignore .
cp ../infrafoundry/example-config/README.md .

# Initialize
git add .
git commit -m "Initial config repository"
```

4. **Update .envrc.local:**
```bash
cp .envrc.local.example .envrc.local
# Edit and add:
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
```

5. **Test:**
```bash
direnv allow
infra envs
infra plan --env dev --dry-run
```

6. **Clean up framework repo:**
```bash
cd ../infrafoundry
rm -rf envs/ secrets/
git add -u
git commit -m "Move configs to separate repository"
```

## Best Practices

### Configuration Repository

1. **Use branch protection** - Require reviews for main branch
2. **Tag releases** - Version your infrastructure configs (`v1.0.0`, `v1.1.0`)
3. **Document changes** - Keep CHANGELOG.md updated
4. **Test in dev first** - Never apply directly to prod
5. **Backup age key** - Store securely offline, not in repo

### Secrets Management

1. **Rotate regularly** - Update encrypted secrets periodically
2. **Per-environment keys** - Different age keys for dev/prod
3. **Audit access** - Review who has age key access
4. **Never commit unencrypted** - Always encrypt before committing
5. **Use .yaml.example** - Provide templates without real secrets

### CI/CD

1. **Pin framework version** - Don't use `latest`, use specific version
2. **Environment-specific jobs** - Separate CI jobs per environment
3. **Manual prod deploys** - Require approval for production
4. **Save artifacts** - Keep generated Terraform for debugging
5. **Test on branches** - Run plan on feature branches

### Team Collaboration

1. **Document everything** - README with setup instructions
2. **Onboarding guide** - How new members get access
3. **Communication** - Announce infrastructure changes
4. **Review process** - All changes reviewed by team
5. **Runbooks** - Document common operations and troubleshooting

## Troubleshooting

### Config repo not found

```bash
# Check environment variable
echo $INFRAFOUNDRY_CONFIG_REPO

# Should point to config repo root
export INFRAFOUNDRY_CONFIG_REPO=/path/to/config

# Or use CLI option
infra --config-dir /path/to/config envs
```

### Wrong environment directory

InfraFoundry looks for `envs/` inside the config repo:

```
config-repo/
└── envs/          ← Must be named "envs"
    ├── dev/
    └── prod/
```

### Secrets not found

```bash
# Check SOPS_AGE_KEY_FILE points to key in config repo
echo $SOPS_AGE_KEY_FILE
# Should be: /path/to/config-repo/secrets/age.key

# Verify key exists
ls -l $SOPS_AGE_KEY_FILE

# Test decryption
sops -d secrets/proxmox.yaml
```

### Generated files location

By default, generated files go to `./generated/`:

```bash
# Override output directory
export INFRAFOUNDRY_OUTPUT_DIR="/path/to/output"

# Or run from config repo root
cd /path/to/config-repo
infra plan --env dev
ls generated/
```

## Examples

### Example 1: Personal Projects

```
~/projects/
├── infrafoundry/           # Framework (git pull to update)
└── my-homelab/             # Config repo (your infrastructure)
    ├── envs/dev/
    ├── secrets/
    └── .envrc.local        # export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
```

### Example 2: Multi-Client Consulting

```
~/clients/
├── infrafoundry/           # Shared framework
├── client-a-infra/         # Client A config repo
├── client-b-infra/         # Client B config repo
└── client-c-infra/         # Client C config repo
```

Each client config has their own:
- Git repository
- Secrets/age key
- CI/CD pipeline
- Access controls

### Example 3: Enterprise with Environments

```
~/enterprise/
├── infrafoundry/           # Framework
└── infrastructure/         # Config repo
    ├── envs/
    │   ├── dev/
    │   ├── staging/
    │   ├── prod-us-east/
    │   ├── prod-us-west/
    │   └── prod-eu/
    ├── secrets/
    │   ├── dev/
    │   ├── staging/
    │   └── prod/
    └── .envrc.local
```

## Additional Resources

- [InfraFoundry Documentation](../README.md)
- [Plugin Development Guide](plugin-development.md)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)
- [direnv Setup](direnv.md)
