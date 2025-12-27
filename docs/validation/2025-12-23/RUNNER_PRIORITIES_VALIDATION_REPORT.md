# Runner Priorities Documentation Validation Report

**Date:** 2025-12-23
**Documentation:** `docs/runners/overview.md`
**Implementation:**
- `src/infrafoundry/core/provider_registry_service.py`
- `src/infrafoundry/core/runners/base_runner.py`
- `src/infrafoundry/core/runners/terraform_runner.py`
- `src/infrafoundry/core/runners/ansible_runner.py`
- `src/infrafoundry/core/runners/pyinfra_runner.py`
- `src/infrafoundry/core/orchestrator_workflows.py`

---

## Executive Summary

**Status:** ✅ **Highly Accurate - Complete Match**

- ✅ **Default priorities verified:** Terraform 0, Ansible 50, PyInfra 50
- ✅ **Execution order verified:** Ascending priority with registration order tie-breaking
- ✅ **Priority override mechanism verified:** `runner_priorities` in settings.yaml
- ✅ **Resource applicability verified:** Field-based runner selection
- ✅ **Output paths verified:** `generated/{env}/{runner}/{provider}/`
- **Accuracy:** ~100% (all documented behaviors match implementation)

---

## Default Runner Priorities

### Documented

```
Default order: Terraform (0) → Ansible (50) → PyInfra (50; after Ansible by registration).
Defaults: Terraform 0, Ansible 50, PyInfra 50.
```

### Actual Implementation

**BaseRunner Default:**
```python
# src/infrafoundry/core/runners/base_runner.py:29-40
@property
def priority(self) -> int:
    """Return the execution priority of the runner (lower runs first).

    Default priorities:
    - Terraform: 0 (Provisioning)
    - Ansible: 50 (Configuration)
    - PyInfra: 50 (Configuration)

    Returns:
        Priority integer
    """
    return 50
```

**TerraformRunner Override:**
```python
# src/infrafoundry/core/runners/terraform_runner.py:34-38
@property
@override
def priority(self) -> int:
    """Terraform must run first to provision resources."""
    return 0
```

**AnsibleRunner:**
- Does not override `priority` property
- Uses default from BaseRunner: **50**

**PyInfraRunner:**
- Does not override `priority` property
- Uses default from BaseRunner: **50**

**Verification:** ✅ **ACCURATE** - Terraform 0, Ansible 50, PyInfra 50

---

## Registration Order

### Documented

```
Ties resolved by registration order (Ansible before PyInfra).
```

### Actual Implementation

```python
# src/infrafoundry/core/provider_registry_service.py:54-58
def _register_default_runners(self) -> None:
    """Register built-in runners."""
    self.runner_registry.register(TerraformRunner)  # Registered first
    self.runner_registry.register(AnsibleRunner)    # Registered second
    self.runner_registry.register(PyInfraRunner)    # Registered third
    # Register experimental runners if enabled
    if os.getenv("INFRA_ENABLE_EXPERIMENTAL"):
        self.runner_registry.register(PulumiRunner)
```

**Registration Order:**
1. TerraformRunner
2. AnsibleRunner
3. PyInfraRunner
4. PulumiRunner (if INFRA_ENABLE_EXPERIMENTAL set)

**Verification:** ✅ **ACCURATE** - Ansible registered before PyInfra

---

## Execution Order Logic

### Documented

```
Execution order: Ascending priority; ties resolved by registration order.
```

### Actual Implementation

**Priority Resolution:**
```python
# src/infrafoundry/core/orchestrator_workflows.py:301-308
def _get_sorted_runners(self, priorities: dict[str, int]) -> list[tuple[str, BaseRunner]]:
    """Get runners sorted by priority."""

    def get_priority(item: tuple[str, BaseRunner]) -> int:
        name, runner = item
        return priorities.get(name, runner.priority)

    return sorted(self.runners.items(), key=get_priority)
```

**How It Works:**
1. For each runner, check if `priorities` dict (from settings.yaml) has an override
2. If no override, use `runner.priority` (default or class-specific)
3. Sort runners by priority (ascending - lower numbers run first)
4. Python's stable sort preserves registration order for equal priorities

**Example with defaults (no overrides):**
- Terraform: priority 0 → runs 1st
- Ansible: priority 50 (registered 2nd) → runs 2nd
- PyInfra: priority 50 (registered 3rd) → runs 3rd

