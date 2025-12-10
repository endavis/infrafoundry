# Pure Protocol-Based Approach: Proposed Answers & Impact Analysis

**Date:** 2025-12-04
**Related:** Issue #48, PR #77
**Status:** Proposal for Discussion

---

## 🔥 **CRITICAL CONTEXT: Pre-Release, Private Repository**

**KEY FACT:** This repository has **no public releases** and is currently **private**.

**What This Means:**
- ✅ **Breaking changes are acceptable** - no external users to impact
- ✅ **No deprecation period needed** - can remove APIs immediately
- ✅ **Aggressive refactoring enabled** - don't need gradual migration
- ✅ **No semantic versioning constraints** - v1.0.0 not shipped yet
- ✅ **Faster migration** - can do larger, more invasive PRs

**Impact on Recommendations:**
This document originally assumed public API stability. **All recommendations have been revised** to take advantage of pre-release flexibility. Where both "safe/gradual" and "aggressive/fast" options exist, we now recommend the **aggressive approach**.

---

## Executive Summary

This document proposes specific answers to 13 key design questions for implementing a pure protocol-based approach for runner interfaces. Each answer includes impact analysis covering:
- Migration complexity
- Breaking changes (acceptable in pre-release)
- Type safety improvements
- Developer experience
- Maintenance burden

**Overall Recommendation:** **Aggressive migration** - Remove `run()` immediately, update all call sites in 1-2 PRs, ship clean protocol-based API from the start.

---

## 1. State Management & History

### Q1.1: How to handle the `command` field in Deployment model?

**PROPOSED:** **Option A** - Keep command strings for historical records

```python
# In models.py - NO CHANGE
command: Mapped[str] = mapped_column(String(50), nullable=False)  # "plan", "apply", "destroy"
```

**Rationale:**
- Database already has historical data with string commands
- Audit logs need human-readable command names
- Command strings are a stable API contract for external tools

**Impact:**
- ✅ **No migration required** for existing database
- ✅ **Backward compatible** with existing queries
- ✅ **No breaking changes** to state API
- ⚠️ **Must maintain mapping** between protocols and command strings
- ❌ **No type safety** at database level (still strings)

**Implementation:**
```python
# Add helper mapping in protocols.py
PROTOCOL_TO_COMMAND = {
    Plannable: "plan",
    Applyable: "apply",
    Destroyable: "destroy",
}

def get_command_name(protocol_type: type) -> str:
    """Get command string for a protocol type."""
    return PROTOCOL_TO_COMMAND.get(protocol_type, "unknown")
```

---

## 2. The Ansible Special Case

### Q2.1: How to handle Ansible's auto_approve logic?

**PROPOSED:** **Option D** - Pass auto_approve to apply() and let runner decide

```python
# In protocols.py - UPDATE Applyable protocol
@runtime_checkable
class Applyable(Protocol):
    def apply(self, provider: "ProviderBase", auto_approve: bool = True, **kwargs: Any) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            provider: Provider instance to apply
            auto_approve: Whether to auto-approve changes (may affect behavior)
            **kwargs: Additional apply options
        """
        ...

# In ansible_runner.py
def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> dict[str, Any]:
    """Run Ansible playbook.

    When auto_approve=False, runs in check mode (dry-run/plan equivalent).
    """
    check_mode = not auto_approve  # Ansible's semantic
    return self._run_ansible(provider, check_mode=check_mode)
```

**Rationale:**
- Keeps the logic where it belongs (in the runner)
- Maintains the semantic meaning: "are you sure?" vs "just check"
- Protocol signature accommodates different interpretations

**Impact:**
- ✅ **Encapsulation**: Logic stays in AnsibleRunner
- ✅ **Flexibility**: Each runner interprets auto_approve appropriately
- ✅ **No special cases** in orchestrator code
- ⚠️ **Semantic ambiguity**: auto_approve means different things per runner
- ✅ **Terraform unchanged**: Already respects auto_approve

**Trade-off Analysis:**
- **Option A** (call plan() vs apply()): ❌ Orchestrator needs tool-specific logic
- **Option B** (add to protocol): ❌ Not all runners need it
- **Option C** (CheckMode protocol): ❌ Over-engineering for one case
- **Option D** (this proposal): ✅ Simple, encapsulated, flexible

---

## 3. Runner Discovery & Capabilities

### Q3.1: How should code discover what operations a runner supports?

**PROPOSED:** **Option A** - Always use `isinstance(runner, Protocol)` checks

```python
# In deployment_executor.py
for tool_name, runner in self._get_sorted_runners():
    if not isinstance(runner, Applyable):
        self.console.print(f"  [dim]Skipping {tool_name}: does not support apply[/dim]")
        continue

    result = runner.apply(provider, auto_approve=auto_approve)
```

