"""Report-only runner for QNAP switches (ADR-0038).

``QnapRestRunner`` acts only for ``provider.name == "qnap"``. ``plan`` prints the
provider's firmware lines and reports no changes; ``apply`` and ``destroy`` succeed with
zero counts, because the ``firmware.update`` resource is never applied (the upgrade is
``foundry provider qnap upgrade``). VLAN and port management will add its diff and apply
here. Core never imports the provider package.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, override

from rich.console import Console
from rich.markup import escape

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, DriftInfo, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

FIRMWARE_TYPE = "firmware.update"  # core must not import the provider package


class QnapRestRunner(BaseRunner):
    """Reports the firmware offer of a QNAP switch; writes nothing."""

    _tool_name = "qnap_rest"
    """Registry key (the registry would otherwise derive ``qnaprest`` from the class name)."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the registry key; ``generate_qnap_rest`` is the dispatch hook."""
        return "qnap_rest"

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The runner auto-runs on plan/apply like the other direct-API runners."""
        return True

    @property
    @override
    def priority(self) -> int:
        """Run before Terraform, like the other direct-API runners."""
        return -10

    @override
    def is_available(self) -> bool:
        """Always available: the runner needs nothing external."""
        return True

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization."""
        return {"success": True, "output": "no init required"}

    @staticmethod
    def _supports(provider: ProviderBase) -> bool:
        """Return True for the qnap provider only (every IaC runner sees every provider)."""
        return getattr(provider, "name", None) == "qnap" and callable(
            getattr(provider, "generate_qnap_rest", None)
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
                "QnapRestRunner requires provider.set_environment(env_name) "
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

    def _print_firmware(
        self,
        provider: ProviderBase,
        kwargs: dict[str, Any],
        env_name: str,
        resources: list[ResourceConfig],
    ) -> None:
        """Print the firmware lines (ADR-0038); never changes the plan's outcome.

        Skipped for add-only (drift) runs and when ``target_resources`` excludes every
        ``firmware.update`` resource, so scheduled drift runs never ask the vendor.
        """
        hook = getattr(provider, "firmware_plan_lines", None)
        if not callable(hook) or kwargs.get("add_only"):
            return
        targets = kwargs.get("target_resources")
        updates = [r for r in resources if r.type == FIRMWARE_TYPE]
        if targets:
            updates = [r for r in updates if r.name in targets]
        if not updates:
            return
        try:
            lines = hook(env_name, updates)
        except Exception as exc:  # a firmware check must never fail the plan
            logger.warning("qnap_rest firmware check failed: %s", type(exc).__name__)
            return
        for line, warning in lines:
            style = "yellow" if warning else "dim"
            self.console.print(f"  [{style}]qnap_rest: {escape(line)}[/{style}]")

    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Print the firmware lines; there is nothing to diff or write.

        Args:
            provider: The QNAP provider.
            **kwargs: ``add_only`` and ``target_resources`` gate the firmware check;
                ``env_name`` overrides the provider's current environment.
        """
        if not self._supports(provider):
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")
        env_name = self._env_name(provider, kwargs)
        resources = self._load_resources(provider, env_name)
        self._print_firmware(provider, kwargs, env_name, resources)
        return PlanResult(
            success=True,
            has_changes=False,
            changes_summary="No changes",
            output=json.dumps({"create": 0, "update": 0, "delete": 0}),
        )

    def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo:
        """Report no drift: the runner never plans a change.

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
        return DriftInfo(
            has_changes=False, summary="No changes", to_add=0, to_change=0, to_destroy=0
        )

    def apply(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> ApplyResult:
        """Succeed without writing: the firmware is upgraded by ``foundry provider qnap upgrade``.

        Args:
            provider: The QNAP provider.
            auto_approve: Ignored.
            **kwargs: Ignored.
        """
        return ApplyResult(success=True, resources_created=0, resources_updated=0)

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Succeed without writing: nothing on the switch is created by this provider.

        Args:
            provider: The QNAP provider.
            auto_approve: Ignored.
            **kwargs: Ignored.
        """
        return DestroyResult(success=True, resources_destroyed=0)
