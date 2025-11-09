# Per-Environment Credentials

Different environments (dev, staging, prod) typically need different credentials. This guide covers best practices for managing environment-specific credentials in InfraFoundry.

## Automatic Credential Loading

**InfraFoundry automatically loads environment-specific credentials based on the `--env` flag.** You don't need to manually switch environment variables - the CLI handles it for you!

```bash
# Just use --env flag - credentials are loaded automatically!
infra plan --env dev      # Uses secrets/dev/proxmox.yaml, etc.
infra apply --env staging # Uses secrets/staging/proxmox.yaml, etc.
infra plan --env prod     # Uses secrets/prod/proxmox.yaml, etc.
```

When you run a command with `--env`, InfraFoundry:
1. Looks for encrypted secrets in `secrets/{env}/proxmox.yaml`, `secrets/{env}/opnsense.yaml`, etc.
2. Decrypts them using SOPS
3. Sets the appropriate environment variables (`PROXMOX_API_URL`, `OPNSENSE_API_KEY`, etc.)
4. Proceeds with the operation using the correct credentials

**No manual environment switching required!** ✨

## The Challenge

Each environment needs its own set of credentials:
- **Dev**: Development Proxmox cluster, test firewall, dev Kubernetes cluster
- **Staging**: Staging infrastructure, pre-prod credentials
- **Production**: Production infrastructure, highly restricted access

## Recommended Approaches

### Approach 1: Environment-Specific Secrets Files (Recommended)

Store credentials in SOPS-encrypted files per environment.

#### Structure

```
config-repo/
├── secrets/
│   ├── .sops.yaml                 # SOPS config
│   ├── dev/                       # Dev environment secrets
│   │   ├── age.key                # Dev encryption key (git-ignored)
│   │   ├── proxmox.yaml           # Encrypted with dev age.key
│   │   ├── opnsense.yaml          # Encrypted with dev age.key
│   │   └── kubernetes.yaml        # Encrypted with dev age.key
│   ├── staging/                   # Staging environment secrets
│   │   ├── age.key                # Staging encryption key (git-ignored)
│   │   ├── proxmox.yaml           # Encrypted with staging age.key
│   │   ├── opnsense.yaml          # Encrypted with staging age.key
│   │   └── kubernetes.yaml        # Encrypted with staging age.key
│   └── prod/                      # Production secrets
│       ├── age.key                # Production encryption key (git-ignored)
│       ├── proxmox.yaml           # Encrypted with prod age.key
│       ├── opnsense.yaml          # Encrypted with prod age.key
│       └── kubernetes.yaml        # Encrypted with prod age.key
└── .envrc.local
```

**Benefits of per-environment keys:**
- **Security isolation**: Compromising one environment's key doesn't expose others
- **Access control**: Give team members only the keys they need (devs get dev key, ops get prod key)
- **Automatic key selection**: InfraFoundry automatically uses the correct key based on `--env` flag

#### Setup

**1. Generate age keys for each environment:**

```bash
# Create age keys per environment
age-keygen -o secrets/dev/age.key
age-keygen -o secrets/staging/age.key
age-keygen -o secrets/prod/age.key  # Keep this highly restricted!

# Add to .gitignore
echo "secrets/*/age.key" >> .gitignore
```

**2. Update `.sops.yaml` for per-environment keys:**

```yaml
# secrets/.sops.yaml
creation_rules:
  - path_regex: dev/.*\.yaml$
    age: age1xxx...dev-public-key...xxx  # Public key from secrets/dev/age.key
  
  - path_regex: staging/.*\.yaml$
    age: age1xxx...staging-public-key...xxx  # Public key from secrets/staging/age.key
  
  - path_regex: prod/.*\.yaml$
    age: age1xxx...prod-public-key...xxx  # Public key from secrets/prod/age.key
```

**3. Create environment-specific secrets:**

