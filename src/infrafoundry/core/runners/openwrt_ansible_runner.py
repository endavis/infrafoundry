"""Runner for OpenWrt devices through generated ``community.openwrt`` playbooks (ADR-0028).

``OpenWrtAnsibleRunner`` acts only for ``provider.name == "openwrt"``. It is separate
from the generic ``AnsibleRunner`` on purpose: that runner is not an IaC runner, runs
one ``playbook.yml`` per provider without ``--diff`` and returns no per-resource
outcomes. This runner shells out to the same ``ansible-playbook`` and the same
collection, runs ``openwrt.yml`` only, and reports outcomes the executor can record.

``plan`` runs ``--check --diff`` with the JSON stdout callback. ``apply`` runs that
check pass first and refuses a plan that could cut the management connection, then runs
the playbook for real; the playbook commits with ``ubus`` rollback and confirms after
reconnecting. Core never imports the provider package: the runner talks to it through
the structural ``_OpenWrtProvider`` protocol.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess  # nosec B404  # required for running ansible-playbook
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast, override

from rich.console import Console
from rich.markup import escape

from infrafoundry.core.managed_set import ManagedResources, ReleasedResource
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.result_types import ApplyResult, DestroyResult, DriftInfo, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.types import ResourceOutcome

logger = logging.getLogger(__name__)

ANSIBLE_BINARY = "ansible-playbook"
"""The executable the runner resolves and runs (``tool_name`` is only the registry key)."""

JSON_CALLBACK = "ansible.posix.json"
"""Stdout callback that prints one JSON document with every task's result."""

STDERR_TAIL = 400
"""Characters of stderr kept in an error message."""


class _Rendered(Protocol):
    """What the runner reads from a rendered run."""

    ansible_dir: Path
    tags: list[str]

    @property
    def playbook(self) -> str:
        """The playbook file name."""
        ...


class _RunResult(Protocol):
    """What the runner reads from an interpreted run."""

    success: bool
    error: str | None
    rollback_pending: bool
    refusals: list[str]
    reconnect_host: str | None
    outcomes: list[ResourceOutcome]
    released: list[ReleasedResource]
    counts: dict[str, int]

    @property
    def has_changes(self) -> bool:
        """True when any object changes."""
        ...

    def summary_lines(self) -> list[str]:
        """Human-readable summary lines."""
        ...


