"""Parse legacy OPNsense filter rules from ``config.xml`` into automation rules (#1497).

Legacy rules (``<filter><rule>`` in ``config.xml``) are not visible to the MVC filter
API that :mod:`.firewall_rule` manages. This module is a pure mapper with no I/O: it
takes the configuration backup text and returns entries in the ``firewall.rules``
schema, in document order, plus the list of things it could not carry over.

Safety
------

``config.xml`` holds secrets. It is parsed with :mod:`defusedxml` (no entity expansion,
no external entities), kept in memory, and never put in an exception message or a log
line. Issue lines name the rule and the field, never the document.

Mapping
-------

- ``type`` -> ``action``; ``descr`` -> ``description`` (an identity marker is stripped
  and reported); ``disabled`` -> ``enabled: false``.
- ``interface`` must be one identifier from ``<interfaces>``, ``<ifgroups>`` or the
  built-in virtual set. A floating rule may leave it empty. A comma-separated list
  cannot be expressed (the schema's ``interface`` is single-valued); that rule is
  skipped and reported, as is a rule naming an unknown interface.
- ``floating`` -> ``state_policy: floating`` with ``quick`` and ``direction`` read from
  the XML; a non-floating rule gets ``quick: true`` and ``direction: in``.
- ``protocol`` is upper-cased (``any`` stays), ``ipprotocol`` defaults to ``inet``.
- ``source`` / ``destination``: ``any``, ``address``, ``network`` (verbatim), ``not``
  and ``port``.
- ``statetype`` maps through the service's option-key table; ``category`` names (or
  UUIDs) resolve to category UUIDs through ``OPNsense/Firewall/Category``.
- Every other element whose name is an MVC wire key is carried over by kind.
- ``sched``, ``dnpipe``, ``pdnpipe``, ``os`` and ``associated-rule-id`` have no
  counterpart and are reported; so is any other non-empty unknown element.

The value vocabulary (network keywords passed verbatim, protocol casing) is inferred
from the legacy format, not proven against a real export.

Order
-----

Rules get ``sequence_start``, ``sequence_start + step`` ... in document order. Callers
pass a start above every live automation sequence so the exported set keeps the
legacy relative order.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET
from defusedxml.ElementTree import ParseError

from infrafoundry.core.exceptions import APIError

from ._identity import has_identity_marker
from .firewall_rule import (
    _PAYLOAD_FIELD_MAP,
    _STATETYPE_TO_KEY,
    ACTION_CHOICES,
    DIRECTION_CHOICES,
    IPPROTOCOL_CHOICES,
    STATE_POLICY_CHOICES,
)

if TYPE_CHECKING:  # pragma: no cover
    from xml.etree.ElementTree import Element  # nosec B405  # typing only; parsing is defused

_Report = Callable[[str, str], None]

#: Identifiers that are valid rule interfaces without a ``<interfaces>`` child.
_BUILTIN_INTERFACES: frozenset[str] = frozenset({"openvpn", "wireguard", "enc0"})

#: Extra ``<network>`` keywords that are not an interface name.
_NETWORK_KEYWORDS: frozenset[str] = frozenset({"(self)", "pppoe", "l2tp", "pptp"})

#: Elements with no automation-rule counterpart: reported when non-empty.
_UNSUPPORTED_ELEMENTS: frozenset[str] = frozenset(
    {"sched", "dnpipe", "pdnpipe", "os", "associated-rule-id"}
)

#: Elements that carry nothing to export.
_IGNORED_ELEMENTS: frozenset[str] = frozenset({"tracker", "created", "updated", "id"})

#: Elements this module maps by hand (so the generic wire-key pass skips them).
_SPECIAL_ELEMENTS: frozenset[str] = frozenset(
    {
        "type",
        "interface",
        "ipprotocol",
        "statetype",
        "descr",
        "protocol",
        "source",
        "destination",
        "disabled",
        "log",
        "floating",
        "quick",
        "direction",
        "category",
    }
)

#: MVC wire keys the generic pass must not copy (set by hand or server-computed).
_GENERIC_SKIP_WIRE_KEYS: frozenset[str] = frozenset(
    {
        "enabled",
        "sequence",
        "sort_order",
        "prio_group",
        "action",
        "quick",
        "interface",
        "direction",
        "ipprotocol",
        "protocol",
        "source_net",
        "source_not",
        "source_port",
        "destination_net",
        "destination_not",
        "destination_port",
        "log",
        "description",
        "statetype",
    }
)

_TRUE_TEXT: frozenset[str] = frozenset({"", "1", "yes", "on", "true"})
_IDENTITY_MARKER = re.compile(r"\s*\[infrafoundry:[^\]]*\]")
_SLUG_MAX = 48


@dataclass(frozen=True)
class LegacyRuleIssue:
    """One thing about a legacy rule that did not carry over.

    Attributes:
        rule_label: Which rule (its description, or its position and interface).
        field: The XML element or field concerned.
        reason: Why it was not exported.
    """

    rule_label: str
    field: str
    reason: str

    def __str__(self) -> str:
        """Render as one line."""
        return f"{self.rule_label}: {self.field}: {self.reason}"


@dataclass
class LegacyExport:
    """The result of mapping the legacy rules.

    Attributes:
        entries: ``{"name": ..., "config": {...}}`` dicts in document order.
        issues: What was not exported.
    """

    entries: list[dict[str, Any]] = field(default_factory=list)
    issues: list[LegacyRuleIssue] = field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:_SLUG_MAX].strip("-")


def _text(elem: Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _flag(elem: Element | None) -> bool:
    """Legacy booleans are presence flags, optionally with a text value."""
    if elem is None:
        return False
    return _text(elem).lower() in _TRUE_TEXT


def _interface_ids(root: Element) -> set[str]:
    known: set[str] = set(_BUILTIN_INTERFACES)
    interfaces = root.find("interfaces")
    if interfaces is not None:
        known.update(child.tag for child in interfaces)
    for entry in root.findall("ifgroups/ifgroupentry"):
        name = _text(entry.find("ifname"))
        if name:
            known.add(name)
    return known


def _category_maps(root: Element) -> tuple[dict[str, str], set[str]]:
    """Return ``({name: uuid}, {uuid})`` from ``OPNsense/Firewall/Category``."""
    by_name: dict[str, str] = {}
    uuids: set[str] = set()
    for cat in root.findall("OPNsense/Firewall/Category/categories/category"):
        uuid = cat.get("uuid", "")
        name = _text(cat.find("name"))
        if uuid:
            uuids.add(uuid)
            if name:
                by_name[name] = uuid
    return by_name, uuids


def parse_legacy_rules(
    xml_text: str,
    *,
    reserved: set[str],
    sequence_start: int,
    sequence_step: int = 10,
) -> LegacyExport:
    """Map the legacy filter rules in a ``config.xml`` to ``firewall.rules`` entries.

    Args:
        xml_text: The configuration backup. It may hold secrets; it is not logged and
            not echoed into any error.
        reserved: Resource names already taken in the environment.
        sequence_start: ``sequence`` of the first exported rule.
        sequence_step: Increment between exported rules.

    Returns:
        The entries in document order and the issues found.

    Raises:
        APIError: If the text is not well-formed XML or uses entities or a DTD.
    """
    try:
        root = SafeET.fromstring(xml_text)
    except (DefusedXmlException, ParseError):
        # Never chain or format the cause: a parse error can quote document text.
        raise APIError("config backup is not valid XML", provider="opnsense") from None

    known_interfaces = _interface_ids(root)
    cat_by_name, cat_uuids = _category_maps(root)
    taken = set(reserved)
    result = LegacyExport()
    sequence = sequence_start

    for index, rule in enumerate(root.findall("./filter/rule"), start=1):
        # OPNsense leaves an empty <rule/> under <filter> after every legacy rule is
        # deleted. It is not a rule: skip it silently. ``index`` still counts it, so
        # reports keep pointing at the document position of the real rules.
        if len(rule) == 0:
            continue
        outcome = _map_rule(
            rule,
            index=index,
            known_interfaces=known_interfaces,
            cat_by_name=cat_by_name,
            cat_uuids=cat_uuids,
            issues=result.issues,
        )
        if outcome is None:
            continue
        mapped, description, scope = outcome
        base = _slug(description) or f"{scope}-rule-{index}"
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}-{n}"
        taken.add(name)
        mapped["sequence"] = sequence
        sequence += sequence_step
        result.entries.append({"name": name, "config": mapped})
    return result


def _map_rule(
    rule: Element,
    *,
    index: int,
    known_interfaces: set[str],
    cat_by_name: dict[str, str],
    cat_uuids: set[str],
    issues: list[LegacyRuleIssue],
) -> tuple[dict[str, Any], str, str] | None:
    """Map one rule.

    Returns:
        ``(config, description, scope)``, or ``None`` when the rule cannot be expressed
        (the reason is in ``issues``).
    """
    raw_descr = _text(rule.find("descr"))
    interface = _text(rule.find("interface"))
    floating = _flag(rule.find("floating"))
    scope = "floating" if floating else (interface or "any")
    label = f'rule #{index} "{raw_descr}"' if raw_descr else f"rule #{index} ({scope})"

    def report(field_name: str, reason: str) -> None:
        issues.append(LegacyRuleIssue(label, field_name, reason))

    action = _text(rule.find("type")) or "pass"
    if action not in ACTION_CHOICES:
        report("type", f"unsupported action {action!r}; rule skipped")
        return None

    if "," in interface:
        report("interface", "several interfaces cannot be expressed; rule skipped")
        return None
    if interface and interface not in known_interfaces:
        report("interface", f"unknown interface {interface!r}; rule skipped")
        return None
    if not interface and not floating:
        report("interface", "no interface on a non-floating rule; rule skipped")
        return None

    description = raw_descr
    if has_identity_marker(description):
        description = _IDENTITY_MARKER.sub("", description).strip()
        report("descr", "contained an InfraFoundry identity marker; removed")

    config: dict[str, Any] = {"action": action, "interface": interface}
    if description:
        config["description"] = description
    if _flag(rule.find("disabled")):
        config["enabled"] = False
    if _flag(rule.find("log")):
        config["log"] = True

    if floating:
        config["state_policy"] = "floating"
        config["quick"] = _flag(rule.find("quick"))
        direction = _text(rule.find("direction")) or "in"
    else:
        config["quick"] = True
        direction = "in"
    if direction not in DIRECTION_CHOICES:
        report("direction", f"unsupported direction {direction!r}; using 'in'")
        direction = "in"
    config["direction"] = direction

    ipprotocol = _text(rule.find("ipprotocol")) or "inet"
    if ipprotocol not in IPPROTOCOL_CHOICES:
        report("ipprotocol", f"unsupported value {ipprotocol!r}; using 'inet'")
        ipprotocol = "inet"
    config["ipprotocol"] = ipprotocol

    protocol = _text(rule.find("protocol"))
    config["protocol"] = "any" if protocol.lower() in ("", "any") else protocol.upper()

    for side in ("source", "destination"):
        _map_endpoint(rule.find(side), side, config, known_interfaces, report)

    statetype = _text(rule.find("statetype"))
    if statetype:
        if statetype in _STATETYPE_TO_KEY:
            config["statetype"] = _STATETYPE_TO_KEY[statetype]
        else:
            report("statetype", f"unsupported value {statetype!r}; not exported")

    categories = _map_categories(_text(rule.find("category")), cat_by_name, cat_uuids, report)
    if categories:
        config["categories"] = categories

    _map_generic(rule, config, report)

    for child in rule:
        tag = child.tag
        if tag in _SPECIAL_ELEMENTS or tag in _IGNORED_ELEMENTS or tag in _GENERIC_WIRE_KEYS:
            continue
        if not (_text(child) or len(child)):
            continue
        if tag in _UNSUPPORTED_ELEMENTS:
            report(tag, "has no automation-rule counterpart; not exported")
        else:
            report(tag, "unknown element; not exported")

    return config, description, scope


_GENERIC_WIRE_KEYS: frozenset[str] = frozenset(
    wire for _, wire, _ in _PAYLOAD_FIELD_MAP if wire not in _GENERIC_SKIP_WIRE_KEYS
)


def _map_generic(rule: Element, config: dict[str, Any], report: _Report) -> None:
    """Copy the remaining MVC wire-key elements by kind."""
    for attr, wire, kind in _PAYLOAD_FIELD_MAP:
        if wire in _GENERIC_SKIP_WIRE_KEYS:
            continue
        elem = rule.find(wire)
        if elem is None or (kind != "bool" and not _text(elem)):
            continue
        if kind == "bool":
            if _flag(elem):
                config[attr] = True
        elif attr == "state_policy":
            value = _text(elem)
            if value not in STATE_POLICY_CHOICES:
                report(wire, f"unsupported value {value!r}; not exported")
            elif "state_policy" not in config:
                config[attr] = value
        else:
            config[attr] = _text(elem)


def _map_endpoint(
    elem: Element | None,
    side: str,
    config: dict[str, Any],
    known_interfaces: set[str],
    report: _Report,
) -> None:
    """Map ``<source>`` / ``<destination>`` onto ``<side>_net`` / ``_not`` / ``_port``."""
    net = "any"
    if elem is not None:
        address = _text(elem.find("address"))
        network = _text(elem.find("network"))
        if address:
            net = address
        elif network:
            net = network
            base = network[:-2] if network.endswith("ip") else network
            if (
                network not in known_interfaces
                and base not in known_interfaces
                and network not in _NETWORK_KEYWORDS
            ):
                report(side, f"unknown network {network!r}; exported verbatim")
        if _flag(elem.find("not")):
            config[f"{side}_not"] = True
        port = _text(elem.find("port"))
        if port:
            config[f"{side}_port"] = port
        for child in elem:
            if child.tag not in {"any", "address", "network", "not", "port"} and (
                _text(child) or len(child)
            ):
                report(f"{side}/{child.tag}", "unknown element; not exported")
    config[f"{side}_net"] = net


def _map_categories(
    raw: str,
    by_name: dict[str, str],
    uuids: set[str],
    report: _Report,
) -> list[str]:
    """Resolve a comma-separated category list to UUIDs."""
    resolved: list[str] = []
    for token in (part.strip() for part in raw.split(",")):
        if not token:
            continue
        if token in uuids:
            resolved.append(token)
        elif token in by_name:
            resolved.append(by_name[token])
        else:
            report("category", f"unknown category {token!r}; not exported")
    return resolved
