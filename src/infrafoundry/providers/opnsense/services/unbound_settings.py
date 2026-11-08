"""Unbound general and advanced settings service for OPNsense direct-API operations (#1091).

Manages the ``general`` and ``advanced`` sections of the Unbound settings document through
``GET unbound/settings/get`` and ``POST unbound/settings/set``. The YAML shape is a
singleton with optional ``general:`` and ``advanced:`` mappings whose keys are the
OPNsense wire field names verbatim.

``privatedomain``, ``insecuredomain`` and ``privateaddress`` stay owned by
``unbound.advanced`` (#1254); declaring one here is a configuration error that names the
``unbound.advanced`` key to use. Both resources echo the whole live section back on write
with only their own declared fields overwritten, so they coexist in either order.

Write envelope: ``{"unbound": {<section>: <whole flattened live section, declared fields
overwritten>}}`` for declared sections only, the same envelope ``unbound.advanced`` uses.
Sending the whole section keeps undeclared settings unchanged.

``SECTIONS`` is the one allowed-key source. :func:`check_config` is shared by
``build_desired`` (which raises) and the validator (which reports each result as an ERROR).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write
from .unbound_advanced import FIELD_MAP as ADVANCED_FIELD_MAP

_BOOL = "bool"
_PORT = "port"
_ENUM = "enum"
_MULTI = "multi"
_PREFIX = "prefix"
_TEXT = "text"
_INDEX = "index"
_TUNING = "tuning"

#: Section -> wire field -> kind.
SECTIONS: dict[str, dict[str, str]] = {
    "general": {
        **dict.fromkeys(
            (
                "enabled",
                "stats",
                "dnssec",
                "dns64",
                "noarecords",
                "regdhcp",
                "regdhcpstatic",
                "noreglladdr6",
                "noregrecords",
                "txtsupport",
                "cacheflush",
                "safesearch",
                "enable_wpad",
            ),
            _BOOL,
        ),
        "port": _PORT,
        "local_zone_type": _ENUM,
        "active_interface": _MULTI,
        "outgoing_interface": _MULTI,
        "dns64prefix": _PREFIX,
        "regdhcpdomain": _TEXT,
    },
    "advanced": {
        **dict.fromkeys(
            (
                "hideidentity",
                "hideversion",
                "prefetch",
                "prefetchkey",
                "dnssecstripped",
                "belownxdomain",
                "aggressivensec",
                "serveexpired",
                "serveexpiredttlreset",
                "qnameminstrict",
                "extendedstatistics",
                "logqueries",
                "logreplies",
                "logtagqueryreply",
                "logservfail",
                "loglocalactions",
                "infrakeepprobing",
            ),
            _BOOL,
        ),
        "logverbosity": _INDEX,
        "valloglevel": _INDEX,
        **dict.fromkeys(
            (
                "serveexpiredreplyttl",
                "serveexpiredttl",
                "serveexpiredclienttimeout",
                "msgcachesize",
                "rrsetcachesize",
                "outgoingnumtcp",
                "incomingnumtcp",
                "numqueriesperthread",
                "outgoingrange",
                "jostletimeout",
                "discardtimeout",
                "cachemaxttl",
                "cachemaxnegativettl",
                "cacheminttl",
                "infrahostttl",
                "infracachenumhosts",
                "unwantedreplythreshold",
            ),
            _TUNING,
        ),
    },
}

#: Accepted ``local_zone_type`` values.
LOCAL_ZONE_TYPES: tuple[str, ...] = (
    "transparent",
    "always_nxdomain",
    "always_refuse",
    "always_transparent",
    "deny",
    "inform",
    "inform_deny",
    "nodefault",
    "refuse",
    "static",
    "typetransparent",
)

#: Highest valid index of the option-list fields.
INDEX_MAX: dict[str, int] = {"logverbosity": 5, "valloglevel": 2}

#: Owned field (wire name or ``unbound.advanced`` YAML key) -> the ``unbound.advanced`` key.
OWNED_BY_ADVANCED: dict[str, str] = {
    **{wire: key for key, wire in ADVANCED_FIELD_MAP.items()},
    **{key: key for key in ADVANCED_FIELD_MAP},
}

#: A desired value: wire string, or a set of keys for the multi-select fields.
DesiredValue = str | frozenset[str]
Desired = dict[str, dict[str, DesiredValue]]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bad_token(value: str) -> bool:
    return any(ch.isspace() or ch == "," for ch in value)


def _check_field(label: str, kind: str, wire: str, value: Any) -> str | None:
    """Return an error message for one field value, or ``None`` when it is valid."""
    if kind == _BOOL:
        return None if isinstance(value, bool) else f"{label} must be a boolean"
    if kind == _PORT:
        if _is_int(value) and 1 <= value <= 65535:
            return None
        return f"{label} must be an integer between 1 and 65535"
    if kind == _ENUM:
        if isinstance(value, str) and value in LOCAL_ZONE_TYPES:
            return None
        return f"{label} must be one of: {', '.join(LOCAL_ZONE_TYPES)}"
    if kind == _MULTI:
        if (
            isinstance(value, list)
            and all(isinstance(v, str) for v in value)
            and not any(not v.strip() or _bad_token(v.strip()) for v in value)
        ):
            return None
        return f"{label} must be a list of non-empty strings without commas or whitespace"
    if kind == _PREFIX:
        if not isinstance(value, str):
            return f"{label} must be a string"
        if value.strip():
            try:
                ipaddress.ip_network(value.strip())
            except ValueError:
                return f"{label} '{value}' is not a valid network prefix"
        return None
    if kind == _TEXT:
        if isinstance(value, str) and not any(ch.isspace() for ch in value):
            return None
        return f"{label} must be a string without whitespace"
    if kind == _INDEX:
        top = INDEX_MAX[wire]
        if _is_int(value) and 0 <= value <= top:
            return None
        return f"{label} must be an integer between 0 and {top}"
    if _is_int(value) and value >= 0:
        return None
    if isinstance(value, str) and not _bad_token(value):
        return None
    return f"{label} must be a non-negative integer or a string without commas or whitespace"


def check_config(config: Any) -> list[tuple[str, str]]:
    """Check an ``unbound.settings`` config mapping.

    Args:
        config: The resource config (``general`` / ``advanced`` mappings).

    Returns:
        ``(check-name suffix, message)`` pairs; empty when the config is valid.
    """
    if not isinstance(config, dict):
        return [("config", "unbound.settings must be a mapping")]
    problems: list[tuple[str, str]] = []
    for name in sorted(set(config) - set(SECTIONS), key=str):
        problems.append((f"section_{name}", f"unbound.settings has unknown key '{name}'"))
    for section, fields in SECTIONS.items():
        if section not in config:
            continue
        body = config[section]
        if not isinstance(body, dict):
            problems.append((section, f"unbound.settings {section} must be a mapping"))
            continue
        for key in sorted(body, key=str):
            label = f"unbound.settings {section}.{key}"
            if key in OWNED_BY_ADVANCED:
                problems.append(
                    (
                        f"{section}_{key}",
                        f"{label} is managed by unbound.advanced; "
                        f"declare '{OWNED_BY_ADVANCED[key]}' there instead",
                    )
                )
            elif key not in fields:
                problems.append((f"{section}_{key}", f"{label} is not a known field"))
            else:
                message = _check_field(label, fields[key], key, body[key])
                if message:
                    problems.append((f"{section}_{key}", message))
    return problems


def _selected_keys(value: Any) -> list[str]:
    """Return the selected keys of an option dict, option list (indexes) or comma string."""
    if isinstance(value, list):
        return [
            str(index)
            for index, entry in enumerate(value)
            if isinstance(entry, dict) and entry.get("selected")
        ]
    if isinstance(value, dict):
        return [
            str(key)
            for key, meta in value.items()
            if str(key) and isinstance(meta, dict) and meta.get("selected")
        ]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _flatten(value: Any) -> str:
    """Flatten a live field into its wire string (selected keys joined with commas)."""
    if isinstance(value, list | dict):
        return ",".join(_selected_keys(value))
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


class UnboundSettingsService(BaseService):
    """Service for the Unbound ``general`` and ``advanced`` settings sections."""

    def get_settings(self) -> Any:
        """Fetch the Unbound settings document."""
        return self.client.request(
            endpoints.UNBOUND_SETTINGS_GET.method, endpoints.UNBOUND_SETTINGS_GET.path()
        )

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.UNBOUND_SETTINGS_SET.method,
            endpoints.UNBOUND_SETTINGS_SET.path(),
            data=payload,
        )
        return raise_on_failed_write(response, "set unbound settings")

    def live_sections(self, response: Any, sections: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return ``response["unbound"][<section>]`` for each requested section.

        Raises:
            APIError: If a section is missing, so a write is never built from nothing.
        """
        unbound = response.get("unbound") if isinstance(response, dict) else None
        live: dict[str, dict[str, Any]] = {}
        for section in sections:
            body = unbound.get(section) if isinstance(unbound, dict) else None
            if not isinstance(body, dict):
                raise APIError(
                    f"OPNsense unbound/settings/get returned no unbound.{section} section",
                    response=str(response)[:200],
                    provider="opnsense",
                )
            live[section] = body
        return live

    def build_desired(self, resource: ResourceConfig) -> Desired:
        """Build the desired values for the declared fields, per declared section.

        Raises:
            InvalidConfigurationError: When :func:`check_config` reports a problem.
        """
        config = resource.config
        problems = check_config(config)
        if problems:
            raise InvalidConfigurationError("; ".join(message for _, message in problems))
        desired: Desired = {}
        for section, fields in SECTIONS.items():
            body = config.get(section) or {}
            values: dict[str, DesiredValue] = {}
            for wire, kind in fields.items():
                if wire not in body:
                    continue
                value = body[wire]
                if kind == _BOOL:
                    values[wire] = "1" if value else "0"
                elif kind == _MULTI:
                    values[wire] = frozenset(v.strip() for v in value)
                elif isinstance(value, str):
                    values[wire] = value.strip()
                else:
                    values[wire] = str(value)
            if values:
                desired[section] = values
        return desired

    def extract_live(
        self, live: dict[str, dict[str, Any]], desired: Desired
    ) -> dict[str, dict[str, DesiredValue]]:
        """Extract the declared fields from the live sections.

        Raises:
            APIError: If a declared field is absent from its live section.
        """
        out: dict[str, dict[str, DesiredValue]] = {}
        for section, values in desired.items():
            out[section] = {}
            for wire in values:
                if wire not in live[section]:
                    raise APIError(
                        f"OPNsense unbound/settings/get returned no '{wire}' field "
                        f"in unbound.{section}",
                        response=str(sorted(live[section]))[:200],
                        provider="opnsense",
                    )
                raw = live[section][wire]
                out[section][wire] = (
                    frozenset(_selected_keys(raw))
                    if SECTIONS[section][wire] == _MULTI
                    else _flatten(raw)
                )
        return out

    def drift(self, live: Desired, desired: Desired) -> Desired | None:
        """Compare declared fields; return ``desired`` on any difference."""
        for section, values in desired.items():
            for wire, value in values.items():
                if live.get(section, {}).get(wire) != value:
                    return desired
        return None

    def build_set_payload(
        self, live: dict[str, dict[str, Any]], desired: Desired
    ) -> dict[str, Any]:
        """Build the write body: each declared section, flattened, with declared fields set."""
        body: dict[str, Any] = {}
        for section, values in desired.items():
            flat = {key: _flatten(value) for key, value in live[section].items()}
            for wire, value in values.items():
                flat[wire] = ",".join(sorted(value)) if isinstance(value, frozenset) else value
            body[section] = flat
        return {"unbound": body}

    def export_to_yaml(self) -> str:
        """Export every supported field present on the box as nested YAML.

        Empty text and empty lists are skipped; fields owned by ``unbound.advanced`` are
        never exported.
        """
        document = self.get_settings()
        unbound = document.get("unbound") if isinstance(document, dict) else None
        clean: dict[str, Any] = {}
        for section, fields in SECTIONS.items():
            body = unbound.get(section) if isinstance(unbound, dict) else None
            if not isinstance(body, dict):
                continue
            exported: dict[str, Any] = {}
            for wire, kind in fields.items():
                if wire not in body:
                    continue
                value = self._to_yaml_value(kind, body[wire])
                if value is not None:
                    exported[wire] = value
            if exported:
                clean[section] = exported
        return emit_nested_singleton_yaml("unbound.settings", clean)

    @staticmethod
    def _to_yaml_value(kind: str, raw: Any) -> Any:
        """Convert a live field to its YAML value, or ``None`` when empty."""
        if kind == _MULTI:
            return sorted(_selected_keys(raw)) or None
        text = _flatten(raw)
        if not text:
            return None
        if kind == _BOOL:
            return text == "1"
        if kind in (_PORT, _INDEX, _TUNING) and text.isdigit() and str(int(text)) == text:
            return int(text)
        return text
