# Age Key Management Best Practices

## Overview

Age keys secure SOPS-encrypted secrets in InfraFoundry. This guide outlines how to generate, distribute, and safeguard keys so environments stay isolated and compliant. InfraFoundry supports other secret backends (Vault, AWS Secrets Manager, etc.); see [Secrets Architecture](../architecture/secrets-architecture.md) for details.

## Audience and Prerequisites

- **Audience:** Infra operators and config repo maintainers responsible for secrets.
- **Prereqs:** `sops`, `age`, access to the config repo, and `.gitignore` entries for `*.key`.

## When to Use This

- Setting up or rotating SOPS/age keys for environments.
- Auditing key handling to ensure keys are not in version control.
- Deciding how to distribute keys to teams with different access levels.

## Quick Start

1. Create per-environment keys and git-ignore them:
   ```bash
   cd $INFRAFOUNDRY_CONFIG_REPO
   mkdir -p envs/dev envs/staging envs/prod
   age-keygen -o envs/dev/age.key
   age-keygen -o envs/staging/age.key
   age-keygen -o envs/prod/age.key
   printf \"*.key\nenvs/*/age.key\nenvs/**/age.key\n\" >> .gitignore
   ```
2. Configure SOPS rules in `.sops.yaml` to target the right key per environment.
3. Encrypt secrets with the matching key:
   ```bash
   sops --encrypt --age $(cat envs/dev/age.key | grep public | cut -d' ' -f3) envs/dev/proxmox.yaml > envs/dev/proxmox.yaml
   ```
4. Run InfraFoundry commands; the correct key is picked up by `--env`:
   ```bash
   infra plan --env dev
   infra apply --env prod
   ```

## Configuration Details

- **File locations:** `envs/{env}/age.key` (git-ignored). Keep `.sops.yaml` at repo root with per-environment rules.
- **Key selection:** InfraFoundry auto-selects the key based on `--env`; ensure keys exist for every environment you plan or apply.
- **Access control:** Limit prod key distribution; prefer password managers or KMS for storage.
- **Backups:** Store recovery copies in a secure vault with auditing.

## Validation and Checks

- Confirm keys are not tracked: `git status --ignored` should not list `age.key`.
- Dry-run encryption/decryption to ensure rules are correct:
  ```bash
  sops --decrypt envs/dev/proxmox.yaml >/dev/null
  ```
- Verify InfraFoundry picks the right key by running `infra plan --env <env>` and checking for missing key errors.

## Examples

- **Per-environment layout:**
  ```
  config-repo/
  ├── envs/
  │   ├── dev/
  │   │   ├── age.key
  │   │   ├── proxmox.yaml
  │   │   └── opnsense.yaml
  │   ├── staging/
  │   │   ├── age.key
  │   │   └── *.yaml
  │   └── prod/
  │       ├── age.key
  │       └── *.yaml
  └── .sops.yaml
  ```
- **Automatic key selection:** `infra plan --env dev` uses `envs/dev/age.key`; `infra apply --env prod` uses `envs/prod/age.key`.
- **Distribution options:** Vault, AWS Secrets Manager, Azure Key Vault, 1Password/Bitwarden (preferred for audit and rotation).

## Related Documentation

