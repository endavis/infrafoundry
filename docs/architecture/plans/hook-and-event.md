# InfraFoundry Orchestration Refactoring Plan

## Summary

The codebase has solid architecture (SOLID 100/100) but operation ordering is broken in several critical ways. The dependency graph system exists but is **only used for analysis commands**, not actual execution.

**Scope:** All 5 phases - complete refactoring including cross-provider dependencies and hook cleanup.

## Critical Issues Found

| Issue | Severity | Location |
|-------|----------|----------|
| Destroy ignores provider order | CRITICAL | `orchestrator_workflows.py:958` - dict iteration |
| Parallel apply ignores ordering | CRITICAL | `deployment_executor.py:190-217` - all providers concurrent |
| Plan ignores provider order | HIGH | `orchestrator_workflows.py:355` - dict iteration |
| Cross-provider deps not tracked | HIGH | `orchestrator.py:345-352` - same-provider only |
| Dependency graph unused in execution | HIGH | Only used in `infra analyze` commands |
| Hook methods duplicated 3x | MEDIUM | Same code in Plan/Apply/Destroy orchestrators |

## Recommendation: Incremental Refactoring

**NOT a rewrite.** The architecture is sound. The issues are localized to execution ordering logic.

---

## Phase 1: Create ExecutionPlanner Service (Foundation)

**New file:** `src/infrafoundry/core/execution_planner.py`

```python
class ExecutionPlanner:
    """Plans execution order based on dependency graph and provider order."""

    def get_execution_order(
        self,
        env_name: str,
        resources_by_provider: dict[str, list[ResourceConfig]],
        operation: Literal["plan", "apply", "destroy"],
    ) -> list[list[str]]:
        """Return batches of provider names for parallel execution.

        For destroy, returns REVERSE order.
        Returns: [[batch1_providers], [batch2_providers], ...]
        """
```

This bridges the existing `DependencyGraph` to the execution flow.

**Files to modify:**
- `orchestrator.py` - Add ExecutionPlanner instance
- `orchestrator_workflows.py` - Use ExecutionPlanner for ordering

---

## Phase 2: Fix Provider Ordering

### 2.1: Fix `_iter_provider_batches()` (orchestrator.py:258-279)

Add sorting using `provider_order` from environment config.

### 2.2: Fix DestroyOrchestrator (orchestrator_workflows.py:958)

Use **reversed** execution order for destroy operations.

### 2.3: Fix Parallel Apply (deployment_executor.py:190-217)

Change from:
```python
# Current: All providers submitted concurrently
for provider_name, resources in resources_by_provider.items():
    executor.submit(...)
```

To batch-based parallelism:
```python
# Fixed: Process batches sequentially, parallelize within batches
for batch in execution_batches:
    # All providers in this batch can run in parallel
    batch_futures = [executor.submit(...) for p in batch]
    wait(batch_futures)  # Complete batch before next
```

---

## Phase 3: Cross-Provider Dependencies (Optional)

Add `depends_on` field to ResourceConfig:

```yaml
resources:
  - name: my-k8s-app
    provider: kubernetes
    depends_on:
      - provider: oci
        name: load-balancer
```

Extend `build_dependency_graph()` to search across all providers.

---

## Phase 4: Hook System Cleanup

### 4.1: Extract HookExecutionMixin

Create `src/infrafoundry/core/hooks/mixin.py` with shared hook methods.

### 4.2: Add Hook Events

New event types: `HOOK_STARTED`, `HOOK_COMPLETED`, `HOOK_FAILED`

### 4.3: Fix Silent Secret Failures

Add `fail_on_missing` option to secret resolution.

---

## Phase 5: Testing & Validation

- Unit tests for ExecutionPlanner
- Integration tests for ordering
- Verify destroy uses reverse order
- Maintain 69%+ coverage

---

## Files to Modify

| File | Changes |
|------|---------|
| `core/execution_planner.py` | NEW - Execution ordering service |
| `core/orchestrator.py` | Add ExecutionPlanner, fix `_iter_provider_batches()` |
| `core/orchestrator_workflows.py` | Use ordered batches, remove hook duplication |
| `core/deployment_executor.py` | Batch-based parallel apply |
| `core/hooks/mixin.py` | NEW - Shared hook execution |
| `core/events.py` | Add hook event types |
| `core/provider.py` | Add `depends_on` field (Phase 3) |

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Provider ordering fixes | Low | Backwards compatible |
| Parallel batching | Medium | Falls back to serial |
| Cross-provider deps | High | Opt-in via new field |
| Hook refactoring | Low | Pure code reorganization |

---

## Implementation Order

1. **Phase 1** - ExecutionPlanner (enables all other fixes)
2. **Phase 2.1-2.2** - Serial ordering fixes (low risk)
3. **Phase 2.3** - Parallel apply batching
4. **Phase 4** - Hook cleanup (independent)
5. **Phase 3** - Cross-provider dependencies

---

## Verification

After implementation, verify with:

1. **Unit tests**: `doit test` - all tests pass, 69%+ coverage
2. **Type checking**: `doit check` - no mypy errors
3. **Manual testing**:
   - `infra plan --env test` - verify providers execute in configured order
   - `infra apply --env test` - verify parallel applies respects batches
   - `infra destroy --env test` - verify reverse order execution
4. **Log inspection**: Check logs show correct provider ordering
5. **Hook events**: Verify new hook events appear in event stream
