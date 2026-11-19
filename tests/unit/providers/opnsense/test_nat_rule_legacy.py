"""Unit tests for the legacy outbound NAT rule mapper and its export wiring (#1509)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, PartialExtractionError
from infrafoundry.providers.opnsense.components.nat_rule import NATRuleManager
from infrafoundry.providers.opnsense.services.firewall_rule_legacy import LegacyExport
from infrafoundry.providers.opnsense.services.nat_rule import (
    LiveNATRule,
    NATRuleService,
    max_live_sequence,
)
from infrafoundry.providers.opnsense.services.nat_rule_legacy import parse_legacy_outbound_rules

_FIXTURES = Path(__file__).parent / "fixtures"


def _parse(xml: str | None = None, **kwargs: Any) -> LegacyExport:
    kwargs.setdefault("reserved", set())
    kwargs.setdefault("sequence_start", 200)
    text = xml if xml is not None else (_FIXTURES / "legacy_outbound_nat_config.xml").read_text()
    return parse_legacy_outbound_rules(text, **kwargs)


def _doc(rules: str) -> str:
    return (
        "<opnsense><interfaces><wan/><lan/><opt1/></interfaces>"
        f"<nat><outbound><mode>hybrid</mode>{rules}</outbound></nat></opnsense>"
    )


def _rule(body: str = "", *, interface: str = "wan", descr: str = "r") -> str:
    iface = f"<interface>{interface}</interface>" if interface else ""
    return f"<rule>{iface}<descr>{descr}</descr>{body}</rule>"


def _cfg(export: LegacyExport, i: int = 0) -> dict[str, Any]:
    return export.entries[i]["config"]  # type: ignore[no-any-return]


def test_clean_fixture_maps_in_order_without_issues() -> None:
    export = _parse()
    assert export.issues == []
    assert [e["name"] for e in export.entries] == [
        "servers-out-via-wan",
        "edge-hosts-v6",
        "documentation-net-to-host",
    ]
    assert [_cfg(export, i)["sequence"] for i in range(3)] == [200, 210, 220]
    first = _cfg(export)
    assert first["kind"] == "outbound"
    assert first["source_net"] == "opt1"
    assert first["destination_net"] == "any"
    assert first["target"] == "wanip"
    assert first["protocol"] == "UDP"
    assert first["staticnatport"] is True
    assert first["enabled"] is True


def test_empty_target_and_ipprotocol_and_disabled() -> None:
    export = _parse()
    second = _cfg(export, 1)
    assert second["ipprotocol"] == "inet6"
    assert second["target"] == "wanip"
    assert second["enabled"] is False
    assert second["source_net"] == "edge_hosts"
    assert second["protocol"] == "any"
    third = _cfg(export, 2)
    assert third["target"] == "192.0.2.1"
    assert third["source_net"] == "198.51.100.0/24"
    assert third["destination_net"] == "203.0.113.5"
    assert third["interface"] == "opt1"


def test_flags_and_ports_map() -> None:
    body = (
        "<nonat>1</nonat><log>1</log><sourceport>1024</sourceport><dstport>53</dstport>"
        "<natport>5353</natport><source><network>opt1</network><not>1</not></source>"
        "<destination><address>203.0.113.9</address><not>1</not></destination>"
    )
    export = _parse(_doc(_rule(body)))
    cfg = _cfg(export)
    assert export.issues == []
    assert cfg["nonat"] is True
    assert cfg["log"] is True
    assert cfg["source_port"] == "1024"
    assert cfg["destination_port"] == "53"
    assert cfg["target_port"] == "5353"
    assert cfg["source_not"] is True
    assert cfg["destination_not"] is True


def test_empty_rule_skipped_but_counted() -> None:
    alone = _parse(_doc("<rule/>"))
    assert alone.entries == []
    assert alone.issues == []
    export = _parse(_doc("<rule/>" + _rule("<ipprotocol>bogus</ipprotocol>")))
    assert export.entries == []
    assert "rule #2" in str(export.issues[0])
    export = _parse(_doc("<rule/>" + _rule(descr="")))
    assert len(export.entries) == 1
    assert export.entries[0]["config"]["sequence"] == 200
    assert export.entries[0]["name"] == "outbound-nat-wan-2"


def test_unmappable_elements_reported_once_each() -> None:
    body = (
        "<category>abc</category><poolopts>round-robin</poolopts><tag>x</tag>"
        "<tagged></tagged><mystery>1</mystery><created><time>1</time></created>"
    )
    export = _parse(_doc(_rule(body)))
    fields = sorted(i.field for i in export.issues)
    assert fields == ["category", "mystery", "poolopts", "tag"]
    assert len(export.entries) == 1


@pytest.mark.parametrize(
    ("interface", "extra", "needle"),
    [
        ("nope", "", "unknown interface"),
        ("", "", "no interface"),
        ("wan,lan", "", "several interfaces"),
        ("wan", "<target>other-subnet</target>", "other-subnet"),
        ("wan", "<ipprotocol>inet46</ipprotocol>", "unsupported"),
    ],
)
def test_skipped_rules(interface: str, extra: str, needle: str) -> None:
    export = _parse(_doc(_rule(extra, interface=interface)))
    assert export.entries == []
    assert len(export.issues) == 1
    assert needle in str(export.issues[0])


def test_names_dedupe_reserved_and_marker() -> None:
    rules = _rule(descr="Same") + _rule(descr="Same") + _rule(descr="Taken")
    export = _parse(_doc(rules), reserved={"taken"})
    assert [e["name"] for e in export.entries] == ["same", "same-2", "taken-2"]
    marked = _parse(_doc(_rule(descr="Web [infrafoundry:abc]")))
    assert marked.entries[0]["config"]["description"] == "Web"
    assert [i.field for i in marked.issues] == ["descr"]


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE a [<!ENTITY x "secret-value">]><a>&x;</a>',
        "<opnsense><unclosed secret-value></opnsense>",
    ],
)
def test_unsafe_xml_raises_without_echo(xml: str) -> None:
    with pytest.raises(APIError) as info:
        _parse(xml)
    assert "secret-value" not in str(info.value)


def _live(kind: str, sequence: str, managed: str | None = None) -> LiveNATRule:
    return LiveNATRule(
        uuid="u",
        kind=kind,  # type: ignore[arg-type]
        managed_name=managed,
        description="",
        raw={"sequence": sequence, "enabled": "1"},
    )


def test_max_live_sequence() -> None:
    rules = [_live("outbound", "5"), _live("outbound", "40"), _live("one_to_one", "900")]
    assert max_live_sequence(rules) == 40
    assert max_live_sequence([]) == 0
    assert max_live_sequence([_live("outbound", "x")]) == 0
    assert max_live_sequence(rules, "one_to_one") == 900


def test_export_entries_filters_managed() -> None:
    service = NATRuleService.__new__(NATRuleService)
    entries = service.export_entries([_live("outbound", "1", "mine"), _live("outbound", "2")])
    assert [e["name"] for e in entries] == ["mine"]
    assert entries[0]["config"]["kind"] == "outbound"


_SVC = "infrafoundry.providers.opnsense.components.nat_rule.NATRuleService"
_BK = "infrafoundry.providers.opnsense.components.nat_rule.ConfigBackupService"
_RES = "infrafoundry.providers.opnsense.components.nat_rule.env_provider_resources"


def _manager(tmp_path: Path) -> NATRuleManager:
    return NATRuleManager(tmp_path)


def _patched(backup: Any, live: list[LiveNATRule]) -> Any:
    service = MagicMock()
    service.search_all_tolerant.return_value = live
    service.export_entries.return_value = [{"name": "live-one", "config": {"kind": "outbound"}}]
    service.export_to_yaml.return_value = "plain"
    bk = MagicMock()
    if isinstance(backup, Exception):
        bk.from_environment.return_value.download_config.side_effect = backup
    else:
        bk.from_environment.return_value.download_config.return_value = backup
    return service, bk


def test_manager_without_flag_has_no_legacy_path(tmp_path: Path) -> None:
    service, bk = _patched("", [])
    with patch(_SVC) as svc, patch(_BK, bk):
        svc.from_environment.return_value = service
        assert _manager(tmp_path).migrate("e") == "plain"
    bk.from_environment.assert_not_called()


def test_manager_clean_path_orders_after_live(tmp_path: Path) -> None:
    clean = (_FIXTURES / "legacy_outbound_nat_config.xml").read_text()
    service, bk = _patched(clean, [_live("outbound", "50", "live-one")])
    with patch(_SVC) as svc, patch(_BK, bk), patch(_RES, return_value=[]):
        svc.from_environment.return_value = service
        out = _manager(tmp_path).migrate("e", include_legacy=True)
    assert "live-one" in out
    assert "servers-out-via-wan" in out
    assert "sequence: 150" in out
    assert out.index("live-one") < out.index("servers-out-via-wan")


def test_manager_partial_and_reserved(tmp_path: Path) -> None:
    xml = _doc(_rule("<mystery>1</mystery>", descr="Live one"))
    service, bk = _patched(xml, [])
    with patch(_SVC) as svc, patch(_BK, bk), patch(_RES, return_value=[]):
        svc.from_environment.return_value = service
        with pytest.raises(PartialExtractionError) as info:
            _manager(tmp_path).migrate("e", include_legacy=True)
    assert "live-one-2" in info.value.yaml_content
    assert info.value.yaml_content.startswith("# Legacy rule fields not exported")
    assert len(info.value.issues) == 1


def test_manager_backup_failure_is_one_issue(tmp_path: Path) -> None:
    service, bk = _patched(APIError("boom", provider="opnsense"), [])
    with patch(_SVC) as svc, patch(_BK, bk), patch(_RES, return_value=[]):
        svc.from_environment.return_value = service
        with pytest.raises(PartialExtractionError) as info:
            _manager(tmp_path).migrate("e", include_legacy=True)
    assert len(info.value.issues) == 1
    assert "not read" in info.value.issues[0]
    assert "live-one" in info.value.yaml_content
