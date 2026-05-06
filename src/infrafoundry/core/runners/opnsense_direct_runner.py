"""Direct-API runner for OPNsense components (ADR-0014).

This runner replaces the terraform/browningluke pipeline for components that
have migrated to the ``opnsense_openapi`` direct-API path. It implements the
ADR-0010 runner protocols (``Plannable``, ``Applyable``, ``Destroyable``,
``StateAware``) by delegating to component managers under
``infrafoundry.providers.opnsense.components``.

Components participate by declaring themselves in
``OPNsenseProvider.get_direct_api_resource_types()`` — the runner iterates
that dispatch table at plan/apply/destroy/get_resource_ids time. Adding a
new direct-API component is a one-entry change in the provider; no runner
edits are required.

The runner deliberately runs at ``priority = -10`` so that direct-API resources
(e.g., VLANs) are applied before any terraform-managed dependents
(``dhcp_static_maps``) within the same provider. See
``orchestrator_workflows.py::_get_sorted_runners`` for the priority sort.

Drift detection (``DriftDetectable``) is intentionally not implemented in this
PR; ``infra plan`` provides equivalent UX via the diff engine, and a full
``DriftDetectable`` implementation is tracked as a follow-up issue.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.types import ResourceOutcome

logger = logging.getLogger(__name__)


class OPNsenseDirectRunner(BaseRunner):
    """Runner that drives OPNsense components via the direct-API path.

    The runner is dispatch-table driven: ``provider.get_direct_api_resource_types()``
    returns ``{type_name: ComponentManager}`` and each public method
    (``plan``/``apply``/``destroy``/``get_resource_ids``) iterates that
    table, filters resources by type, and delegates to the manager. New
    components opt in by adding a single entry to the provider's dispatch
    table; no runner code changes required.

    The provider must expose ``generate_opnsense_direct(resources)`` (a no-op
    is fine — see ``OPNsenseProvider.generate_opnsense_direct``) so the
    orchestrator's plan/apply dispatch loop selects this runner. Resource
    routing then happens inside each ``plan/apply/destroy`` method below by
    filtering ``resources`` on ``resource.type``.
    """

    _tool_name: str = "opnsense_direct"

    def __init__(self, console: Console | None = None) -> None:
        """Initialize OPNsense direct-API runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the tool identifier used by the orchestrator dispatch loop."""
        return "opnsense_direct"

    @property
    @override
    def priority(self) -> int:
        """Run before terraform (priority 0) so direct-API VLANs apply first.

        The orchestrator sorts runners by priority before each phase; placing
        this runner at -10 guarantees that VLAN add/update/delete completes
        before terraform plans dependents like dhcp_static_maps.
        """
        return -10

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The direct-API runner is an IaC provisioner; it auto-runs in plan/apply."""
        return True

    @override
    def is_available(self) -> bool:
        """Return True if the ``opnsense_openapi`` package can be imported."""
        try:
            import opnsense_openapi  # noqa: F401  # availability probe only
        except ImportError:
            return False
        return True

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization — the direct-API runner has nothing to provision.

        Args:
            working_dir: Provided for protocol compatibility with terraform's
                ``terraform init`` semantics; ignored here.
            **kwargs: Tool-specific options (ignored).

        Returns:
            Dict with success flag.
        """
        return {"success": True, "output": "no init required"}

    # ------------------------------------------------------------------
    # Provider-config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _supports_direct_api(provider: ProviderBase) -> bool:
        """Return True if the provider opted into the direct-API dispatch path.

        Two conditions must hold:

        1. ``provider.name == "opnsense"`` — direct-API runner is OPNsense-specific.
        2. ``generate_opnsense_direct`` is callable on the provider.

        The first check guards against the ``deployment_executor.apply_single_provider``
        path, which iterates every IaC runner against every provider (unlike
        the orchestrator's plan path, which gates on ``generate_<tool_name>``
        presence). The second check is the explicit opt-in marker per
        ADR-0014 §4 dispatch.
        """
        if getattr(provider, "name", None) != "opnsense":
            return False
        return callable(getattr(provider, "generate_opnsense_direct", None))

    @staticmethod
    def _resolve_env_name(provider: ProviderBase) -> str:
        """Return the active environment name from the provider.

        The orchestrator calls ``provider.set_environment(env_name)`` before
        runner dispatch; the env name is then exposed on the protected
        ``_current_environment`` attribute. We accept that coupling rather
        than threading the env through every protocol method.

        Raises:
            RuntimeError: If the provider has no active environment.
        """
        env_name = getattr(provider, "_current_environment", None)
        if not env_name:
            raise RuntimeError(
                "OPNsenseDirectRunner requires provider.set_environment(env_name) "
                "to be called before plan/apply/destroy."
            )
        return str(env_name)

    @staticmethod
    def _filter_by_type(
        resources: list[ResourceConfig],
        type_name: str,
        target_resources: list[str] | None,
    ) -> list[ResourceConfig]:
        """Pick out resources of a given type, optionally filtering by name.

        Args:
            resources: All provider resources for the current environment.
            type_name: ``ResourceConfig.type`` to keep (e.g., ``"vlans"``).
            target_resources: Optional name filter (CLI ``--resource``).

        Returns:
            Matching ResourceConfig entries the runner should act on.
        """
        filtered = [r for r in resources if r.type == type_name]
        if target_resources:
            target_set = set(target_resources)
            filtered = [r for r in filtered if r.name in target_set]
        return filtered

    @staticmethod
    def _filter_vlans(
        resources: list[ResourceConfig],
        target_resources: list[str] | None,
    ) -> list[ResourceConfig]:
        """Pick out the VLAN resources, optionally filtering by name.

        Thin compatibility wrapper around ``_filter_by_type`` retained
        because existing callers and tests reach for the VLAN-specific
        helper directly.

        Args:
            resources: All provider resources for the current environment.
            target_resources: Optional name filter (CLI ``--resource``).

        Returns:
            VLAN ResourceConfig entries the runner should act on.
        """
        return OPNsenseDirectRunner._filter_by_type(resources, "vlans", target_resources)

    @staticmethod
    def _resolve_dispatch_table(provider: ProviderBase) -> dict[str, type[Any]]:
        """Return the provider's direct-API dispatch table or an empty dict.

        Centralizes the ``getattr`` + callable check so each method body
        stays readable. If the provider doesn't expose
        ``get_direct_api_resource_types``, the runner treats it as having
        no direct-API components — a safe default.
        """
        getter = getattr(provider, "get_direct_api_resource_types", None)
        if not callable(getter):
            return {}
        table = getter()
        if not isinstance(table, dict):
            return {}
        return table

    @staticmethod
    def _load_provider_resources(provider: ProviderBase) -> list[ResourceConfig]:
        """Read the provider's resources for the active environment.

        The runner needs the resource list at plan/apply time; the
        orchestrator does not pass it to runner methods directly. Mirroring
        the resource load path in ``orchestrator_workflows.py``, we go
        through ``ConfigManager`` to retrieve the resolved resource list for
        this provider.

        Returns an empty list rather than raising if the provider's
        ``config_dir`` isn't a real path (defensive against unit tests that
        substitute ``Mock()`` providers).
        """
        from pathlib import Path

        from infrafoundry.core.config import ConfigManager

        env_name = OPNsenseDirectRunner._resolve_env_name(provider)
        config_dir = getattr(provider, "config_dir", None)
        if not isinstance(config_dir, Path):
            logger.debug("OPNsenseDirectRunner: provider.config_dir is not a Path; skipping load")
            return []
        config_manager = ConfigManager(config_dir)
        env_config = config_manager.load_environment(env_name)
        if not env_config:
            return []

        # ConfigManager.get_all_resources merges provider-centric and
        # resource-centric YAML for this provider.
        return config_manager.get_all_resources(env_name, provider.name)

    # ------------------------------------------------------------------
    # Plannable / Applyable / Destroyable / StateAware
    # ------------------------------------------------------------------

    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Compute a diff between desired YAML state and live OPNsense state.

        Iterates ``provider.get_direct_api_resource_types()`` and dispatches
        each registered component manager's ``plan``. Aggregates per-type
        results into a single ``PlanResult``: ``has_changes`` is True if any
        component reports changes; ``changes_summary`` concatenates each
        component's summary line.

        Args:
            provider: OPNsense provider instance (env must be set).
            **kwargs: Runner options:
                - target_resources: Optional list of resource names to scope to.
                - add_only: If True, suppress deletes (ADR-0014 §5).

        Returns:
            PlanResult with a human-readable changes summary.
        """
        if not self._supports_direct_api(provider):
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")

        dispatch_table = self._resolve_dispatch_table(provider)
        if not dispatch_table:
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")

        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")
        add_only = bool(kwargs.get("add_only", False))

        resources = self._load_provider_resources(provider)

        any_changes = False
        summary_parts: list[str] = []

        for type_name, manager_cls in dispatch_table.items():
            typed_resources = self._filter_by_type(resources, type_name, target_resources)
            if not typed_resources:
                continue

            manager = manager_cls(provider.config_dir)
            try:
                diff = manager.plan(env_name, typed_resources, add_only=add_only)
            except Exception as exc:
                logger.exception("opnsense_direct %s plan failed", type_name)
                return PlanResult(success=False, error=str(exc))

            type_summary = self._format_plan_summary(type_name, diff, add_only=add_only)
            summary_parts.append(type_summary)
            self.console.print(f"  [dim]opnsense_direct: {type_summary}[/dim]")

            if not diff.is_empty:
                any_changes = True

        if not summary_parts:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to plan[/dim]")
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")

        return PlanResult(
            success=True,
            has_changes=any_changes,
            changes_summary=" | ".join(summary_parts),
        )

    @staticmethod
    def _format_plan_summary(type_name: str, diff: Any, *, add_only: bool) -> str:
        """Render a one-line plan summary for a single component's diff.

        Args:
            type_name: Resource type name (e.g., ``"vlans"``).
            diff: A ``Diff``-like object exposing ``adds``/``updates``/
                ``deletes``/``locked`` lists. Read-only components may
                supply additional attributes (e.g., ``read_only``,
                ``message``) which are surfaced verbatim when present.
            add_only: Whether the runner is in add-only mode.

        Returns:
            Human-readable summary line; downstream code joins these with
            " | " for the aggregate ``PlanResult``.
        """
        if getattr(diff, "read_only", False):
            note = getattr(diff, "message", "read-only")
            return f"{type_name}: {note}"
        summary = (
            f"{type_name}: {len(diff.adds)} to add, {len(diff.updates)} to update, "
            f"{len(diff.deletes)} to delete, {len(diff.locked)} locked."
        )
        if add_only:
            summary += " (add-only mode)"
        return summary

    def apply(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> ApplyResult:
        """Apply direct-API changes for managed components.

        Iterates ``provider.get_direct_api_resource_types()`` and dispatches
        each registered component manager's ``apply``. Aggregates counts
        and ``resource_outcomes`` across types into a single ``ApplyResult``.

        Args:
            provider: OPNsense provider instance (env must be set).
            auto_approve: Always treated as True (the diff engine is the gate).
            **kwargs: Runner options:
                - target_resources: Optional list of resource names.
                - add_only: If True, suppress deletes.

        Returns:
            ApplyResult with resource counts and a ``resource_outcomes`` list
            for downstream lifecycle event firing.
        """
        if not self._supports_direct_api(provider):
            return self._empty_apply_result()

        dispatch_table = self._resolve_dispatch_table(provider)
        if not dispatch_table:
            return self._empty_apply_result()

        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")
        add_only = bool(kwargs.get("add_only", False))

        resources = self._load_provider_resources(provider)

        total_created = 0
        total_updated = 0
        total_deleted = 0
        all_outcomes: list[ResourceOutcome] = []
        any_dispatched = False

        # Track finalization-hook keys whose managers actually mutated state in
        # this apply (#758). A hook fires once at end-of-apply per unique key,
        # so multiple managers sharing a key share a single hook firing.
        triggered_hook_keys: set[str] = set()

        for type_name, manager_cls in dispatch_table.items():
            typed_resources = self._filter_by_type(resources, type_name, target_resources)
            if not typed_resources:
                continue
            any_dispatched = True

            manager = manager_cls(provider.config_dir)
            try:
                result = manager.apply(
                    env_name, typed_resources, auto_approve=auto_approve, add_only=add_only
                )
            except Exception as exc:
                logger.exception("opnsense_direct %s apply failed", type_name)
                return ApplyResult(success=False, error=str(exc))

            created = int(result.get("resources_created", 0))
            updated = int(result.get("resources_updated", 0))
            deleted = int(result.get("resources_deleted", 0))
            total_created += created
            total_updated += updated
            total_deleted += deleted
            all_outcomes.extend(result.get("resource_outcomes", []))

            had_changes = (created + updated + deleted) > 0
            if had_changes:
                hook_key = getattr(manager_cls, "FINALIZATION_HOOK", None)
                if isinstance(hook_key, str) and hook_key:
                    triggered_hook_keys.add(hook_key)

            self._log_apply_progress(type_name, result, created, updated, deleted)

        if not any_dispatched:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to apply[/dim]")
            return self._empty_apply_result()

        # Fire finalization hooks once each (#758). Errors propagate — a failing
        # post-apply hook (e.g., Kea reconfigure) must fail the apply.
        if triggered_hook_keys:
            self._fire_finalization_hooks(provider, env_name, triggered_hook_keys)

        applied: ApplyResult = {
            "success": True,
            "resources_created": total_created,
            "resources_updated": total_updated,
            "resources_deleted": total_deleted,
        }
        applied["resource_outcomes"] = all_outcomes  # type: ignore[typeddict-unknown-key]
        applied["resource_outcomes_summary"] = [  # type: ignore[typeddict-unknown-key]
            o.to_dict() for o in all_outcomes
        ]
        return applied

    def _fire_finalization_hooks(
        self,
        provider: ProviderBase,
        env_name: str,
        hook_keys: set[str],
    ) -> None:
        """Run end-of-apply finalization hooks the provider exposes (#758).

        The runner discovers hook keys from each manager class's optional
        ``FINALIZATION_HOOK`` ClassVar during the apply loop and dispatches
        them here exactly once per unique key. Each provider that needs
        post-apply work (e.g., Kea reconfigure for DHCPv6 changes) exposes
        a ``get_finalization_hooks()`` method returning
        ``{key: callable(env_name)}``; providers that don't implement it
        produce a graceful no-op.

        This is a generic facility, not kea-specific: any future component
        whose apply needs deferred end-of-apply work can register a key
        and a hook callable. See ADR-0014 §"Finalization hooks".

        Args:
            provider: Provider whose components were dispatched.
            env_name: Active environment name; passed verbatim to each hook.
            hook_keys: Hook keys triggered by managers that mutated state.

        Raises:
            Any exception the hook itself raises — propagated so a failing
            hook (e.g., reconfigure) fails the apply.
        """
        getter = getattr(provider, "get_finalization_hooks", None)
        if not callable(getter):
            logger.debug(
                "opnsense_direct: provider %r does not expose get_finalization_hooks; "
                "skipping %d triggered hook(s)",
                getattr(provider, "name", provider),
                len(hook_keys),
            )
            return

        hooks = getter()
        if not isinstance(hooks, dict):
            logger.debug(
                "opnsense_direct: provider.get_finalization_hooks() did not return a dict; "
                "skipping %d triggered hook(s)",
                len(hook_keys),
            )
            return

        for key in sorted(hook_keys):
            hook = hooks.get(key)
            if hook is None:
                logger.debug(
                    "opnsense_direct: no finalization hook registered for key %r; skipping", key
                )
                continue
            self.console.print(f"  [dim]opnsense_direct: running finalization hook {key}[/dim]")
            hook(env_name)

    @staticmethod
    def _empty_apply_result() -> ApplyResult:
        """Build an ``ApplyResult`` with zero counts and an empty outcomes list."""
        empty: ApplyResult = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
        }
        empty["resource_outcomes"] = []  # type: ignore[typeddict-unknown-key]
        return empty

    def _log_apply_progress(
        self,
        type_name: str,
        result: dict[str, Any],
        created: int,
        updated: int,
        deleted: int,
    ) -> None:
        """Log per-type apply progress, surfacing read-only informational messages.

        Read-only components (e.g., ``interface_assignments``) include a
        ``message`` key in their result so the no-op is loud, not silent.
        """
        message = result.get("message")
        if message:
            self.console.print(f"  [dim]opnsense_direct: {type_name}: {message}[/dim]")
            return
        self.console.print(
            f"  [dim]opnsense_direct: {type_name}: applied "
            f"{created} adds, {updated} updates, {deleted} deletes[/dim]"
        )

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Delete direct-API resources for managed components.

        Iterates ``provider.get_direct_api_resource_types()`` and dispatches
        each registered component manager's ``destroy``. Aggregates counts
        across types.

        Args:
            provider: OPNsense provider instance (env must be set).
            auto_approve: Always treated as True.
            **kwargs: Runner options:
                - target_resources: Optional list of resource names.

        Returns:
            DestroyResult with the count of resources removed.
        """
        if not self._supports_direct_api(provider):
            return DestroyResult(success=True, resources_destroyed=0)

        dispatch_table = self._resolve_dispatch_table(provider)
        if not dispatch_table:
            return DestroyResult(success=True, resources_destroyed=0)

        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")

        resources = self._load_provider_resources(provider)

        total_destroyed = 0
        any_dispatched = False

        for type_name, manager_cls in dispatch_table.items():
            typed_resources = self._filter_by_type(resources, type_name, target_resources)
            if not typed_resources:
                continue
            any_dispatched = True

            manager = manager_cls(provider.config_dir)
            try:
                result = manager.destroy(env_name, typed_resources, auto_approve=auto_approve)
            except Exception as exc:
                logger.exception("opnsense_direct %s destroy failed", type_name)
                return DestroyResult(success=False, error=str(exc))

            destroyed = int(result.get("resources_destroyed", 0))
            total_destroyed += destroyed

            message = result.get("message")
            if message:
                self.console.print(f"  [dim]opnsense_direct: {type_name}: {message}[/dim]")
            else:
                self.console.print(
                    f"  [dim]opnsense_direct: {type_name}: destroyed {destroyed} resources[/dim]"
                )

        if not any_dispatched:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to destroy[/dim]")
            return DestroyResult(success=True, resources_destroyed=0)

        return DestroyResult(success=True, resources_destroyed=total_destroyed)

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Return ``{resource_name: opnsense_uuid}`` for live direct-API resources.

        Iterates ``provider.get_direct_api_resource_types()`` and merges
        each component's ``get_resource_ids`` mapping. Used by
        ``DeploymentExecutor`` (``deployment_executor.py:531-540``) to
        persist UUIDs after a successful apply via ``StateManager``.

        Args:
            provider: OPNsense provider instance (env must be set).

        Returns:
            Mapping from resource name to OPNsense UUID. Returns an empty
            dict on failure rather than raising — the runner should not
            block the apply pipeline if state lookup fails.
        """
        if not self._supports_direct_api(provider):
            return {}

        dispatch_table = self._resolve_dispatch_table(provider)
        if not dispatch_table:
            return {}

        env_name = self._resolve_env_name(provider)
        resources = self._load_provider_resources(provider)

        merged: dict[str, str] = {}
        for type_name, manager_cls in dispatch_table.items():
            typed_resources = self._filter_by_type(resources, type_name, target_resources=None)
            if not typed_resources:
                continue

            manager = manager_cls(provider.config_dir)
            try:
                ids = manager.get_resource_ids(env_name, typed_resources)
            except Exception as exc:
                logger.warning("opnsense_direct %s get_resource_ids failed: %s", type_name, exc)
                continue
            if isinstance(ids, dict):
                merged.update(ids)

        return merged