**Rationale:**
- Pythonic: `isinstance()` is the idiomatic way to check protocol compliance
- Type-safe: mypy understands isinstance guards
- No additional API surface to maintain
- Runtime overhead is negligible (~O(1) per check)

**Impact:**
- ✅ **Standard Python**: Uses language features correctly
- ✅ **Type safety**: mypy recognizes isinstance guards
- ✅ **Zero overhead**: No new abstractions
- ✅ **Clear intent**: Code reads naturally
- ⚠️ **Verbose**: Requires check at every call site
- ❌ **No metadata**: Can't query capabilities without instance

**Alternative Rejected:**
```python
# Option B - Too much API surface
if runner.supports_operation("apply"):
    runner.apply(...)

# Option C - Redundant with isinstance
caps = runner.get_capabilities()  # Returns [Plannable, Applyable]

# Option D - Static only, no runtime benefit
class TerraformRunner:
    SUPPORTED_PROTOCOLS = [Plannable, Applyable, Destroyable]
```

**When to use each:**
- **isinstance()**: 95% of cases (call sites)
- **Class attributes**: Documentation/introspection only
- **Capability methods**: If building UI/CLI helpers

---

## 4. Error Handling & User Feedback

### Q4.1: What if calling code forgets the isinstance check?

**PROPOSED:** **Option A** - Let it fail with AttributeError (fail fast)

**Implementation:**
```python
# BaseRunner - NO plan/apply/destroy methods AT ALL
class BaseRunner(ABC):
    """Abstract base - only has tool_name, is_available, initialize, run()"""
    pass

# If you call runner.plan() without checking, you get:
# AttributeError: 'AnsibleRunner' object has no attribute 'plan'
```

**Rationale:**
- Fail fast is better than silent failures
- Forces developers to use isinstance checks
- mypy will catch this at dev time
- Clear error messages point to the problem

**Impact:**
- ✅ **Forces correctness**: Can't accidentally call unsupported methods
- ✅ **Fast debugging**: AttributeError is immediately obvious
- ✅ **Mypy enforcement**: Static type checking prevents this
- ❌ **No graceful degradation**: Crashes if check is forgotten
- ⚠️ **Breaking change**: Existing code without checks will break

**Mitigation:**
```python
# Add mypy strict mode to CI/CD
# pyproject.toml
[tool.mypy]
strict = true
warn_unused_ignores = true
warn_return_any = true

# Any call to runner.plan() without isinstance check will fail mypy
```

### Q4.2: Should we standardize error messages?

**PROPOSED:** **Option A** - Use consistent, user-friendly messages

```python
# In orchestrator code, use consistent format:
if not isinstance(runner, Destroyable):
    self.console.print(
        f"[yellow]⚠ Skipping {tool_name}: "
        f"does not support destroy operations[/yellow]"
    )
    continue
```

**Impact:**
- ✅ **User-friendly**: Non-technical users understand
- ✅ **Consistent UX**: Same format everywhere
- ✅ **Actionable**: Clear what's happening and why
- ⚠️ **String duplication**: Message format repeated at call sites

---

## 5. The `run()` Method Migration 🔴 CRITICAL

### Q5.1: What happens to the existing `run()` method?

**PROPOSED:** **🔥 AGGRESSIVE - Option A** - Remove `run()` entirely, no deprecation

**⚡ Pre-Release Advantage:**
Since there are no external users, we can skip the deprecation dance and go straight to the clean design.

**Single PR Approach** (Update all at once):

**Step 1:** Remove `run()` from BaseRunner
```python
# base_runner.py - REMOVE run() entirely
class BaseRunner(ABC):
    """Abstract base - only has tool_name, is_available, initialize"""
    # NO run() method at all
    pass
```

**Step 2:** Remove `run()` from all runner implementations
```python
# terraform_runner.py - DELETE run() method (lines ~150-165)
# ansible_runner.py - DELETE run() method (lines ~120-145)
# pyinfra_runner.py - DELETE run() method (lines ~130-145)
# pulumi_runner.py - DELETE run() method (lines ~230-240)
```

