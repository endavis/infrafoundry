"""Monit settings service for OPNsense direct-API operations (ADR-0014, #791).

Manages the ``general`` section of the core monit module through
``GET monit/settings/get`` and ``POST monit/settings/set``; ``POST
monit/service/reconfigure`` applies it.

The OPNsense API has no ``setGeneral`` action. ``settings/get`` returns the whole model
(``general`` plus the ``alert``, ``service`` and ``test`` rows keyed by UUID) and
``settings/set`` takes ``{"monit": {"general": {...}}}``.

YAML keys (all optional; only declared keys are compared and written) and their wire
fields under ``monit.general``:

- ``enabled``, ``interval``, ``start_delay`` (``startdelay``)
- ``mailserver`` (list), ``port``, ``username``, ``password`` (secret)
- ``ssl``, ``ssl_version`` (``sslversion``), ``ssl_verify`` (``sslverify``)
- ``logfile``, ``statefile``, ``eventqueue_path`` (``eventqueuePath``),
  ``eventqueue_slots`` (``eventqueueSlots``)
- ``httpd_enabled``, ``httpd_username``, ``httpd_password`` (secret), ``httpd_port``,
  ``httpd_allow`` (list), all ``httpd*`` on the wire
- ``mmonit_url`` (secret, it may carry credentials), ``mmonit_timeout``,
  ``mmonit_register_credentials``, all ``mmonit*`` on the wire

Secrets
-------

``password``, ``httpd_password`` and ``mmonit_url`` take ``secret://`` URIs that the
manager resolves before this module runs. They are compared plainly against the live
value. They are never logged, put in a message, a ``repr`` or a plan map (:func:`redacted`
swaps them for ``[REDACTED]``). The write body echoes the flattened live ``general`` with
the declared fields overwritten but never a live secret field the operator did not
declare: MVC ``setNodes`` leaves a field that is not posted alone, so a masked value can
never clobber the stored one.

What is verified and what is not
--------------------------------

See ``docs/development/opnsense-resource-coverage.md`` (section "Monit").
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .acmeclient import BOOL, ENUM, INT, STR, FieldSpec
from .base import BaseService, raise_on_failed_write
from .monit import LIST, fetch_model, serialize_field
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

_SSL_VERSIONS: tuple[str, ...] = ("auto", "tlsv1", "tlsv11", "tlsv12", "tlsv13")

#: YAML key -> :class:`FieldSpec` (wire name and kind) under ``monit.general``.
FIELDS: dict[str, FieldSpec] = {
    "enabled": FieldSpec("enabled", BOOL),
    "interval": FieldSpec("interval", INT, low=1),
    "start_delay": FieldSpec("startdelay", INT),
    "mailserver": FieldSpec("mailserver", LIST),
    "port": FieldSpec("port", INT, low=1, high=65535),
    "username": FieldSpec("username", STR),
    "password": FieldSpec("password", STR),
    "ssl": FieldSpec("ssl", BOOL),
    "ssl_version": FieldSpec("sslversion", ENUM, _SSL_VERSIONS),
    "ssl_verify": FieldSpec("sslverify", BOOL),
    "logfile": FieldSpec("logfile", STR),
    "statefile": FieldSpec("statefile", STR),
    "eventqueue_path": FieldSpec("eventqueuePath", STR),
    "eventqueue_slots": FieldSpec("eventqueueSlots", INT),
    "httpd_enabled": FieldSpec("httpdEnabled", BOOL),
    "httpd_username": FieldSpec("httpdUsername", STR),
    "httpd_password": FieldSpec("httpdPassword", STR),
    "httpd_port": FieldSpec("httpdPort", INT, low=1, high=65535),
    "httpd_allow": FieldSpec("httpdAllow", LIST),
    "mmonit_url": FieldSpec("mmonitUrl", STR),
    "mmonit_timeout": FieldSpec("mmonitTimeout", INT),
    "mmonit_register_credentials": FieldSpec("mmonitRegisterCredentials", BOOL),
}

#: YAML keys that hold a secret.
SECRET_FIELDS: tuple[str, ...] = ("password", "httpd_password", "mmonit_url")

#: What replaces a secret in a plan map.
REDACTED = "[REDACTED]"

_SECRET_WIRES: frozenset[str] = frozenset(FIELDS[k].wire for k in SECRET_FIELDS)


def secret_placeholder(key: str) -> str:
    """Return the ``secret://`` placeholder that migrate writes for a secret key."""
    return f"secret://env_secrets/opnsense/monit/settings/{key}"


