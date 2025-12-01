# Credential Loader System

## Overview

The Credential Loader decrypts provider credentials and exports them as environment variables, using provider-specific loaders to map secret keys into the expected env vars.

## Audience and Prerequisites

- **Audience:** Contributors extending credential loading or adding new providers.
- **Prereqs:** SOPS/age secrets in the config repo, knowledge of provider credential formats, and Python familiarity.

## When to Use This

- Loading credentials for CLI/runners without manual exports.
- Adding new provider credential mappings.
- Temporarily applying credentials within a context manager.

## Quick Start

```python
from pathlib import Path
from infrafoundry.core.credential_loader import CredentialLoader

loader = CredentialLoader(config_dir=Path("/path/to/config"))
creds = loader.load("prod")              # dict of env vars
loader.apply_to_environment(creds)       # sets env vars
with loader.temporary_credentials("prod"):
    run_deployment()
```

## Architecture Details

- **CredentialLoader:** Factory/coordinator that discovers provider loaders, decrypts secrets (via SecretProvider), and applies env vars.
- **BaseCredentialLoader:** Defines interface for provider-specific loaders (file name, field mapping).
- **Provider loaders:** Map secret keys → environment variables (e.g., Proxmox, OPNsense, Kubernetes); extensible for new providers.
- **Storage:** Encrypted YAML per environment (e.g., `envs/{env}/proxmox.yaml`, `envs/{env}/opnsense.yaml`) with age keys per env.

## Validation and Checks

- Confirm secrets are encrypted (SOPS/age) and keys are git-ignored.
- Use `loader.load(env, providers=[...])` to target specific providers and verify mappings.
- Ensure mappings match provider env var expectations (e.g., `PROXMOX_API_URL`, `PROXMOX_API_TOKEN_ID`).

## Examples

- **Load specific providers:**
  ```python
  creds = loader.load("dev", providers=["proxmox", "opnsense"])
  loader.apply_to_environment(creds)
  ```
- **Context manager for temporary credentials:**
  ```python
  with loader.temporary_credentials("staging"):
      run_deployment()
  # env restored after context
  ```
- **Custom loader skeleton:**
  ```python
  class MyProviderCredentialLoader(BaseCredentialLoader):
      filename = "myprovider.yaml"
      field_mapping = {
          "myprovider_api_url": "MYPROVIDER_API_URL",
          "myprovider_api_key": "MYPROVIDER_API_KEY",
      }
  ```

## Related Documentation

- [Implementing Custom Secret Providers](implementing-secret-providers.md)
- [Per-Environment Credentials](../per-environment-credentials.md)
- [Secrets Management Architecture](../architecture/secrets-architecture.md)
- [Age Key Management Best Practices](../age-key-management.md)

## Troubleshooting

- **Symptom:** Env vars missing. **Fix:** Verify credential file names and field mappings; ensure SOPS decryption works.
- **Symptom:** Wrong credentials loaded. **Fix:** Check `--env` or config path; ensure provider list passed to `load` if targeting specific providers.
- **Symptom:** Decryption fails. **Fix:** Set `SOPS_AGE_KEY_FILE` for the environment; confirm `.sops.yaml` rules.

---

Last updated: 2025-11-29 14:27 GMT
