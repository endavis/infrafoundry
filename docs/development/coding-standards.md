# InfraFoundry Coding Standards

## Overview

Guidelines for exceptions, typing, structure, testing, and docs to keep InfraFoundry code consistent and safe.

## Audience and Prerequisites

- **Audience:** Contributors writing or reviewing InfraFoundry code.
- **Prereqs:** Python 3.12+, familiarity with the repo layout, and access to local tooling (`uv`, `doit`, ruff, pytest).

## When to Use This

- Implementing new features or refactors.
- Reviewing PRs for compliance and safety.
- Adding tests or updating typing/structure.

## Quick Start

- Use typed functions with explicit return types.
- Prefer specific exceptions; use `InfraFoundryError` hierarchy.
- Run `doit format && doit lint && uv run pytest` before submitting.

## Coding Standards

- **Exception handling:** Use specific exceptions first; fallback to `InfraFoundryError`; final `Exception` only as last resort. `InfraFoundryError` supports `context` for debugging. CLI: use `raise_cli_error` for user-facing errors.
- **Typing:** Full annotations on params/returns; avoid `Any` unless necessary; prefer modern hints (`list[str]`, `dict[str, str]`, `X | None`); use `@override` on implementations.
- **Structure:** Follow package organization (`core/config`, `core/state`, `core/dependencies`, `core/notifications`, `core/policy`, `core/validation_helpers`, `core/runners`); re-export public APIs via `__init__.py` for compatibility.
- **Managers/providers:** Inherit `BaseManager`/`PathBasedManager`; use mixins (TemplateRendererMixin/ResourceGrouperMixin) to avoid duplication; call `super().__init__()`.
- **Error patterns:** Defensive catches in events/notifications/orchestration to avoid crashes; record failures in state and re-raise when appropriate.
- **Logging:** Use structured/log-level appropriate logging; avoid print in core logic.

## Testing

- Minimum coverage target: ≥69%.
- Commands: `uv run pytest` or `doit test`; coverage: `doit coverage`.
- Add/adjust tests when changing behavior; use fixtures/mocks for isolation.

## Documentation

- Use Google-style docstrings; keep max line length 100; prefer concise inline comments only when needed.
- Update relevant docs when public behavior changes; maintain consistency with repo docs.

## Validation and Checks

- Run formatting/linting: `doit format`, `doit lint`.
- Run tests/coverage: `uv run pytest` or `doit coverage`.
- Ensure imports remain backward compatible when moving modules (update `__init__.py`).

## Examples

- **Exception pattern:**
  ```python
  try:
      do_work()
  except click.ClickException:
      raise
  except SpecificError as exc:
      handle(exc)
  except InfraFoundryError as exc:
      handle_generic(exc)
  except Exception as exc:
      handle_unexpected(exc)
  ```
- **Typed function:**
  ```python
  def load_environment(self, env_name: str) -> EnvironmentConfig:
      ...
  ```

## Related Documentation

- [Manager Patterns](manager-patterns.md)
- [Implementing Providers](implementing-providers.md)
- [CI/CD Testing](ci-cd-testing.md)
- [Implementing Secret Providers](implementing-secret-providers.md)

## Troubleshooting

- **Symptom:** Lint/format failures. **Fix:** Run `doit format && doit lint` and address violations.
- **Symptom:** Coverage drop. **Fix:** Add/adjust tests for new code paths.
- **Symptom:** Import breakage after refactor. **Fix:** Update `__init__.py` re-exports and verify dependent imports.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
