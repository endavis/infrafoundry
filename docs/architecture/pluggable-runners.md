# Pluggable Runner System

## Overview

InfraFoundry runners execute generated configs (Terraform, Ansible, etc.). The runner system is pluggable so new tools can be added without modifying core orchestration.

## Audience and Prerequisites

- **Audience:** Contributors adding or extending runners.
- **Prereqs:** Python familiarity, understanding of provider outputs, and access to `core/runners`.

## When to Use This

- Integrating a new infrastructure tool.
- Customizing execution behavior for existing tools.
- Inspecting built-in Terraform/Ansible runner capabilities.

## Quick Start

1. Explore built-ins:
   ```bash
   ls src/infrafoundry/core/runners
   ```
2. Implement a custom runner extending `BaseRunner`.
3. Register it (auto-registration in `__init__.py` or manual `register_runner`).

## Architecture Details

- **Layout:**
  ```
  src/infrafoundry/core/runners/
    base_runner.py
    terraform_runner.py
    ansible_runner.py
    runner_registry.py
  ```
- **BaseRunner contract:** `tool_name`, `is_available`, `initialize`, `plan`, `apply`, `destroy` (and optional validate/drift helpers).
- **Built-ins:**
  - TerraformRunner: plan/apply/destroy/validate; auto-init; supports drift/state interactions.
  - AnsibleRunner: check-mode plan, apply, validate playbooks.
- **Registry:** `register_runner`, `get_runner`, `create_runner` manage discovery and instantiation.

## Validation and Checks

- Ensure `is_available` verifies tool presence.
- Return structured dicts for runner results (success flags, messages).
- Keep outputs deterministic for CI (avoid interactive prompts).

## Examples

- **Custom runner skeleton:**
  ```python
  class CustomRunner(BaseRunner):
      @property
      def tool_name(self) -> str:
          return "mycustomtool"

      def is_available(self) -> bool:
          import shutil
          return shutil.which("mycustomtool") is not None

      def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
          return {"success": True}
  ```
- **Register manually:**
  ```python
  from infrafoundry.core.runners import register_runner
  register_runner(CustomRunner)
  ```

## Related Documentation

- [Orchestrator Architecture](orchestrator-architecture.md)
- [Architecture Overview](overview.md)
- [Runners Overview](../runners/overview.md)

## Troubleshooting

- **Symptom:** Runner not found. **Fix:** Register via `register_runner` or import in `__init__.py`.
- **Symptom:** Availability check failing. **Fix:** Verify `is_available` logic and tool installation.
- **Symptom:** Execution output missing. **Fix:** Return structured dict with `success`, `message`, and any artifacts; ensure runner writes logs to console or files as needed.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