**Step 3:** Update all call sites to use protocol methods
```python
# deployment_executor.py:288 - BEFORE
run_result = runner.run(provider, "apply", auto_approve)

# deployment_executor.py:288 - AFTER
if not isinstance(runner, Applyable):
    self.console.print(f"[dim]Skipping {tool_name}: no apply support[/dim]")
    continue
run_result = runner.apply(provider, auto_approve=auto_approve)

# orchestrator_workflows.py:385 - BEFORE
runner_result = runner.run(provider, "plan", auto_approve=False)

# orchestrator_workflows.py:385 - AFTER
if not isinstance(runner, Plannable):
    self.console.print(f"[dim]Skipping {tool_name}: no plan support[/dim]")
    continue
runner_result = runner.plan(provider)

# orchestrator_workflows.py:832 - BEFORE
runner_result = runner.run(provider, "destroy", auto_approve)

# orchestrator_workflows.py:832 - AFTER
if not isinstance(runner, Destroyable):
    self.console.print(f"[dim]Skipping {tool_name}: no destroy support[/dim]")
    continue
runner_result = runner.destroy(provider, auto_approve=auto_approve)

# drift_detector.py:107 - BEFORE
plan_result = terraform_runner.run(provider, "plan", auto_approve=False)

# drift_detector.py:107 - AFTER
if not isinstance(terraform_runner, Plannable):
    return {...}  # Error case
plan_result = terraform_runner.plan(provider)
```

**Step 4:** Update tests
```python
# All test mocks need protocol methods instead of run()
# BEFORE:
runner.run.return_value = {"success": True}

# AFTER:
runner.apply = MagicMock(return_value={"success": True})
runner.plan = MagicMock()
runner.destroy = MagicMock()
```

**Impact Analysis:**

✅ **Clean Architecture:**
- No deprecated code
- No string-based dispatch
- Pure protocol-based from day one

✅ **Better Type Safety:**
- mypy enforces protocol checks
- No runtime string validation needed

✅ **Clearer Intent:**
- `runner.plan()` vs `runner.run("plan")`
- Obvious what operations do

✅ **Simpler Codebase:**
- Removes ~60 lines of dispatch logic from runners
- Removes command string handling

⚠️ **Single Large PR:**
- ~8 files changed
- ~100 lines modified
- More to review at once

✅ **No Deprecation Baggage:**
- Skip warnings
- Skip transition period
- Skip version bump concerns

**Effort Estimate:**
- **Time:** 3-4 hours for complete migration
- **Complexity:** Medium (straightforward find/replace pattern)
- **Testing:** ~1 hour to update all mocks
- **Review:** Single coherent PR, easier to review than 5 small ones

**Migration Checklist:**
```
☐ Remove run() from BaseRunner
☐ Remove run() from TerraformRunner
☐ Remove run() from AnsibleRunner
☐ Remove run() from PyInfraRunner
☐ Remove run() from PulumiRunner
☐ Update deployment_executor.py (1 call site)
☐ Update orchestrator_workflows.py (2 call sites)
☐ Update drift_detector.py (1 call site)
☐ Update all test mocks (~20 files)
☐ Run full test suite
☐ Run mypy --strict
☐ Update PR #77 or create new PR #78
```

**Why This Is Better (Pre-Release):**
1. **No technical debt** - Don't ship deprecated code
2. **Faster** - One PR instead of 5
3. **Cleaner history** - No "add then remove" commits
4. **Better review** - See complete picture at once
5. **No confusion** - Users never see old API

---

## 6. Type Safety & Mypy 🔴 CRITICAL

### Q6.1: How do we ensure type safety when calling protocol methods?

**PROPOSED:** **Option B** - Type narrowing (mypy supports this since 0.971)

```python
# deployment_executor.py
def apply_single_provider(self, provider: ProviderBase, ...) -> dict[str, Any]:
    for tool_name, runner in self._get_sorted_runners():
        # runner has type BaseRunner here

        if not isinstance(runner, Applyable):
            continue

        # After isinstance check, mypy narrows type to Applyable
        # No cast needed!
        result = runner.apply(provider, auto_approve=auto_approve)  # ✅ mypy OK

        if isinstance(runner, StateAware):
            # mypy knows runner is both Applyable AND StateAware here
            ids = runner.get_resource_ids(provider)  # ✅ mypy OK
```

**Why this works:**
- Python 3.10+ with mypy 0.971+ supports protocol type narrowing
- `isinstance()` with `@runtime_checkable` protocols narrows types
- No explicit `cast()` needed in most cases

**When you DO need cast():**
```python
# Only when type checker can't infer, or for clarity
runners: list[BaseRunner] = [...]
plannable_runners = [r for r in runners if isinstance(r, Plannable)]
# mypy still sees list[BaseRunner], not list[Plannable]

# Use cast for clarity:
from typing import cast
plannable_runners = cast(list[Plannable], [r for r in runners if isinstance(r, Plannable)])
```

**Impact:**
- ✅ **Clean code**: No cast() clutter in normal cases
- ✅ **Type safety**: Full mypy coverage
- ✅ **Modern Python**: Uses language features properly
- ⚠️ **Requires mypy 0.971+**: Check CI/CD config
- ⚠️ **Occasional cast needed**: List comprehensions, complex flows

