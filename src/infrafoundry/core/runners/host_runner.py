"""Runner for existing hosts (ADR-0022).

``HostRunner`` configures machines that already exist and that no provider creates.
It acts only for ``provider.name == "host"``. ``apply`` runs each host's playbooks
with ``ansible-playbook`` and reports a ``create`` outcome the first time and an
``update`` afterwards, so the executor records the host in the state database and
fires its lifecycle handlers. ``destroy`` reports ``delete`` outcomes and never
contacts the machine.

The Tailscale auth secret is passed to the enrollment playbook in one environment
variable, for that subprocess only. It is never written to the inventory or to the
controller's disk, and never appears in an error message.
"""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404  # required for running ansible-playbook
from pathlib import Path
from typing import Any, Protocol, cast, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.result_types import ApplyResult, DestroyResult, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.types import ResourceOutcome

logger = logging.getLogger(__name__)

AUTH_ENV_VAR = "INFRAFOUNDRY_TAILSCALE_AUTH_KEY"
"""Environment variable that carries the Tailscale auth secret to the enrollment run."""


class _HostProvider(Protocol):
    """What the runner needs from the host provider (kept structural: core never imports it)."""

    ansible_dir: Path

    def get_host_runs(self, names: list[str] | None = None) -> list[Any]:
        """Return the playbook runs per host."""
        ...

    def resolve_tailscale_auth(self, ref: str) -> str:
        """Return the secret a reference points at."""
        ...


class HostRunner(BaseRunner):
    """Runs Ansible against hosts the ``host`` provider declares."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the tool identifier; the provider's ``generate_host_ansible`` matches it."""
        return "host_ansible"

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The runner provisions the host's configuration, so it auto-runs on plan/apply."""
        return True

    @override
    def is_available(self) -> bool:
        """Return True if ``ansible-playbook`` is on PATH."""
        import shutil

        return shutil.which("ansible-playbook") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization."""
        return {"success": True, "output": "no init required"}

    @staticmethod
    def _supports(provider: ProviderBase) -> bool:
        """Return True for the host provider only (every IaC runner sees every provider)."""
        return getattr(provider, "name", None) == "host" and callable(
            getattr(provider, "get_host_runs", None)
        )

    @staticmethod
    def _names(kwargs: dict[str, Any]) -> list[str] | None:
        """Pick the host names to act on: the ``-r`` targets, else the run's resources."""
        names = kwargs.get("target_resources") or kwargs.get("resource_names")
        return list(names) if names else None

    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Report the hosts apply would configure; runs no subprocess.

        Args:
            provider: The host provider.
            **kwargs: ``target_resources`` / ``resource_names`` restrict the hosts.
        """
        if not self._supports(provider):
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")
        runs = cast(_HostProvider, provider).get_host_runs(self._names(kwargs))
        if not runs:
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")
        names = ", ".join(r.name for r in runs)
        return PlanResult(
            success=True,
            has_changes=True,
            changes_summary=f"Ansible will configure {len(runs)} existing host(s): {names}",
        )

    def apply(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> ApplyResult:
        """Run each host's playbooks and report one outcome per host.

        Args:
            provider: The host provider.
            auto_approve: Accepted for the protocol; Ansible does not prompt.
            **kwargs: ``target_resources`` / ``resource_names`` restrict the hosts;
                ``managed_resources`` tells a first run (``create``) from a later one
                (``update``).
        """
        empty: ApplyResult = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
        }
        if not self._supports(provider):
            return empty
        runs = cast(_HostProvider, provider).get_host_runs(self._names(kwargs))
        if not runs:
            return empty
        if not self.is_available():
            return ApplyResult(success=False, error="ansible-playbook not found on PATH")

        managed = kwargs.get("managed_resources") or {}
        known = {r.name for r in managed.get("host", [])}
        ansible_dir = Path(provider.ansible_dir)
        outcomes: list[ResourceOutcome] = []
        created = updated = 0
        for run in runs:
            for playbook in run.playbooks:
                error = self._run_playbook(provider, ansible_dir, run, playbook)
                if error:
                    return ApplyResult(success=False, error=error)
            action = "update" if run.name in known else "create"
            created += action == "create"
            updated += action == "update"
            outcomes.append(ResourceOutcome(f"host.{run.name}", action, run.name))

        result: ApplyResult = {
            "success": True,
            "resources_created": created,
            "resources_updated": updated,
            "resources_deleted": 0,
            "resource_outcomes": outcomes,
        }
        result["resource_outcomes_summary"] = [o.to_dict() for o in outcomes]
        return result

    def _run_playbook(
        self, provider: ProviderBase, ansible_dir: Path, run: Any, playbook: str
    ) -> str | None:
        """Run one playbook against one host; return an error message or ``None``."""
        env: dict[str, str] | None = None
        if run.enrollment_playbook and playbook == run.enrollment_playbook:
            try:
                secret = cast(_HostProvider, provider).resolve_tailscale_auth(
                    run.tailscale_auth_ref
                )
            except ValueError as exc:
                return str(exc)
            env = {**os.environ, AUTH_ENV_VAR: secret}
        argv = [
            self.tool_path,
            "-i",
            "inventory.yml",
            "--limit",
            run.name,
            playbook,
        ]
        self.console.print(f"  [dim]host_ansible: {run.name}: {Path(playbook).name}[/dim]")
        try:
            result = subprocess.run(  # nosec B603  # list argv, no shell
                argv, cwd=ansible_dir, env=env, capture_output=False, check=False
            )
        except FileNotFoundError:
            return "ansible-playbook not found on PATH"
        if result.returncode != 0:
            return (
                f"ansible-playbook failed for host '{run.name}' "
                f"({Path(playbook).name}, exit {result.returncode})"
            )
        return None

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Report ``delete`` outcomes so the hosts are forgotten; never contacts them.

        Args:
            provider: The host provider.
            auto_approve: Accepted for the protocol.
            **kwargs: ``target_resources`` / ``resource_names`` name the hosts.
        """
        if not self._supports(provider):
            return DestroyResult(success=True, resources_destroyed=0)
        names = self._names(kwargs) or []
        outcomes = [ResourceOutcome(f"host.{name}", "delete", name) for name in names]
        result: DestroyResult = {"success": True, "resources_destroyed": len(outcomes)}
        result["resource_outcomes"] = outcomes
        return result