def serialize_setting(key: str, value: Any) -> str:
    """Serialize one settings value to its wire string.

    Raises:
        InvalidConfigurationError: On a wrong type or out-of-range value (no value shown).
    """
    try:
        return serialize_field("monit.settings", key, FIELDS[key], value)
    except ValueError as exc:
        raise InvalidConfigurationError(str(exc)) from None


def redacted(desired: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of the desired map that is safe to show: secrets are replaced."""
    return {k: (REDACTED if k in SECRET_FIELDS else v) for k, v in desired.items()}


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class MonitSettingsService(BaseService):
    """Service for the monit settings singleton."""

    def get_model(self) -> dict[str, Any]:
        """Fetch ``settings/get`` and return the ``monit`` model object.

        Raises:
            APIError: If the envelope is missing; the message carries key names only.
        """
        return fetch_model(self.client)

    @staticmethod
    def live_general(model: Mapping[str, Any]) -> dict[str, Any]:
        """Return ``model["general"]``.

        Raises:
            APIError: If it is missing, so a write is never built from nothing.
        """
        general = model.get("general")
        if not isinstance(general, dict):
            raise APIError(
                "OPNsense monit/settings/get returned no general object",
                response=str(sorted(model)),
                provider="opnsense",
            )
        return general

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.MONIT_SETTINGS_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set monit settings")

    def reconfigure(self) -> Any:
        """Apply the saved monit configuration.

        Called by the provider's ``monit_reconfigure`` finalization hook and by a list
        manager's destroy; the settings manager must not call it.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.MONIT_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure monit")

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELDS))
        if unknown:
            raise InvalidConfigurationError(
                f"monit.settings has unknown key(s): {', '.join(unknown)}"
            )
        return {key: serialize_setting(key, config[key]) for key in FIELDS if key in config}

    def extract_live(self, general: Mapping[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings.

        Raises:
            APIError: If a requested field is absent from the live object.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = FIELDS[key].wire
            if wire not in general:
                raise APIError(
                    f"OPNsense monit/settings/get returned no '{wire}' field",
                    response=str(sorted(general))[:200],
                    provider="opnsense",
                )
            flat = flatten_option(general[wire]).strip()
            if FIELDS[key].kind == BOOL:
                flat = "1" if flat == "1" else "0"
            live[key] = flat
        return live

    def drift(self, live: Mapping[str, str], desired: Mapping[str, str]) -> list[str]:
        """Return the YAML keys whose live value differs from the desired one.

        Lists compare as sets. Field names only, never values.
        """
        changed: list[str] = []
        for key, value in desired.items():
            have = live.get(key, "")
            if FIELDS[key].kind == LIST:
                if frozenset(_split(have)) != frozenset(_split(value)):
                    changed.append(key)
            elif have != value:
                changed.append(key)
        return changed

    def build_set_payload(
        self, general: Mapping[str, Any], desired: Mapping[str, str]
    ) -> dict[str, Any]:
        """Build the write body: the flattened live section with declared fields set.

        A live secret field the operator did not declare is left out.
        """
        declared = {FIELDS[key].wire for key in desired}
        flat = {
            wire: flatten_option(value)
            for wire, value in general.items()
            if wire not in _SECRET_WIRES or wire in declared
        }
        for key, value in desired.items():
            flat[FIELDS[key].wire] = value
        return {"monit": {"general": flat}}

    def export_to_yaml(self) -> str:
        """Export every mapped field present on the box as nested YAML.

        A non-empty secret becomes a ``secret://`` placeholder and an empty one ``""``.
        An empty or non-numeric integer is omitted.
        """
        general = self.live_general(self.get_model())
        present = [key for key, spec in FIELDS.items() if spec.wire in general]
        live = self.extract_live(general, present)
        clean: dict[str, Any] = {}
        for key in present:
            text = live[key]
            kind = FIELDS[key].kind
            if key in SECRET_FIELDS:
                clean[key] = secret_placeholder(key) if text else ""
            elif kind == BOOL:
                clean[key] = text == "1"
            elif kind == LIST:
                clean[key] = sorted(_split(text))
            elif kind == INT:
                if text.isascii() and text.isdigit():
                    clean[key] = int(text)
                elif text:
                    logger.warning("monit.settings: non-integer %s; omitted", key)
            else:
                clean[key] = text
        return emit_nested_singleton_yaml("monit.settings", clean)