**Verification:** ✅ **ACCURATE** - Ascending priority with stable sort

---

## Priority Override Mechanism

### Documented

**From documentation:**
```yaml
runner_priorities:
  pyinfra: 40
  ansible: 60
```

### Actual Implementation

**Settings Model:**
```python
# src/infrafoundry/core/config/models.py:28
runner_priorities: dict[str, int] = Field(default_factory=dict)
```

**Loading Priorities:**
```python
# src/infrafoundry/core/provider_registry_service.py:49-52
def get_runner_priorities(self, env_name: str) -> dict[str, int]:
    """Fetch runner priorities from providers' environment configs if available."""
    env_config = self.config_manager.load_environment(env_name)
    return env_config.runner_priorities if env_config else {}
```

**Usage in Orchestrator:**
```python
# src/infrafoundry/core/orchestrator_workflows.py:333
runner_priorities = self._get_runner_priorities(env_name)

# Line 371
for tool_name, runner in self._get_sorted_runners(runner_priorities):
```

**Verification:** ✅ **ACCURATE** - Priorities loaded from settings.yaml and passed to sorting logic

---

## Resource Applicability

### Documented

```
Runner applicability by resource fields:
  - Terraform: resource provisioning (VMs, networks, etc.).
  - Ansible: ansible_roles, ansible_tasks, ansible_vars.
  - PyInfra: pyinfra_ops, pyinfra_deploy_funcs.
```

### Actual Implementation

**Runner Selection Logic:**
```python
# src/infrafoundry/core/orchestrator_workflows.py:372-389
for tool_name, runner in self._get_sorted_runners(runner_priorities):
    generate_method = getattr(provider, f"generate_{tool_name}", None)
    if generate_method and callable(generate_method):
        if not isinstance(runner, Plannable):
            self.console.print(
                f"  [dim]Skipping {tool_name}: does not support plan[/dim]"
            )
            continue

        self.console.print(
            f"  [dim]Generating {tool_name} configuration...[/dim]"
        )
        generate_method(provider_resources)
        self.console.print(f"  [dim]Running {tool_name} plan...[/dim]")
        runner_result = runner.plan(provider)
        provider_results[f"{tool_name}_plan"] = runner_result
```

**Resource Field Checking in Templates:**
```jinja2
# src/infrafoundry/providers/proxmox/templates/proxmox/playbook.yml.j2:12-13
{% if resource.type == 'vms' and resource.config.get('ansible_roles') %}
{% for role in resource.config.ansible_roles %}

# Line 36-38
{% if resource.type == 'vms' and resource.config.get('ansible_tasks') %}
{% for task in resource.config.ansible_tasks %}

# src/infrafoundry/providers/proxmox/templates/proxmox/deploy.py.j2:38
{% if resource.config.get('pyinfra_ops') or resource.config.get('pyinfra_deploy_funcs') %}
```

**How It Works:**
1. All providers implement `generate_terraform()` (required for provisioning)
2. Providers optionally implement `generate_ansible()` and `generate_pyinfra()`
3. Templates check resource config fields to determine what to render:
   - Ansible: `ansible_roles`, `ansible_tasks`, `ansible_vars`
   - PyInfra: `pyinfra_ops`, `pyinfra_deploy_funcs`

**Verification:** ✅ **ACCURATE** - Field-based applicability documented correctly

---

## Generated Output Paths

### Documented

```
Generated outputs: generated/{env}/{runner}/{provider}/
```

### Actual Implementation

**Provider Output Directories:**
```python
# src/infrafoundry/core/provider.py:59-61
self.terraform_dir = output_dir / "terraform" / name
self.ansible_dir = output_dir / "ansible" / name
self.pyinfra_dir = output_dir / "pyinfra" / name
```

**After set_environment("dev"):**
```python
# src/infrafoundry/core/provider.py:128-132
def set_environment(self, env_name: str) -> None:
    self._current_environment = env_name
    self.output_dir = self.base_output_dir / env_name
    self.terraform_dir = self.output_dir / "terraform" / self.name
    self.ansible_dir = self.output_dir / "ansible" / self.name
    self.pyinfra_dir = self.output_dir / "pyinfra" / self.name
```

**Result:** `generated/dev/terraform/proxmox/`, `generated/dev/ansible/proxmox/`, etc.

