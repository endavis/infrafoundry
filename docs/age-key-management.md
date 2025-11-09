# Age Key Management Best Practices

## Overview

Age keys are used to encrypt/decrypt your infrastructure secrets with SOPS. This guide covers best practices for managing these sensitive keys.

## Critical Rules

### ⚠️ Rule #1: NEVER Commit Private Keys to Git

**Private age keys (`age.key` files) must NEVER be committed to version control.**

Your `.gitignore` should always include:
```gitignore
*.key
secrets/*/age.key
secrets/**/age.key
```

## Per-Environment Keys (Recommended)

InfraFoundry supports per-environment age keys for enhanced security:

```
config-repo/
├── secrets/
│   ├── dev/
│   │   ├── age.key          # Development key (git-ignored)
│   │   ├── proxmox.yaml     # Encrypted with dev key
│   │   └── opnsense.yaml    # Encrypted with dev key
│   ├── staging/
│   │   ├── age.key          # Staging key (git-ignored)
│   │   └── *.yaml           # Encrypted with staging key
│   └── prod/
│       ├── age.key          # Production key (git-ignored, highly restricted!)
│       └── *.yaml           # Encrypted with prod key
└── .sops.yaml               # SOPS config with per-env rules
```

### Benefits

1. **Security Isolation**: Compromising one environment's key doesn't expose others
2. **Access Control**: Give developers dev keys only, ops team gets prod keys
3. **Audit Trail**: Track who can access which environments
4. **Compliance**: Meet regulatory requirements for production key restrictions

### Automatic Key Selection

InfraFoundry automatically uses the correct key based on `--env`:

```bash
# Uses secrets/dev/age.key
infra plan --env dev

# Uses secrets/staging/age.key  
infra apply --env staging

# Uses secrets/prod/age.key (if you have it!)
infra plan --env prod
```

## Key Distribution Methods

### Method 1: Secure Key Management System (Most Secure)

Store keys in a dedicated key management system:

- **HashiCorp Vault**: Enterprise-grade secret management
- **AWS Secrets Manager**: Cloud-native secret storage
- **Azure Key Vault**: Microsoft's key management service
- **1Password / Bitwarden**: Team password managers with CLI access

**Pros:**
- Centralized management
- Audit logs
- Automatic rotation
- Fine-grained access control

**Cons:**
- Additional infrastructure
- Learning curve
- Cost

**Example (HashiCorp Vault):**
```bash
# Store key
vault kv put secret/infrafoundry/prod-age-key content=@secrets/prod/age.key

# Retrieve key
vault kv get -field=content secret/infrafoundry/prod-age-key > secrets/prod/age.key
chmod 600 secrets/prod/age.key
```

### Method 2: Encrypted Channel (Good for Small Teams)

Share keys via secure, encrypted channels:

**Options:**
- Encrypted email (with GPG/PGP)
- Signal private messages
- Password-protected ZIP files (strong password via separate channel)
- Encrypted cloud storage (with separate password)

**Pros:**
- Simple, no infrastructure
- Works for small teams
- Flexible

**Cons:**
- Manual process
- No audit trail
- Keys can be lost

**Example (Password-protected ZIP):**
```bash
# Sender: Create encrypted archive
zip -e -P "$(openssl rand -base64 32)" keys.zip secrets/prod/age.key
# Send keys.zip via one channel, password via another (Signal/phone)

# Receiver: Extract
unzip keys.zip
install -m 600 age.key secrets/prod/age.key
rm keys.zip age.key
```

### Method 3: Separate Private Repo (Common for Teams)

Create a separate, highly-restricted git repository for keys only:

```
infrastructure-keys/    # Private repo, restricted access
├── dev/
│   └── age.key
├── staging/
│   └── age.key
└── prod/
    └── age.key

infrastructure-config/  # Main repo, team access
├── secrets/
│   ├── dev/
│   │   └── *.yaml      # Encrypted files only
│   └── prod/
│       └── *.yaml      # Encrypted files only
```

**Setup:**
```bash
# Clone both repos
git clone git@github.com:company/infrastructure-config.git
git clone git@github.com:company/infrastructure-keys.git  # Requires special access

# Symlink keys
ln -s ../infrastructure-keys/dev/age.key infrastructure-config/secrets/dev/age.key
```

**Pros:**
- Version controlled
- Access control via Git permissions
- Works with existing Git workflows

**Cons:**
- Keys still in Git (private, but still a risk)
- Need to manage two repos
- Access control limited to repo level

## CI/CD Integration

### GitHub Actions

Store base64-encoded keys as repository secrets:

```bash
# Generate secret value
cat secrets/dev/age.key | base64 -w0
# Copy output to GitHub Settings → Secrets → Actions → New repository secret
# Name: SOPS_AGE_KEY_DEV
```

**Workflow:**
```yaml
- name: Setup SOPS age key
  run: |
    mkdir -p secrets/dev
    echo "${{ secrets.SOPS_AGE_KEY_DEV }}" | base64 -d > secrets/dev/age.key
    chmod 600 secrets/dev/age.key
    
- name: Run InfraFoundry
  run: infra plan --env dev
```

### GitLab CI

```yaml
variables:
  SOPS_AGE_KEY_DEV: $SOPS_AGE_KEY_DEV  # Set in GitLab CI/CD Variables

before_script:
  - mkdir -p secrets/dev
  - echo "$SOPS_AGE_KEY_DEV" | base64 -d > secrets/dev/age.key
  - chmod 600 secrets/dev/age.key
```

