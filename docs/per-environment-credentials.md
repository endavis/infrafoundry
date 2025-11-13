# Per-Environment Credentials

Different environments (dev, staging, prod) typically need different credentials. This guide covers best practices for managing environment-specific credentials in InfraFoundry.

## Automatic Credential Loading

**InfraFoundry automatically loads environment-specific credentials based on the `--env` flag.** You don't need to manually switch environment variables - the CLI handles it for you!

```bash
# Just use --env flag - credentials are loaded automatically!
infra plan --env dev      # Uses envs/dev/settings.yaml
infra apply --env staging # Uses envs/staging/settings.yaml
infra plan --env prod     # Uses envs/prod/settings.yaml
```

When you run a command with `--env`, InfraFoundry:
1. Looks for encrypted settings in `envs/{env}/settings.yaml`
2. Decrypts them using SOPS with the environment's age key
3. Extracts credentials from `provider_settings` section
4. Sets the appropriate environment variables (`PROXMOX_API_URL`, `OPNSENSE_API_KEY`, etc.)
5. Proceeds with the operation using the correct credentials

**No manual environment switching required!** ✨

## The Challenge

Each environment needs its own set of credentials:
- **Dev**: Development Proxmox cluster, test firewall, dev Kubernetes cluster
- **Staging**: Staging infrastructure, pre-prod credentials
- **Production**: Production infrastructure, highly restricted access

## Recommended Approaches

### Approach 1: Per-Environment Settings Files (Recommended)

Store all configuration and credentials in SOPS-encrypted `settings.yaml` per environment.

#### Structure

```
config-repo/
├── .sops.yaml                     # SOPS config with per-environment rules
├── envs/
│   ├── dev/                       # Dev environment
│   │   ├── age.key                # Dev encryption key (git-ignored)
│   │   ├── settings.yaml          # Encrypted config + credentials
│   │   └── resources/             # Resource definitions (not encrypted)
│   │       └── vms.yaml
│   ├── staging/                   # Staging environment
│   │   ├── age.key                # Staging encryption key (git-ignored)
│   │   ├── settings.yaml          # Encrypted config + credentials
│   │   └── resources/
│   │       └── vms.yaml
│   └── prod/                      # Production environment
│       ├── age.key                # Production encryption key (git-ignored)
│       ├── settings.yaml          # Encrypted config + credentials
│       └── resources/
│           └── vms.yaml
└── .envrc.local                   # Local environment variables
```

**Benefits of per-environment structure:**
- **Security isolation**: Each environment has its own encryption key
- **Access control**: Give team members only the keys they need (devs get dev key, ops get prod key)
- **Automatic key selection**: InfraFoundry automatically uses the correct key based on `--env` flag
- **Consolidated configuration**: All settings and credentials in one encrypted file per environment

#### Setup

**1. Generate age keys for each environment:**

```bash
# Create age keys in each environment directory
age-keygen -o envs/dev/age.key
age-keygen -o envs/staging/age.key
age-keygen -o envs/prod/age.key  # Keep this highly restricted!

# Add to .gitignore
echo "envs/*/age.key" >> .gitignore
```

**2. Update `.sops.yaml` for per-environment keys:**

```yaml
# .sops.yaml (in config repo root)
creation_rules:
  - path_regex: envs/dev/settings\.yaml$
    age: age1xxx...dev-public-key...xxx  # From: age-keygen -y envs/dev/age.key

  - path_regex: envs/staging/settings\.yaml$
    age: age1xxx...staging-public-key...xxx  # From: age-keygen -y envs/staging/age.key

  - path_regex: envs/prod/settings\.yaml$
    age: age1xxx...prod-public-key...xxx  # From: age-keygen -y envs/prod/age.key
```

**3. Add credentials to settings.yaml and encrypt:**

```bash
# Edit your settings file to add credentials
vim envs/dev/settings.yaml
```

Add provider credentials to `provider_settings`:
```yaml
# envs/dev/settings.yaml
name: dev
description: Development environment

provider_settings:
  proxmox:
    api_url: https://pve-dev.example.com:8006
    api_token_id: terraform@pve!dev
    api_token_secret: your-dev-secret

  opnsense:
    api_url: https://fw-dev.example.com
    api_key: dev-api-key
    api_secret: dev-api-secret
```

**4. Encrypt the settings file:**

```bash
# Encrypt settings.yaml
sops --encrypt --in-place envs/dev/settings.yaml
sops --encrypt --in-place envs/staging/settings.yaml
sops --encrypt --in-place envs/prod/settings.yaml

# Verify encryption
head envs/dev/settings.yaml  # Should show ENC[...] values
```

**5. Set age key for each environment:**

```bash
# In .envrc.local, point to the environment-specific age key
# The --env flag will automatically use the right key
export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/envs/dev/age.key"  # For dev work

# Or set per-command:
SOPS_AGE_KEY_FILE=envs/prod/age.key infra plan --env prod
```
  api_url: https://proxmox-dev.example.com:8006/api2/json
  api_token_id: terraform@pve!dev-token
  api_token_secret: dev-secret-here