**Configuration Required:**
```toml
# pyproject.toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_redundant_casts = true
warn_unused_ignores = true
```

**Verification:**
```bash
# Add to CI/CD
uv run mypy src/infrafoundry --strict
```

---

## 7. Result Format Consistency

### Q7.1: Should we standardize result dictionaries?

**PROPOSED:** **Option B** - Create TypedDict result classes

```python
# In protocols.py or new results.py
from typing import TypedDict, NotRequired

class BaseResult(TypedDict):
    """Base result for all runner operations."""
    success: bool
    exit_code: NotRequired[int]
    error: NotRequired[str]

class PlanResult(BaseResult):
    """Result from plan operation."""
    output: NotRequired[str]
    has_changes: NotRequired[bool]
    changes_summary: NotRequired[str]

class ApplyResult(BaseResult):
    """Result from apply operation."""
    output: NotRequired[str]
    resources_created: NotRequired[int]
    resources_updated: NotRequired[int]

class DestroyResult(BaseResult):
    """Result from destroy operation."""
    output: NotRequired[str]
    resources_destroyed: NotRequired[int]

class DriftInfo(TypedDict):
    """Result from drift detection."""
    has_changes: bool
    summary: str
    added: NotRequired[int]
    changed: NotRequired[int]
    destroyed: NotRequired[int]
```

**Update Protocol Signatures:**
```python
@runtime_checkable
class Plannable(Protocol):
    def plan(self, provider: "ProviderBase", **kwargs: Any) -> PlanResult:
        ...

@runtime_checkable
class Applyable(Protocol):
    def apply(self, provider: "ProviderBase", auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
        ...

@runtime_checkable
class Destroyable(Protocol):
    def destroy(self, provider: "ProviderBase", auto_approve: bool = True, **kwargs: Any) -> DestroyResult:
        ...

@runtime_checkable
class DriftDetectable(Protocol):
    def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo:
        ...
```

**Impact:**
- ✅ **Type safety**: mypy checks result dictionary keys
- ✅ **IDE support**: Autocomplete on result['key']
- ✅ **Documentation**: TypedDict serves as API contract
- ✅ **Gradual typing**: Can migrate incrementally (TypedDict is structural)
- ⚠️ **Migration needed**: Update all return statements
- ⚠️ **Runtime unchanged**: TypedDict is just hints, no runtime checks

**Migration Strategy:**
```python
# Phase 1: Add TypedDict definitions (no breaking changes)
# Phase 2: Update protocol signatures to use them
# Phase 3: Update runner implementations
# Phase 4: Update call sites to use typed results

# Example migration of a call site:
# Before:
result = runner.apply(provider)
if result["success"]:  # mypy doesn't know what keys exist
    print(result["output"])

# After:
result: ApplyResult = runner.apply(provider)
if result["success"]:  # mypy knows ApplyResult structure
    print(result.get("output", ""))  # type-safe access
```

---

## 8. Testing Strategy

### Q8.1: How do we ensure all call sites are properly updated?

**PROPOSED:** **Combination of Options A, B, C**

**Step 1 - Static Analysis:**
```bash
# Find all .run( call sites
rg "\.run\(" --type py src/infrafoundry/core/

# Generate migration checklist
rg "\.run\(" --type py src/ --json | jq -r '.data.lines.text' > migration_checklist.txt
```

**Step 2 - Add Deprecation Warnings (Option A):**
```python
# In base_runner.py run() method
warnings.warn(
    f"{self.__class__.__name__}.run() is deprecated",
    DeprecationWarning,
    stacklevel=2
)
```

**Step 3 - Update Tests First (Option C):**
```python
# tests/unit/test_deployment_executor.py - BEFORE
runner.run.return_value = {"success": True}
executor.apply(...)
runner.run.assert_called_once_with(provider, "apply", True)

# tests/unit/test_deployment_executor.py - AFTER
runner.apply.return_value = {"success": True}
executor.apply(...)
runner.apply.assert_called_once_with(provider, auto_approve=True)
```

**Step 4 - Run Tests with Warnings as Errors:**
```bash
# pytest with deprecation warnings
uv run pytest -W error::DeprecationWarning

# This will fail until all run() calls are migrated
```

### Q8.2: Should we add protocol compliance tests?

**PROPOSED:** **YES** - Add comprehensive protocol tests

