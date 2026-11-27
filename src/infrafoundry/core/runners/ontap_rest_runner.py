"""Runner for NetApp ONTAP clusters over the REST API (ADR-0026, ADR-0042).

``OntapRestRunner`` acts only for ``provider.name == "ontap"``. ``plan`` reads the cluster,
diffs the declared data LIFs against it and refuses a plan that could cut the management
connection. ``apply`` runs the planned writes in order and stops at the first error;
``destroy`` deletes the declared LIFs that exist on the cluster.

Core never imports the provider package: the runner talks to it through the
structural ``_OntapProvider`` protocol.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast, override

from rich.console import Console
from rich.markup import escape

from infrafoundry.core.managed_set import ManagedResources, ReleasedResource
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, DriftInfo, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)


class _Plan(Protocol):
    """What the runner reads from a provider plan."""

    refusals: list[str]
    warnings: list[str]

    @property
    def has_changes(self) -> bool:
        """True when any type has a change."""
        ...

    @property
    def counts(self) -> dict[str, int]:
        """Creates, updates and deletes."""
        ...

    @property
    def unmanaged(self) -> dict[str, list[str]]:
        """Undeclared live objects kept, per type."""
        ...

    def summary_lines(self) -> list[str]:
        """Human-readable summary lines."""
        ...


class _ApplyOutcome(Protocol):
    """What the runner reads from a provider apply or destroy result."""

    refusals: list[str]
    warnings: list[str]
    error: str | None
    outcomes: list[Any]
    counts: dict[str, int]
    released: list[ReleasedResource]
    completed: list[Any]

    @property
    def success(self) -> bool:
        """True when nothing was refused and every step ran."""
        ...


class _OntapProvider(Protocol):
    """What the runner needs from the ontap provider."""

    def rest_plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> _Plan:
        """Plan the cluster's changes."""
        ...

    def rest_apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> _ApplyOutcome:
        """Plan and apply the cluster's changes."""
        ...

    def rest_destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> _ApplyOutcome:
        """Delete the declared objects that exist on the cluster."""
        ...

    def rest_resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Map resource names to the cluster's interface uuids."""
        ...

    def deletable_types(self) -> set[str]:
        """Resource types the provider can delete."""
        ...


