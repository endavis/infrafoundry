"""Runner for MikroTik RouterOS devices over the REST API (ADR-0026).

``MikroTikRestRunner`` acts only for ``provider.name == "mikrotik"``. ``plan`` reads
the device, diffs it against the YAML and refuses a plan whose end state would cut the
management connection. ``apply`` and ``destroy`` are not implemented yet (#1483) and
fail loudly rather than doing nothing.

Core never imports the provider package: the runner talks to it through the
structural ``_MikroTikProvider`` protocol.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast, override

from rich.console import Console
from rich.markup import escape

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, DriftInfo, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

NOT_IMPLEMENTED_MESSAGE = "mikrotik apply is not implemented yet (see #1483)"
"""Failure message of ``apply`` and ``destroy`` until the follow-up lands."""


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


class _MikroTikProvider(Protocol):
    """What the runner needs from the MikroTik provider."""

    def rest_plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> _Plan:
        """Plan the device's changes."""
        ...


class MikroTikRestRunner(BaseRunner):
    """Plans changes to a RouterOS device through its REST API."""

    _tool_name = "mikrotik_rest"
    """Registry key (the registry would otherwise derive ``mikrotikrest`` from the class name)."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the registry key; ``generate_mikrotik_rest`` is the dispatch hook."""
        return "mikrotik_rest"

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The runner provisions the device, so it auto-runs on plan/apply."""
        return True

    @property
    @override
    def priority(self) -> int:
        """Run before Terraform, like the other direct-API runners."""
        return -10

    @override
    def is_available(self) -> bool:
        """Always available: the runner needs only ``requests``."""
        return True

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization."""
        return {"success": True, "output": "no init required"}

    @staticmethod
    def _supports(provider: ProviderBase) -> bool:
        """Return True for the mikrotik provider only (every IaC runner sees every provider)."""
        return getattr(provider, "name", None) == "mikrotik" and callable(
            getattr(provider, "generate_mikrotik_rest", None)
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
                "MikroTikRestRunner requires provider.set_environment(env_name) "
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
        """Diff the YAML against the device; writes nothing.

        Args:
            provider: The MikroTik provider.
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
            plan = cast(_MikroTikProvider, provider).rest_plan(
                env_name,
                resources,
                add_only=bool(kwargs.get("add_only", False)),
                managed_resources=kwargs.get("managed_resources"),
                target_resources=kwargs.get("target_resources"),
            )
        except Exception as exc:
            logger.exception("mikrotik_rest plan failed")
            return PlanResult(success=False, error=str(exc))

        if plan.refusals:
            return PlanResult(
                success=False,
                error="mikrotik plan refused, it could cut the management connection:\n"
                + "\n".join(f"- {r}" for r in plan.refusals),
            )
        lines = plan.summary_lines()
        for line in lines:
            self.console.print(f"  [dim]mikrotik_rest: {escape(line)}[/dim]")
        for warning in plan.warnings:
            self.console.print(f"  [yellow]mikrotik_rest: {escape(warning)}[/yellow]")
        for type_name, names in plan.unmanaged.items():
            self.console.print(
                f"  [dim]mikrotik_rest: {type_name}: unmanaged (kept): "
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
        """Not implemented yet (#1483): fail loudly instead of doing nothing."""
        if not self._supports(provider):
            return ApplyResult(success=True, resources_created=0, resources_updated=0)
        return ApplyResult(success=False, error=NOT_IMPLEMENTED_MESSAGE)

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Not implemented yet (#1483): fail loudly instead of doing nothing."""
        if not self._supports(provider):
            return DestroyResult(success=True, resources_destroyed=0)
        return DestroyResult(success=False, error=NOT_IMPLEMENTED_MESSAGE)