## Key Generation

### Creating Keys

```bash
# Generate new age key
age-keygen -o secrets/new-env/age.key

# Secure permissions
chmod 600 secrets/new-env/age.key

# Extract public key for .sops.yaml
grep "public key:" secrets/new-env/age.key
# Example output: public key: age1ep57rqlyy6awft8sterut0kfqjn62pv6yutpwv0vp6xmpwvtdgpqwj8afs
```

### Updating .sops.yaml

Add the public key to `.sops.yaml`:

```yaml
creation_rules:
  - path_regex: dev/.*\.yaml$
    age: age1xxx...dev-public-key...xxx
  
  - path_regex: staging/.*\.yaml$
    age: age1xxx...staging-public-key...xxx
  
  - path_regex: prod/.*\.yaml$
    age: age1xxx...prod-public-key...xxx
```

### Encrypting Secrets

```bash
# Set the correct key for the environment
export SOPS_AGE_KEY_FILE="secrets/dev/age.key"

# Encrypt files
sops --encrypt --in-place secrets/dev/proxmox.yaml
sops --encrypt --in-place secrets/dev/opnsense.yaml

# Verify encryption worked (should see ENC[...])
head -n 3 secrets/dev/proxmox.yaml
```

## Key Rotation

Rotate keys periodically (quarterly recommended for production):

```bash
# 1. Generate new key
age-keygen -o secrets/prod/age-new.key

# 2. Update .sops.yaml with new public key

# 3. Re-encrypt all secrets
export SOPS_AGE_KEY_FILE="secrets/prod/age.key"  # Old key to decrypt
for file in secrets/prod/*.yaml; do
  # Decrypt with old key, encrypt with new key
  sops --decrypt "$file" | \
  SOPS_AGE_KEY_FILE="secrets/prod/age-new.key" sops --encrypt /dev/stdin > "${file}.new"
  mv "${file}.new" "$file"
done

# 4. Replace old key
mv secrets/prod/age.key secrets/prod/age-old.key.backup
mv secrets/prod/age-new.key secrets/prod/age.key

# 5. Test decryption works
sops --decrypt secrets/prod/proxmox.yaml

# 6. Distribute new key to team via secure channel

# 7. After confirmation, delete old key backup
rm secrets/prod/age-old.key.backup
```

## Backup and Recovery

### Backup Strategy

1. **Print to paper**: Print keys and store in physical safe
2. **Encrypted backup**: Store encrypted copy in different location
3. **Split key**: Use Shamir's Secret Sharing for critical keys

**Example (Encrypted backup):**
```bash
# Create encrypted backup
gpg --symmetric --cipher-algo AES256 secrets/prod/age.key
# Outputs: age.key.gpg

# Store age.key.gpg in separate secure location
# Restore when needed:
gpg --decrypt secrets/prod/age.key.gpg > secrets/prod/age.key
chmod 600 secrets/prod/age.key
```

### Recovery Plan

Document your key recovery plan:

1. **Where are keys stored?** (Key management system, encrypted backups, etc.)
2. **Who has access?** (Names, roles, contact info)
3. **How to restore?** (Step-by-step recovery procedures)
4. **What if keys are lost?** (Re-encryption plan, impact assessment)

## Checklist

### For Developers

- [ ] I understand private keys are NEVER committed to git
- [ ] My `.gitignore` includes `*.key` and `secrets/*/age.key`
- [ ] I have the age keys I need stored in `secrets/*/age.key`
- [ ] I can decrypt secrets: `sops --decrypt secrets/dev/proxmox.yaml`
- [ ] I don't have production keys (unless I'm ops)

### For Ops/Admins

- [ ] Per-environment keys are set up in `.sops.yaml`
- [ ] Keys are distributed via secure channel (not Slack/email)
- [ ] CI/CD has keys stored as base64-encoded secrets
- [ ] Backup plan is documented and tested
- [ ] Key rotation schedule is defined (quarterly recommended)
- [ ] Access control is documented (who has which keys)

### For CI/CD

- [ ] Age keys stored as repository secrets (base64-encoded)
- [ ] Keys decoded and set with correct permissions (600)
- [ ] Keys cleaned up after job completes
- [ ] No keys in logs or artifacts

## Troubleshooting

### "Failed to decrypt" error

```bash
# Check key file exists
ls -la secrets/dev/age.key

# Verify it's the right key (public key should match .sops.yaml)
grep "public key:" secrets/dev/age.key

# Try manual decryption
SOPS_AGE_KEY_FILE=secrets/dev/age.key sops --decrypt secrets/dev/proxmox.yaml
```

### "Permission denied" error

```bash
# Keys must have 600 permissions
chmod 600 secrets/*/age.key
```

### Key was lost

1. Check backup locations (encrypted backups, key vault, etc.)
2. If no backup: Need to re-encrypt all secrets with new key
3. Generate new key: `age-keygen -o secrets/prod/age.key`
4. Create new secrets files with new credentials (old secrets are lost)

## References

- [age encryption tool](https://github.com/FiloSottile/age)
- [SOPS documentation](https://github.com/mozilla/sops)
- [InfraFoundry per-environment credentials](./per-environment-credentials.md)
