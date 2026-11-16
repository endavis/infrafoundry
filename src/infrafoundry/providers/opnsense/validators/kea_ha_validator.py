"""Kea DHCPv4 high-availability validator for OPNsense (#1392).

Plan-time checks for ``kea.dhcp4.ha`` and ``kea.dhcp4.ha_peers`` (offline: YAML only).
Messages name fields and peer names, never URLs.

- Settings: unknown keys are ERRORs. ``enabled`` must be a boolean, ``this_server_name``
  a string and ``max_unacked_clients`` an integer >= 0.
- Peers: unknown keys are ERRORs (``uuid`` carries a hint). ``name`` is required,
  non-empty and unique within the type. ``role`` is required (``primary`` or
  ``standby``; there is no silent default for HA). ``url`` is required and an
  ``http(s)://host[:port]`` URL. ``lock`` must be a boolean.
- When ``enabled: true``: the declared peers must be exactly one ``primary`` and exactly
  one ``standby``, and a non-empty ``this_server_name`` must equal a declared peer name.
  An empty ``this_server_name`` is an INFO: each node falls back to its own hostname, so
  the peer names must equal the node hostnames (not checkable offline).
- When ``enabled`` is false or absent the per-row checks still run, but the peer count
  is not enforced.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import kea_dhcp4_ha as ha_svc
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_URL = re.compile(r"^https?://[^\s/:]+(:\d+)?(/\S*)?$")
_HA = "kea.dhcp4.ha"
_PEERS = "kea.dhcp4.ha_peers"


class KeaHAValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``kea.dhcp4.ha`` and ``kea.dhcp4.ha_peers`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all Kea DHCPv4 HA resources.

        Args:
            context: Context whose ``resources`` hold the HA resources.
        """
        settings: list[ResourceConfig] = []
        peers: list[ResourceConfig] = []
        for resource in context.resources:
            if resource.type == _HA:
                settings.append(resource)
            elif resource.type == _PEERS:
                peers.append(resource)
        for resource in settings:
            self._validate_settings(resource)
        self._check_duplicates(peers)
        for resource in peers:
            self._validate_peer(resource)
        for resource in settings:
            if resource.config.get("enabled") is True:
                self._validate_enabled(resource, peers)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    @staticmethod
    def _peer_name(resource: ResourceConfig) -> Any:
        return resource.config.get("name", resource.name)

    # -- settings -----------------------------------------------------------------

    def _validate_settings(self, resource: ResourceConfig) -> None:
        config = resource.config
        for key in sorted(set(config) - set(ha_svc.HA_FIELD_MAP)):
            self._error(
                f"kea_ha_unknown_key_{key}",
                f"{_HA} has unknown key '{key}'; allowed: {sorted(ha_svc.HA_FIELD_MAP)}",
            )
        for key in ha_svc.HA_FIELD_MAP:
            if key not in config:
                continue
            try:
                ha_svc.serialize_ha_setting(key, config[key])
            except InvalidConfigurationError as exc:
                self._error(f"kea_ha_{key}", str(exc))

    def _validate_enabled(self, resource: ResourceConfig, peers: list[ResourceConfig]) -> None:
        roles = [p.config.get("role") for p in peers]
        primaries = roles.count("primary")
        standbys = roles.count("standby")
        if len(peers) != 2 or primaries != 1 or standbys != 1:
            self._error(
                "kea_ha_peer_roles",
                f"{_HA} is enabled: declare exactly one primary and one standby in "
                f"{_PEERS} (found {primaries} primary, {standbys} standby, "
                f"{len(peers)} total)",
            )
        name = resource.config.get("this_server_name")
        if not isinstance(name, str):
            return
        if name:
            if name not in {self._peer_name(p) for p in peers}:
                self._error(
                    "kea_ha_this_server_name",
                    f"{_HA} this_server_name must equal the name of a declared peer",
                )
            return
        self.report.add_check(
            check_name="kea_ha_this_server_name_empty",
            passed=True,
            message=(
                f"{_HA} this_server_name is empty: each node falls back to its own "
                f"hostname, so the peer names must equal the nodes' hostnames "
                f"(not checkable offline)"
            ),
            level=ValidationLevel.INFO,
        )

    # -- peers --------------------------------------------------------------------

    def _check_duplicates(self, peers: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for peer in peers:
            name = self._peer_name(peer)
            if not isinstance(name, str):
                continue
            (dupes if name in seen else seen).add(name)
        if dupes:
            self._error(
                "kea_ha_peers_unique_names",
                f"{_PEERS} resources share names: {sorted(dupes)!r}. "
                f"The name is the identity on the box; make each unique.",
            )

    def _validate_peer(self, resource: ResourceConfig) -> None:
        config = resource.config
        label = f"kea ha peer '{resource.name}'"
        prefix = f"kea_ha_peer_{resource.name}"
        for key in sorted(set(config) - ha_svc.PEER_ALLOWED_KEYS):
            if key in ha_svc.PEER_BOX_ASSIGNED_KEYS:
                message = f"{label} must not set '{key}': the box assigns it"
            else:
                message = (
                    f"{label} has unknown key '{key}'; allowed: {sorted(ha_svc.PEER_ALLOWED_KEYS)}"
                )
            self._error(f"{prefix}_unknown_key_{key}", message)
        name = self._peer_name(resource)
        if not isinstance(name, str) or not name.strip():
            self._error(f"{prefix}_name", f"{label} requires a non-empty name")
        if config.get("role") not in ha_svc.PEER_ROLES:
            self._error(
                f"{prefix}_role", f"{label} role must be one of: {', '.join(ha_svc.PEER_ROLES)}"
            )
        url = config.get("url")
        if not isinstance(url, str) or not _URL.match(url.strip()):
            self._error(f"{prefix}_url", f"{label} url must be an http(s)://host[:port] URL")
        if "lock" in config and not isinstance(config["lock"], bool):
            self._error(f"{prefix}_lock", f"{label} lock must be a boolean")