```python
# tests/unit/test_protocol_compliance.py
import pytest
from infrafoundry.core.protocols import (
    Plannable, Applyable, Destroyable, StateAware, DriftDetectable
)
from infrafoundry.core.runners import (
    TerraformRunner, AnsibleRunner, PyInfraRunner, PulumiRunner
)

class TestProtocolCompliance:
    """Verify each runner implements expected protocols."""

    def test_terraform_runner_protocols(self):
        runner = TerraformRunner()
        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)
        assert isinstance(runner, Destroyable)
        assert isinstance(runner, StateAware)
        assert isinstance(runner, DriftDetectable)

        # Verify methods exist and have correct signatures
        assert callable(runner.plan)
        assert callable(runner.apply)
        assert callable(runner.destroy)
        assert callable(runner.get_resource_ids)
        assert callable(runner.parse_plan_for_drift)

    def test_ansible_runner_protocols(self):
        runner = AnsibleRunner()
        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)

    def test_pyinfra_runner_protocols(self):
        runner = PyInfraRunner()
        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)

    @pytest.mark.parametrize("runner_class,protocols", [
        (TerraformRunner, [Plannable, Applyable, Destroyable, StateAware, DriftDetectable]),
        (AnsibleRunner, [Plannable, Applyable]),
        (PyInfraRunner, [Plannable, Applyable]),
        (PulumiRunner, [Plannable, Applyable, Destroyable, StateAware, DriftDetectable]),
    ])
    def test_runner_protocol_matrix(self, runner_class, protocols):
        """Verify expected protocol compliance for each runner."""
        runner = runner_class()
        for protocol in protocols:
            assert isinstance(runner, protocol), \
                f"{runner_class.__name__} should implement {protocol.__name__}"
```

**Impact:**
- ✅ **Regression prevention**: Tests catch accidental protocol removal
- ✅ **Documentation**: Tests serve as specification
- ✅ **CI enforcement**: Can't merge without protocol compliance
- ✅ **Refactoring safety**: Can change implementations safely
- ⚠️ **Maintenance**: Need to update when adding new protocols

---

## 9. Third-Party Extensions

### Q9.1: Are there external consumers of the Runner API?

**ANALYSIS:** Based on code review:
- ❌ **No plugin system found**: Runners are hardcoded in `orchestrator.py:88-91`
- ❌ **No dynamic registration**: All runners imported statically
- ❌ **No external imports**: No evidence of external runner implementations
- ✅ **Internal only**: All usage is within infrafoundry package

**PROPOSED:** Assume internal-only, but provide migration guide

**Impact:**
- ✅ **Free to break**: No external compatibility concerns
- ✅ **Faster migration**: Don't need to support old API
- ⚠️ **Document breaking changes**: Clear CHANGELOG and upgrade guide
- ⚠️ **Semantic versioning**: Bump to v2.0 when removing run()

### Q9.2: Should we add a plugin system?

**PROPOSED:** **Not now, but design for it**

```python
# Future-proofing: Keep registry flexible
class RunnerRegistry:
    def register(self, runner_class: type[BaseRunner], tool_name: str | None = None):
        """Register can be called externally to add custom runners."""
        ...

# Document the protocol requirements
# docs/extending_runners.md
"""
To create a custom runner:

1. Implement protocols for supported operations
2. Inherit from BaseRunner for basic functionality
3. Register with global registry

Example:
    from infrafoundry.core.runners import BaseRunner, register_runner
    from infrafoundry.core.protocols import Plannable, Applyable

    class CustomRunner(BaseRunner):
        @property
        def tool_name(self) -> str:
            return "custom"

        def plan(self, provider, **kwargs):
            ...

        def apply(self, provider, auto_approve=True, **kwargs):
            ...

    # Register your runner
    register_runner(CustomRunner)
"""
```

**Impact:**
- ✅ **Future-proof**: Easy to add plugins later
- ✅ **Clean API**: Registry already supports external registration
- ⚠️ **Undocumented**: No official plugin API yet
- ⚠️ **Unsupported**: Breaking changes can still happen

---

## 10. Priority & Ordering

### Q10.1: Should runner priority change with protocols?

**PROPOSED:** **Option A** - Keep priority on BaseRunner (unchanged)

```python
# base_runner.py - NO CHANGE
class BaseRunner(ABC):
    @property
    def priority(self) -> int:
        """Execution priority (lower runs first)."""
        return 50
```

**Rationale:**
- Priority is about execution order, not capabilities
- Terraform must run before Ansible regardless of operation
- No use case for operation-specific priorities found

**Impact:**
- ✅ **No changes needed**: Existing priority system works
- ✅ **Simple**: One priority value per runner
- ⚠️ **Not protocol-specific**: Can't have different order for destroy vs apply
- ✅ **Sufficient**: No evidence this is needed

**Future Consideration:**
If operation-specific ordering is needed:
```python
class BaseRunner(ABC):
    @property
    def priority_apply(self) -> int:
        return self.priority

    @property
    def priority_destroy(self) -> int:
        # Destroy in reverse order
        return 100 - self.priority
```

