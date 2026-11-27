"""Validation for the ONTAP provider: schema, settings, spec, connectivity and references."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers._netapp.ontap import OntapService, spec_hint

from .components.manager import default_service_factory
from .schema import TYPE_NAME, check_resources, desired_from_resources
from .settings import PROVIDER_NAME, OntapSettings, load_settings, settings_problems, spec_file_for

_SECRET_PREFIX = "secret://env_secrets/"  # nosec B105  # URI scheme, not a password

ServiceFactory = Callable[[OntapSettings], OntapService]


class OntapValidator:
    """Validates ONTAP resources and the cluster connection for ``infra doctor``."""

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        config_dir: Path | None = None,
        service_factory: ServiceFactory | None = None,
    ) -> None:
        """Initialize the validator.

        Args:
            env_config: Environment configuration (holds the decrypted secrets).
            report: Report to add findings to.
            config_dir: Configuration directory, to load the connection settings.
            service_factory: Builds the cluster service; replaced in tests.
        """
        self.env_config = env_config
        self.report = report
        self.config_dir = config_dir
        self._factory: ServiceFactory = service_factory or default_service_factory

    def validate_offline(self, resources: list[ResourceConfig]) -> None:
        """Check schema, settings, secret references and the spec file; no network.

        Args:
            resources: Resources to validate; only ONTAP types are checked.
        """
        for finding in check_resources(resources):
            self.report.add_check(
                check_name=f"ontap_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        self._check_settings()

    def _check_settings(self) -> None:
        raw: dict[str, Any] = self.env_config.provider_settings.get(PROVIDER_NAME) or {}
        for problem in settings_problems(raw):
            self.report.add_check("ontap_settings", False, problem)
        flat = _flatten(self.env_config.secrets or {})
        for key, value in raw.items():
            if isinstance(value, str) and value.startswith(_SECRET_PREFIX):
                path = value[len(_SECRET_PREFIX) :].replace("/", ".")
                if path not in flat:
                    self.report.add_check(
                        f"ontap_secret_{key}",
                        False,
                        f"provider_settings.ontap.{key} references a secret that is not "
                        f"in the environment secrets ('{path}')",
                    )
        if raw:
            spec = spec_file_for(raw, self.config_dir)
            if not spec.is_file():
                self.report.add_check("ontap_spec", False, _spec_message(spec))

    def validate_connectivity(self) -> None:
        """Check the cluster answers over REST and report its ONTAP version."""
        try:
            _settings, service = self._connect()
            info = service.cluster_info()
        except InfraFoundryError as exc:
            self.report.add_check("ontap_connectivity", False, str(exc))
            return
        version = (info.get("version") or {}).get("full") or "unknown version"
        self.report.add_check("ontap_version", True, f"ONTAP '{version}' reachable")

    def validate_references(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Check schema and settings, then that every SVM, node and port exists.

        Args:
            resources: Resources to validate; only ONTAP types are checked.
            reference_resources: Unused; LIFs reference cluster objects, not each other.
        """
        self.validate_offline(resources)
        if check_resources(resources):
            return
        desired = [d for d in desired_from_resources(resources) if not d.absent]
        if not desired:
            return
        try:
            _settings, service = self._connect()
            svms = service.list_names("svms")
            nodes = service.list_names("nodes")
            ports = service.list_names("ports")
        except InfraFoundryError as exc:
            self.report.add_check("ontap_references", False, str(exc))
            return
        for obj in desired:
            problems = []
            if obj.svm not in svms:
                problems.append(f"svm '{obj.svm}'")
            node, port = obj.fields.get("home_node"), obj.fields.get("home_port")
            if node and node not in nodes:
                problems.append(f"home node '{node}'")
            elif node and port and f"{node}:{port}" not in ports:
                problems.append(f"home port '{port}' on node '{node}'")
            for problem in problems:
                self.report.add_check(
                    f"ontap_reference_{obj.resource_name}",
                    False,
                    f"{TYPE_NAME} '{obj.resource_name}' references {problem}, which is not on "
                    "the cluster",
                )

    def _connect(self) -> tuple[OntapSettings, OntapService]:
        if self.config_dir is None:
            raise InfraFoundryError("ontap: no config directory to load settings from")
        settings = load_settings(self.config_dir, self.env_config.name)
        return settings, self._factory(settings)


def _spec_message(spec: Path) -> str:
    """Name the missing spec and, when pynetappfoundry is installed, where to get it."""
    try:
        return spec_hint(spec)
    except ImportError:
        return (
            f"the ONTAP OpenAPI spec is missing at {spec}, and pynetappfoundry is not "
            "installed: pip install 'infrafoundry[netapp]'"
        )


def _flatten(tree: dict[str, Any], prefix: str = "") -> set[str]:
    """Return the dotted leaf paths of a nested secrets tree."""
    paths: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths |= _flatten(value, path + ".")
        elif value is not None:
            paths.add(path)
    return paths
