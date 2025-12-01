# Plugin Development Guide

## Overview

Provider plugins implement `ProviderBase`, render Terraform/Ansible via Jinja2, validate configs, and declare resource types/dependencies. Use the 3-layer pattern (Provider → Component Manager → Service) for complex flows.

## Audience and Prerequisites

- **Audience:** Contributors building or extending providers.
- **Prereqs:** Python familiarity, Jinja2 templates, and knowledge of the target platform’s APIs.

## When to Use This

- Adding a new provider.
- Extending provider resource types or templates.
- Applying the 3-layer architecture for complex API interactions.

## Quick Start

1. Create `src/infrafoundry/providers/<provider>/__init__.py` extending `ProviderBase`.
2. Add Terraform/Ansible templates under `templates/<provider>/`.
3. Implement validation, generation, and resource declarations.

## Architecture Details

- **ProviderBase responsibilities:** set `name`, configure template dirs/env, validate configs, generate Terraform/Ansible, expose `get_resource_types()` and `get_dependencies()`.
- **Templates:** Use Jinja2; leverage mixins (`TemplateRendererMixin`, `ResourceGrouperMixin`) to render and group resources; output to `generated/{env}/{terraform|ansible}/{provider}/`.
- **3-layer stack:** Provider (orchestration) → Component Manager (complex workflows) → Service (API layer).
- **Dependencies:** `get_dependencies()` returns ordering (e.g., servers depend on networks).
- **Backward compatibility:** Re-export public APIs in `__init__.py`; keep provider module imports stable.

## Validation and Checks

- Validate required fields per resource type; surface clear errors.
- Ensure templates produce deterministic output; keep secrets out of generated files.
- Run `infra validate --env <env> --check-api --check-refs` for new providers; add provider-specific validators as needed.

## Examples

- **Provider skeleton:**
  ```python
  class YourProvider(ProviderBase):
      def __init__(self, config_dir: Path, output_dir: Path) -> None:
          super().__init__("yourprovider", config_dir, output_dir)
          self.template_dir = Path(__file__).parent / "templates"

      def get_resource_types(self) -> list[str]:
          return ["servers", "networks"]

      def get_dependencies(self) -> dict[str, list[str]]:
          return {"servers": ["networks"], "networks": []}

      def validate_config(self, config: dict[str, Any]) -> bool:
          return all(key in config for key in ["name", "type"])

      def generate_terraform(self, resources: list[ResourceConfig]) -> None:
          self.ensure_directories()
          # render templates ...
  ```
- **Template snippet (provider.tf.j2):**
  ```hcl
  terraform {
    required_providers {
      yourprovider = {
        source  = "vendor/yourprovider"
        version = "~> 1.0"
      }
    }
  }
  provider "yourprovider" {
    api_url    = var.yourprovider_api_url
    api_key    = var.yourprovider_api_key
    api_secret = var.yourprovider_api_secret
  }
  ```

## Related Documentation

- [Manager Patterns](manager-patterns.md)
- [Architectural Patterns](../architecture/architectural-patterns.md)
- [Pluggable Runners](../architecture/pluggable-runners.md)
- [Implementing Secret Providers](implementing-secret-providers.md)
- [ISC to Kea Migration (example)](../guides/isc-to-kea-migration.md)

## Troubleshooting

- **Symptom:** Resources out of order. **Fix:** Update `get_dependencies()` and verify resource references.
- **Symptom:** Templates fail to render. **Fix:** Check template paths and Jinja2 variables; use mixins for consistent filters.
- **Symptom:** New provider not discovered. **Fix:** Ensure it is registered and exposed via `__init__.py`.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