---

## 11. Pulumi Runner Status

### Q11.1: What to do with PulumiRunner?

**ANALYSIS:**
```python
# orchestrator.py:30
from infrafoundry.core.runners import AnsibleRunner, PyInfraRunner, RunnerRegistry, TerraformRunner
# ❌ PulumiRunner NOT imported

# orchestrator.py:88-91
self.runner_registry.register(TerraformRunner)
self.runner_registry.register(AnsibleRunner)
self.runner_registry.register(PyInfraRunner)
# ❌ PulumiRunner NOT registered
```

**PROPOSED:** Register PulumiRunner (complete the implementation)

```python
# orchestrator.py - ADD import
from infrafoundry.core.runners import (
    AnsibleRunner,
    PyInfraRunner,
    PulumiRunner,  # ← ADD THIS
    RunnerRegistry,
    TerraformRunner
)

# orchestrator.py:88-91 - ADD registration
self.runner_registry.register(TerraformRunner)
self.runner_registry.register(PulumiRunner)  # ← ADD THIS
self.runner_registry.register(AnsibleRunner)
self.runner_registry.register(PyInfraRunner)
```

**Impact:**
- ✅ **Feature complete**: Pulumi support fully enabled
- ✅ **No breaking changes**: Just enables existing code
- ⚠️ **Needs testing**: Pulumi runner may be untested in CI
- ⚠️ **Documentation**: Need to document Pulumi support

**Alternative:** If Pulumi is experimental:
```python
# orchestrator.py
EXPERIMENTAL_RUNNERS = ["pulumi"]

if os.getenv("INFRA_ENABLE_EXPERIMENTAL"):
    self.runner_registry.register(PulumiRunner)
```

---

## 12. Migration Strategy 🔴 CRITICAL

### Q12.1: What's the migration path?

**PROPOSED:** **🔥 AGGRESSIVE - Option A** - Single PR, complete migration, no deprecation

**⚡ Pre-Release Advantage:**
No need to maintain backward compatibility. Remove `run()` and update all call sites in one atomic change.

### Single PR Approach

**PR #78: Complete Protocol Migration**

**Scope:**
```
☐ Remove run() from BaseRunner (abstract method gone in PR #77)
☐ Remove run() implementations from all 4 runners
☐ Update 4 call sites to use protocol methods
☐ Update ~20 test files to mock protocol methods
☐ Remove debug print statements from PR #77
☐ Register PulumiRunner in orchestrator
```

**Files to Change:**

1. **Runner Implementations** (~60 lines deleted)
   - `src/infrafoundry/core/runners/terraform_runner.py` - Delete run() method
   - `src/infrafoundry/core/runners/ansible_runner.py` - Delete run() method
   - `src/infrafoundry/core/runners/pyinfra_runner.py` - Delete run() method
   - `src/infrafoundry/core/runners/pulumi_runner.py` - Delete run() method

2. **Call Sites** (~40 lines modified)
   - `src/infrafoundry/core/deployment_executor.py:288` - Replace run() with apply()
   - `src/infrafoundry/core/orchestrator_workflows.py:385` - Replace run() with plan()
   - `src/infrafoundry/core/orchestrator_workflows.py:832` - Replace run() with destroy()
   - `src/infrafoundry/core/drift_detector.py:107` - Replace run() with plan()

3. **Cleanup from PR #77** (~3 lines deleted)
   - `src/infrafoundry/core/deployment_executor.py:291-292` - Remove debug prints
   - `src/infrafoundry/core/deployment_executor.py:307` - Remove debug print

4. **Pulumi Registration** (~2 lines added)
   - `src/infrafoundry/core/orchestrator.py:30` - Add PulumiRunner import
   - `src/infrafoundry/core/orchestrator.py:91` - Register PulumiRunner

5. **Test Mocks** (~50 lines modified)
   - `tests/unit/test_deployment_executor.py` - Update all mocks
   - `tests/unit/test_orchestrator_workflows_unit.py` - Update mocks
   - `tests/unit/test_drift_detector.py` - Update mocks (if exists)
   - Any other test files that mock runner.run()

**Implementation Order:**

```bash
# 1. Remove run() implementations from runners
# 2. Update call sites (will temporarily break)
# 3. Update test mocks
# 4. Remove debug output
# 5. Register Pulumi
# 6. Run full test suite
# 7. Run mypy --strict
# 8. Commit atomic change
```

### Detailed Changes

