# PR: External Vault Integration

## Objective
Implement "External Vault Integration" (Feature #7) by creating a pluggable `SecretProvider` interface to abstract away the current SOPS-based secret management.

## Changes
- **New Interface:** Created `src/infrafoundry/core/secrets/provider.py` defining the `SecretProvider` abstract base class.
- **New Provider:** Implemented `src/infrafoundry/core/secrets/providers/sops.py` as the default SOPS implementation.
- **Refactor `SecretManager`:** Updated `src/infrafoundry/core/secrets/secret_manager.py` to use the `SecretProvider` interface.
- **Refactor `CredentialLoader`:** Updated `src/infrafoundry/core/credential_loader/` classes to use `SecretProvider` for decryption.
- **Cleanup:** Removed `src/infrafoundry/core/secrets/sops_wrapper.py`.
- **Tests:** Updated `tests/unit/test_secrets.py` and `tests/unit/test_credential_loader.py` to use mock providers.

## Verification
- Ran `uv run pytest tests/unit/test_secrets.py tests/unit/test_credential_loader.py` - **PASSED**
- Ran `uv run ruff check ...` - **PASSED**
- Ran `uv run mypy ...` - **PASSED**

## Impact
- Decouples the application from Mozilla SOPS.
- Enables future support for HashiCorp Vault, AWS Secrets Manager, etc.
- No breaking changes for existing CLI usage (SOPS remains the default).
