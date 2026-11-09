"""ACME-client settings service for OPNsense direct-API operations (#790).

Manages the ``settings`` section of the ``os-acme-client`` plugin through
``GET acmeclient/settings/get``, ``POST acmeclient/settings/set``,
``POST acmeclient/settings/fetchCronIntegration`` and
``POST acmeclient/service/reconfigure``.

YAML keys (all optional; only declared keys are compared and written) and their
wire fields under ``acmeclient.settings``:

- ``enabled``              -> ``enabled`` (bool)
- ``auto_renewal``         -> ``autoRenewal`` (bool)
- ``environment``          -> ``environment`` (``""``, ``prod`` or ``stg``)
- ``challenge_port``       -> ``challengePort`` (1-65535)
- ``tls_challenge_port``   -> ``TLSchallengePort`` (1-65535)
- ``restart_timeout``      -> ``restartTimeout`` (non-negative int)
- ``haproxy_integration``  -> ``haproxyIntegration`` (bool)
- ``haproxy_acl_ref``, ``haproxy_action_ref``, ``haproxy_server_ref``,
  ``haproxy_backend_ref`` -> ``haproxyAclRef`` and friends (passive strings)
- ``log_level``            -> ``logLevel`` (``normal``, ``extended``, ``debug``,
  ``debug2`` or ``debug3``)
- ``show_intro``           -> ``showIntro`` (bool)

``UpdateCron`` (the plugin's renewal cron job) is plugin-managed: it is not a YAML key,
it is never diffed, and the write body echoes the live value unchanged. After a write
with renewal on, the manager calls ``settings/fetchCronIntegration`` so the plugin
creates or repairs its own job.

Write envelope: ``{"acmeclient": {"settings": {...}}}``. The apply posts the whole
flattened live ``settings`` section with the declared fields overwritten, so undeclared
settings stay unchanged.

Unverified live: ``set``, ``fetchCronIntegration`` and ``reconfigure`` (see the coverage
document). The GET shape was probed on 26.1.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

#: YAML key -> wire key under ``acmeclient.settings``.
FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "auto_renewal": "autoRenewal",
    "environment": "environment",
    "challenge_port": "challengePort",
    "tls_challenge_port": "TLSchallengePort",
    "restart_timeout": "restartTimeout",
    "haproxy_integration": "haproxyIntegration",
    "haproxy_acl_ref": "haproxyAclRef",
    "haproxy_action_ref": "haproxyActionRef",
    "haproxy_server_ref": "haproxyServerRef",
    "haproxy_backend_ref": "haproxyBackendRef",
    "log_level": "logLevel",
    "show_intro": "showIntro",
}

#: YAML keys whose value is a boolean (wire ``"1"``/``"0"``).
BOOL_FIELDS: frozenset[str] = frozenset(
    {"enabled", "auto_renewal", "haproxy_integration", "show_intro"}
)

#: YAML keys with a closed set of values.
ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "environment": ("", "prod", "stg"),
    "log_level": ("normal", "extended", "debug", "debug2", "debug3"),
}

#: YAML keys that are TCP ports.
PORT_FIELDS: frozenset[str] = frozenset({"challenge_port", "tls_challenge_port"})

#: YAML keys that are passive strings (HAProxy references, written as given).
STRING_FIELDS: frozenset[str] = frozenset(
    {"haproxy_acl_ref", "haproxy_action_ref", "haproxy_server_ref", "haproxy_backend_ref"}
)

#: Plugin-managed wire field: never mapped, only echoed back.
CRON_WIRE_KEY = "UpdateCron"


def _flatten(value: Any) -> str:
    """Flatten a live field into its wire string.

    An option dict flattens to the comma-joined selected keys. ``None`` and ``[]``
    flatten to ``""``.
    """
    if isinstance(value, dict):
        return ",".join(
            str(key)
            for key, meta in value.items()
            if str(key) and isinstance(meta, dict) and meta.get("selected")
        )
    if value is None or value == []:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def serialize_setting(key: str, value: Any) -> str:
    """Serialize one settings value to its wire string.

    Raises:
        InvalidConfigurationError: On a wrong type or out-of-range value (no value shown).
    """
    label = f"acmeclient.settings {key}"
    if key in BOOL_FIELDS:
        if not isinstance(value, bool):
            raise InvalidConfigurationError(f"{label} must be a boolean")
        return "1" if value else "0"
    if key in ENUM_FIELDS:
        if not isinstance(value, str) or value not in ENUM_FIELDS[key]:
            raise InvalidConfigurationError(f"{label} must be one of {list(ENUM_FIELDS[key])}")
        return value
    if key in STRING_FIELDS:
        if not isinstance(value, str):
            raise InvalidConfigurationError(f"{label} must be a string")
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidConfigurationError(f"{label} must be an integer")
    if key in PORT_FIELDS:
        if not 1 <= value <= 65535:
            raise InvalidConfigurationError(f"{label} must be in range 1-65535")
    elif value < 0:
        raise InvalidConfigurationError(f"{label} must be a non-negative integer")
    return str(value)


class AcmeClientSettingsService(BaseService):
    """Service for the ACME-client settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the ACME-client settings document."""
        ep = endpoints.ACMECLIENT_SETTINGS_GET
        return self.client.request(ep.method, ep.path())

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the ACME-client settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.ACMECLIENT_SETTINGS_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set acmeclient settings")

    def fetch_cron_integration(self) -> Any:
        """Ask the plugin to create or repair its renewal cron job.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.ACMECLIENT_FETCH_CRON
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "fetch acmeclient cron integration")

    def reconfigure(self) -> Any:
        """Apply the saved ACME-client configuration.

        Called only by the provider's ``_reconfigure_acmeclient`` finalization hook
        (and by a list manager's destroy); the settings manager must not call it.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.ACMECLIENT_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure acmeclient")

    def live_settings(self, response: Any) -> dict[str, Any]:
        """Return ``response["acmeclient"]["settings"]``.

        Raises:
            APIError: If the envelope is missing, so a write is never built from nothing.
        """
        acme = response.get("acmeclient") if isinstance(response, dict) else None
        settings = acme.get("settings") if isinstance(acme, dict) else None
        if not isinstance(settings, dict):
            raise APIError(
                "OPNsense acmeclient/settings/get returned no acmeclient.settings object",
                response=str(response)[:200],
                provider="opnsense",
            )
        return settings

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            hint = " (UpdateCron is managed by the plugin)" if "update_cron" in unknown else ""
            raise InvalidConfigurationError(
                f"acmeclient.settings has unknown key(s): {', '.join(unknown)}{hint}"
            )
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            desired[key] = serialize_setting(key, config[key])
        return desired

    def extract_live(self, settings: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings.

        Raises:
            APIError: If a requested field is absent from the live object.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = FIELD_MAP[key]
            if wire not in settings:
                raise APIError(
                    f"OPNsense acmeclient/settings/get returned no '{wire}' field",
                    response=str(sorted(settings))[:200],
                    provider="opnsense",
                )
            live[key] = _flatten(settings[wire])
        return live

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    def build_set_payload(
        self, settings: dict[str, Any], desired: dict[str, str]
    ) -> dict[str, Any]:
        """Build the write body: the whole flattened live section with declared fields set.

        ``UpdateCron`` is echoed back unchanged.
        """
        flat = {key: _flatten(value) for key, value in settings.items()}
        for key, value in desired.items():
            flat[FIELD_MAP[key]] = value
        return {"acmeclient": {"settings": flat}}

    @staticmethod
    def renewal_effective(payload: dict[str, Any]) -> bool:
        """Return True when the write body has ``enabled`` and ``autoRenewal`` both on."""
        flat = payload["acmeclient"]["settings"]
        return bool(flat.get("enabled") == "1" and flat.get("autoRenewal") == "1")

    def export_to_yaml(self) -> str:
        """Export every mapped field present on the box as nested YAML.

        Empty HAProxy references are omitted. A live integer that is not a
        non-negative digit string is logged and omitted.
        """
        settings = self.live_settings(self.get_settings())
        present = [key for key, wire in FIELD_MAP.items() if wire in settings]
        live = self.extract_live(settings, present)
        clean: dict[str, Any] = {}
        for key in present:
            text = live[key]
            if key in BOOL_FIELDS:
                clean[key] = text == "1"
            elif key in STRING_FIELDS:
                if text:
                    clean[key] = text
            elif key in ENUM_FIELDS:
                clean[key] = text
            elif text.isascii() and text.isdigit():
                clean[key] = int(text)
            else:
                logger.warning("acmeclient.settings: non-integer %s %r; omitted", key, text)
        return emit_nested_singleton_yaml("acmeclient.settings", clean)