**1. deployment_executor.py** (Lines 274-318)
```python
# BEFORE (with debug output):
for tool_name, runner in self._get_sorted_runners():
    if not isinstance(runner, Applyable):
        continue

    command = "apply"
    if tool_name == "ansible" and not auto_approve:
        command = "plan"

    run_result = runner.run(provider, command, auto_approve)

    is_state_aware = isinstance(runner, StateAware)
    self.console.print(f"[dim]Runner {tool_name} is StateAware: {is_state_aware}[/dim]")

    if isinstance(runner, StateAware):
        terraform_ids = state_runner.get_resource_ids(provider)
        self.console.print(f"[dim]Got terraform IDs: {terraform_ids}[/dim]")

# AFTER (clean):
for tool_name, runner in self._get_sorted_runners():
    if not isinstance(runner, Applyable):
        self.console.print(f"[dim]Skipping {tool_name}: no apply support[/dim]")
        continue

    # Ansible interprets auto_approve=False as check mode
    run_result = runner.apply(provider, auto_approve=auto_approve)

    if tool_name == "terraform" and run_result["success"] and isinstance(runner, StateAware):
        state_runner = cast(StateAware, runner)
        terraform_ids = state_runner.get_resource_ids(provider)
        # Update state with IDs
        for resource_name, terraform_id in terraform_ids.items():
            if resource_name in resource_ids:
                self.state_manager.update_resource(...)
```

**2. orchestrator_workflows.py** (Line 385)
```python
# BEFORE:
runner_result = runner.run(provider, "plan", auto_approve=False)

# AFTER:
if not isinstance(runner, Plannable):
    self.console.print(f"[dim]Skipping {tool_name}: no plan support[/dim]")
    continue
runner_result = runner.plan(provider)
```

**3. orchestrator_workflows.py** (Line 832)
```python
# BEFORE:
runner_result = runner.run(provider, "destroy", auto_approve)

# AFTER:
if not isinstance(runner, Destroyable):
    self.console.print(f"[dim]Skipping {tool_name}: no destroy support[/dim]")
    continue
runner_result = runner.destroy(provider, auto_approve=auto_approve)
```

**4. drift_detector.py** (Line 107)
```python
# BEFORE:
plan_result = terraform_runner.run(provider, "plan", auto_approve=False)
if not isinstance(terraform_runner, DriftDetectable):
    # warning...
    continue

# AFTER:
if not isinstance(terraform_runner, Plannable):
    self.console.print("[yellow]Terraform runner doesn't support plan[/yellow]")
    continue
plan_result = terraform_runner.plan(provider)

if not isinstance(terraform_runner, DriftDetectable):
    self.console.print("[yellow]Terraform doesn't support drift detection[/yellow]")
    continue
```

### Timeline Estimate

| Task | Effort | Notes |
|------|--------|-------|
| Remove run() from runners | 30 min | Straightforward deletion |
| Update 4 call sites | 1 hour | Pattern-based replacement |
| Update test mocks | 1.5 hours | ~20 files, repetitive |
| Remove debug output | 5 min | Delete 3 lines |
| Register Pulumi | 5 min | Add 2 lines |
| Run tests & fix issues | 1 hour | Iterate until green |
| **TOTAL** | **4 hours** | Single afternoon |

### Risk Assessment

✅ **Low Risk:**
- Atomic change - either works or doesn't
- All tests must pass before merge
- Type checking enforces correctness
- Easy to revert (single commit)

✅ **High Confidence:**
- Clear pattern to follow
- Tests verify correctness
- mypy catches type errors
- No runtime configuration changes

⚠️ **Potential Issues:**
- Might miss some test mocks (test suite will fail)
- Might miss edge cases in call sites (mypy will catch)

✅ **Mitigation:**
```bash
# Before starting, find ALL usages:
rg "\.run\(" --type py src/ tests/

# Checklist approach ensures nothing missed
# Test suite must be 100% green
# mypy --strict must pass
```

### Comparison: Gradual vs Aggressive

| Aspect | Gradual (5 PRs) | Aggressive (1 PR) |
|--------|----------------|-------------------|
| **Total Time** | ~12 hours | ~4 hours |
| **Duration** | 2-3 weeks | 1 day |
| **PRs to Review** | 5 separate | 1 comprehensive |
| **Deprecation** | Yes | No |
| **Tech Debt** | Temporary | None |
| **Rollback** | Complex | Simple (1 revert) |
| **Consistency** | Mixed state during migration | Clean throughout |
| **Testing** | Test 5 times | Test once |

**🔥 Pre-Release Winner: AGGRESSIVE**

Why?
1. **3x faster** - 4 hours vs 12 hours
2. **Cleaner** - No deprecated code ever ships
3. **Simpler** - One review, one merge, one deploy
4. **Less work** - Don't test intermediate states
5. **Better history** - Clean git log, no churn

### Rollback Plan