- [Secrets Architecture](../architecture/secrets-architecture.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Key committed to git. **Fix:** Add ignore patterns, rotate keys, re-encrypt, and purge history if needed.
- **Symptom:** `sops` cannot decrypt. **Cause:** Wrong key selected or `.sops.yaml` rule mismatch. **Fix:** Verify `--env` matches the key path and public key values in `.sops.yaml`.
- **Symptom:** InfraFoundry warns about missing keys. **Fix:** Ensure `envs/{env}/age.key` exists and permissions allow reading.

---

Last updated: 2025-11-29 14:12 GMT

**Cons:**
- Additional infrastructure
- Learning curve
- Cost

**Example (HashiCorp Vault):**
```bash
# Store key
vault kv put secret/infrafoundry/prod-age-key content=@envs/prod/age.key

# Retrieve key
vault kv get -field=content secret/infrafoundry/prod-age-key > envs/prod/age.key
chmod 600 envs/prod/age.key
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
zip -e -P "$(openssl rand -base64 32)" keys.zip envs/prod/age.key
# Send keys.zip via one channel, password via another (Signal/phone)

# Receiver: Extract
unzip keys.zip
install -m 600 age.key envs/prod/age.key
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
├── envs/
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
ln -s ../infrastructure-keys/dev/age.key infrastructure-config/envs/dev/age.key
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
cat envs/dev/age.key | base64 -w0
# Copy output to GitHub Settings → Secrets → Actions → New repository secret
# Name: SOPS_AGE_KEY_DEV
```

**Workflow:**
```yaml
- name: Setup SOPS age key
  run: |
    mkdir -p envs/dev
    echo "${{ secrets.SOPS_AGE_KEY_DEV }}" | base64 -d > envs/dev/age.key
    chmod 600 envs/dev/age.key

- name: Run InfraFoundry
  run: infra plan --env dev
```

### GitLab CI

```yaml
variables:
  SOPS_AGE_KEY_DEV: $SOPS_AGE_KEY_DEV  # Set in GitLab CI/CD Variables

before_script:
  - mkdir -p envs/dev
  - echo "$SOPS_AGE_KEY_DEV" | base64 -d > envs/dev/age.key
  - chmod 600 envs/dev/age.key
```

## Key Generation

### Creating Keys

```bash
# Generate new age key
age-keygen -o envs/new-env/age.key

# Secure permissions
chmod 600 envs/new-env/age.key

# Extract public key for .sops.yaml
grep "public key:" envs/new-env/age.key
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
export SOPS_AGE_KEY_FILE="envs/dev/age.key"

# Encrypt files
sops --encrypt --in-place envs/dev/proxmox.yaml
sops --encrypt --in-place envs/dev/opnsense.yaml

# Verify encryption worked (should see ENC[...])
head -n 3 envs/dev/proxmox.yaml
```

## Key Rotation

Rotate keys periodically (quarterly recommended for production):

```bash
# 1. Generate new key
age-keygen -o envs/prod/age-new.key

# 2. Update .sops.yaml with new public key

# 3. Re-encrypt all secrets
export SOPS_AGE_KEY_FILE="envs/prod/age.key"  # Old key to decrypt
for file in envs/prod/*.yaml; do
  # Decrypt with old key, encrypt with new key
  sops --decrypt "$file" | \
  SOPS_AGE_KEY_FILE="envs/prod/age-new.key" sops --encrypt /dev/stdin > "${file}.new"
  mv "${file}.new" "$file"
done

# 4. Replace old key
mv envs/prod/age.key envs/prod/age-old.key.backup
mv envs/prod/age-new.key envs/prod/age.key

# 5. Test decryption works
sops --decrypt envs/prod/proxmox.yaml

# 6. Distribute new key to team via secure channel

# 7. After confirmation, delete old key backup
rm envs/prod/age-old.key.backup
```

## Backup and Recovery

### Backup Strategy

1. **Print to paper**: Print keys and store in physical safe
2. **Encrypted backup**: Store encrypted copy in different location
3. **Split key**: Use Shamir's Secret Sharing for critical keys

**Example (Encrypted backup):**
```bash
# Create encrypted backup
gpg --symmetric --cipher-algo AES256 envs/prod/age.key
# Outputs: age.key.gpg

# Store age.key.gpg in separate secure location
# Restore when needed:
gpg --decrypt envs/prod/age.key.gpg > envs/prod/age.key
chmod 600 envs/prod/age.key
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
- [ ] My `.gitignore` includes `*.key` and `envs/*/age.key`
- [ ] I have the age keys I need stored in `envs/*/age.key`
- [ ] I can decrypt secrets: `sops --decrypt envs/dev/proxmox.yaml`
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
ls -la envs/dev/age.key

# Verify it's the right key (public key should match .sops.yaml)
grep "public key:" envs/dev/age.key

# Try manual decryption
SOPS_AGE_KEY_FILE=envs/dev/age.key sops --decrypt envs/dev/proxmox.yaml
```

### "Permission denied" error

```bash
# Keys must have 600 permissions
chmod 600 envs/*/age.key
```

### Key was lost

1. Check backup locations (encrypted backups, key vault, etc.)
2. If no backup: Need to re-encrypt all secrets with new key
3. Generate new key: `age-keygen -o envs/prod/age.key`
4. Create new secrets files with new credentials (old secrets are lost)

## References

- [age encryption tool](https://github.com/FiloSottile/age)
- [SOPS documentation](https://github.com/mozilla/sops)
- [InfraFoundry per-environment credentials](../configuration/per-environment-credentials.md)


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
