# Secrets Handling Security

## Overview

InfraFoundry decrypts SOPS-encrypted secrets and delivers them to Terraform and Ansible
runners. This document describes the security controls applied to plaintext secret files
during that process.

## Where Plaintext Secrets Appear

| Location | Purpose | Lifetime |
|---|---|---|
| `generated/{env}/terraform/{provider}/terraform.tfvars` | Provider credentials for Terraform | Duration of apply |
| `generated/{env}/ansible/{provider}/vars/*.yml` | Ansible variable files | Duration of playbook run |
| SOPS `.tmp` files | Intermediate plaintext before encryption | Momentary (during `save_secret`) |
| `TF_VAR_*` environment variables | Preferred credential delivery | Process lifetime only |

## File Permissions Policy

All plaintext secret files are written with **0o600** (owner read/write only) permissions
using the `secure_write` and `secure_write_yaml` utilities in
`infrafoundry.core.security.file_utils`.

These functions use `os.open()` with explicit mode bits to atomically create files with
the correct permissions, avoiding the TOCTOU race condition that occurs when calling
`open()` followed by `chmod()`.

```python
from infrafoundry.core.security.file_utils import secure_write, secure_write_yaml

# Write plaintext content with 0o600 permissions
secure_write(path, content)

# Write YAML data with 0o600 permissions
secure_write_yaml(path, data)
```

## Secret Delivery Architecture

### Preferred: Environment Variables

The preferred method for delivering secrets to Terraform is via `TF_VAR_*` environment
variables through the `build_terraform_env_vars()` method on provider mixins. This
approach:

- Never writes secrets to disk
- Limits secret exposure to the subprocess lifetime
- Cannot be accidentally committed to version control

### Legacy: File-Based Export

The `export_for_terraform()` and `export_for_ansible()` methods write plaintext files.
These are hardened with:

1. **Restrictive permissions** (0o600) via `secure_write`
2. **Cleanup support** via the `temporary_export()` context manager

```python
# Automatic cleanup after use
with secret_manager.temporary_export("secrets.yaml", output_path, fmt="terraform") as path:
    # Use the exported file
    runner.apply(tfvars=path)
# File is automatically deleted here, even if an exception occurred
```

## Cleanup Behavior

The `temporary_export()` context manager ensures exported secret files are deleted after
use, even when exceptions occur. For manual cleanup, use `cleanup_secret_files()`:

```python
SecretManager.cleanup_secret_files(path1, path2)
```

## Production Recommendations

1. **Use environment variables** (`build_terraform_env_vars()`) instead of tfvars files
   whenever possible.
2. **Use remote state backends** (S3, GCS, Azure Blob) with encryption at rest to avoid
   plaintext state files on disk.
3. **Restrict access** to the `generated/` directory tree, which is gitignored but may
   contain plaintext secrets during apply operations.
4. **Rotate secrets regularly** using `SecretManager.rotate_secrets()`.
5. **Audit file permissions** periodically -- all secret files should be 0o600.