If issues found:
```bash
# Can rollback any individual PR
git revert <commit-sha>

# Or rollback to any phase
git checkout v1.9.0  # Before breaking changes
git checkout phase-2  # With deprecation
git checkout phase-1  # Current state (PR #77)
```

---

## 13. CLI Command Mapping

### Q13.1: Does CLI need updates?

**ANALYSIS:**
```python
# Current flow:
CLI (plan.py) → orchestrator.plan() → runner.run(provider, "plan")

# New flow:
CLI (plan.py) → orchestrator.plan() → runner.plan(provider)
```

**PROPOSED:** CLI remains **unchanged**

```python
# cli/commands/plan.py - NO CHANGES NEEDED
@click.command()
def plan(env: str, ...):
    orchestrator.plan(env, ...)  # Same API
```

**Why no changes:**
- CLI calls orchestrator methods, not runner methods
- Orchestrator methods maintain same signatures
- Changes are internal to orchestrator implementation

**Impact:**
- ✅ **Zero CLI changes**: User experience unchanged
- ✅ **Backward compatible**: CLI commands work identically
- ✅ **Transparent**: Users don't see internal refactoring
- ✅ **No documentation updates**: CLI docs stay the same

---

## Summary: Recommended Decisions (Pre-Release Edition)

### 🔴 Critical Decisions (Must Agree Before Starting)

| # | Question | Recommended Answer | Impact |
|---|----------|-------------------|--------|
| 5.1 | run() method fate | 🔥 **Remove immediately** (Option A) | 4 hours work, 1 day duration |
| 6.1 | Type safety approach | isinstance() type narrowing (Option B) | Clean code, requires mypy 0.971+ |
| 12.1 | Migration strategy | 🔥 **Single PR** (Option A) | Low risk, atomic change |
| 2.1 | Ansible auto_approve | Pass to apply(), runner decides (Option D) | Encapsulated, flexible |

### 🟡 Important Decisions (Should Agree)

| # | Question | Recommended Answer | Impact |
|---|----------|-------------------|--------|
| 7.1 | Result format | TypedDict classes (Option B) | Better type safety, can add later |
| 8.1 | Testing strategy | Static analysis + test suite | High confidence |
| 8.2 | Protocol tests | Yes, comprehensive suite | Regression prevention |
| 4.1 | Error handling | Fail fast with AttributeError (Option A) | Forces correctness |

### 🟢 Minor Decisions (Can Decide Later)

| # | Question | Recommended Answer | Impact |
|---|----------|-------------------|--------|
| 1.1 | Database command field | Keep as strings (Option A) | No migration needed |
| 3.1 | Capability discovery | isinstance() checks (Option A) | Pythonic, simple |
| 4.2 | Error messages | Standardize format | Better UX |
| 9.1 | External consumers | 🔥 **None - pre-release** | Free to break |
| 10.1 | Runner priority | Keep on BaseRunner (Option A) | No changes needed |
| 11.1 | Pulumi status | Register it (complete feature) | Enable existing code |
| 13.1 | CLI changes | None needed | Transparent |

---

## Next Steps

### 🔥 If You Agree with Aggressive Approach:

1. **✅ PR #77 is merged** (foundation complete)
2. **Create PR #78** - Complete protocol migration in single PR:
   - Remove `run()` from all runners (4 files)
   - Update all call sites (4 files)
   - Update test mocks (~20 files)
   - Remove debug output from PR #77
   - Register PulumiRunner
   - **Estimated time:** 4 hours
3. **Merge and deploy** - Done! Pure protocol-based design achieved

### If You Want to Discuss:

Reply with:
- Which decisions you disagree with
- Whether you prefer gradual approach despite pre-release status
- Any concerns about 4-hour timeline
- Testing requirements

### Estimated Completion

**🔥 Aggressive (Recommended):**
- **Start:** Today
- **Finish:** Tomorrow
- **Effort:** 4 hours
- **PRs:** 1
- **Risk:** LOW (atomic, easily reverted)

**⚠️ Gradual (If preferred):**
- **Start:** Today
- **Finish:** 2-3 weeks
- **Effort:** 12 hours
- **PRs:** 5
- **Risk:** LOW (but more overhead)

---

## Open Questions for You

1. **🔥 Aggressive or Gradual?** Pre-release suggests aggressive, but your call
2. **When to start?** Can begin immediately if approved
3. **TypedDict results?** Tackle in PR #78 or separate PR later?
4. **Pulumi?** Register now or mark experimental?
5. **PR #77 issues?** Should we fix debug output now or in #78?

**My Recommendation:**
Do it all in one go (PR #78). You'll have clean protocol-based code by tomorrow, no technical debt, no deprecation period, cleaner git history. The pre-release status is a huge advantage - use it!