EOF

# Staging credentials
cat > envs/staging/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox-staging.example.com:8006/api2/json
proxmox_token_id: terraform@pve!staging-token
proxmox_token_secret: staging-secret-here
EOF

# Production credentials
cat > envs/prod/proxmox.yaml <<EOF
proxmox_api_url: https://proxmox.example.com:8006/api2/json
proxmox_token_id: terraform@pve!prod-token
proxmox_token_secret: prod-secret-here
EOF

# Encrypt all
sops --encrypt --in-place envs/dev/proxmox.yaml
sops --encrypt --in-place envs/staging/proxmox.yaml
sops --encrypt --in-place envs/prod/proxmox.yaml
```

**3. Use with InfraFoundry:**

```bash
# Credentials are loaded automatically based on --env flag!
infra plan --env dev       # Automatically uses envs/dev/settings.yaml
infra apply --env staging  # Automatically uses envs/staging/settings.yaml
infra plan --env prod      # Automatically uses envs/prod/settings.yaml
```

**That's it!** No need to manually load environment variables or switch contexts. The CLI handles everything automatically.

#### Optional: Manual Age Key Setup for Local Development

For local development, set the age key in `.envrc.local`:

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Point to your default environment's age key
export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/envs/dev/age.key"

# Or dynamically set based on environment variable
# export INFRA_ENV="${INFRA_ENV:-dev}"
# export SOPS_AGE_KEY_FILE="${INFRAFOUNDRY_CONFIG_REPO}/envs/${INFRA_ENV}/age.key"
```

**Note:** The CLI automatically handles credential loading when you use `--env`. Manual setup is only needed for:
- Running `sops --encrypt` or `sops --decrypt` commands directly
- Debugging credential issues
- CI/CD pipelines

#### Pros & Cons

**Pros:**
- ✅ Automatic credential loading - no manual environment switching
- ✅ All settings and credentials in one encrypted file per environment
- ✅ Per-environment encryption keys for better security isolation
- ✅ Easy to add new environments
- ✅ Settings stored with infrastructure configs
- ✅ Team can share encrypted settings
- ✅ Simple workflow: just use `--env` flag
- ✅ Clear separation between environments

**Cons:**
- ⚠️  Requires SOPS and age for encryption/decryption
- ⚠️  Need to manage separate age keys per environment (but better security!)

---

### Approach 2: Alternative - Separate Provider Credential Files (Legacy)

**Note:** This approach is supported but not recommended. Use consolidated `settings.yaml` instead.

You can still store credentials in separate files per provider if needed:

#### Structure

```
config-repo/
├── envs/
│   ├── dev/
│   │   ├── age.key                # Dev encryption key (git-ignored)
│   │   ├── settings.yaml          # Main config (encrypted with dev key)
│   │   ├── proxmox-alt.yaml       # Optional separate provider file
│   │   └── opnsense-alt.yaml
│   ├── staging/
│   │   ├── age.key                # Staging key (git-ignored)
│   │   ├── settings.yaml          # Main config
│   │   ├── proxmox-alt.yaml       # Encrypted with staging key
│   │   └── opnsense-alt.yaml
│   └── prod/
│       ├── age.key                # Prod key (git-ignored)
│       ├── proxmox.yaml           # Encrypted with prod key
│       └── opnsense.yaml
└── .envrc.local
```

#### Setup

**1. Create `.sops.yaml` with per-environment keys:**

```yaml
# .sops.yaml (in config repo root)
creation_rules:
  # Dev secrets - dev team members
  - path_regex: envs/dev/settings\.yaml$
    age: age1dev_public_key_here...

  # Staging secrets - senior devs + ops
  - path_regex: envs/staging/settings\.yaml$
    age: age1staging_public_key_here...

  # Production secrets - ops team only
  - path_regex: envs/prod/settings\.yaml$
    age: age1prod_public_key_here...
```

**2. Generate keys per environment:**

```bash
# Dev key
age-keygen -o envs/dev/age.key

# Staging key
age-keygen -o envs/staging/age.key

# Production key (kept by ops team)
age-keygen -o envs/prod/age.key
```

**3. Encrypt secrets with environment-specific keys:**

```bash
# Encrypt dev secrets with dev key
export SOPS_AGE_KEY_FILE="envs/dev/age.key"
sops --encrypt --in-place envs/dev/proxmox.yaml

# Encrypt staging secrets with staging key
export SOPS_AGE_KEY_FILE="envs/staging/age.key"
sops --encrypt --in-place envs/staging/proxmox.yaml

# Encrypt prod secrets with prod key
export SOPS_AGE_KEY_FILE="envs/prod/age.key"
sops --encrypt --in-place envs/prod/proxmox.yaml
```

**4. Update `.envrc.local` (simplified!):**

