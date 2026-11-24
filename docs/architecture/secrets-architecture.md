---
title: "Secrets Management Architecture"
description: "The pluggable secrets system, with SecretManager as a facade over SOPS/age and other providers"
audience:
  - contributors
tags:
  - architecture
---

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
- `infra doctor -p <package>` or `-r <resource>` lists where each secret reference resolves from (package, env or another provider's outputs) without showing values; see [Secret Sources](../usage/validation.md#secret-sources).
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
foundry secrets rotate --env dev --generate-new-key

# Rotate with an existing new key file
foundry secrets rotate --env prod --new-key-file /path/to/new_age.key

# Rotate specific files only
foundry secrets rotate --env dev --generate-new-key --files proxmox.yaml --files opnsense.yaml

# Dry run to preview rotation
foundry secrets rotate --env dev --generate-new-key --dry-run

# Skip verification (not recommended)
foundry secrets rotate --env dev --generate-new-key --no-verify

# Don't keep backup after rotation (not recommended)
foundry secrets rotate --env dev --generate-new-key --no-backup
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

## Secrets Transport: No Secrets on Disk

InfraFoundry follows a **no-secrets-on-disk** approach for Terraform execution. Provider
credentials and sensitive settings are never written to `.tfvars` files. Instead:

1. **Provider credentials** from `settings.yaml` are mapped to `TF_VAR_*` environment
   variables via each provider's `_CREDENTIAL_ENV_MAPPING` dict
2. `TerraformRunner._prepare_environment()` calls `provider.get_terraform_env_vars()`
   to build the full set of `TF_VAR_*` variables
3. `build_terraform_env_vars()` in `provider_mixins.py` reads settings and returns the
   `TF_VAR_*` dict
4. These environment variables are passed to the Terraform process at runtime

The deprecated `generate_provider_tfvars()` and `SecretManager.export_for_terraform()` /
`_export_secrets()` methods have been removed from the orchestration workflow.

### Per-Package Secrets

Packages can include a `secrets.yaml` file alongside their `infrafoundry.yml` manifest.
This file is SOPS-encrypted and automatically decrypted during package loading:

- Variables from `secrets.yaml` merge into the manifest's `variables` dict
- Secret values override same-named variables from `infrafoundry.yml`
- Merged variables are exposed to scripts as `INFRAFOUNDRY_VAR_<KEY>` env vars
  and as a JSON dict in `INFRAFOUNDRY_PACKAGE_VARS`
- Scripts read configuration from env vars rather than re-parsing files

See [Infrastructure Packages: Per-Package Secrets](../configuration/infrastructure-packages.md#per-package-secrets)
for format and usage details. Secret-backed fields can also read these values without
rendering them into generated files, through `package.<key>` references; see
[Package Secret References](../configuration/infrastructure-packages.md#package-secret-references).

### SSH Host Keys

A Proxmox VM, or an OCI instance with `tailscale:`, that sets `ssh_host_key` gets a pre-generated ed25519 host key (see
[SSH Host Keys](../configuration/infrastructure-packages.md#ssh-host-keys)). The private key
travels through these places:

| Place | Protection |
|:------|:-----------|
| Package `secrets.yaml` | SOPS + age. Written by `foundry secrets host-keys` through `sops set --value-stdin`, so it is never on a command line or in a plaintext file. |
| `TF_VAR_*` at apply | A sensitive Terraform variable, set through the secrets bridge ([ADR-0031](../decisions/0031-secret-references-resolve-from-the-owning-packages-secretsyaml-through-a-package-prefix.md)). |
| Terraform state | Stored in `proxmox_virtual_environment_file.source_raw.data`, with the cloud-init user data. With the local backend that is under `generated/{env}/terraform/proxmox/`. Use an encrypted remote backend and restrict access to the state. |
| Proxmox snippet storage | The cloud-init user-data file on the node's snippet datastore, readable by those who can read that datastore. |
| OCI Terraform state | The Tailscale module's data source and `oci_core_instance.metadata.user_data` hold the cloud-init content, key included. Use an encrypted remote backend and restrict access to the state. |
| OCI instance metadata | `user_data` is readable by anyone with instance read rights on the OCI API, and from the node by any process that can reach the metadata service (including k3s pods). The Tailscale OAuth secret travels the same way. |
| The VM | `/etc/ssh` (mode 0600) and cloud-init's root-only copy of the user data. |

A VM with `ssh_host_key.format: dropbear` (the `openwrt-vm` blueprint, #1650) is the one exception to
"never script environment". Its key is converted to dropbear's format and installed over the serial
console, so it travels as the package variable `ssh_host_keys_dropbear` of that package only: in the
script environment, in the JSON on stdin to a jumphost, and in the expect script rendered on the
Proxmox host until an `always:` step removes it. It is never in Terraform state, generated files or
logs (the key lines are sent with the log file closed, and the Ansible tasks use `no_log`).

Otherwise it never reaches generated `.tf` files (they hold only a variable reference), tfvars, script
environment, inventories, logs or outputs, and the plan shows `(sensitive value)`. The public
keys are not secret and are passed to scripts as `ssh_known_hosts`.

## Related Documentation

- [Age Key Management Best Practices](../guides/age-key-management.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Per-Package Secrets](../configuration/infrastructure-packages.md#per-package-secrets)
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

Last updated: 2026-03-18


---
[Back to Table of Contents](../index.md)