```bash
# Dev credentials
cat > secrets/dev/proxmox.yaml <<EOF
proxmox:
  api_url: https://proxmox-dev.example.com:8006/api2/json
  api_token_id: terraform@pve!dev-token
  api_token_secret: dev-secret-here
EOF

# Staging credentials
cat > secrets/staging/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox-staging.example.com:8006/api2/json
proxmox_token_id: terraform@pve!staging-token
proxmox_token_secret: staging-secret-here
EOF

# Production credentials
cat > secrets/prod/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox.example.com:8006/api2/json
proxmox_token_id: terraform@pve!prod-token
proxmox_token_secret: prod-secret-here
EOF

# Encrypt all
sops --encrypt --in-place secrets/dev/proxmox.yaml
sops --encrypt --in-place secrets/staging/proxmox.yaml
sops --encrypt --in-place secrets/prod/proxmox.yaml
```

**3. Use with InfraFoundry:**

```bash
# Credentials are loaded automatically based on --env flag!
infra plan --env dev       # Automatically uses secrets/dev/proxmox.yaml
infra apply --env staging  # Automatically uses secrets/staging/proxmox.yaml
infra plan --env prod      # Automatically uses secrets/prod/proxmox.yaml
```

**That's it!** No need to manually load environment variables or switch contexts. The CLI handles everything automatically.

#### Optional: Manual Loading in .envrc.local

For advanced use cases (debugging, testing, CI/CD), you can still manually load credentials in `.envrc.local`:

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/secrets/age.key"

# Optional: Set default environment for direnv-based workflows
export INFRA_ENV="${INFRA_ENV:-dev}"

# Optional: Function to manually load environment secrets
load_env_secrets() {
    local env=$1
    local secrets_dir="${INFRAFOUNDRY_CONFIG_REPO}/secrets/${env}"

    if [[ -f "${secrets_dir}/proxmox.yaml" ]]; then
        # Decrypt and export Proxmox credentials
        eval "$(sops --decrypt "${secrets_dir}/proxmox.yaml" | \
            yq eval '.proxmox_api_url, .proxmox_token_id, .proxmox_token_secret' - | \
            awk '{print "export PROXMOX_" toupper($1) "=" $2}')"
    fi

    if [[ -f "${secrets_dir}/opnsense.yaml" ]]; then
        # Decrypt and export OPNsense credentials
        eval "$(sops --decrypt "${secrets_dir}/opnsense.yaml" | \
            yq eval '.opnsense_api_url, .opnsense_api_key, .opnsense_api_secret' - | \
            awk '{print "export OPNSENSE_" toupper($1) "=" $2}')"
    fi
}

# Uncomment to auto-load on direnv reload (not needed for normal CLI usage)
# load_env_secrets "$INFRA_ENV"
# echo "Loaded credentials for environment: $INFRA_ENV"
```

**Note:** Manual loading is **optional** and rarely needed. The CLI loads credentials automatically.

#### Pros & Cons

**Pros:**
- ✅ Automatic credential loading - no manual environment switching
- ✅ All secrets version controlled (encrypted)
- ✅ Single age key for all environments
- ✅ Easy to add new environments
- ✅ Credentials stored with infrastructure configs
- ✅ Team can share encrypted secrets
- ✅ Simple workflow: just use `--env` flag

**Cons:**
- ❌ All team members have access to all env secrets (if shared key)
- ⚠️  Requires SOPS and age for encryption/decryption

---

### Approach 2: Separate Age Keys Per Environment

Use different encryption keys for each environment, granting access per environment.

#### Structure

```
config-repo/
├── secrets/
│   ├── .sops.yaml                 # SOPS config with per-env keys
│   ├── dev/
│   │   ├── age.key                # Dev encryption key (git-ignored)
│   │   ├── proxmox.yaml           # Encrypted with dev key
│   │   └── opnsense.yaml
│   ├── staging/
│   │   ├── age.key                # Staging key (git-ignored)
│   │   ├── proxmox.yaml           # Encrypted with staging key
│   │   └── opnsense.yaml
│   └── prod/
│       ├── age.key                # Prod key (git-ignored)
│       ├── proxmox.yaml           # Encrypted with prod key
│       └── opnsense.yaml
└── .envrc.local
```

#### Setup

**1. Create `.sops.yaml` with per-environment keys:**

```yaml
# secrets/.sops.yaml
creation_rules:
  # Dev secrets - dev team members
  - path_regex: dev/.*\.yaml$
    age: age1dev_public_key_here...

  # Staging secrets - senior devs + ops
  - path_regex: staging/.*\.yaml$
    age: age1staging_public_key_here...

  # Production secrets - ops team only
  - path_regex: prod/.*\.yaml$
    age: age1prod_public_key_here...