class OntapRestRunner(BaseRunner):
    """Plans changes to a ONTAP cluster through its REST API."""

    _tool_name = "ontap_rest"
    """Registry key (the registry would otherwise derive ``ontaprest`` from the class name)."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the registry key; ``generate_ontap_rest`` is the dispatch hook."""
        return "ontap_rest"

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The runner provisions the cluster, so it auto-runs on plan/apply."""
        return True

    @property
    @override
    def priority(self) -> int:
        """Run before Terraform, like the other direct-API runners."""
        return -10

    @override
    def is_available(self) -> bool:
        """Always available: a missing pynetappfoundry fails at plan time with an install hint."""
        return True

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization."""
        return {"success": True, "output": "no init required"}

    @staticmethod
    def _supports(provider: ProviderBase) -> bool:
        """Return True for the ontap provider only (every IaC runner sees every provider)."""
        return getattr(provider, "name", None) == "ontap" and callable(
            getattr(provider, "generate_ontap_rest", None)
        )

    @staticmethod
    def _env_name(provider: ProviderBase, kwargs: dict[str, Any]) -> str:
        """Return the active environment name.

        Raises:
            RuntimeError: If neither the run nor the provider names an environment.
        """
        env_name = kwargs.get("env_name") or getattr(provider, "_current_environment", None)
        if not env_name:
            raise RuntimeError(
                "OntapRestRunner requires provider.set_environment(env_name) "
                "to be called before plan."
            )
        return str(env_name)

    @staticmethod
    def _load_resources(provider: ProviderBase, env_name: str) -> list[ResourceConfig]:
        """Read this provider's resources for the environment."""
        from infrafoundry.core.config import ConfigManager

        config_dir = getattr(provider, "config_dir", None)
        if not isinstance(config_dir, Path):
            return []
        manager = ConfigManager(config_dir)
        if not manager.load_environment(env_name):
            return []
        return [
            r
            for r in manager.get_all_resources_all_providers(env_name)
            if r.provider == provider.name
        ]

    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Diff the YAML against the cluster; writes nothing.

        Args:
            provider: The ontap provider.
            **kwargs: ``add_only`` suppresses deletes (drift runs); ``target_resources``
                restricts the run and implies add-only; ``managed_resources`` holds the
                managed rows by type (ADR-0018); ``env_name`` overrides the provider's
                current environment.
        """
        if not self._supports(provider):
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")
        env_name = self._env_name(provider, kwargs)
        resources = self._load_resources(provider, env_name)
        try:
            plan = cast(_OntapProvider, provider).rest_plan(
                env_name,
                resources,
                add_only=bool(kwargs.get("add_only", False)),
                managed_resources=kwargs.get("managed_resources"),
                target_resources=kwargs.get("target_resources"),
            )
        except Exception as exc:
            logger.exception("ontap_rest plan failed")
            return PlanResult(success=False, error=str(exc))

        if plan.refusals:
            return PlanResult(
                success=False,
                error="ontap plan refused, it could cut the management connection:\n"
                + "\n".join(f"- {r}" for r in plan.refusals),
            )
        lines = plan.summary_lines()
        for line in lines:
            self.console.print(f"  [dim]ontap_rest: {escape(line)}[/dim]")
        for warning in plan.warnings:
            self.console.print(f"  [yellow]ontap_rest: {escape(warning)}[/yellow]")
        for type_name, names in plan.unmanaged.items():
            self.console.print(
                f"  [dim]ontap_rest: {type_name}: unmanaged (kept): "
                f"{escape(', '.join(names))}[/dim]"
            )
        return PlanResult(
            success=True,
            has_changes=plan.has_changes,
            changes_summary=" | ".join(lines) if plan.has_changes else "No changes",
            output=json.dumps(plan.counts),
        )

    def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo:
        """Count the changes of a plan run add-only, from its structured output.

        Args:
            plan_result: Result of :meth:`plan`.
        """
        if not plan_result.get("success", False):
            return DriftInfo(
                has_changes=False,
                summary=plan_result.get("error", "plan failed"),
                to_add=0,
                to_change=0,
                to_destroy=0,
            )
        try:
            counts = json.loads(plan_result.get("output", "{}") or "{}")
        except ValueError:
            counts = {}
        add, change, destroy = (int(counts.get(k, 0)) for k in ("create", "update", "delete"))
        return DriftInfo(
            has_changes=bool(add or change or destroy),
            summary=plan_result.get("changes_summary", "No changes"),
            to_add=add,
            to_change=change,
            to_destroy=destroy,
        )

    def apply(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> ApplyResult:
        """Plan against the cluster, then write the planned changes in order.

        Stops at the first error. A plan that could cut the management connection is
        refused before any write.

        Args:
            provider: The ontap provider.
            auto_approve: Ignored; the run is always approved.
            **kwargs: ``add_only`` suppresses deletes; ``target_resources`` restricts the
                run and implies add-only; ``managed_resources`` holds the managed rows by
                type (ADR-0018); ``env_name`` overrides the provider's current environment.
        """
        if not self._supports(provider):
            return ApplyResult(success=True, resources_created=0, resources_updated=0)
        target_resources = kwargs.get("target_resources")
        try:
            env_name = self._env_name(provider, kwargs)
            resources = self._load_resources(provider, env_name)
            outcome = cast(_OntapProvider, provider).rest_apply(
                env_name,
                resources,
                add_only=bool(kwargs.get("add_only", False)) or bool(target_resources),
                managed_resources=kwargs.get("managed_resources"),
                target_resources=target_resources,
            )
        except Exception as exc:
            logger.exception("ontap_rest apply failed")
            return ApplyResult(success=False, error=str(exc))

        for warning in outcome.warnings:
            self.console.print(f"  [yellow]ontap_rest: {escape(warning)}[/yellow]")
        if outcome.refusals:
            return ApplyResult(
                success=False,
                error="ontap apply refused, it could cut the management connection:\n"
                + "\n".join(f"- {r}" for r in outcome.refusals),
            )
        result = ApplyResult(
            success=outcome.success,
            resources_created=outcome.counts.get("create", 0),
            resources_updated=outcome.counts.get("update", 0),
            resources_deleted=outcome.counts.get("delete", 0),
        )
        result["resource_outcomes"] = outcome.outcomes
        result["resource_outcomes_summary"] = [o.to_dict() for o in outcome.outcomes]
        if not outcome.success:
            result["error"] = outcome.error or "ontap apply failed"
            return result
        self.console.print(f"  [dim]ontap_rest: applied {len(outcome.completed)} step(s)[/dim]")
        if outcome.released:
            result["released_resources"] = outcome.released
        return result

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Delete the declared objects that exist on the cluster.

        Never touches ``absent: true`` entries or undeclared LIFs. A destroy that would
        remove the management LIF is refused before any write.

        Args:
            provider: The ontap provider.
            auto_approve: Ignored; the run is always approved.
            **kwargs: ``target_resources`` restricts the run; ``env_name`` overrides the
                provider's current environment.
        """
        if not self._supports(provider):
            return DestroyResult(success=True, resources_destroyed=0)
        try:
            env_name = self._env_name(provider, kwargs)
            resources = self._load_resources(provider, env_name)
            outcome = cast(_OntapProvider, provider).rest_destroy(
                env_name, resources, target_resources=kwargs.get("target_resources")
            )
        except Exception as exc:
            logger.exception("ontap_rest destroy failed")
            return DestroyResult(success=False, error=str(exc))

        if outcome.refusals:
            return DestroyResult(
                success=False,
                error="ontap destroy refused, it would remove the management connection:\n"
                + "\n".join(f"- {r}" for r in outcome.refusals),
            )
        result = DestroyResult(
            success=outcome.success, resources_destroyed=outcome.counts.get("delete", 0)
        )
        result["resource_outcomes"] = outcome.outcomes
        result["resource_outcomes_summary"] = [o.to_dict() for o in outcome.outcomes]
        if not outcome.success:
            result["error"] = outcome.error or "ontap destroy failed"
        return result

    def needs_managed_dispatch(
        self, provider: ProviderBase, managed_resources: ManagedResources
    ) -> bool:
        """Return True if managed objects need deleting though no YAML remains (#1260).

        Args:
            provider: Provider with no resources in the environment's YAML.
            managed_resources: Managed resources by type.

        Returns:
            True for the ontap provider when a deletable type has managed rows.
        """
        if not self._supports(provider):
            return False
        deletable = cast(_OntapProvider, provider).deletable_types()
        return any(rows for type_name, rows in managed_resources.items() if type_name in deletable)

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for the declared objects that exist live.

        Args:
            provider: The ontap provider (its environment must be set).

        Returns:
            The mapping, or an empty one on any failure so the apply pipeline goes on.
        """
        if not self._supports(provider):
            return {}
        try:
            env_name = self._env_name(provider, {})
            resources = self._load_resources(provider, env_name)
            return cast(_OntapProvider, provider).rest_resource_ids(env_name, resources)
        except Exception:
            logger.exception("ontap_rest resource id lookup failed")
            return {}
