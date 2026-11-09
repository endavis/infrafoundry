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

The runner runs at ``priority = -10`` so that direct-API resources
(e.g., VLANs) are applied before any terraform-managed dependents within
the same provider. After #782, OPNsense itself has no terraform-managed
components left; the priority is retained for the cross-runner ordering
contract and for any future provider that introduces a terraform path
behind direct-API state.

Deletes are limited to the managed set (ADR-0018). The orchestrator and executor
read the objects InfraFoundry applied before from the state database and pass them
as ``managed_resources=``. A manager that declares ``DELETE_SCOPE`` deletes only
those, and a type whose last YAML entry was removed is still dispatched so its
managed objects go away. Live objects InfraFoundry never applied are left alone.
The orchestrator also dispatches the provider when the environment has no opnsense
YAML at all, if ``needs_managed_dispatch`` says managed objects remain (#1260).

A manager that declares ``SPLIT_DELETE_PHASE`` (every type that depends on another
table type: the kea managers, firewall rules, NAT, gateways, static routes and
virtual IPs, interface assignments) has its deletes run in a separate phase before any
adds, in reverse table order, so a child type such as reservations is deleted while its
parent subnet is still live (#1264, #1269). Interface assignments delete before their
VLAN (#1271). The forward pass then adds and updates only. ``destroy`` uses the same order.

Drift detection (``DriftDetectable``) is intentionally not implemented in this
PR; ``infra plan`` provides equivalent UX via the diff engine, and a full
``DriftDetectable`` implementation is tracked as a follow-up issue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, override

from rich.console import Console

from infrafoundry.core.managed_set import ManagedResources, ReleasedResource
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.types import ResourceOutcome

logger = logging.getLogger(__name__)


@dataclass
class _ApplyTotals:
    """Counts and outcomes accumulated across the manager calls of one apply."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    outcomes: list[ResourceOutcome] = field(default_factory=list)
    released: list[ReleasedResource] = field(default_factory=list)
    hook_keys: set[str] = field(default_factory=set)


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
        this runner at -10 keeps the cross-runner ordering contract stable.
        After #782, OPNsense has no terraform-managed components left, so
        the contract is currently inert for OPNsense — but future providers
        with mixed direct-API + terraform dispatch rely on the same priority.
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
            type_name: ``ResourceConfig.type`` to keep
                (e.g., ``"interfaces.vlans"``).
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
    def _sibling_resources_for(
        manager_cls: type[Any],
        all_resources: list[ResourceConfig],
    ) -> list[ResourceConfig] | None:
        """Return the sibling-resource slice for a manager that opts in (#802).

        Managers that need cross-resource context at dispatch time (e.g.,
        the kea reservation managers needing the matching kea subnets to
        resolve ``subnet_ref`` to a CIDR) declare a class-level
        ``SIBLING_RESOURCE_TYPE: ClassVar[str | tuple[str, ...] | None]`` whose
        value is the dotted resource type (or a tuple of them, #790) to slice
        from ``all_resources``.

        Managers that don't declare the attribute return ``None`` here —
        the dispatch loops check for ``None`` before threading the
        ``sibling_resources`` kwarg, so existing managers keep their
        unchanged signatures.

        Args:
            manager_cls: The manager class registered in the dispatch
                table.
            all_resources: All provider resources for the active
                environment.

        Returns:
            The sibling slice (possibly empty if the type isn't present
            in YAML) or ``None`` when the manager doesn't opt in.
        """
        sibling_types = OPNsenseDirectRunner._sibling_types(manager_cls)
        if not sibling_types:
            return None
        return [r for r in all_resources if r.type in sibling_types]

    @staticmethod
    def _sibling_types(manager_cls: type[Any]) -> tuple[str, ...]:
        """Return the sibling resource types a manager declares (#802, #790).

        ``SIBLING_RESOURCE_TYPE`` is a type name, or a tuple of type names for a
        manager that resolves references into several types (the ACME certificate
        manager reads accounts, validations and actions).

        Args:
            manager_cls: The manager class registered in the dispatch table.

        Returns:
            The declared types; empty when the attribute is absent, empty or of
            another type.
        """
        declared = getattr(manager_cls, "SIBLING_RESOURCE_TYPE", None)
        if isinstance(declared, str):
            return (declared,) if declared else ()
        if (
            isinstance(declared, tuple)
            and declared
            and all(isinstance(t, str) and t for t in declared)
        ):
            return tuple(declared)
        return ()

    @staticmethod
    def _splits_deletes(manager_cls: type[Any]) -> bool:
        """Return True if a manager's deletes run in their own reverse-order phase (#1264).

        Uses ``is True`` because a plain ``MagicMock`` class returns a truthy mock for
        any attribute.

        Args:
            manager_cls: The manager class registered in the dispatch table.
        """
        return bool(getattr(manager_cls, "SPLIT_DELETE_PHASE", None) is True)

    def _dependent_kwargs(
        self,
        manager_cls: type[Any],
        resources: list[ResourceConfig],
        managed: ManagedResources | None,
    ) -> dict[str, Any]:
        """Build the dependent-resource kwargs for a manager that declares one (#1264).

        A kea subnet manager predicts, at plan time, which subnet deletes would orphan a
        reservation. It declares ``DEPENDENT_RESOURCE_TYPE`` and receives that type's
        YAML slice as ``dependent_resources``, plus the managed rows as
        ``managed_dependent_resources`` when it has a managed-set delete scope.

        Args:
            manager_cls: The manager class.
            resources: All provider resources for the environment.
            managed: Managed resources by type, or ``None``.

        Returns:
            The kwargs, empty for a manager without the marker.
        """
        dependent_type = getattr(manager_cls, "DEPENDENT_RESOURCE_TYPE", None)
        if not isinstance(dependent_type, str) or not dependent_type:
            return {}
        kwargs: dict[str, Any] = {
            "dependent_resources": [r for r in resources if r.type == dependent_type]
        }
        if managed is not None and self._delete_scope(manager_cls) == "managed_set":
            kwargs["managed_dependent_resources"] = list(managed.get(dependent_type, []))
        return kwargs

    @staticmethod
    def _delete_scope(manager_cls: type[Any]) -> str | None:
        """Return how a manager limits its deletes, or ``None`` if it does not opt in (#1256).

        Managers declare a class-level ``DELETE_SCOPE: ClassVar[str]``:

        - ``"managed_set"``: deletes only live objects InfraFoundry applied
          before. The runner passes ``managed_resources=`` to the manager.
        - ``"marker"``: the engine already deletes only objects carrying
          InfraFoundry's marker, so no managed set is needed.

        Args:
            manager_cls: The manager class registered in the dispatch table.

        Returns:
            ``"managed_set"``, ``"marker"`` or ``None``.
        """
        scope = getattr(manager_cls, "DELETE_SCOPE", None)
        if scope in ("managed_set", "marker"):
            return str(scope)
        return None

    def needs_managed_dispatch(
        self, provider: ProviderBase, managed_resources: ManagedResources
    ) -> bool:
        """Return True if managed objects need deleting though no YAML remains (#1260).

        Args:
            provider: Provider with no resources in the environment's YAML.
            managed_resources: Managed resources by type.

        Returns:
            True if some type with a delete scope has managed rows.
        """
        if not self._supports_direct_api(provider):
            return False
        table = self._resolve_dispatch_table(provider)
        return bool(
            self._types_to_dispatch(table, [], None, add_only=False, managed=managed_resources)
        )

    def _types_to_dispatch(
        self,
        dispatch_table: dict[str, type[Any]],
        resources: list[ResourceConfig],
        target_resources: list[str] | None,
        *,
        add_only: bool,
        managed: ManagedResources | None,
    ) -> list[tuple[str, type[Any], list[ResourceConfig]]]:
        """Pick the types to dispatch, with the YAML resources each one gets.

        A type with YAML entries is always dispatched. A type without any is
        dispatched only to delete what InfraFoundry managed (#1256): the run
        has a managed set, is not add-only, and the manager has a delete scope
        and managed rows. Everything else is skipped, so unmanaged objects of
        an unreferenced type are never touched.

        Args:
            dispatch_table: Provider dispatch table.
            resources: All provider resources for the environment.
            target_resources: Optional name filter.
            add_only: Whether deletes are suppressed (filtered runs are add-only).
            managed: Managed resources by type, or ``None`` when the caller
                did not supply any (legacy behaviour).

        Returns:
            ``(type_name, manager_class, typed_resources)`` in table order.
        """
        selected: list[tuple[str, type[Any], list[ResourceConfig]]] = []
        for type_name, manager_cls in dispatch_table.items():
            typed = self._filter_by_type(resources, type_name, target_resources)
            if typed:
                selected.append((type_name, manager_cls, typed))
                continue
            if managed is None or add_only or self._delete_scope(manager_cls) is None:
                continue
            if managed.get(type_name):
                selected.append((type_name, manager_cls, []))
        return selected

    def _managed_kwargs(
        self,
        type_name: str,
        manager_cls: type[Any],
        managed: ManagedResources | None,
    ) -> dict[str, Any]:
        """Build the managed-set kwargs for a manager that opted in (#1256).

        Args:
            type_name: Resource type being dispatched.
            manager_cls: The manager class.
            managed: Managed resources by type, or ``None``.

        Returns:
            ``managed_resources`` (and ``managed_sibling_resources`` for a
            manager with a sibling type) for ``"managed_set"`` managers;
            otherwise an empty dict.
        """
        if managed is None or self._delete_scope(manager_cls) != "managed_set":
            return {}
        kwargs: dict[str, Any] = {"managed_resources": list(managed.get(type_name, []))}
        sibling_types = self._sibling_types(manager_cls)
        if sibling_types:
            kwargs["managed_sibling_resources"] = [
                row for sibling_type in sibling_types for row in managed.get(sibling_type, [])
            ]
        return kwargs

    @staticmethod
    def _released_for(
        type_name: str,
        manager_cls: type[Any],
        resources: list[ResourceConfig],
        managed: ManagedResources | None,
        unresolved: set[str] | None = None,
    ) -> list[ReleasedResource]:
        """List managed names of a type that left YAML (#1256).

        Called after a full-mode apply of the type succeeded, so the engine
        has deleted them (or found them already gone). Names in ``unresolved`` are
        managed rows whose key the manager could not derive (fail closed); they stay
        managed so the next run retries them and warns again.

        Args:
            type_name: Resource type just applied.
            manager_cls: The manager class.
            resources: All provider resources for the environment.
            managed: Managed resources by type, or ``None``.
            unresolved: Managed names the manager reported it could not resolve.

        Returns:
            One entry per managed name that is no longer in YAML and was resolved.
        """
        if managed is None or OPNsenseDirectRunner._delete_scope(manager_cls) is None:
            return []
        yaml_names = {r.name for r in resources if r.type == type_name}
        blocked = unresolved or set()
        seen: set[str] = set()
        released: list[ReleasedResource] = []
        for row in managed.get(type_name, []):
            if row.name in yaml_names or row.name in seen or row.name in blocked:
                continue
            seen.add(row.name)
            released.append({"resource_type": type_name, "name": row.name})
        return released

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
        return OPNsenseDirectRunner._filter_by_type(resources, "interfaces.vlans", target_resources)

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

        # Load the whole environment, as the orchestrator does, and keep this
        # provider's resources. get_all_resources(env, provider) reads only
        # envs/<env>/<provider>/ and resource-centric files, so it missed
        # opnsense resources declared in other providers' packages, such as a
        # proxmox blueprint's DHCP reservations (#1128).
        return [
            resource
            for resource in config_manager.get_all_resources_all_providers(env_name)
            if resource.provider == provider.name
        ]

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
                - managed_resources: Managed rows by type from the state
                  database (ADR-0018). Managers with a delete scope delete
                  only these; a type with no YAML entries is dispatched when
                  it has managed rows. ``None`` keeps the legacy behaviour.

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
        # A filtered run hands each manager only the targeted resources, and the
        # managers reconcile fully, so anything else live would be deleted.
        # Scope the run to the targets by suppressing deletes (#1128).
        add_only = bool(kwargs.get("add_only", False)) or bool(target_resources)

        resources = self._load_provider_resources(provider)
        managed: ManagedResources | None = kwargs.get("managed_resources")
        selected = self._types_to_dispatch(
            dispatch_table, resources, target_resources, add_only=add_only, managed=managed
        )

        # Reject resource types the box's OPNsense version cannot serve before
        # any manager touches the box (#1239). ``apply`` runs plan first. Types
        # dispatched only to delete managed objects are checked too (#1256).
        types_in_scope = [type_name for type_name, _, _ in selected]
        if types_in_scope:
            support_errors = self._check_endpoint_support(provider, env_name, types_in_scope)
            if support_errors:
                return PlanResult(success=False, error="\n".join(support_errors))

        any_changes = False
        summary_parts: list[str] = []

        for type_name, manager_cls, typed_resources in selected:
            manager = manager_cls(provider.config_dir)
            sibling_resources = self._sibling_resources_for(manager_cls, resources)
            extra_kwargs: dict[str, Any] = self._managed_kwargs(type_name, manager_cls, managed)
            if sibling_resources is not None:
                extra_kwargs["sibling_resources"] = sibling_resources
            extra_kwargs.update(self._dependent_kwargs(manager_cls, resources, managed))
            try:
                diff = manager.plan(env_name, typed_resources, add_only=add_only, **extra_kwargs)
            except Exception as exc:
                logger.exception("opnsense_direct %s plan failed", type_name)
                return PlanResult(success=False, error=str(exc))

            type_summary = self._format_plan_summary(type_name, diff, add_only=add_only)
            summary_parts.append(type_summary)
            self.console.print(f"  [dim]opnsense_direct: {type_summary}[/dim]")
            self._print_warnings(getattr(diff, "warnings", None))

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

    def _check_endpoint_support(
        self, provider: ProviderBase, env_name: str, resource_types: list[str]
    ) -> list[str]:
        """Ask the provider whether the box's version serves the types' endpoints (#1239).

        Reads the optional duck-typed ``check_endpoint_support`` hook; a provider
        without it, or a hook that does not return ``{"errors": [...], "warnings":
        [...]}``, is treated as having nothing to report.

        Args:
            provider: Provider being planned.
            env_name: Active environment name.
            resource_types: Resource types that have resources in scope.

        Returns:
            The error messages; warnings are printed.
        """
        hook = getattr(provider, "check_endpoint_support", None)
        if not callable(hook):
            return []
        result = hook(env_name, resource_types)
        if not isinstance(result, dict):
            return []
        errors = result.get("errors")
        warnings = result.get("warnings")
        if isinstance(warnings, list):
            for warning in warnings:
                self.console.print(f"  [yellow]opnsense_direct: {warning}[/yellow]")
        if isinstance(errors, list) and all(isinstance(e, str) for e in errors):
            return list(errors)
        return []

    @staticmethod
    def _format_plan_summary(type_name: str, diff: Any, *, add_only: bool) -> str:
        """Render a one-line plan summary for a single component's diff.

        Args:
            type_name: Resource type name (e.g., ``"interfaces.vlans"``).
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
        unmanaged = getattr(diff, "unmanaged", None)
        if isinstance(unmanaged, list) and unmanaged:
            summary = summary[:-1] + f", {len(unmanaged)} unmanaged (kept)."
        blocked = getattr(diff, "blocked", None)
        if isinstance(blocked, list) and blocked:
            summary = summary[:-1] + f", {len(blocked)} blocked (kept)."
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
                - managed_resources: Managed rows by type, as for ``plan``
                  (ADR-0018).

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
        # A filtered run hands each manager only the targeted resources, and the
        # managers reconcile fully, so anything else live would be deleted.
        # Scope the run to the targets by suppressing deletes (#1128).
        add_only = bool(kwargs.get("add_only", False)) or bool(target_resources)

        resources = self._load_provider_resources(provider)
        managed: ManagedResources | None = kwargs.get("managed_resources")
        selected = self._types_to_dispatch(
            dispatch_table, resources, target_resources, add_only=add_only, managed=managed
        )

        totals = _ApplyTotals()
        any_dispatched = bool(selected)

        # Deletes of types that split them run first, in reverse table order, so a
        # child (reservations) is deleted while its parent (subnets) is still live;
        # the forward pass below then only adds and updates them (#1264). Add-only and
        # filtered runs have no deletes and make one add-only call as before.
        two_phase = not add_only
        if two_phase:
            for type_name, manager_cls, typed_resources in reversed(selected):
                if not self._splits_deletes(manager_cls):
                    continue
                error = self._apply_one(
                    provider,
                    env_name,
                    auto_approve,
                    type_name,
                    manager_cls,
                    typed_resources,
                    resources,
                    managed,
                    totals,
                    add_only=False,
                    deletes_only=True,
                    release=True,
                )
                if error is not None:
                    return ApplyResult(success=False, error=error)

        for type_name, manager_cls, typed_resources in selected:
            splits = two_phase and self._splits_deletes(manager_cls)
            if splits and not typed_resources:
                continue  # only had managed rows to delete, done in the first phase
            error = self._apply_one(
                provider,
                env_name,
                auto_approve,
                type_name,
                manager_cls,
                typed_resources,
                resources,
                managed,
                totals,
                add_only=add_only or splits,
                deletes_only=False,
                release=not add_only and not splits,
            )
            if error is not None:
                return ApplyResult(success=False, error=error)

        if not any_dispatched:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to apply[/dim]")
            return self._empty_apply_result()

        # Fire finalization hooks once each (#758). Errors propagate — a failing
        # post-apply hook (e.g., Kea reconfigure) must fail the apply.
        if totals.hook_keys:
            self._fire_finalization_hooks(provider, env_name, totals.hook_keys)

        applied: ApplyResult = {
            "success": True,
            "resources_created": totals.created,
            "resources_updated": totals.updated,
            "resources_deleted": totals.deleted,
        }
        applied["resource_outcomes"] = totals.outcomes
        applied["resource_outcomes_summary"] = [o.to_dict() for o in totals.outcomes]
        if totals.released:
            applied["released_resources"] = totals.released
        return applied

    def _apply_one(
        self,
        provider: ProviderBase,
        env_name: str,
        auto_approve: bool,
        type_name: str,
        manager_cls: type[Any],
        typed_resources: list[ResourceConfig],
        resources: list[ResourceConfig],
        managed: ManagedResources | None,
        totals: _ApplyTotals,
        *,
        add_only: bool,
        deletes_only: bool,
        release: bool,
    ) -> str | None:
        """Run one manager's apply and fold its result into ``totals``.

        Args:
            provider: OPNsense provider instance.
            env_name: Active environment name.
            auto_approve: Passed through to the manager.
            type_name: Resource type being applied.
            manager_cls: The manager class.
            typed_resources: YAML resources of the type.
            resources: All provider resources for the environment.
            managed: Managed resources by type, or ``None``.
            totals: Accumulator updated in place.
            add_only: Passed to the manager (suppresses deletes).
            deletes_only: When True, passes ``deletes_only=True`` (the delete phase).
            release: Whether managed names that left YAML are released after this call.

        Returns:
            ``None`` on success, otherwise the error message of the failed call.
        """
        manager = manager_cls(provider.config_dir)
        sibling_resources = self._sibling_resources_for(manager_cls, resources)
        extra_kwargs: dict[str, Any] = self._managed_kwargs(type_name, manager_cls, managed)
        if sibling_resources is not None:
            extra_kwargs["sibling_resources"] = sibling_resources
        extra_kwargs.update(self._dependent_kwargs(manager_cls, resources, managed))
        if deletes_only:
            extra_kwargs["deletes_only"] = True
        try:
            result = manager.apply(
                env_name,
                typed_resources,
                auto_approve=auto_approve,
                add_only=add_only,
                **extra_kwargs,
            )
        except Exception as exc:
            logger.exception("opnsense_direct %s apply failed", type_name)
            return str(exc)

        created = int(result.get("resources_created", 0))
        updated = int(result.get("resources_updated", 0))
        deleted = int(result.get("resources_deleted", 0))
        totals.created += created
        totals.updated += updated
        totals.deleted += deleted
        totals.outcomes.extend(result.get("resource_outcomes", []))
        if release:
            reported = result.get("unresolved_managed")
            unresolved = (
                {str(n) for n in reported} if isinstance(reported, (list, set, tuple)) else set()
            )
            totals.released.extend(
                self._released_for(type_name, manager_cls, resources, managed, unresolved)
            )

        if (created + updated + deleted) > 0:
            hook_key = getattr(manager_cls, "FINALIZATION_HOOK", None)
            if isinstance(hook_key, str) and hook_key:
                totals.hook_keys.add(hook_key)

        self._log_apply_progress(type_name, result, created, updated, deleted)
        self._print_warnings(result.get("warnings"))
        return None

    def _print_warnings(self, warnings: Any) -> None:
        """Print a manager's warnings in yellow; ignore anything but a list of strings."""
        if not isinstance(warnings, list):
            return
        for warning in warnings:
            if isinstance(warning, str):
                self.console.print(f"  [yellow]opnsense_direct: {warning}[/yellow]")

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
        empty["resource_outcomes"] = []
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

        # Types that split deletes go first in reverse table order, so a subnet's
        # reservations are gone before the subnet is (#1264); the rest keep table order.
        ordered = [(t, c) for t, c in reversed(dispatch_table.items()) if self._splits_deletes(c)]
        ordered += [(t, c) for t, c in dispatch_table.items() if not self._splits_deletes(c)]

        for type_name, manager_cls in ordered:
            typed_resources = self._filter_by_type(resources, type_name, target_resources)
            if not typed_resources:
                continue
            any_dispatched = True

            manager = manager_cls(provider.config_dir)
            sibling_resources = self._sibling_resources_for(manager_cls, resources)
            extra_kwargs: dict[str, Any] = {}
            if sibling_resources is not None:
                extra_kwargs["sibling_resources"] = sibling_resources
            try:
                result = manager.destroy(
                    env_name, typed_resources, auto_approve=auto_approve, **extra_kwargs
                )
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
            self._print_warnings(result.get("warnings"))

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
            sibling_resources = self._sibling_resources_for(manager_cls, resources)
            extra_kwargs: dict[str, Any] = {}
            if sibling_resources is not None:
                extra_kwargs["sibling_resources"] = sibling_resources
            try:
                ids = manager.get_resource_ids(env_name, typed_resources, **extra_kwargs)
            except Exception as exc:
                logger.warning("opnsense_direct %s get_resource_ids failed: %s", type_name, exc)
                continue
            if isinstance(ids, dict):
                merged.update(ids)

        return merged