```

**2. Generate keys per environment:**

```bash
# Dev key
age-keygen -o secrets/dev/age.key

# Staging key
age-keygen -o secrets/staging/age.key

# Production key (kept by ops team)
age-keygen -o secrets/prod/age.key
```

**3. Encrypt secrets with environment-specific keys:**

```bash
# Encrypt dev secrets with dev key
export SOPS_AGE_KEY_FILE="secrets/dev/age.key"
sops --encrypt --in-place secrets/dev/proxmox.yaml

# Encrypt staging secrets with staging key
export SOPS_AGE_KEY_FILE="secrets/staging/age.key"
sops --encrypt --in-place secrets/staging/proxmox.yaml

# Encrypt prod secrets with prod key
export SOPS_AGE_KEY_FILE="secrets/prod/age.key"
sops --encrypt --in-place secrets/prod/proxmox.yaml
```

**4. Update `.envrc.local` (simplified!):**

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Note: SOPS age key is automatically set per-environment!
# InfraFoundry will use secrets/{env}/age.key based on --env flag
# No need to manually set SOPS_AGE_KEY_FILE
```

**5. Usage:**

```bash
# Dev work - automatically uses secrets/dev/age.key
infra plan --env dev

# Staging - automatically uses secrets/staging/age.key
infra apply --env staging

# Production - automatically uses secrets/prod/age.key (if you have the key!)
infra plan --env prod

# Staging work (need staging age key)
export INFRA_ENV=staging
direnv reload
infra plan --env staging

# Prod work (need prod age key - ops only)
export INFRA_ENV=prod
direnv reload
infra apply --env prod
```

#### Pros & Cons

**Pros:**
- ✅ Fine-grained access control (different keys per env)
- ✅ Developers can't decrypt prod secrets
- ✅ Compliance-friendly (separation of duties)
- ✅ Easy to revoke access (change env key)

**Cons:**
- ❌ More complex key management
- ❌ Need multiple keys backed up
- ❌ Team members need correct key for their environments

---

### Approach 3: Environment Variable Override

Use `.envrc.local` with environment detection or manual override.

#### Structure

```
config-repo/
├── secrets/
│   ├── age.key                    # Single key
│   ├── .sops.yaml
│   └── credentials.yaml           # All environments in one file (encrypted)
└── .envrc.local
```

#### Setup

**1. Create multi-environment secrets file:**

```yaml
# secrets/credentials.yaml (before encryption)
dev:
  proxmox:
    api_url: https://proxmox-dev.example.com:8006/api2/json
    token_id: terraform@pve!dev
    token_secret: dev-secret
  opnsense:
    api_url: https://firewall-dev.example.com
    api_key: dev-key
    api_secret: dev-secret

staging:
  proxmox:
    api_url: https://proxmox-staging.example.com:8006/api2/json
    token_id: terraform@pve!staging
    token_secret: staging-secret
  opnsense:
    api_url: https://firewall-staging.example.com
    api_key: staging-key
    api_secret: staging-secret

prod:
  proxmox:
    api_url: https://proxmox.example.com:8006/api2/json
    token_id: terraform@pve!prod
    token_secret: prod-secret
  opnsense:
    api_url: https://firewall.example.com
    api_key: prod-key
    api_secret: prod-secret
```

**2. Encrypt:**

```bash
sops --encrypt --in-place secrets/credentials.yaml
```

**3. Update `.envrc.local`:**

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/secrets/age.key"

# Determine environment (default to dev)
export INFRA_ENV="${INFRA_ENV:-dev}"

# Decrypt and load credentials for current environment
SECRETS_FILE="${INFRAFOUNDRY_CONFIG_REPO}/secrets/credentials.yaml"

if [[ -f "$SECRETS_FILE" ]]; then
    # Extract credentials for current environment
    CREDS=$(sops --decrypt "$SECRETS_FILE" | yq eval ".${INFRA_ENV}" -)

    # Proxmox
    export PROXMOX_API_URL=$(echo "$CREDS" | yq eval '.proxmox.api_url' -)
    export PROXMOX_API_TOKEN_ID=$(echo "$CREDS" | yq eval '.proxmox.token_id' -)
    export PROXMOX_API_TOKEN_SECRET=$(echo "$CREDS" | yq eval '.proxmox.token_secret' -)

    # OPNsense
    export OPNSENSE_API_URL=$(echo "$CREDS" | yq eval '.opnsense.api_url' -)
    export OPNSENSE_API_KEY=$(echo "$CREDS" | yq eval '.opnsense.api_key' -)
    export OPNSENSE_API_SECRET=$(echo "$CREDS" | yq eval '.opnsense.api_secret' -)

    echo "Loaded ${INFRA_ENV} credentials"
