# Manager Pattern Documentation

## Overview

Managers inherit from `BaseManager` or `PathBasedManager` for consistent logging, error handling, initialization, and path utilities. Component Managers and Services follow the 3-layer architecture for complex workflows.

## Audience and Prerequisites

- **Audience:** Contributors implementing managers or component/service layers.
- **Prereqs:** Python familiarity and knowledge of InfraFoundry’s manager base classes and 3-layer pattern.

## When to Use This

- Creating managers that handle config, state, secrets, or notifications.
- Building component managers/services for provider-specific workflows.
- Ensuring consistent initialization/logging/error patterns.

## Quick Start

- Use `BaseManager` for non-path managers (state, events).
- Use `PathBasedManager` for path-centric managers (config, secrets, notifications).
- Call `super().__init__()` first in constructors; follow the standard init order.

## Architecture Details

- **Hierarchy:**
  ```
  BaseManager (ABC)
  ├── StateManager
  ├── EventManager
  └── PathBasedManager
      ├── ConfigManager
      ├── SecretManager
      └── NotificationManager

  Component Managers (3-layer)
  ├── BaseComponentManager
  │   ├── KeaDHCPManager
  │   └── ISCToKeaMigrationManager
  └── Services (API layer)
      ├── BaseService
      ├── KeaDHCPService
      └── ISCDHCPService
  ```
- **Initialization pattern:**
  ```python
  class MyManager(BaseManager):
      def __init__(self, param: Type):
          super().__init__()          # 1) init logging/state
          self.param = param          # 2) set attributes
          self._validate_config()     # 3) init/validation
          self._log_debug("Initialized", param=param)  # 4) log
  ```
- **Logging helpers:** `_log_debug/_info/_warning/_error` with structured kwargs.
- **Path helpers (PathBasedManager):** `_resolve_path`, `_ensure_directory_exists`, `_validate_path_exists`, `_get_env_var`.
- **Error handling:** Validate inputs, log with context, and raise specific exceptions; use `_handle_error` for consistent handling.

## Validation and Checks

- Ensure `super().__init__()` is first to initialize logging.
- Use path helpers when working with filesystem resources.
- Keep logging structured and contextual; avoid print.

## Examples

- **Loading config with validation:**
  ```python
  def load_config(self, path: Path) -> dict:
      if not path.exists():
          self._handle_error(f"Config file not found: {path}", FileNotFoundError(path))
      return yaml.safe_load(path.read_text())
  ```
- **Component manager for API workflow:**
  ```python
  class MyComponentManager(BaseComponentManager):
      def perform(self, data: dict[str, Any]) -> None:
          # orchestrate API calls with retries/logging
          ...
  ```

## Related Documentation

- [Architectural Patterns](../architecture/architectural-patterns.md)
- [Coding Standards](coding-standards.md)
- [Implementing Providers](implementing-providers.md)
- [Implementing Secret Providers](implementing-secret-providers.md)

## Troubleshooting

- **Symptom:** Logging missing. **Fix:** Ensure managers inherit correct base and call `super().__init__()`.
- **Symptom:** Path resolution errors. **Fix:** Use `_resolve_path` and `_validate_path_exists` from `PathBasedManager`.
- **Symptom:** Inconsistent error handling. **Fix:** Use `_handle_error` with specific exceptions; avoid silent failures.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
