# Secrets Management Architecture

## Overview

InfraFoundry uses a pluggable secrets system with `SecretManager` as a facade and provider implementations (SOPS/age by default; Vault/AWS/custom as extensions). Each environment is isolated and providers expose a simple load/save contract.

## Audience and Prerequisites

- **Audience:** Operators and contributors extending or integrating secret backends.
- **Prereqs:** SOPS/age familiarity (default), provider credentials for alternate backends, and access to config repos.

## When to Use This

- Storing and retrieving per-environment secrets for Terraform/Ansible.
- Swapping the default SOPS provider for Vault/AWS Secrets Manager/custom backends.
- Auditing how secrets flow into generated configs.

## Quick Start

```python
from infrafoundry.core.secrets import SecretManager

manager = SecretManager(env_name="dev")  # uses SOPS provider by default
data = manager.load_secret("envs/dev/settings.yaml")
manager.save_secret("envs/dev/settings.yaml", data)
```

## Architecture Details

- **SecretManager:** Facade that injects a `SecretProvider`, manages per-environment locations, and exposes load/save.
- **SecretProvider interface:** `load_secret(location) -> dict`, `save_secret(location, data) -> None`.
- **Default provider:** `SopsSecretProvider` (file-based, age-encrypted, per-env keys).
- **Extensibility:** Implement `SecretProvider` for Vault, AWS Secrets Manager, Azure Key Vault, etc.; inject into `SecretManager`.
- **Design principles:** Dependency injection, interface segregation, environment isolation, backend agnostic to callers.

## Validation and Checks

- Verify `.sops.yaml` rules and age keys per environment; confirm keys are git-ignored.
- Test decryption:
  ```bash
  sops --decrypt envs/dev/settings.yaml >/dev/null
  ```
- For custom providers, add availability/credential checks and meaningful errors (`SecretError`/`SecretNotFoundError`).

## Examples

- **Load with default SOPS provider:**
  ```python
  manager = SecretManager(env_name="prod")
  secrets = manager.load_secret("envs/prod/settings.yaml")
  ```
- **Custom provider injection:**
  ```python
  from infrafoundry.core.secrets.providers.vault import VaultSecretProvider
  manager = SecretManager(env_name="prod", provider=VaultSecretProvider())
  manager.save_secret("secret/data/prod/app", {"token": "value"})
  ```
- **Rotate encryption keys:**
  ```python
  manager = SecretManager(env_name="prod")
  # Generate new key and rotate all secrets
  result = manager.rotate_secrets(generate_new_key=True)

  # Or use existing new key
  result = manager.rotate_secrets(new_key_file=Path("new_age.key"))
  ```

## Secrets Rotation

InfraFoundry supports safe rotation of age encryption keys for compliance and security best practices.

### Rotation Process

The rotation workflow:
1. **Backup**: Creates timestamped backup of all encrypted files
2. **Generate/Use Key**: Generates new age key or uses provided key
3. **Decrypt**: Decrypts all secrets with old key
4. **Update Config**: Updates .sops.yaml with new public key
5. **Re-encrypt**: Re-encrypts all secrets with new key
6. **Verify**: Verifies decryption works with new key (optional)
7. **Cleanup**: Keeps backup by default, removes on request

On failure, automatically rolls back to the backup.

### CLI Usage

```bash
# Generate new key and rotate all secrets for dev environment
infra secrets rotate --env dev --generate-new-key

# Rotate with an existing new key file
infra secrets rotate --env prod --new-key-file /path/to/new_age.key

# Rotate specific files only
infra secrets rotate --env dev --generate-new-key --files proxmox.yaml --files opnsense.yaml

# Dry run to preview rotation
infra secrets rotate --env dev --generate-new-key --dry-run

# Skip verification (not recommended)
infra secrets rotate --env dev --generate-new-key --no-verify

# Don't keep backup after rotation (not recommended)
infra secrets rotate --env dev --generate-new-key --no-backup
```

### Post-Rotation Steps

After successful rotation:
1. Update `SOPS_AGE_KEY_FILE` environment variable to point to new key
2. Test decryption with new key
3. Securely delete or archive the old key
4. Distribute new key to team members (if applicable)
5. Update CI/CD pipelines with new key

### Safety Features

- **Automatic backup**: All encrypted files are backed up before rotation
- **Transaction-like semantics**: All-or-nothing operation
- **Verification**: Optional verification that re-encrypted secrets match originals
- **Rollback**: Automatic rollback to backup on any failure
- **Dry-run mode**: Preview rotation without making changes

## Related Documentation

- [Age Key Management Best Practices](../guides/age-key-management.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Decryption fails. **Fix:** Point `SOPS_AGE_KEY_FILE` to the correct env key; verify `.sops.yaml` rules.
- **Symptom:** Wrong backend used. **Fix:** Inject the intended `SecretProvider` when initializing `SecretManager`.
- **Symptom:** Secrets committed to git. **Fix:** Ensure keys and encrypted files are git-ignored; rotate keys and re-encrypt.
- **Symptom:** Rotation fails during re-encryption. **Fix:** Check that `SOPS_AGE_KEY_FILE` points to the old key before rotation; verify new key is valid; check backup was created.
- **Symptom:** Can't decrypt after rotation. **Fix:** Ensure `SOPS_AGE_KEY_FILE` points to the new key; verify rotation completed successfully; restore from backup if needed.
- **Symptom:** Rotation rolled back unexpectedly. **Fix:** Check rotation error messages; verify age-keygen is installed; ensure sufficient disk space for backups.

---

Last updated: 2025-12-27 19:30 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