fi
```

**4. Usage:**

```bash
# Dev (default)
infra plan --env dev

# Staging
INFRA_ENV=staging infra plan --env staging

# Production
INFRA_ENV=prod infra apply --env prod

# Or export and reload
export INFRA_ENV=prod
direnv reload
infra apply --env prod
```

#### Pros & Cons

**Pros:**
- ✅ Single secrets file
- ✅ Easy environment switching
- ✅ Simple setup

**Cons:**
- ❌ All environments visible in one file
- ❌ Everyone with age key can decrypt all environments
- ❌ No separation of duties

---

### Approach 4: CI/CD with External Secret Management

For production deployments, use external secret managers.

#### Setup

**GitHub Actions:**

```yaml
# .github/workflows/deploy-prod.yml
name: Deploy Production

on:
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # GitHub environment protection

    steps:
      - uses: actions/checkout@v4

      - name: Set up secrets
        env:
          # From GitHub Secrets
          PROXMOX_API_URL: ${{ secrets.PROD_PROXMOX_API_URL }}
          PROXMOX_API_TOKEN_ID: ${{ secrets.PROD_PROXMOX_TOKEN_ID }}
          PROXMOX_API_TOKEN_SECRET: ${{ secrets.PROD_PROXMOX_TOKEN_SECRET }}
          OPNSENSE_API_URL: ${{ secrets.PROD_OPNSENSE_API_URL }}
          OPNSENSE_API_KEY: ${{ secrets.PROD_OPNSENSE_API_KEY }}
          OPNSENSE_API_SECRET: ${{ secrets.PROD_OPNSENSE_API_SECRET }}
        run: |
          # Credentials available as environment variables
          infra apply --env prod --auto-approve
```

**AWS Secrets Manager:**

```bash
# .envrc.local
export INFRA_ENV="${INFRA_ENV:-dev}"

# Fetch from AWS Secrets Manager
fetch_aws_secrets() {
    local env=$1
    local secret_name="infrafoundry/${env}/credentials"

    # Fetch and parse secrets
    aws secretsmanager get-secret-value \
        --secret-id "$secret_name" \
        --query SecretString \
        --output text | jq -r 'to_entries[] | "export \(.key)=\(.value)"'
}

# Load secrets
eval "$(fetch_aws_secrets "$INFRA_ENV")"
```

**HashiCorp Vault:**

```bash
# .envrc.local
export INFRA_ENV="${INFRA_ENV:-dev}"
export VAULT_ADDR="https://vault.example.com"

# Fetch from Vault
fetch_vault_secrets() {
    local env=$1
    local path="secret/infrafoundry/${env}"

    # Read secrets from Vault
    vault kv get -format=json "$path" | \
        jq -r '.data.data | to_entries[] | "export \(.key)=\(.value)"'
}

# Authenticate to Vault (assumes token in VAULT_TOKEN)
if [[ -n "$VAULT_TOKEN" ]]; then
    eval "$(fetch_vault_secrets "$INFRA_ENV")"
