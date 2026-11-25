"""Validation for the QNAP provider: resources, settings and connectivity."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from .client import QnapClient
from .components.firmware import FirmwareClient, check_firmware_resources, read_firmware
from .settings import PROVIDER_NAME, QnapSettings, load_settings, raw_settings_problems

_SECRET_PREFIX = "secret://env_secrets/"  # nosec B105  # URI scheme, not a password

ClientFactory = Callable[[QnapSettings], FirmwareClient]


class QnapValidator:
    """Validates QNAP resources and the switch connection for ``infra doctor``."""

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        config_dir: Path | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Initialize the validator.

        Args:
            env_config: Environment configuration (holds the decrypted secrets).
            report: Report to add findings to.
            config_dir: Configuration directory, to load the connection settings.
            client_factory: Builds the client; replaced in tests.
        """
        self.env_config = env_config
        self.report = report
        self.config_dir = config_dir
        self._client_factory: ClientFactory = client_factory or QnapClient

    def validate_offline(self, resources: list[ResourceConfig]) -> None:
        """Check resources, settings and secret references; no network.

        Args:
            resources: Resources to validate; only ``firmware.update`` is checked.
        """
        for finding in check_firmware_resources(resources):
            self.report.add_check(
                check_name=f"qnap_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        self._check_settings()

    def _check_settings(self) -> None:
        raw: dict[str, Any] = self.env_config.provider_settings.get(PROVIDER_NAME) or {}
        for index, problem in enumerate(raw_settings_problems(raw)):
            self.report.add_check(f"qnap_settings_{index}", False, problem)
        flat = _flatten(self.env_config.secrets or {})
        for key, value in raw.items():
            if isinstance(value, str) and value.startswith(_SECRET_PREFIX):
                path = value[len(_SECRET_PREFIX) :].replace("/", ".")
                if path not in flat:
                    self.report.add_check(
                        f"qnap_secret_{key}",
                        False,
                        f"provider_settings.qnap.{key} references a secret that is not "
                        f"in the environment secrets ('{path}')",
                    )

    def validate_connectivity(self) -> None:
        """Check the switch answers and a login works; warn when the pin is skipped."""
        try:
            settings = self._settings()
            client = self._client_factory(settings)
            client.about()
            with client.session():
                version = read_firmware(client).version
        except InfraFoundryError as exc:
            self.report.add_check("qnap_connectivity", False, str(exc))
            return
        self.report.add_check("qnap_firmware", True, f"QNAP firmware {version} reachable")
        if not settings.verify_ssl:
            self.report.add_check(
                "qnap_verify_ssl",
                False,
                "verify_ssl is false: the switch's certificate is not checked",
                level=ValidationLevel.WARNING,
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Offline checks only: the provider has no cross-resource references."""
        self.validate_offline(resources)

    def _settings(self) -> QnapSettings:
        if self.config_dir is None:
            raise InfraFoundryError("qnap: no config directory to load settings from")
        return load_settings(self.config_dir, self.env_config.name)


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
