"""Unit tests for the legacy filter rule mapper (#1497)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.opnsense.services.firewall_rule_legacy import (
    LegacyExport,
    parse_legacy_rules,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text()


def _parse(name: str = "legacy_filter_config.xml", **kwargs: Any) -> LegacyExport:
    kwargs.setdefault("reserved", set())
    kwargs.setdefault("sequence_start", 200)
    return parse_legacy_rules(_fixture(name), **kwargs)


def _doc(rules: str, *, extra: str = "") -> str:
    return (
        "<opnsense><interfaces><lan/><opt1/></interfaces>"
        f"{extra}<filter>{rules}</filter></opnsense>"
    )


def _by_name(export: LegacyExport) -> dict[str, dict[str, Any]]:
    return {e["name"]: e["config"] for e in export.entries}


def _issue_fields(export: LegacyExport) -> set[tuple[str, str]]:
    return {(i.rule_label, i.field) for i in export.issues}


class TestOrder:
    def test_document_order_with_increasing_sequence(self) -> None:
        export = _parse("legacy_filter_config_clean.xml")
        names = [e["name"] for e in export.entries]
        assert names == [
            "allow-web",
            "block-host",
            "floating-block",
            "reject-ssh",
            "guest-ping",
            "trusted-rule-6",
        ]
        assert [e["config"]["sequence"] for e in export.entries] == [200, 210, 220, 230, 240, 250]

    def test_sequence_start_and_step_are_respected(self) -> None:
        export = _parse("legacy_filter_config_clean.xml", sequence_start=1100, sequence_step=5)
        assert [e["config"]["sequence"] for e in export.entries][:3] == [1100, 1105, 1110]

    def test_skipped_rules_do_not_consume_a_sequence(self) -> None:
        export = _parse()
        sequences = [e["config"]["sequence"] for e in export.entries]
        assert sequences == sorted(set(sequences))
        assert sequences == list(range(200, 200 + 10 * len(sequences), 10))

    def test_interleaved_floating_and_interface_order_is_kept(self) -> None:
        by_name = _by_name(_parse("legacy_filter_config_clean.xml"))
        assert by_name["allow-web"]["sequence"] < by_name["floating-block"]["sequence"]
        assert by_name["floating-block"]["sequence"] < by_name["reject-ssh"]["sequence"]


class TestInterfaces:
    def test_clean_fixture_has_no_issues(self) -> None:
        assert _parse("legacy_filter_config_clean.xml").issues == []

    def test_ifgroup_and_optn_are_accepted(self) -> None:
        by_name = _by_name(_parse("legacy_filter_config_clean.xml"))
        assert by_name["trusted-rule-6"]["interface"] == "trusted"
        assert by_name["reject-ssh"]["interface"] == "opt1"

    def test_builtin_virtual_interface_is_accepted(self) -> None:
        xml = _doc("<rule><type>pass</type><interface>openvpn</interface></rule>")
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.issues == []
        assert export.entries[0]["config"]["interface"] == "openvpn"

    def test_unknown_interface_is_reported_with_the_description_and_skipped(self) -> None:
        export = _parse()
        assert ('rule #12 "Missing interface"', "interface") in _issue_fields(export)
        assert "missing-interface" not in _by_name(export)

    def test_multi_interface_floating_rule_is_skipped_and_reported(self) -> None:
        export = _parse()
        assert ('rule #11 "Two interfaces"', "interface") in _issue_fields(export)
        assert "two-interfaces" not in _by_name(export)

    def test_network_keyword_with_ip_suffix_resolves(self) -> None:
        export = _parse("legacy_filter_config_clean.xml")
        assert _by_name(export)["guest-ping"]["source_net"] == "opt2ip"
        assert export.issues == []

    def test_unknown_network_is_reported_but_exported_verbatim(self) -> None:
        xml = _doc(
            "<rule><type>pass</type><interface>lan</interface>"
            "<source><network>opt7ip</network></source></rule>"
        )
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.entries[0]["config"]["source_net"] == "opt7ip"
        assert [(i.field) for i in export.issues] == ["source"]

    def test_non_floating_rule_without_interface_is_skipped(self) -> None:
        export = parse_legacy_rules(
            _doc("<rule><type>pass</type></rule>"), reserved=set(), sequence_start=1
        )
        assert export.entries == []
        assert [i.field for i in export.issues] == ["interface"]


class TestFieldMapping:
    def test_basic_pass_rule(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["allow-web"]
        assert config["action"] == "pass"
        assert config["interface"] == "lan"
        assert config["description"] == "Allow web"
        assert config["log"] is True
        assert config["quick"] is True
        assert config["direction"] == "in"
        assert config["ipprotocol"] == "inet"
        assert config["protocol"] == "TCP"
        assert config["source_net"] == "lan"
        assert config["destination_net"] == "any"
        assert config["destination_port"] == "443"
        assert config["statetype"] == "keep"
        assert "enabled" not in config

    def test_block_with_address_and_not(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["block-host"]
        assert config["action"] == "block"
        assert config["protocol"] == "any"
        assert config["source_net"] == "192.0.2.10/32"
        assert config["destination_net"] == "opt1"
        assert config["destination_not"] is True
        assert "source_not" not in config

    def test_disabled_reject_with_gateway_and_statetype(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["reject-ssh"]
        assert config["action"] == "reject"
        assert config["enabled"] is False
        assert config["gateway"] == "WAN_GW"
        assert config["statetype"] == "sloppy"
        assert config["protocol"] == "TCP/UDP"
        assert config["destination_net"] == "example_hosts"
        assert config["destination_port"] == "22"

    def test_floating_rule(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["floating-block"]
        assert config["state_policy"] == "floating"
        assert config["interface"] == ""
        assert config["direction"] == "any"
        assert config["quick"] is True
        assert config["protocol"] == "UDP"

    def test_non_floating_rule_has_no_state_policy(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["allow-web"]
        assert "state_policy" not in config

    def test_floating_rule_without_quick_is_not_quick(self) -> None:
        xml = _doc(
            "<rule><type>pass</type><floating>yes</floating><direction>out</direction></rule>"
        )
        config = parse_legacy_rules(xml, reserved=set(), sequence_start=1).entries[0]["config"]
        assert config["quick"] is False
        assert config["direction"] == "out"

    def test_ipv6_icmp_rule(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["guest-ping"]
        assert config["ipprotocol"] == "inet6"
        assert config["protocol"] == "ICMP"
        assert config["icmp6type"] == "echoreq"

    def test_defaults_when_elements_are_absent(self) -> None:
        xml = _doc("<rule><type>pass</type><interface>lan</interface></rule>")
        config = parse_legacy_rules(xml, reserved=set(), sequence_start=1).entries[0]["config"]
        assert config["ipprotocol"] == "inet"
        assert config["protocol"] == "any"
        assert config["source_net"] == "any"
        assert config["destination_net"] == "any"

    def test_presence_flags_and_generic_wire_keys(self) -> None:
        xml = _doc(
            "<rule><type>pass</type><interface>lan</interface><disabled/><log/>"
            "<allowopts/><max-src-nodes>5</max-src-nodes><tag>t1</tag></rule>"
        )
        config = parse_legacy_rules(xml, reserved=set(), sequence_start=1).entries[0]["config"]
        assert config["enabled"] is False
        assert config["log"] is True
        assert config["allowopts"] is True
        assert config["max_src_nodes"] == "5"
        assert config["tag"] == "t1"

    def test_explicit_zero_flag_is_false(self) -> None:
        xml = _doc("<rule><type>pass</type><interface>lan</interface><log>0</log></rule>")
        config = parse_legacy_rules(xml, reserved=set(), sequence_start=1).entries[0]["config"]
        assert "log" not in config

    def test_invalid_action_skips_the_rule(self) -> None:
        xml = _doc("<rule><type>weird</type><interface>lan</interface></rule>")
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.entries == []
        assert [i.field for i in export.issues] == ["type"]

    def test_invalid_statetype_is_reported_and_not_exported(self) -> None:
        xml = _doc(
            "<rule><type>pass</type><interface>lan</interface><statetype>nope</statetype></rule>"
        )
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert "statetype" not in export.entries[0]["config"]
        assert [i.field for i in export.issues] == ["statetype"]

    def test_category_names_and_uuids_resolve(self) -> None:
        categories = (
            "<OPNsense><Firewall><Category><categories>"
            '<category uuid="uuid-a"><name>Alpha</name></category>'
            '<category uuid="uuid-b"><name>Beta</name></category>'
            "</categories></Category></Firewall></OPNsense>"
        )
        xml = _doc(
            "<rule><type>pass</type><interface>lan</interface>"
            "<category>Alpha,uuid-b,Gamma</category></rule>",
            extra=categories,
        )
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.entries[0]["config"]["categories"] == ["uuid-a", "uuid-b"]
        assert [i.field for i in export.issues] == ["category"]

    def test_clean_fixture_category_maps_to_uuid(self) -> None:
        config = _by_name(_parse("legacy_filter_config_clean.xml"))["allow-web"]
        assert config["categories"] == ["11111111-2222-3333-4444-555555555555"]


class TestUnmappable:
    @pytest.mark.parametrize(
        ("label", "field"),
        [
            ('rule #7 "Scheduled access"', "sched"),
            ('rule #8 "Os match"', "os"),
            ('rule #9 "Shaped"', "dnpipe"),
            ('rule #9 "Shaped"', "associated-rule-id"),
            ('rule #10 "Odd element"', "frobnicate"),
        ],
    )
    def test_each_unmappable_field_yields_one_issue(self, label: str, field: str) -> None:
        issues = [(i.rule_label, i.field) for i in _parse().issues]
        assert issues.count((label, field)) == 1

    def test_the_rest_of_the_rule_is_still_exported(self) -> None:
        by_name = _by_name(_parse())
        assert by_name["scheduled-access"]["action"] == "pass"
        assert by_name["os-match"]["protocol"] == "TCP"
        assert "sched" not in by_name["scheduled-access"]

    def test_empty_elements_and_ignored_ones_are_not_reported(self) -> None:
        # The clean fixture holds an empty <sched/>, <tracker>, <created> and <updated>.
        assert _parse("legacy_filter_config_clean.xml").issues == []

    def test_issue_renders_as_one_line(self) -> None:
        issue = _parse().issues[0]
        assert str(issue) == f"{issue.rule_label}: {issue.field}: {issue.reason}"


class TestNames:
    def test_slug_dedupe_and_fallback(self) -> None:
        names = [e["name"] for e in _parse().entries]
        assert "allow-web" in names
        assert "allow-web-2" in names
        assert "trusted-rule-6" in names

    def test_reserved_names_are_avoided(self) -> None:
        export = _parse("legacy_filter_config_clean.xml", reserved={"allow-web", "allow-web-2"})
        assert export.entries[0]["name"] == "allow-web-3"

    def test_floating_fallback_name(self) -> None:
        xml = _doc("<rule><type>pass</type><floating>yes</floating></rule>")
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.entries[0]["name"] == "floating-rule-1"

    def test_long_description_slug_is_capped(self) -> None:
        xml = _doc(
            f"<rule><type>pass</type><interface>lan</interface><descr>{'a' * 80}</descr></rule>"
        )
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert len(export.entries[0]["name"]) == 48

    def test_identity_marker_in_description_is_stripped_and_reported(self) -> None:
        xml = _doc(
            "<rule><type>pass</type><interface>lan</interface>"
            "<descr>Keep me [infrafoundry:other]</descr></rule>"
        )
        export = parse_legacy_rules(xml, reserved=set(), sequence_start=1)
        assert export.entries[0]["config"]["description"] == "Keep me"
        assert export.entries[0]["name"] == "keep-me"
        assert [i.field for i in export.issues] == ["descr"]


class TestSafeParsing:
    def test_entity_expansion_is_rejected_without_echoing_the_document(self) -> None:
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "SECRET-synthetic">]>'
            "<opnsense><filter><rule><descr>&a;</descr></rule></filter></opnsense>"
        )
        with pytest.raises(APIError) as excinfo:
            parse_legacy_rules(bomb, reserved=set(), sequence_start=1)
        assert "SECRET" not in str(excinfo.value)
        assert excinfo.value.__cause__ is None

    def test_malformed_xml_is_rejected_without_echoing_the_document(self) -> None:
        with pytest.raises(APIError, match="not valid XML") as excinfo:
            parse_legacy_rules(
                "<opnsense><secret>hunter2</opnsense>", reserved=set(), sequence_start=1
            )
        assert "hunter2" not in str(excinfo.value)
        assert excinfo.value.__cause__ is None

    def test_no_filter_section_gives_an_empty_result(self) -> None:
        export = parse_legacy_rules("<opnsense/>", reserved=set(), sequence_start=1)
        assert export.entries == []
        assert export.issues == []