fi
```

#### Pros & Cons

**Pros:**
- ✅ Enterprise-grade secret management
- ✅ Audit logging built-in
- ✅ Fine-grained access control
- ✅ Automatic rotation support
- ✅ Integration with existing systems

**Cons:**
- ❌ Requires external infrastructure
- ❌ More complex setup
- ❌ Additional costs
- ❌ Network dependency

---

## Comparison Matrix

| Approach | Access Control | Complexity | Cost | Best For |
|----------|---------------|------------|------|----------|
| **Env-Specific Files** | Shared key | Low | Free | Small teams, simple projects |
| **Separate Keys** | Per-environment | Medium | Free | Medium teams, compliance needs |
| **Single File** | Shared key | Low | Free | Solo developers |
| **External Secret Manager** | Fine-grained | High | $$$ | Enterprises, production systems |

## Recommended Setup by Team Size

### Solo Developer / Hobby Projects
**Use:** Approach 3 (Single File)
- Simple, easy to manage
- Quick environment switching
- Minimal overhead

### Small Team (2-10 people)
**Use:** Approach 1 (Env-Specific Files)
- Balances simplicity and organization
- Easy to add new environments
- Team can collaborate on encrypted secrets

### Medium Team (10-50 people)
**Use:** Approach 2 (Separate Keys)
- Control who can access prod
- Developers only get dev/staging keys
- Ops team manages prod keys

### Enterprise / Production Systems
**Use:** Approach 4 (External Secret Manager)
- Integrate with existing secret management
- Full audit trail
- Automated rotation
- Compliance requirements met

## Migration Example

Migrating from single `.envrc.local` to environment-specific secrets:

```bash
# 1. Create directory structure
mkdir -p secrets/{dev,staging,prod}

# 2. Move existing credentials to dev
cat > secrets/dev/proxmox.yaml <<EOF
proxmox_api_url: $PROXMOX_API_URL
proxmox_token_id: $PROXMOX_API_TOKEN_ID
proxmox_token_secret: $PROXMOX_API_TOKEN_SECRET
EOF

# 3. Create staging/prod with different values
cat > secrets/staging/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox-staging.example.com:8006/api2/json
proxmox_token_id: terraform@pve!staging-token
proxmox_token_secret: staging-secret-here
EOF

# 4. Encrypt all
for env in dev staging prod; do
    sops --encrypt --in-place secrets/${env}/proxmox.yaml
done

# 5. Update .envrc.local to load from secrets/
# (See Approach 1 above)

# 6. Test each environment
INFRA_ENV=dev infra plan --env dev
INFRA_ENV=staging infra plan --env staging
INFRA_ENV=prod infra plan --env prod --dry-run
```

## Security Best Practices

1. **Never commit unencrypted secrets**
   ```bash
   # .gitignore
   secrets/*.key
   secrets/**/*.key
   .envrc.local
   ```

2. **Rotate credentials regularly**
   ```bash
   # Update secret
   sops secrets/prod/proxmox.yaml
   # Change proxmox_token_secret

   # Re-encrypt
   sops --encrypt --in-place secrets/prod/proxmox.yaml
   ```

3. **Use principle of least privilege**
   - Developers: dev + staging keys only
   - Ops team: all keys
   - CI/CD: env-specific tokens with minimal permissions

4. **Backup age keys securely**
   ```bash
   # Encrypt age key with GPG
   gpg --encrypt --recipient your-email@example.com secrets/age.key

   # Store encrypted backup in password manager
   ```

5. **Audit access**
   ```bash
   # Log who decrypts secrets (in CI)
   echo "$(date): $USER decrypted secrets for $INFRA_ENV" >> audit.log
   ```

6. **Use different tokens per environment**
   - Don't reuse prod tokens in dev
   - Create environment-specific API tokens
   - Limit token permissions (read-only for plan, read-write for apply)

## Troubleshooting

### Wrong credentials loaded

**Problem:** Applied to prod with dev credentials

**Solution:**
```bash
# Check current environment
echo $INFRA_ENV

# Verify loaded credentials (without exposing secrets)
echo $PROXMOX_API_URL

# Should show prod URL
# If not, reload environment
export INFRA_ENV=prod
direnv reload
```

### Cannot decrypt secrets

**Problem:** `error decrypting key`

**Solution:**
```bash
# Verify age key exists
ls -l $SOPS_AGE_KEY_FILE

# Check if key matches encrypted file
sops --decrypt secrets/dev/proxmox.yaml

# If wrong key, check INFRA_ENV
echo $INFRA_ENV
export INFRA_ENV=dev
```

### Missing credentials

**Problem:** Variables not set after direnv reload

**Solution:**
```bash
# Check if secrets file exists
ls -l secrets/${INFRA_ENV}/

# Manually decrypt to debug
sops --decrypt secrets/${INFRA_ENV}/proxmox.yaml

# Check .envrc.local syntax
bash -n .envrc.local
```

## Related Documentation

- [State Management Strategies](state-management.md)
- [Separate Configuration Repository](separate-config-repo.md)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)
- [direnv Setup](direnv.md)