class _OpenWrtProvider(Protocol):
    """What the runner needs from the OpenWrt provider."""

    def render_run(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        mode: str = "apply",
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> _Rendered:
        """Write the run's files."""
        ...

    def parse_run(self, raw: str, run: _Rendered, *, check: bool) -> _RunResult:
        """Interpret the run's JSON output."""
        ...

    def deletable_types(self) -> set[str]:
        """Resource types the provider can delete."""
        ...


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``ansible-playbook`` with captured output (patched in tests)."""
    return subprocess.run(  # nosec B603  # list argv, no shell
        argv, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


class OpenWrtAnsibleRunner(BaseRunner):
    """Plans and applies changes to an OpenWrt device with ``ansible-playbook``."""

    _tool_name = "openwrt_ansible"
    """Registry key (the registry would otherwise derive ``openwrtansible``)."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the registry key; ``generate_openwrt_ansible`` is the dispatch hook."""
        return "openwrt_ansible"

    @property
    @override
    def is_iac_runner(self) -> bool:
        """The runner provisions the device, so it auto-runs on plan/apply."""
        return True

    @property
    @override
    def priority(self) -> int:
        """Run before Terraform, like the other direct runners."""
        return -10

    @property
    @override
    def tool_path(self) -> str:
        """Return the path of ``ansible-playbook``.

        Raises:
            FileNotFoundError: If ``ansible-playbook`` is not on PATH.
        """
        path = shutil.which(ANSIBLE_BINARY)
        if path is None:
            raise FileNotFoundError(
                f"{ANSIBLE_BINARY} not found on PATH. Please install {ANSIBLE_BINARY}."
            )
        return path

    @override
    def is_available(self) -> bool:
        """Return True if ``ansible-playbook`` is on PATH."""
        try:
            self.tool_path  # noqa: B018  # the lookup is the check
        except FileNotFoundError:
            return False
        return True

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """No-op initialization."""
        return {"success": True, "output": "no init required"}

    @staticmethod
    def _supports(provider: ProviderBase) -> bool:
        """Return True for the openwrt provider only (every IaC runner sees every provider)."""
        return getattr(provider, "name", None) == "openwrt" and callable(
            getattr(provider, "generate_openwrt_ansible", None)
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
                "OpenWrtAnsibleRunner requires provider.set_environment(env_name) "
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

    def _playbook(
        self,
        run: _Rendered,
        *,
        check: bool,
        reconnect_host: str | None = None,
    ) -> tuple[str, str | None]:
        """Run the playbook once; return ``(stdout, error)``.

        The error is set when ``ansible-playbook`` cannot run or printed no output.
        """
        try:
            argv = [self.tool_path, "-i", "inventory.yml", run.playbook]
        except FileNotFoundError:
            return "", f"{ANSIBLE_BINARY} not found on PATH"
        if check:
            argv += ["--check", "--diff"]
        if run.tags:
            argv += ["--tags", ",".join(run.tags)]
        if reconnect_host:
            argv += ["-e", f"infrafoundry_reconnect_host={reconnect_host}"]
        # Host-key checking is forced on: an ANSIBLE_HOST_KEY_CHECKING=False in the
        # caller's environment would otherwise override the generated ansible.cfg.
        env = {
            **os.environ,
            "ANSIBLE_STDOUT_CALLBACK": JSON_CALLBACK,
            "ANSIBLE_HOST_KEY_CHECKING": "True",
        }
        self.console.print(
            f"  [dim]openwrt_ansible: {'check' if check else 'run'} {run.playbook}[/dim]"
        )
        try:
            result = _run(argv, run.ansible_dir, env)
        except OSError as exc:
            return "", f"{ANSIBLE_BINARY} could not run: {exc}"
        if not result.stdout.strip():
            tail = (result.stderr or "").strip()[-STDERR_TAIL:]
            return "", f"{ANSIBLE_BINARY} exited {result.returncode} with no output: {tail}"
        return result.stdout, None

    def _pass(
        self,
        provider: ProviderBase,
        run: _Rendered,
        *,
        check: bool,
        reconnect_host: str | None = None,
    ) -> tuple[_RunResult | None, str | None]:
        """Run and interpret one pass; return ``(result, error)``."""
        stdout, error = self._playbook(run, check=check, reconnect_host=reconnect_host)
        if error is not None:
            return None, error
        try:
            return cast(_OpenWrtProvider, provider).parse_run(stdout, run, check=check), None
        except ValueError as exc:
            return None, str(exc)

    def _check_pass(
        self, provider: ProviderBase, kwargs: dict[str, Any]
    ) -> tuple[_Rendered | None, _RunResult | None, str | None]:
        """Render and run the check pass shared by ``plan`` and ``apply``."""
        env_name = self._env_name(provider, kwargs)
        resources = self._load_resources(provider, env_name)
        target_resources = kwargs.get("target_resources")
        run = cast(_OpenWrtProvider, provider).render_run(
            env_name,
            resources,
            mode="apply",
            add_only=bool(kwargs.get("add_only", False)) or bool(target_resources),
            managed_resources=kwargs.get("managed_resources"),
            target_resources=target_resources,
        )
        result, error = self._pass(provider, run, check=True)
        return run, result, error

    @staticmethod
    def _refusal_text(verb: str, result: _RunResult) -> str:
        return f"openwrt {verb} refused, it could cut the management connection:\n" + "\n".join(
            f"- {r}" for r in result.refusals
        )

    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Diff the YAML against the device with a check-mode run; writes nothing.

        Args:
            provider: The OpenWrt provider.
            **kwargs: ``add_only`` suppresses deletes (drift runs); ``target_resources``
                restricts the run and implies add-only; ``managed_resources`` holds the
                managed rows by type (ADR-0018); ``env_name`` overrides the provider's
                current environment.
        """
        if not self._supports(provider):
            return PlanResult(success=True, has_changes=False, changes_summary="No changes")
        try:
            _run_files, result, error = self._check_pass(provider, kwargs)
        except Exception as exc:
            logger.exception("openwrt_ansible plan failed")
            return PlanResult(success=False, error=str(exc))
        if error is not None or result is None:
            return PlanResult(success=False, error=error or "openwrt plan failed")
        if not result.success:
            return PlanResult(success=False, error=result.error or "openwrt plan failed")
        if result.refusals:
            return PlanResult(success=False, error=self._refusal_text("plan", result))
        lines = result.summary_lines()
        for line in lines:
            self.console.print(f"  [dim]openwrt_ansible: {escape(line)}[/dim]")
        return PlanResult(
            success=True,
            has_changes=result.has_changes,
            changes_summary=" | ".join(lines) if result.has_changes else "No changes",
            output=json.dumps(result.counts),
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
        """Check the plan, then run the playbook for real.

        A plan that could cut the management connection is refused before any write.
        If the device does not confirm the commit it reverts by itself, and the result
        says so.

        Args:
            provider: The OpenWrt provider.
            auto_approve: Ignored; the run is always approved.
            **kwargs: ``add_only`` suppresses deletes; ``target_resources`` restricts the
                run and implies add-only; ``managed_resources`` holds the managed rows by
                type (ADR-0018); ``env_name`` overrides the provider's current environment.
        """
        if not self._supports(provider):
            return ApplyResult(success=True, resources_created=0, resources_updated=0)
        try:
            run, checked, error = self._check_pass(provider, kwargs)
            if error is not None or checked is None or run is None:
                return ApplyResult(success=False, error=error or "openwrt check failed")
            if not checked.success:
                return ApplyResult(success=False, error=checked.error or "openwrt check failed")
            if checked.refusals:
                return ApplyResult(success=False, error=self._refusal_text("apply", checked))
            result, error = self._pass(
                provider, run, check=False, reconnect_host=checked.reconnect_host
            )
        except Exception as exc:
            logger.exception("openwrt_ansible apply failed")
            return ApplyResult(success=False, error=str(exc))
        if error is not None or result is None:
            return ApplyResult(success=False, error=error or "openwrt apply failed")
        applied = ApplyResult(
            success=result.success,
            resources_created=result.counts.get("create", 0),
            resources_updated=result.counts.get("update", 0),
            resources_deleted=result.counts.get("delete", 0),
        )
        applied["resource_outcomes"] = result.outcomes
        applied["resource_outcomes_summary"] = [o.to_dict() for o in result.outcomes]
        if not result.success:
            applied["error"] = result.error or "openwrt apply failed"
            return applied
        if result.released:
            applied["released_resources"] = result.released
        return applied

    def destroy(
        self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any
    ) -> DestroyResult:
        """Delete the declared objects that can be deleted; forget the others.

        Args:
            provider: The OpenWrt provider.
            auto_approve: Ignored; the run is always approved.
            **kwargs: ``target_resources`` restricts the run; ``env_name`` overrides the
                provider's current environment.
        """
        if not self._supports(provider):
            return DestroyResult(success=True, resources_destroyed=0)
        try:
            env_name = self._env_name(provider, kwargs)
            resources = self._load_resources(provider, env_name)
            run = cast(_OpenWrtProvider, provider).render_run(
                env_name,
                resources,
                mode="destroy",
                target_resources=kwargs.get("target_resources"),
            )
            result, error = self._pass(provider, run, check=False)
        except Exception as exc:
            logger.exception("openwrt_ansible destroy failed")
            return DestroyResult(success=False, error=str(exc))
        if error is not None or result is None:
            return DestroyResult(success=False, error=error or "openwrt destroy failed")
        destroyed = DestroyResult(success=result.success, resources_destroyed=len(result.outcomes))
        destroyed["resource_outcomes"] = result.outcomes
        destroyed["resource_outcomes_summary"] = [o.to_dict() for o in result.outcomes]
        if not result.success:
            destroyed["error"] = result.error or "openwrt destroy failed"
        return destroyed

    def needs_managed_dispatch(
        self, provider: ProviderBase, managed_resources: ManagedResources
    ) -> bool:
        """Return True if managed objects need deleting though no YAML remains (#1260).

        Args:
            provider: Provider with no resources in the environment's YAML.
            managed_resources: Managed resources by type.

        Returns:
            True for the openwrt provider when a deletable type has managed rows.
        """
        if not self._supports(provider):
            return False
        deletable = cast(_OpenWrtProvider, provider).deletable_types()
        return any(rows for type_name, rows in managed_resources.items() if type_name in deletable)

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Return no ids: anonymous UCI sections have no stable identifier."""
        return {}