```bash
# .envrc.local
export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"

# Note: SOPS age key is automatically set per-environment!
# InfraFoundry will use envs/{env}/age.key based on --env flag
# No need to manually set SOPS_AGE_KEY_FILE
```

**5. Usage:**

```bash
# Dev work - automatically uses envs/dev/age.key
infra plan --env dev

# Staging - automatically uses envs/staging/age.key
infra apply --env staging

# Production - automatically uses envs/prod/age.key (if you have the key!)
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

## Comparison Matrix

| Approach | Access Control | Complexity | Cost | Best For |
|----------|---------------|------------|------|----------|
| **Env-Specific Files** | Shared key | Low | Free | Small teams, simple projects |
| **Separate Keys** | Per-environment | Medium | Free | Medium teams, compliance needs |

## Recommended Setup by Team Size

### Solo Developer / Small Team (1-10 people)
**Use:** Approach 1 (Environment-Specific Files in settings.yaml)
- Simple, easy to manage
- Credentials in encrypted settings.yaml
- All config in one file per environment
- Minimal overhead

### Medium/Large Team (10+ people)
**Use:** Approach 2 (Separate Keys per Environment)
- Control who can access prod
- Developers only get dev/staging keys
- Ops team manages prod keys
- Security isolation between environments

---

## Working with settings.yaml

All credentials are stored in the `provider_settings` section of each environment's `settings.yaml` file:

```yaml
# envs/dev/settings.yaml (SOPS-encrypted)
name: dev
description: Development environment

providers:
  - proxmox
  - opnsense

provider_settings:
  proxmox:
    api_url: https://proxmox-dev.example.com:8006
    token_id: terraform@pve!dev
    token_secret: dev-secret-here
  opnsense:
    api_url: https://firewall-dev.example.com
    api_key: dev-key-here
    api_secret: dev-secret-here
```

### Encrypting settings.yaml

```bash
# Encrypt a settings file
sops --encrypt --in-place envs/dev/settings.yaml

# Decrypt to view
sops --decrypt envs/dev/settings.yaml

# Edit encrypted file
sops envs/dev/settings.yaml
```

---

## Migration Example

If you have credentials in environment variables, migrate them to settings.yaml:

```bash
# 1. Create environment directories
mkdir -p envs/{dev,staging,prod}

# 2. Create settings.yaml with credentials in provider_settings
cat > envs/dev/settings.yaml <<EOF
provider_settings:
  proxmox:
    api_url: $PROXMOX_API_URL
    token_id: $PROXMOX_API_TOKEN_ID
    token_secret: $PROXMOX_API_TOKEN_SECRET
EOF

# 3. Create staging/prod with different values
cat > envs/staging/settings.yaml <<EOF
provider_settings:
  proxmox:
    api_url: https://proxmox-staging.example.com:8006/api2/json
    token_id: terraform@pve!staging-token
    token_secret: staging-secret-here
EOF

# 4. Encrypt all settings files
for env in dev staging prod; do
    sops --encrypt --in-place envs/${env}/settings.yaml
done

# 5. Test each environment
infra plan --env dev
infra plan --env staging
infra plan --env prod --dry-run
```

## Security Best Practices

1. **Never commit unencrypted secrets**
   ```bash
   # .gitignore
   envs/*/age.key
   .envrc.local
   generated/
   ```

2. **Rotate credentials regularly**
   ```bash
   # Update secret
   sops envs/prod/settings.yaml
   # Change credentials in provider_settings section

   # Save (SOPS re-encrypts automatically)
   ```

3. **Use principle of least privilege**
   - Developers: dev + staging keys only
   - Ops team: all keys
   - CI/CD: env-specific tokens with minimal permissions

4. **Backup age keys securely**
   ```bash
   # Encrypt age key with GPG
   gpg --encrypt --recipient your-email@example.com envs/prod/age.key

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
# Check which environment you're using
infra plan --env prod --dry-run

# Verify credentials are correct in settings.yaml
sops --decrypt envs/prod/settings.yaml | grep api_url
```

### Cannot decrypt secrets

**Problem:** `error decrypting key`

**Solution:**
```bash
# Verify age key exists for this environment
ls -l envs/prod/age.key

# Set SOPS_AGE_KEY_FILE if needed
export SOPS_AGE_KEY_FILE="$(pwd)/envs/prod/age.key"

# Try to decrypt
sops --decrypt envs/prod/settings.yaml
```

### Missing credentials

**Problem:** Provider credentials not found

**Solution:**
```bash
# Check if settings file exists
ls -l envs/prod/settings.yaml

# Verify provider_settings structure
sops --decrypt envs/prod/settings.yaml | grep -A 5 provider_settings

# Ensure credentials are in the provider_settings section
```

## Related Documentation

- [State Management Strategies](state-management.md)
- [Separate Configuration Repository](separate-config-repo.md)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)
- [direnv Setup](direnv.md)
