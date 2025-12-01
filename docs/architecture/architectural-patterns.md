# Architectural Patterns

## Overview

InfraFoundry standardizes managers, providers, and runners to keep logging, error handling, templating, and path management consistent across the codebase.

## Audience and Prerequisites

- **Audience:** Contributors implementing managers/providers/runners or refactoring core modules.
- **Prereqs:** Familiarity with Python, the InfraFoundry module layout, and provider templates.

## When to Use This

- Creating new managers or providers.
- Refactoring code to align with shared mixins and base classes.
- Ensuring backward-compatible imports across reorganized packages.

## Quick Start

- Inherit managers from `BaseManager` or `PathBasedManager` for logging, error handling, and path utilities.
- For providers, extend `ProviderBase` and mix in `TemplateRendererMixin` and `ResourceGrouperMixin` as needed.
- Keep public APIs re-exported via `__init__.py` to preserve import compatibility.

## Architecture Details

- **Module organization:** Core packages split into `core/config`, `core/state`, `core/dependencies`, `core/notifications`, `core/policy`, `core/validation_helpers`, `core/runners`, with re-exported public APIs for compatibility.
- **BaseManager:** Standard logging helpers, `_handle_error`, context manager support, and `cleanup()` contract.
- **PathBasedManager:** Adds path resolution, directory creation, path validation, and env-var helpers for filesystem-centric managers.
- **Provider mixins:**
  - `TemplateRendererMixin` — Jinja2 setup, filters (`to_terraform_name`, `to_snake_case`, `to_kebab_case`), template loading/writing.
  - `ResourceGrouperMixin` — Resource grouping helpers.
- **Runner pattern:** Pluggable runners in `core/runners` (Terraform, Ansible, PyInfra, etc.) extending `BaseRunner`.
- **Compatibility:** Package `__init__.py` files re-export public classes/functions to preserve legacy import paths.

## Validation and Checks

- Ensure new managers call `super().__init__()` to initialize logging and state.
- Verify providers render using mixins and write outputs under `generated/{env}/{terraform|ansible}/{provider}`.
- Keep imports stable by updating `__init__.py` re-exports when adding or moving modules.

## Examples

- **BaseManager usage:**
  ```python
  class MyManager(BaseManager):
      def __init__(self, path: Path):
          super().__init__()
          self.path = path

      def cleanup(self) -> None:
          self._log_info("Cleaned up")
  ```
- **Template rendering in a provider:**
  ```python
  class MyProvider(TemplateRendererMixin, ProviderBase):
      def render(self, data: dict[str, Any]) -> None:
          self.render_template("main.tf.j2", data, output_path)
  ```

## Related Documentation

- [Infrastructure Architecture](ARCHITECTURE.md)
- [Orchestrator Architecture](orchestrator-architecture.md)
- [Pluggable Runners](pluggable-runners.md)
- [Manager Patterns](../development/manager-patterns.md)

## Troubleshooting

- **Symptom:** Logging or error handling missing. **Fix:** Confirm classes inherit `BaseManager`/`PathBasedManager` and call `super().__init__()`.
- **Symptom:** Templates fail to render. **Fix:** Use `TemplateRendererMixin` and verify template paths/filters.
- **Symptom:** Imports break after refactor. **Fix:** Update `__init__.py` re-exports to maintain legacy import paths.

---

Last updated: 2025-11-29 14:27 GMT
