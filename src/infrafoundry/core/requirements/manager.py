"""Resolve and check the requirements of the blueprints in scope (#1046)."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.exceptions import MissingRequirementsError
from infrafoundry.core.requirements.checker import (
    SpecFinder,
    VersionLookup,
    check_collection,
    check_python,
    installed_collections,
)
from infrafoundry.core.requirements.installer import (
    InstallStep,
    Runner,
    Which,
    plan_install,
    run_install,
)
from infrafoundry.core.requirements.models import (
    BlueprintRequirements,
    CollectionRequirement,
    PythonRequirement,
    RequirementStatus,
)

if TYPE_CHECKING:
    from infrafoundry.core.config import ConfigManager

CollectionsLookup = Callable[[], Mapping[str, str] | None]


@dataclass(frozen=True)
class RequirementsReport:
    """The requirement statuses for one environment and scope.

    Attributes:
        env_name: Environment checked
        statuses: One status per distinct requirement
    """

    env_name: str
    statuses: tuple[RequirementStatus, ...]

    @property
    def unmet(self) -> tuple[RequirementStatus, ...]:
        """The requirements that are not satisfied."""
        return tuple(s for s in self.statuses if not s.satisfied)

    def format_unmet(self) -> str:
        """Describe every unmet requirement, its blueprints and its fix.

        Returns:
            A multi-line message; empty when every requirement is met
        """
        if not self.unmet:
            return ""
        lines = [f"Blueprint requirements not met for environment '{self.env_name}':"]
        for status in self.unmet:
            label = f"{status.name}{status.wanted}" if status.wanted else status.name
            lines.append(
                f"  - {status.kind.value} {label}: {status.problem} "
                f"(needed by blueprint {', '.join(status.blueprints)})"
            )
            lines.append(f"    run: {status.fix}")
        lines.append(f"Or install them all with: foundry deps sync --env {self.env_name}")
        return "\n".join(lines)


@dataclass(frozen=True)
class SyncResult:
    """What ``deps sync`` did, or would do with ``--dry-run``.

    Attributes:
        steps: Install commands run (or planned); empty when nothing was unmet
        report: Requirement status after the install (before it, on a dry run)
        dry_run: Whether the steps were only planned
    """

    steps: tuple[InstallStep, ...]
    report: RequirementsReport
    dry_run: bool


class RequirementsManager(BaseManager):
    """Check that the blueprints a run uses have their requirements installed.

    Requirements come from the ``requirements:`` block of each blueprint that a
    package in scope references. Scope is the environment, narrowed by the same
    package and provider filters that ``infra plan``/``apply``/``destroy`` take.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        *,
        get_version: VersionLookup = importlib.metadata.version,
        find_spec: SpecFinder = importlib.util.find_spec,
        collections_lookup: CollectionsLookup = installed_collections,
    ) -> None:
        """Initialize the requirements manager.

        Args:
            config_manager: Source of packages and blueprints
            get_version: Returns a distribution's installed version
            find_spec: Locates an importable module
            collections_lookup: Returns installed Ansible collections
        """
        super().__init__()
        self.config_manager = config_manager
        self._get_version = get_version
        self._find_spec = find_spec
        self._collections_lookup = collections_lookup

    def blueprints_in_scope(
        self,
        env_name: str,
        package_filter: str | None = None,
        provider_filter: list[str] | None = None,
    ) -> list[str]:
        """Return the blueprints referenced by the packages in scope.

        Args:
            env_name: Environment name
            package_filter: Only the package with this name
            provider_filter: Only packages targeting one of these providers

        Returns:
            Distinct blueprint names, sorted
        """
        names: set[str] = set()
        for provider, manifest in self.config_manager.list_package_manifests(env_name):
            if not manifest.blueprint:
                continue
            if package_filter is not None and manifest.name != package_filter:
                continue
            if provider_filter is not None and provider not in provider_filter:
                continue
            names.add(manifest.blueprint)
        return sorted(names)

    def check(
        self,
        env_name: str,
        package_filter: str | None = None,
        provider_filter: list[str] | None = None,
    ) -> RequirementsReport:
        """Check every requirement of the blueprints in scope.

        Args:
            env_name: Environment name
            package_filter: Only the package with this name
            provider_filter: Only packages targeting one of these providers

        Returns:
            The status of each distinct requirement

        Raises:
            InvalidConfigurationError: If a blueprint's ``requirements:`` is invalid
        """
        python: dict[PythonRequirement, list[str]] = {}
        collections: dict[CollectionRequirement, tuple[list[str], list[str]]] = {}
        resolver = self.config_manager.blueprint_resolver
        for name in self.blueprints_in_scope(env_name, package_filter, provider_filter):
            declared: BlueprintRequirements = resolver.resolve(name)["requirements"]
            for py_req in declared.python:
                python.setdefault(py_req, []).append(name)
            for col_req in declared.collections:
                blueprints, files = collections.setdefault(col_req, ([], []))
                blueprints.append(name)
                if declared.collections_file is not None:
                    files.append(str(declared.collections_file))

        statuses: list[RequirementStatus] = []
        for py_req, blueprints in python.items():
            status = check_python(
                py_req,
                tuple(blueprints),
                get_version=self._get_version,
                find_spec=self._find_spec,
            )
            if status is not None:
                statuses.append(status)
        if collections:
            installed = self._collections_lookup()
            for col_req, (blueprints, files) in collections.items():
                statuses.append(
                    check_collection(
                        col_req, tuple(blueprints), installed, tuple(dict.fromkeys(files))
                    )
                )

        report = RequirementsReport(env_name=env_name, statuses=tuple(statuses))
        self._log_debug(
            f"Checked {len(report.statuses)} blueprint requirement(s) for {env_name}, "
            f"{len(report.unmet)} unmet"
        )
        return report

    def ensure(
        self,
        env_name: str,
        package_filter: str | None = None,
        provider_filter: list[str] | None = None,
    ) -> RequirementsReport:
        """Check requirements and raise if any is unmet.

        Args:
            env_name: Environment name
            package_filter: Only the package with this name
            provider_filter: Only packages targeting one of these providers

        Returns:
            The report, when every requirement is met

        Raises:
            MissingRequirementsError: If any requirement is unmet
        """
        report = self.check(env_name, package_filter, provider_filter)
        if report.unmet:
            message = report.format_unmet()
            self._log_error(message)
            raise MissingRequirementsError(
                message, context={"unmet": [status.name for status in report.unmet]}
            )
        return report

    def sync(
        self,
        env_name: str,
        package_filter: str | None = None,
        provider_filter: list[str] | None = None,
        *,
        dry_run: bool = False,
        run: Runner | None = None,
        which: Which | None = None,
    ) -> SyncResult:
        """Install the unmet requirements of the blueprints in scope (#1047).

        Args:
            env_name: Environment name
            package_filter: Only the package with this name
            provider_filter: Only packages targeting one of these providers
            dry_run: Plan the install commands without running them
            run: Runs one install command; defaults to :func:`subprocess.run`
            which: Locates ``uv`` and ``ansible-galaxy``

        Returns:
            The steps and the resulting report

        Raises:
            RequirementInstallError: If a tool is missing or an install fails
            MissingRequirementsError: If requirements are still unmet afterwards
        """
        report = self.check(env_name, package_filter, provider_filter)
        steps = tuple(plan_install(report.unmet))
        if not steps or dry_run:
            return SyncResult(steps=steps, report=report, dry_run=dry_run)

        for step in steps:
            self._log_info(f"Installing {', '.join(step.covers)}: {step.display()}")
        run_install(steps, run=run, which=which or shutil.which)

        # New distributions are on disk; drop the import system's stale caches
        # so the re-check finds them.
        importlib.invalidate_caches()
        after = self.check(env_name, package_filter, provider_filter)
        if after.unmet:
            raise MissingRequirementsError(
                "Installed, but still unmet:\n" + after.format_unmet(),
                context={"unmet": [status.name for status in after.unmet]},
            )
        return SyncResult(steps=steps, report=after, dry_run=False)

    @override
    def cleanup(self) -> None:
        """Nothing to release."""
