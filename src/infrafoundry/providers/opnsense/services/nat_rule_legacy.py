"""Parse legacy OPNsense outbound NAT rules from ``config.xml`` (#1509).

The Source NAT API (``firewall/source_nat``) lists only rules created on the Source NAT
page or through the API. Rules created on the legacy Firewall > NAT > Outbound page live
in ``<nat><outbound><rule>`` in ``config.xml`` and are invisible to it. This module is a
pure mapper with no I/O: it takes the configuration backup text and returns entries in
the ``firewall.nat`` schema (``kind: outbound``), in document order, plus the list of
things it could not carry over. It reuses the safe parsing and the result types of
:mod:`.firewall_rule_legacy`; the same secrecy rules apply (the document never reaches
an exception message or a log line).

Mapping
-------

- ``interface`` must be one identifier from ``<interfaces>`` or ``<ifgroups>``;
  anything else (empty, a list, an unknown name) skips and reports the rule.
- ``ipprotocol`` defaults to ``inet`` and must be ``inet`` or ``inet6``.
- ``protocol`` absent or ``any`` -> ``any``, otherwise upper-cased.
- ``source`` / ``destination``: ``any``, ``address`` or ``network`` pass through
  verbatim (``network`` holds aliases, CIDRs and interface network names), ``not`` and
  ``port`` map to ``*_not`` and ``*_port``.
- ``sourceport``, ``dstport`` and ``natport`` map to ``source_port``,
  ``destination_port`` and ``target_port`` when non-empty (the last two element names
  are inferred, not measured).
- ``target`` empty -> ``<interface>ip`` (the interface address); ``other-subnet`` is
  skipped and reported; anything else is verbatim.
- ``staticnatport``, ``nonat`` and ``log`` -> ``true`` when set; ``disabled`` ->
  ``enabled: false``; ``descr`` -> ``description`` (an identity marker is stripped and
  reported).
- Non-empty ``category``, ``poolopts``, ``poolopts_sourcehashkey``, ``tag``, ``tagged``
  and unknown elements are reported as not exported. ``created`` / ``updated`` are
  ignored.

Order
-----

Rules get ``sequence_start``, ``sequence_start + step`` ... in document order. An empty
``<rule/>`` (OPNsense leaves one after every legacy rule is deleted) is skipped
silently but still counts in the report index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._identity import has_identity_marker
from .firewall_rule_legacy import (
    _IDENTITY_MARKER,
    LegacyExport,
    LegacyRuleIssue,
    _flag,
    _interface_ids,
    _slug,
    _text,
    parse_config_document,
)

if TYPE_CHECKING:  # pragma: no cover
    from xml.etree.ElementTree import Element  # nosec B405  # typing only; parsing is defused

_IPPROTOCOLS: frozenset[str] = frozenset({"inet", "inet6"})

#: Elements this module maps by hand.
_MAPPED_ELEMENTS: frozenset[str] = frozenset(
    {
        "interface",
        "ipprotocol",
        "protocol",
        "source",
        "destination",
        "target",
        "targetip",
        "targetip_subnet",
        "staticnatport",
        "nonat",
        "log",
        "disabled",
        "descr",
        "sourceport",
        "dstport",
        "natport",
    }
)

#: Elements that carry nothing to export.
_IGNORED_ELEMENTS: frozenset[str] = frozenset({"created", "updated"})

#: Elements that exist in the legacy rule but have no counterpart in the schema.
_UNSUPPORTED_ELEMENTS: frozenset[str] = frozenset(
    {"category", "poolopts", "poolopts_sourcehashkey", "tag", "tagged"}
)

_SIDE_KEYS: frozenset[str] = frozenset({"any", "address", "network", "not", "port"})


def parse_legacy_outbound_rules(
    xml_text: str,
    *,
    reserved: set[str],
    sequence_start: int,
    sequence_step: int = 10,
) -> LegacyExport:
    """Map the legacy outbound NAT rules in a ``config.xml`` to ``firewall.nat`` entries.

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
    root = parse_config_document(xml_text)
    known_interfaces = _interface_ids(root)
    taken = set(reserved)
    result = LegacyExport()
    sequence = sequence_start

    for index, rule in enumerate(root.findall("./nat/outbound/rule"), start=1):
        # An empty <rule/> is not a rule: skip it, but keep counting it in ``index``.
        if len(rule) == 0:
            continue
        outcome = _map_rule(
            rule, index=index, known_interfaces=known_interfaces, issues=result.issues
        )
        if outcome is None:
            continue
        mapped, description, interface = outcome
        base = _slug(description) or f"outbound-nat-{interface}-{index}"
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
    issues: list[LegacyRuleIssue],
) -> tuple[dict[str, Any], str, str] | None:
    """Map one rule; ``None`` when it cannot be expressed (the reason is in ``issues``)."""
    raw_descr = _text(rule.find("descr"))
    interface = _text(rule.find("interface"))
    label = (
        f'outbound rule #{index} "{raw_descr}"'
        if raw_descr
        else f"outbound rule #{index} ({interface or 'no interface'})"
    )

    def report(field_name: str, reason: str) -> None:
        issues.append(LegacyRuleIssue(label, field_name, reason))

    if "," in interface or " " in interface:
        report("interface", "several interfaces cannot be expressed; rule skipped")
        return None
    if not interface:
        report("interface", "no interface; rule skipped")
        return None
    if interface not in known_interfaces:
        report("interface", f"unknown interface {interface!r}; rule skipped")
        return None

    ipprotocol = _text(rule.find("ipprotocol")) or "inet"
    if ipprotocol not in _IPPROTOCOLS:
        report("ipprotocol", f"unsupported value {ipprotocol!r}; rule skipped")
        return None

    target = _text(rule.find("target"))
    if target == "other-subnet":
        report("target", "'other-subnet' cannot be expressed; rule skipped")
        return None
    if not target:
        target = f"{interface}ip"

    description = raw_descr
    if has_identity_marker(description):
        description = _IDENTITY_MARKER.sub("", description).strip()
        report("descr", "contained an InfraFoundry identity marker; removed")

    protocol = _text(rule.find("protocol"))
    config: dict[str, Any] = {
        "kind": "outbound",
        "enabled": not _flag(rule.find("disabled")),
        "interface": interface,
        "ipprotocol": ipprotocol,
        "protocol": "any" if protocol.lower() in ("", "any") else protocol.upper(),
    }
    for side in ("source", "destination"):
        _map_side(rule.find(side), side, config, report)
    for element, key in (
        ("sourceport", "source_port"),
        ("dstport", "destination_port"),
        ("natport", "target_port"),
    ):
        value = _text(rule.find(element))
        if value:
            config[key] = value
    config["target"] = target
    for element, key in (("staticnatport", "staticnatport"), ("nonat", "nonat"), ("log", "log")):
        if _flag(rule.find(element)):
            config[key] = True
    if description:
        config["description"] = description

    subnet = _text(rule.find("targetip_subnet"))
    if subnet not in ("", "0"):
        report("targetip_subnet", f"unsupported value {subnet!r}; not exported")

    for child in rule:
        tag = child.tag
        if tag in _MAPPED_ELEMENTS or tag in _IGNORED_ELEMENTS:
            continue
        if not (_text(child) or len(child)):
            continue
        if tag in _UNSUPPORTED_ELEMENTS:
            report(tag, "has no automation-rule counterpart; not exported")
        else:
            report(tag, "unknown element; not exported")

    return config, description, interface


def _map_side(elem: Element | None, side: str, config: dict[str, Any], report: Any) -> None:
    """Map ``<source>`` / ``<destination>`` onto ``<side>_net`` / ``_not`` / ``_port``."""
    net = "any"
    if elem is not None:
        address = _text(elem.find("address"))
        network = _text(elem.find("network"))
        net = address or network or "any"
        if _flag(elem.find("not")):
            config[f"{side}_not"] = True
        port = _text(elem.find("port"))
        if port:
            config[f"{side}_port"] = port
        for child in elem:
            if child.tag not in _SIDE_KEYS and (_text(child) or len(child)):
                report(f"{side}/{child.tag}", "unknown element; not exported")
    config[f"{side}_net"] = net
