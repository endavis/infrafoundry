"""Direct-API runner for OPNsense components (ADR-0014).

This runner replaces the terraform/browningluke pipeline for components that
have migrated to the ``opnsense_openapi`` direct-API path. It implements the
ADR-0010 runner protocols (``Plannable``, ``Applyable``, ``Destroyable``,
``StateAware``) by delegating to component managers under
``infrafoundry.providers.opnsense.components``.

The runner deliberately runs at ``priority = -10`` so that direct-API resources
(e.g., VLANs) are applied before any terraform-managed dependents
(``firewall_rules``, ``dhcp_static_maps``) within the same provider. See
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

    The runner is hardcoded for the components currently migrated to
    direct-API (VLANs as of #709). When additional components migrate, extend
    ``_dispatch_*`` methods to instantiate the relevant component manager.

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
        before terraform plans dependents like firewall_rules and
        dhcp_static_maps.
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
    def _filter_vlans(
        resources: list[ResourceConfig],
        target_resources: list[str] | None,
    ) -> list[ResourceConfig]:
        """Pick out the VLAN resources, optionally filtering by name.

        Args:
            resources: All provider resources for the current environment.
            target_resources: Optional name filter (CLI ``--resource``).

        Returns:
            VLAN ResourceConfig entries the runner should act on.
        """
        vlans = [r for r in resources if r.type == "vlans"]
        if target_resources:
            target_set = set(target_resources)
            vlans = [v for v in vlans if v.name in target_set]
        return vlans

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
        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")
        add_only = bool(kwargs.get("add_only", False))

        resources = self._load_provider_resources(provider)
        vlans = self._filter_vlans(resources, target_resources)

        if not vlans:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to plan[/dim]")
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")

        from infrafoundry.providers.opnsense.components.vlan import VlanManager

        manager = VlanManager(provider.config_dir)
        try:
            diff = manager.plan(env_name, vlans, add_only=add_only)
        except Exception as exc:
            logger.exception("opnsense_direct VLAN plan failed")
            return PlanResult(success=False, error=str(exc))

        summary = (
            f"Plan: {len(diff.adds)} to add, {len(diff.updates)} to update, "
            f"{len(diff.deletes)} to delete, {len(diff.locked)} locked."
        )
        if add_only:
            summary += " (add-only mode)"
        self.console.print(f"  [dim]opnsense_direct: {summary}[/dim]")

        return PlanResult(
            success=True,
            has_changes=not diff.is_empty,
            changes_summary=summary,
        )

    def apply(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> ApplyResult:
        """Apply direct-API changes for managed components.

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
            empty_other: ApplyResult = {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
            }
            empty_other["resource_outcomes"] = []  # type: ignore[typeddict-unknown-key]
            return empty_other
        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")
        add_only = bool(kwargs.get("add_only", False))

        resources = self._load_provider_resources(provider)
        vlans = self._filter_vlans(resources, target_resources)

        if not vlans:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to apply[/dim]")
            empty: ApplyResult = {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
            }
            empty["resource_outcomes"] = []  # type: ignore[typeddict-unknown-key]
            return empty

        from infrafoundry.providers.opnsense.components.vlan import VlanManager

        manager = VlanManager(provider.config_dir)
        try:
            result = manager.apply(env_name, vlans, auto_approve=auto_approve, add_only=add_only)
        except Exception as exc:
            logger.exception("opnsense_direct VLAN apply failed")
            return ApplyResult(success=False, error=str(exc))

        outcomes: list[ResourceOutcome] = result.get("resource_outcomes", [])
        self.console.print(
            f"  [dim]opnsense_direct: applied "
            f"{result.get('resources_created', 0)} adds, "
            f"{result.get('resources_updated', 0)} updates, "
            f"{result.get('resources_deleted', 0)} deletes[/dim]"
        )

        applied: ApplyResult = {
            "success": True,
            "resources_created": result.get("resources_created", 0),
            "resources_updated": result.get("resources_updated", 0),
            "resources_deleted": result.get("resources_deleted", 0),
        }
        applied["resource_outcomes"] = outcomes  # type: ignore[typeddict-unknown-key]
        applied["resource_outcomes_summary"] = [  # type: ignore[typeddict-unknown-key]
            o.to_dict() for o in outcomes
        ]
        return applied

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Delete direct-API resources for managed components.

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
        env_name = self._resolve_env_name(provider)
        target_resources = kwargs.get("target_resources")

        resources = self._load_provider_resources(provider)
        vlans = self._filter_vlans(resources, target_resources)

        if not vlans:
            self.console.print("  [dim]opnsense_direct: no direct-API resources to destroy[/dim]")
            return DestroyResult(success=True, resources_destroyed=0)

        from infrafoundry.providers.opnsense.components.vlan import VlanManager

        manager = VlanManager(provider.config_dir)
        try:
            result = manager.destroy(env_name, vlans, auto_approve=auto_approve)
        except Exception as exc:
            logger.exception("opnsense_direct VLAN destroy failed")
            return DestroyResult(success=False, error=str(exc))

        self.console.print(
            f"  [dim]opnsense_direct: destroyed "
            f"{result.get('resources_destroyed', 0)} resources[/dim]"
        )
        return DestroyResult(
            success=True,
            resources_destroyed=int(result.get("resources_destroyed", 0)),
        )

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Return ``{resource_name: opnsense_uuid}`` for live direct-API resources.

        Used by ``DeploymentExecutor`` (``deployment_executor.py:531-540``)
        to persist UUIDs after a successful apply via ``StateManager``.

        Args:
            provider: OPNsense provider instance (env must be set).

        Returns:
            Mapping from resource name to OPNsense UUID. Returns an empty
            dict on failure rather than raising — the runner should not
            block the apply pipeline if state lookup fails.
        """
        if not self._supports_direct_api(provider):
            return {}
        env_name = self._resolve_env_name(provider)
        resources = self._load_provider_resources(provider)
        vlans = self._filter_vlans(resources, target_resources=None)
        if not vlans:
            return {}

        from infrafoundry.providers.opnsense.components.vlan import VlanManager

        manager = VlanManager(provider.config_dir)
        try:
            return manager.get_resource_ids(env_name, vlans)
        except Exception as exc:
            logger.warning("opnsense_direct get_resource_ids failed: %s", exc)
            return {}