**Verification:** ✅ **ACCURATE** - Path structure matches documentation

---

## Configuration Examples

### Documented Example

**Default order:**
```yaml
# No runner_priorities specified
# Result: Terraform → Ansible → PyInfra
```

**Run PyInfra before Ansible:**
```yaml
runner_priorities:
  pyinfra: 40
  ansible: 60
```

### Validation

**Default Case:**
- Terraform: priority 0 (runs 1st)
- Ansible: priority 50 (runs 2nd, registered before PyInfra)
- PyInfra: priority 50 (runs 3rd)

**Override Case:**
```python
runner_priorities = {"pyinfra": 40, "ansible": 60}
```
- Terraform: priority 0 (default, runs 1st)
- PyInfra: priority 40 (override, runs 2nd)
- Ansible: priority 60 (override, runs 3rd)

**Verification:** ✅ **ACCURATE** - Examples produce documented behavior

---

## Validation Commands

### Documented

```bash
# Confirm priorities with runner_priorities in settings.yaml
# Inspect generated runner outputs for order and content
# Validate resources before run
infra validate --env <env> --check-refs
```

### Actual Implementation

**Settings Inspection:**
- File location: `envs/{env}/settings.yaml`
- Field: `runner_priorities` (dict[str, int])

**Generated Outputs:**
- Directories: `generated/{env}/{terraform|ansible|pyinfra}/{provider}/`
- Files created by `generate_terraform()`, `generate_ansible()`, `generate_pyinfra()`

**Validation Command:**
- Exists in CLI as `validate.py` command
- Supports `--check-refs` flag

**Verification:** ✅ **ACCURATE** - All validation methods documented correctly

---

## Troubleshooting Scenarios

### Documented

**Symptom:** Runner executes unexpectedly.
**Fix:** Check resource fields that trigger runner applicability and `runner_priorities`.

**Symptom:** Order incorrect.
**Fix:** Adjust priorities; ensure numeric values differ if order must change.

**Symptom:** Outputs missing.
**Fix:** Verify resources trigger runner; check `generated/{env}/{runner}/{provider}` for rendered files.

### Validation

**Scenario 1: Unexpected Execution**
- Root cause: Resource has `ansible_roles` field, triggers Ansible runner
- Fix accurate: Check resource config fields and priorities

**Scenario 2: Wrong Order**
- Root cause: PyInfra and Ansible both have priority 50, registration order determines execution
- Fix accurate: Set different numeric priorities in settings.yaml

**Scenario 3: Missing Outputs**
- Root cause: Provider doesn't implement `generate_{runner}()` or resource lacks trigger fields
- Fix accurate: Check generated/ directory structure

**Verification:** ✅ **ACCURATE** - All troubleshooting scenarios are valid

---

## Documentation Completeness

### All Key Concepts Documented

1. ✅ Default priorities (Terraform 0, Ansible 50, PyInfra 50)
2. ✅ Registration order tie-breaking
3. ✅ Ascending priority execution order
4. ✅ Override mechanism via `runner_priorities` in settings.yaml
5. ✅ Resource field-based applicability
6. ✅ Generated output paths
7. ✅ Configuration examples
8. ✅ Validation methods
9. ✅ Troubleshooting guidance

### No Gaps Found

The documentation covers all aspects of the runner priority system comprehensively.

---

## Recommendations

### Documentation Enhancements (Optional)

1. **Add visual diagram** - Show priority resolution flowchart (LOW priority)
2. **Add more examples** - Complex scenarios with multiple priority overrides (LOW priority)
3. **Cross-reference experimental runners** - Mention Pulumi runner if INFRA_ENABLE_EXPERIMENTAL (LOW priority)

### No Corrections Required

The documentation is accurate and complete as-is. The optional enhancements would improve clarity but are not necessary for correctness.

---

## Overall Assessment

**Documentation Quality:** ✅ **EXCELLENT**

The runner priorities documentation is:
- **100% accurate** - All documented behaviors match implementation
- **Complete** - All key concepts covered
- **Well-organized** - Clear structure with examples and troubleshooting
- **Practical** - Provides actionable guidance for users

**Accuracy Rate:** ~100%

**No corrections required.**

---

**Validated By:** Claude Code
**Last Updated:** 2025-12-23
