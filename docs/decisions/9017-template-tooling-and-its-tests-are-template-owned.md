# ADR-9017: Template tooling and its tests are template-owned

## Status
Accepted

## Decision
Template tooling tests (`tests/template/test_*.py` that test `tools/pyproject_template/`) are
**template-owned**: they run only in the template's own CI, are excluded from the drift checker,
and are shed from downstream projects by `cleanup --setup`.

A single constant `TEMPLATE_OWNED_TEST_FILES` in `utils.py` is the authoritative list.
Both `check_template_updates.py` and `cleanup.py` import from it; neither hardcodes the list.

## Rationale
Before this decision, tooling tests lived alongside skeleton tests with no distinction.
The drift checker would present them as "please adopt" suggestions to downstream projects,
and `cleanup --setup` left them in place — meaning a downstream project would carry
template-CI tests that import `tools.pyproject_template.*` (a namespace that no longer
exists after cleanup removes the tooling directory).

A single source of truth avoids the shed-list and exclude-list diverging silently.

The "straddler" file `tests/template/test_properties.py` was split:
- `test_properties.py` — downstream-owned; contains only skeleton (`greet`) assertions.
- `tests/template/test_utils_properties.py` — template-owned; contains tooling property tests.

A coupling guard (`_emit_coupling_warnings`) warns when a drifted non-owned test imports
tooling that has also drifted, so users know to run `bootstrap --sync` before adopting
that test.

## Consequences
- **Downstream projects carry no tests for the tooling they run.** The tooling
  (`manage.py`, `check_template_updates.py`, `cleanup.py`, …) still ships via
  `bootstrap.py` `SYNC_FILES`, but its tests do not. We accept this: downstreams
  consume the tooling without modifying it, and these tests depend on template-only
  fixtures (the `package_name` skeleton) that no longer exist once a downstream is
  configured. This is why the alternative — adding the tests to `SYNC_FILES` so
  tooling and tests travel together — was rejected: it would push non-runnable,
  skeleton-coupled tests into every downstream.
- **Existing downstreams need a one-time cleanup.** Projects that adopted these
  tests in an earlier sync are not cleaned up automatically; they should run
  `cleanup --setup` once to shed them (see
  [AI Sync Checklist – Phase 1](../template/ai-sync-checklist.md)).
- **Known limitation — the stale-comparator facet remains.** The drift checker runs
  from the downstream's local (possibly stale) tooling, so both the exclusion list
  (`TEMPLATE_OWNED_TEST_FILES`) and the comparison logic are only as fresh as the
  last `bootstrap --sync`; a newly template-owned test added upstream is not excluded
  until the downstream syncs `utils.py`. A self-updating comparator was considered and
  declined as too fragile — running `bootstrap --sync` first (now an always-run early
  step) is the mitigation.

## Related Issues
- Issue #631: Make template tooling tests template-owned

## Related Documentation
- [Template Tooling](../template/tools-reference.md)
- [AI Sync Checklist – Phase 1](../template/ai-sync-checklist.md)
