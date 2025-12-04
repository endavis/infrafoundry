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
  src/infrafoundry/core/
    runners/
      base_runner.py
      terraform_runner.py
      ansible_runner.py
      pyinfra_runner.py
      pulumi_runner.py (experimental)
      runner_registry.py
    protocols.py      # Runner capability protocols
    result_types.py   # TypedDict result types
  ```

- **Protocol-Based Architecture (ISP Compliance):**

  Runners implement only the protocols they support, following the Interface Segregation Principle:

  ```python
  @runtime_checkable
  class Plannable(Protocol):
      """Runners that can generate execution plans."""
      def plan(self, provider: ProviderBase, **kwargs) -> PlanResult: ...

  @runtime_checkable
  class Applyable(Protocol):
      """Runners that can apply infrastructure changes."""
      def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs) -> ApplyResult: ...

  @runtime_checkable
  class Destroyable(Protocol):
      """Runners that can destroy infrastructure."""
      def destroy(self, provider: ProviderBase, auto_approve: bool = True, **kwargs) -> DestroyResult: ...

  @runtime_checkable
  class DriftDetectable(Protocol):
      """Runners that can detect configuration drift."""
      def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo: ...

  @runtime_checkable
  class StateAware(Protocol):
      """Runners that track infrastructure state."""
      def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]: ...
  ```

- **BaseRunner contract:** `tool_name`, `is_available`, `initialize` (required for all runners). Additional capabilities implemented via protocols.

- **Built-ins:**
  - **TerraformRunner**: Implements all 5 protocols (Plannable, Applyable, Destroyable, StateAware, DriftDetectable)
  - **AnsibleRunner**: Implements 2 protocols (Plannable, Applyable) - no destroy, state, or drift support
  - **PyInfraRunner**: Implements 2 protocols (Plannable, Applyable)
  - **PulumiRunner**: Implements all 5 protocols (experimental, requires `INFRA_ENABLE_EXPERIMENTAL=1`)

- **Type-Safe Results:**

  All protocol methods return TypedDict types for IDE autocomplete and mypy validation:
  - `PlanResult` - Plan operation results
  - `ApplyResult` - Apply operation results with resource counts
  - `DestroyResult` - Destroy operation results
  - `DriftInfo` - Drift detection information

- **Registry:** `register_runner`, `get_runner`, `create_runner` manage discovery and instantiation.

## Validation and Checks

- Ensure `is_available` verifies tool presence.
- Return structured dicts for runner results (success flags, messages).
- Keep outputs deterministic for CI (avoid interactive prompts).

## Examples

- **Custom runner implementing only needed protocols:**
  ```python
  from infrafoundry.core.runners.base_runner import BaseRunner
  from infrafoundry.core.result_types import PlanResult, ApplyResult
  from infrafoundry.core.provider import ProviderBase
  import shutil

  class CustomRunner(BaseRunner):
      """Custom runner implementing only Plannable and Applyable protocols."""

      @property
      def tool_name(self) -> str:
          return "mycustomtool"

      def is_available(self) -> bool:
          return shutil.which("mycustomtool") is not None

      def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
          """Initialize the tool in working directory."""
          return {"success": True}

      # Implement Plannable protocol
      def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
          """Generate execution plan."""
          # Your plan logic here
          return {
              "success": True,
              "has_changes": False,
              "changes_summary": "No changes detected"
          }

      # Implement Applyable protocol
      def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
          """Apply infrastructure changes."""
          # Your apply logic here
          return {
              "success": True,
              "resources_created": 0,
              "resources_updated": 0,
              "resources_deleted": 0
          }

      # Note: This runner does NOT implement Destroyable, StateAware, or DriftDetectable
      # Code using this runner should check capabilities:
      #   if isinstance(runner, Plannable):
      #       runner.plan(provider)
  ```

- **Register manually:**
  ```python
  from infrafoundry.core.runners import register_runner
  register_runner(CustomRunner)
  ```

- **Usage with capability checking:**
  ```python
  from infrafoundry.core.protocols import Plannable, Destroyable

  runner = runner_registry.create_runner("mycustomtool")

  # Always check capabilities before use
  if isinstance(runner, Plannable):
      result = runner.plan(provider)
      print(f"Plan success: {result['success']}")

  if isinstance(runner, Destroyable):
      # This won't execute for CustomRunner
      runner.destroy(provider, auto_approve=True)
  else:
      print("Runner does not support destroy operation")
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

Last updated: 2025-12-04 (Protocol-based refactoring - Issue #48 / PR #77)


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
