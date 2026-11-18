"""Validation for the MikroTik provider: schema, settings, connectivity and references."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from .client import RouterOSClient, RouterOSReader
from .schema import SPECS, check_resources, desired_from_resources
from .settings import PROVIDER_NAME, MikroTikSettings, load_settings

MIN_MAJOR_VERSION = 7
_SECRET_PREFIX = "secret://env_secrets/"  # nosec B105  # URI scheme, not a password
_REQUIRED = ("api_url", "username", "password")
_REFERENCES: dict[str, tuple[str, ...]] = {
    "interface.bridge.port": ("interface", "bridge"),
    "interface.vlan": ("interface",),
    "interface.bridge.vlan": ("bridge",),
    "ip.address": ("interface",),
    "ip.dhcp-client": ("interface",),
}

ClientFactory = Callable[[MikroTikSettings], RouterOSReader]


class MikroTikValidator:
    """Validates MikroTik resources and the device connection for ``infra doctor``."""

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
            client_factory: Builds the REST client; replaced in tests.
        """
        self.env_config = env_config
        self.report = report
        self.config_dir = config_dir
        self._client_factory: ClientFactory = client_factory or RouterOSClient

    def validate_offline(self, resources: list[ResourceConfig]) -> None:
        """Check schema, settings presence and secret references; no network.

        Args:
            resources: Resources to validate; only MikroTik types are checked.
        """
        for finding in check_resources(resources):
            self.report.add_check(
                check_name=f"mikrotik_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        self._check_settings()

    def _check_settings(self) -> None:
        raw: dict[str, Any] = self.env_config.provider_settings.get(PROVIDER_NAME) or {}
        missing = [key for key in _REQUIRED if not raw.get(key)]
        if missing:
            self.report.add_check(
                "mikrotik_settings",
                False,
                "provider_settings.mikrotik is missing: " + ", ".join(missing),
            )
        flat = _flatten(self.env_config.secrets or {})
        for key, value in raw.items():
            if isinstance(value, str) and value.startswith(_SECRET_PREFIX):
                path = value[len(_SECRET_PREFIX) :].replace("/", ".")
                if path not in flat:
                    self.report.add_check(
                        f"mikrotik_secret_{key}",
                        False,
                        f"provider_settings.mikrotik.{key} references a secret that is not "
                        f"in the environment secrets ('{path}')",
                    )

    def validate_connectivity(self) -> None:
        """Check the device answers and runs RouterOS 7 or later; warn on plain http."""
        try:
            settings, client = self._connect()
            rows = client.get("system/resource")
        except InfraFoundryError as exc:
            self.report.add_check("mikrotik_connectivity", False, str(exc))
            return
        version = str(rows[0].get("version", "")) if rows else ""
        match = re.match(r"(\d+)\.", version)
        major = int(match.group(1)) if match else 0
        self.report.add_check(
            "mikrotik_version",
            major >= MIN_MAJOR_VERSION,
            f"RouterOS {version} reachable"
            if major >= MIN_MAJOR_VERSION
            else f"RouterOS {version or 'unknown version'}: the REST API needs RouterOS 7 or later",
        )
        if settings.scheme == "http":
            self.report.add_check(
                "mikrotik_http",
                False,
                "api_url uses http: basic-auth credentials travel in plaintext",
                level=ValidationLevel.WARNING,
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Check schema and settings, then that every referenced interface exists.

        An interface or bridge exists when the device holds it or a resource declares it.

        Args:
            resources: Resources to validate; only MikroTik types are checked.
        """
        self.validate_offline(resources)
        declared = {
            str(obj.fields.get("name"))
            for obj in _safe_desired(resources)
            if obj.type_name in ("interface.bridge", "interface.vlan")
        }
        try:
            _settings, client = self._connect()
            known = {str(r.get("name")) for r in client.get("interface")}
        except InfraFoundryError as exc:
            self.report.add_check("mikrotik_references", False, str(exc))
            return
        for obj in _safe_desired(resources):
            for name in _REFERENCES.get(obj.type_name, ()):
                target = str(obj.fields.get(name, ""))
                if target and target not in known | declared:
                    self.report.add_check(
                        f"mikrotik_reference_{obj.resource_name}",
                        False,
                        f"{obj.type_name} '{obj.resource_name}' references '{target}', which "
                        "is neither on the device nor declared",
                    )

    def _connect(self) -> tuple[MikroTikSettings, RouterOSReader]:
        if self.config_dir is None:
            raise InfraFoundryError("mikrotik: no config directory to load settings from")
        settings = load_settings(self.config_dir, self.env_config.name)
        return settings, self._client_factory(settings)


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


def _safe_desired(resources: list[ResourceConfig]) -> list[Any]:
    """Declared objects, or none when the schema is broken (schema errors are reported)."""
    if check_resources(resources):
        return []
    return desired_from_resources([r for r in resources if r.type in SPECS])
