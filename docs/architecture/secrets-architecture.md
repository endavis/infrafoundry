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

## Related Documentation

- [Age Key Management Best Practices](../guides/age-key-management.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Decryption fails. **Fix:** Point `SOPS_AGE_KEY_FILE` to the correct env key; verify `.sops.yaml` rules.
- **Symptom:** Wrong backend used. **Fix:** Inject the intended `SecretProvider` when initializing `SecretManager`.
- **Symptom:** Secrets committed to git. **Fix:** Ensure keys and encrypted files are git-ignored; rotate keys and re-encrypt.

---

Last updated: 2025-11-29 14:27 GMT
