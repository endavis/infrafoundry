# Implementing Custom Secret Providers

## Overview

Create a `SecretProvider` to integrate InfraFoundry with alternate secret backends (Vault, AWS Secrets Manager, etc.) beyond the default SOPS/age provider.

## Audience and Prerequisites

- **Audience:** Contributors extending secret backends.
- **Prereqs:** Python familiarity, backend SDK/credentials, and knowledge of `SecretProvider` interface (`core/secrets/provider.py`).

## When to Use This

- Integrating a non-SOPS backend for secrets.
- Aligning secret storage with existing org standards.
- Adding env-scoped secret handling consistent with InfraFoundry.

## Quick Start

1. Create `src/infrafoundry/core/secrets/providers/<name>.py`.
2. Implement `SecretProvider` with `load_secret` and `save_secret`.
3. Inject your provider into `SecretManager`.

## Implementation Details

- **Interface:**
  ```python
  class SecretProvider(ABC):
      @abstractmethod
      def load_secret(self, location: str | Path) -> dict[str, Any]: ...
      @abstractmethod
      def save_secret(self, location: str | Path, data: dict[str, Any]) -> None: ...
  ```
- **Exceptions:** Raise `SecretNotFoundError` when missing; `SecretError` for other failures.
- **Location mapping:** Convert InfraFoundry location to backend path/name (e.g., Vault `secret/data/{env}/{name}`, AWS `infrafoundry/{env}/{name}`).
- **Injection:**
  ```python
  from infrafoundry.core.secrets import SecretManager
  manager = SecretManager(env_name="dev", provider=MyVaultProvider(...))
  ```

## Validation and Checks

- Add availability/auth checks in provider init; surface clear errors.
- Return `dict[str, Any]` from `load_secret`; ensure deterministic shapes.
- Avoid leaking secrets to logs; include contextual error messages without secret values.

## Examples

- **Provider skeleton:**
  ```python
  class MyVaultProvider(SecretProvider):
      def __init__(self, api_url: str, api_key: str):
          self.api_url = api_url
          self.api_key = api_key

      def load_secret(self, location: str | Path) -> dict[str, Any]:
          path = self._build_path(location)
          try:
              data = self.client.get(path)
              return data
          except NotFoundError:
              raise SecretNotFoundError(f"Secret not found: {path}")
          except Exception as exc:
              raise SecretError(f"Failed to load secret: {path}") from exc

      def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
          path = self._build_path(location)
          try:
              self.client.put(path, data)
          except Exception as exc:
              raise SecretError(f"Failed to save secret: {path}") from exc
  ```
- **Path builder concept:**
  ```python
  def _build_path(self, location: str | Path) -> str:
      return f"secret/data/{self.env}/{location}"
  ```

## Related Documentation

- [Secrets Management Architecture](../architecture/secrets-architecture.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Age Key Management Best Practices](../guides/age-key-management.md)
- [Implementing Providers](implementing-providers.md)

## Troubleshooting

- **Symptom:** Secret not found. **Fix:** Map backend not-found to `SecretNotFoundError`; verify location/path mapping.
- **Symptom:** Auth failures. **Fix:** Validate credentials/roles at init; expose actionable error messages.
- **Symptom:** Wrong data shape. **Fix:** Normalize backend response to a dict and document expected keys.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
