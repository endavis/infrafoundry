"""Unit tests for ``infrafoundry.providers.opnsense.services.nat_rule``.

Coverage:
    - Identity-suffix encoder/parser (round-trip + malformed cases).
    - Per-kind payload shape from ``NATRuleConfig.to_payload``.
    - ``compute_diff`` with both kinds, isolation, lock + add-only semantics.
    - Unmanaged live rules silently ignored.
    - ``nat_rule_configs_from_resources`` validation.
    - ``NATRuleService`` API method dispatch via ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration (per-kind ``apply``).
    - ``export_to_yaml`` round-trip (managed rules only).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.nat_rule import (
    Diff,
    LiveNATRule,
    NATRuleConfig,
    NATRuleService,
    OpnsenseDriftError,
    _row_to_live,
    compute_diff,
    encode_identity,
    nat_rule_configs_from_resources,
    parse_identity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outbound(
    name: str,
    *,
    description: str = "",
    target: str = "wanip",
    interface: str = "wan",
    sequence: int = 100,
    lock: bool = False,
    enabled: bool = True,
    log: bool = False,
    nonat: bool = False,
    source_net: str = "any",
    destination_net: str = "any",
) -> NATRuleConfig:
    return NATRuleConfig(
        name=name,
        kind="outbound",
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        target=target,
        nonat=nonat,
        source_net=source_net,
        destination_net=destination_net,
    )


def _one_to_one(
    name: str,
    *,
    description: str = "",
    interface: str = "wan",
    external: str = "198.51.100.10",
    source_net: str = "10.0.0.10",
    destination_net: str = "any",
    sequence: int = 100,
    lock: bool = False,
    type_: str = "binat",
    natreflection: str = "",
) -> NATRuleConfig:
    return NATRuleConfig(
        name=name,
        kind="one_to_one",
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        type=type_,
        external=external,
        source_net=source_net,
        destination_net=destination_net,
        natreflection=natreflection,
    )


def _live(
    uuid: str,
    name: str | None,
    kind: str,
    *,
    description: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveNATRule:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "description": (
            (f"{description} [infrafoundry:{name}]" if description else f"[infrafoundry:{name}]")
            if name is not None
            else description
        ),
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveNATRule(
        uuid=uuid,
        kind=kind,  # type: ignore[arg-type]
        managed_name=name,
        description=description,
        raw=raw,
    )


def _resource(
    name: str,
    config: dict[str, Any],
) -> ResourceConfig:
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# Identity-suffix helpers
# ---------------------------------------------------------------------------


class TestIdentityEncoder:
    def test_encode_with_user_description(self) -> None:
        assert encode_identity("foo", "user desc") == "user desc [infrafoundry:foo]"

    def test_encode_with_empty_user_description(self) -> None:
        # Just the tag, no leading space.
        assert encode_identity("foo", "") == "[infrafoundry:foo]"


class TestIdentityParser:
    def test_parse_with_user_description(self) -> None:
        name, user = parse_identity("something [infrafoundry:foo]")
        assert name == "foo"
        assert user == "something"

    def test_parse_tag_only(self) -> None:
        name, user = parse_identity("[infrafoundry:foo]")
        assert name == "foo"
        assert user == ""

    def test_parse_unmanaged_returns_none(self) -> None:
        name, user = parse_identity("regular operator description")
        assert name is None
        assert user == "regular operator description"

    def test_parse_empty_unmanaged(self) -> None:
        name, user = parse_identity("")
        assert name is None
        assert user == ""

    def test_parse_malformed_empty_name_raises(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[infrafoundry:]")

    def test_parse_malformed_uppercase_raises(self) -> None:
        # Strict regex: lowercase + digits + hyphen only.
        with pytest.raises(OpnsenseDriftError):
            parse_identity("user desc [infrafoundry:Foo]")

    def test_parse_malformed_underscore_raises(self) -> None:
        # Strict regex disallows underscore in name (only [a-z0-9-]+).
        with pytest.raises(OpnsenseDriftError):
            parse_identity("user desc [infrafoundry:foo_bar]")

    def test_parse_tag_in_middle_raises(self) -> None:
        # The tag must be the LAST token; trailing text after the tag is
        # drift (operator-edited or otherwise out-of-protocol).
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[infrafoundry:foo] trailing text")

    def test_parse_double_bracket_raises(self) -> None:
        # ``[[infrafoundry:foo]]`` contains the tag pattern in a non-suffix
        # position; treated as drift since the tag namespace is reserved.
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[[infrafoundry:foo]]")


# ---------------------------------------------------------------------------
# NATRuleConfig.to_payload
# ---------------------------------------------------------------------------


class TestOutboundPayload:
    def test_payload_has_rule_envelope(self) -> None:
        payload = _outbound("foo", description="desc", target="wanip").to_payload()
        assert set(payload.keys()) == {"rule"}

    def test_payload_fields_serialize_correctly(self) -> None:
        rule = _outbound(
            "foo",
            description="my desc",
            target="wanip",
            interface="wan",
            sequence=200,
            log=True,
            nonat=True,
        )
        inner = rule.to_payload()["rule"]
        # Booleans → "0"/"1"
        assert inner["enabled"] == "1"
        assert inner["log"] == "1"
        assert inner["nonat"] == "1"
        assert inner["staticnatport"] == "0"
        # Stringified int
        assert inner["sequence"] == "200"
        # Description carries identity suffix.
        assert inner["description"] == "my desc [infrafoundry:foo]"
        # Pass-through fields.
        assert inner["interface"] == "wan"
        assert inner["target"] == "wanip"
        assert inner["ipprotocol"] == "inet"
        assert inner["protocol"] == "any"


class TestOneToOnePayload:
    def test_payload_has_rule_envelope(self) -> None:
        payload = _one_to_one("dmz").to_payload()
        assert set(payload.keys()) == {"rule"}

    def test_payload_fields_serialize_correctly(self) -> None:
        rule = _one_to_one(
            "dmz",
            description="DMZ srv",
            interface="wan",
            external="198.51.100.42",
            source_net="10.20.30.40",
            destination_net="any",
            type_="binat",
            natreflection="enable",
        )
        inner = rule.to_payload()["rule"]
        assert inner["enabled"] == "1"
        assert inner["log"] == "0"
        assert inner["sequence"] == "100"
        assert inner["interface"] == "wan"
        assert inner["type"] == "binat"
        assert inner["external"] == "198.51.100.42"
        assert inner["source_net"] == "10.20.30.40"
        assert inner["destination_net"] == "any"
        assert inner["natreflection"] == "enable"
        assert inner["description"] == "DMZ srv [infrafoundry:dmz]"


class TestPayloadIdentityIntegration:
    def test_empty_user_description_yields_tag_only(self) -> None:
        rule = _outbound("foo", description="", target="wanip")
        inner = rule.to_payload()["rule"]
        assert inner["description"] == "[infrafoundry:foo]"


class TestDiffKey:
    def test_outbound_and_one_to_one_same_name_have_different_keys(self) -> None:
        out = _outbound("foo", target="wanip")
        oto = _one_to_one("foo")
        assert out.diff_key != oto.diff_key
        assert out.diff_key == ("outbound", "foo")
        assert oto.diff_key == ("one_to_one", "foo")


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiffEmpty:
    def test_no_desired_no_live_is_empty(self) -> None:
        diff = compute_diff([], [])
        assert diff.is_empty
        assert diff.adds == []
        assert diff.deletes == []
        assert diff.updates == []
        assert diff.locked == []


class TestComputeDiffAdds:
    def test_new_outbound_adds(self) -> None:
        diff = compute_diff([_outbound("foo", target="wanip")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "foo"

    def test_new_one_to_one_adds(self) -> None:
        diff = compute_diff([_one_to_one("dmz")], [])
        assert len(diff.adds) == 1


class TestComputeDiffUpdates:
    def test_update_when_target_changes(self) -> None:
        # Live raw must reflect the target field.
        live_raw = {
            "uuid": "u1",
            "description": "[infrafoundry:foo]",
            "enabled": "1",
            "nonat": "0",
            "sequence": "100",
            "interface": "wan",
            "ipprotocol": "inet",
            "protocol": "any",
            "source_net": "any",
            "source_not": "0",
            "source_port": "",
            "destination_net": "any",
            "destination_not": "0",
            "destination_port": "",
            "target": "old",
            "target_port": "",
            "staticnatport": "0",
            "log": "0",
        }
        live = LiveNATRule(
            uuid="u1",
            kind="outbound",
            managed_name="foo",
            description="",
            raw=live_raw,
        )
        diff = compute_diff([_outbound("foo", target="new", interface="wan")], [live])
        assert len(diff.updates) == 1
        assert len(diff.adds) == 0
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.target == "new"

    def test_no_update_when_payload_matches(self) -> None:
        # Build live raw matching what a freshly-applied outbound rule would
        # look like.
        rule = _outbound("foo", target="wanip", interface="wan")
        payload_inner = rule.to_payload()["rule"]
        live_raw: dict[str, Any] = {"uuid": "u1", **payload_inner}
        # description column carries the suffix tag in raw, but parser sets
        # managed_name + strips the tag for the parsed description field.
        live = LiveNATRule(
            uuid="u1",
            kind="outbound",
            managed_name="foo",
            description="",
            raw=live_raw,
        )
        diff = compute_diff([rule], [live])
        assert diff.is_empty


class TestComputeDiffDeletes:
    def test_managed_live_with_no_desired_is_deleted(self) -> None:
        live = _live("u1", "stale", "outbound")
        diff = compute_diff([], [live])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_unmanaged_live_silently_ignored(self) -> None:
        # A row without the InfraFoundry tag is unmanaged — the diff
        # never proposes deleting it, even if not in YAML.
        live = LiveNATRule(
            uuid="u-unmanaged",
            kind="outbound",
            managed_name=None,
            description="manually-created rule",
            raw={"uuid": "u-unmanaged", "description": "manually-created rule"},
        )
        diff = compute_diff([], [live])
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_suppresses_deletes(self) -> None:
        live = _live("u1", "stale", "outbound")
        diff = compute_diff([], [live], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        live = _live(
            "u1",
            "wan-survival",
            "outbound",
            raw_overrides={"target": "wanip", "interface": "wan"},
        )
        rule = _outbound("wan-survival", target="different-target", lock=True)
        diff = compute_diff([rule], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        rule = _outbound("missing", target="wanip", lock=True)
        diff = compute_diff([rule], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None


class TestComputeDiffPerKindIsolation:
    def test_outbound_and_one_to_one_with_same_name_are_independent(self) -> None:
        out_live = _live("u-out", "shared", "outbound")
        oto_live = _live("u-oto", "shared", "one_to_one")
        # Both kinds in YAML.
        rule_out = _outbound("shared", target="wanip", interface="wan")
        rule_oto = _one_to_one("shared")
        diff = compute_diff([rule_out, rule_oto], [out_live, oto_live])
        # Both are updates (because raw doesn't match defaults), not crossed.
        # The key invariant: the outbound desired never matches the 1:1
        # live and vice-versa.
        update_uuids = {live.uuid for live, _ in diff.updates}
        assert "u-out" in update_uuids or "u-oto" in update_uuids
        # Independent of the field comparison details: there must be no
        # delete (each kind's desired matches its kind's live name).
        assert diff.deletes == []

    def test_outbound_diff_does_not_match_1to1_live(self) -> None:
        # YAML only has outbound "foo"; box has 1:1 "foo".
        oto_live = _live("u-oto", "foo", "one_to_one")
        rule_out = _outbound("foo", target="wanip", interface="wan")
        diff = compute_diff([rule_out], [oto_live])
        # The 1:1 live is treated as managed-but-not-in-desired-of-its-kind →
        # delete proposed; the outbound is missing → add proposed.
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "foo"
        assert diff.adds[0].kind == "outbound"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].kind == "one_to_one"


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        rule = _outbound("foo", target="wanip", lock=True)
        diff = Diff(locked=[(rule, None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_outbound("foo", target="wanip")])
        assert not diff.is_empty


# ---------------------------------------------------------------------------
# nat_rule_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResourcesOutbound:
    def test_valid_outbound_parses(self) -> None:
        r = _resource(
            "lan-out",
            {
                "kind": "outbound",
                "interface": "wan",
                "target": "wanip",
                "description": "LAN out",
            },
        )
        result = nat_rule_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.kind == "outbound"
        assert cfg.target == "wanip"
        assert cfg.description == "LAN out"

    def test_outbound_missing_target_rejected(self) -> None:
        r = _resource("bad", {"kind": "outbound", "interface": "wan"})
        with pytest.raises(ValueError, match="target"):
            nat_rule_configs_from_resources([r])

    def test_outbound_missing_interface_rejected(self) -> None:
        r = _resource("bad", {"kind": "outbound", "target": "wanip"})
        with pytest.raises(ValueError, match="interface"):
            nat_rule_configs_from_resources([r])


class TestConfigsFromResourcesOneToOne:
    def test_valid_1to1_parses(self) -> None:
        r = _resource(
            "dmz",
            {
                "kind": "one_to_one",
                "interface": "wan",
                "external": "198.51.100.10",
                "source_net": "10.0.0.10",
            },
        )
        result = nat_rule_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.kind == "one_to_one"
        assert cfg.external == "198.51.100.10"

    def test_1to1_missing_external_rejected(self) -> None:
        r = _resource("bad", {"kind": "one_to_one", "interface": "wan"})
        with pytest.raises(ValueError, match="external"):
            nat_rule_configs_from_resources([r])

    def test_1to1_invalid_type_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "one_to_one",
                "interface": "wan",
                "external": "198.51.100.10",
                "type": "wrong",
            },
        )
        with pytest.raises(ValueError, match="type"):
            nat_rule_configs_from_resources([r])

    def test_1to1_invalid_natreflection_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "one_to_one",
                "interface": "wan",
                "external": "198.51.100.10",
                "natreflection": "not-allowed",
            },
        )
        with pytest.raises(ValueError, match="natreflection"):
            nat_rule_configs_from_resources([r])


class TestConfigsFromResourcesGeneral:
    def test_invalid_kind_rejected(self) -> None:
        r = _resource("bad", {"kind": "port_forward"})
        with pytest.raises(ValueError, match="kind"):
            nat_rule_configs_from_resources([r])

    def test_missing_kind_rejected(self) -> None:
        r = _resource("bad", {"interface": "wan", "target": "wanip"})
        with pytest.raises(ValueError, match="kind"):
            nat_rule_configs_from_resources([r])

    def test_non_nat_resources_ignored(self) -> None:
        nat = _resource("ok", {"kind": "outbound", "interface": "wan", "target": "wanip"})
        other = ResourceConfig(name="x", type="aliases", provider="opnsense", config={})
        result = nat_rule_configs_from_resources([nat, other])
        assert len(result) == 1

    def test_lock_must_be_bool(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "outbound",
                "interface": "wan",
                "target": "wanip",
                "lock": "yes",
            },
        )
        with pytest.raises(ValueError, match="lock"):
            nat_rule_configs_from_resources([r])

    def test_description_with_identity_tag_rejected(self) -> None:
        # Forging the InfraFoundry tag is rejected at parse time. The probe
        # is position-agnostic — operator-set descriptions can't contain
        # the tag in any position.
        r = _resource(
            "evil",
            {
                "kind": "outbound",
                "interface": "wan",
                "target": "wanip",
                "description": "forged [infrafoundry:other]",
            },
        )
        with pytest.raises(ValueError, match="reserved"):
            nat_rule_configs_from_resources([r])

    def test_sequence_default_when_omitted(self) -> None:
        r = _resource("ok", {"kind": "outbound", "interface": "wan", "target": "wanip"})
        result = nat_rule_configs_from_resources([r])
        assert result[0].sequence == 100

    def test_sequence_must_be_int(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "outbound",
                "interface": "wan",
                "target": "wanip",
                "sequence": "not-int",
            },
        )
        with pytest.raises(ValueError, match="sequence"):
            nat_rule_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="nat_rules",
            provider="opnsense",
            config={"kind": "outbound", "interface": "wan", "target": "wanip"},
        )
        # Manipulate after construction to bypass pydantic — guard the
        # service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            nat_rule_configs_from_resources([r])


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_managed_row_parses(self) -> None:
        row = {"uuid": "u1", "description": "something [infrafoundry:foo]"}
        live = _row_to_live(row, "outbound")
        assert live.uuid == "u1"
        assert live.kind == "outbound"
        assert live.managed_name == "foo"
        assert live.description == "something"

    def test_managed_row_no_user_description(self) -> None:
        row = {"uuid": "u1", "description": "[infrafoundry:foo]"}
        live = _row_to_live(row, "outbound")
        assert live.managed_name == "foo"
        assert live.description == ""

    def test_unmanaged_row_managed_name_none(self) -> None:
        row = {"uuid": "u1", "description": "regular description"}
        live = _row_to_live(row, "outbound")
        assert live.managed_name is None
        assert live.description == "regular description"

    def test_malformed_tag_raises(self) -> None:
        row = {"uuid": "u1", "description": "[infrafoundry:]"}
        with pytest.raises(OpnsenseDriftError):
            _row_to_live(row, "outbound")

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({}, "one_to_one")
        assert live.uuid == ""
        assert live.managed_name is None
        assert live.description == ""


# ---------------------------------------------------------------------------
# NATRuleService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_outbound_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        result = svc.search("outbound")
        client.request.assert_called_once_with("POST", "firewall/source_nat/searchRule")
        assert result == []

    def test_one_to_one_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        svc.search("one_to_one")
        client.request.assert_called_once_with("POST", "firewall/one_to_one/searchRule")

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "description": "desc [infrafoundry:a]"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "description": "unmanaged"},
            ]
        }
        svc = NATRuleService(client)
        result = svc.search("outbound")
        assert len(result) == 2
        assert result[0].managed_name == "a"
        assert result[1].managed_name is None

    def test_search_all_calls_both_controllers(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        svc.search_all()
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/source_nat/searchRule" in endpoints
        assert "firewall/one_to_one/searchRule" in endpoints


def _expected_with_category(rule: NATRuleConfig, category_uuid: str = "fake-cat") -> dict[str, Any]:
    """Return the payload ``add``/``update`` should send: rule envelope + category UUID."""
    payload = rule.to_payload()
    payload["rule"]["categories"] = category_uuid
    return payload


class TestServiceWriteOps:
    def test_add_outbound_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"  # short-circuit category bootstrap
        rule = _outbound("foo", target="wanip", interface="wan")
        svc.add(rule)
        client.request.assert_called_once_with(
            "POST", "firewall/source_nat/addRule", data=_expected_with_category(rule)
        )

    def test_add_one_to_one_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        rule = _one_to_one("dmz")
        svc.add(rule)
        client.request.assert_called_once_with(
            "POST", "firewall/one_to_one/addRule", data=_expected_with_category(rule)
        )

    def test_update_outbound(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        rule = _outbound("foo", target="wanip", interface="wan")
        svc.update("uuid-abc", rule)
        client.request.assert_called_once_with(
            "POST", "firewall/source_nat/setRule/uuid-abc", data=_expected_with_category(rule)
        )

    def test_delete_outbound_uses_outbound_endpoint(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.delete("u1", "outbound")
        client.request.assert_called_once_with("POST", "firewall/source_nat/delRule/u1")

    def test_delete_one_to_one_uses_one_to_one_endpoint(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.delete("u1", "one_to_one")
        client.request.assert_called_once_with("POST", "firewall/one_to_one/delRule/u1")

    def test_apply_changes_outbound(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.apply_changes("outbound")
        client.request.assert_called_once_with("POST", "firewall/source_nat/apply")

    def test_apply_changes_one_to_one(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.apply_changes("one_to_one")
        client.request.assert_called_once_with("POST", "firewall/one_to_one/apply")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_outbound_add_applies_only_outbound_changes(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"  # short-circuit category bootstrap
        diff = Diff(adds=[_outbound("foo", target="wanip", interface="wan")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/source_nat/addRule" in endpoints
        assert "firewall/source_nat/apply" in endpoints
        assert "firewall/one_to_one/apply" not in endpoints
        assert counts["created"] == 1

    def test_mixed_kinds_apply_changes_for_both(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        diff = Diff(
            adds=[
                _outbound("foo", target="wanip", interface="wan"),
                _one_to_one("dmz"),
            ]
        )
        svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/source_nat/apply" in endpoints
        assert "firewall/one_to_one/apply" in endpoints

    def test_delete_dispatches_per_kind(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        live_out = _live("u1", "foo", "outbound")
        live_oto = _live("u2", "bar", "one_to_one")
        diff = Diff(deletes=[live_out, live_oto])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/source_nat/delRule/u1" in endpoints
        assert "firewall/one_to_one/delRule/u2" in endpoints
        assert counts["deleted"] == 2


# ---------------------------------------------------------------------------
# export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_managed_rules_appear_in_export(self) -> None:
        client = MagicMock()
        # First call: outbound rows. Second call: 1:1 rows.
        client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "description": "LAN out [infrafoundry:lan-out]",
                        "interface": "wan",
                        "target": "wanip",
                    },
                    {"uuid": "u2", "description": "manual"},  # unmanaged
                ]
            },
            {
                "rows": [
                    {
                        "uuid": "u3",
                        "description": "DMZ [infrafoundry:dmz]",
                        "interface": "wan",
                        "external": "198.51.100.10",
                    }
                ]
            },
        ]
        svc = NATRuleService(client)
        text = svc.export_to_yaml()
        assert "lan-out" in text
        assert "dmz" in text
        assert "manual" not in text  # unmanaged rule excluded
        assert "kind: outbound" in text
        assert "kind: one_to_one" in text

    def test_export_with_no_managed_rules_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text


# ---------------------------------------------------------------------------
# Category bootstrap (fleet-wide marker)
# ---------------------------------------------------------------------------


class TestCategoryBootstrap:
    def test_returns_existing_category_uuid_from_search(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "other-uuid", "name": "other"},
                {"uuid": "ifn-uuid", "name": "infrafoundry"},
            ]
        }
        svc = NATRuleService(client)
        uuid = svc._ensure_infrafoundry_category()
        assert uuid == "ifn-uuid"
        # Only one call: searchItem; no addItem because category exists.
        client.request.assert_called_once_with("POST", "firewall/category/searchItem")

    def test_creates_category_when_search_returns_no_match(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {"rows": []},  # searchItem: no match
            {"uuid": "new-uuid"},  # addItem: created
        ]
        svc = NATRuleService(client)
        uuid = svc._ensure_infrafoundry_category()
        assert uuid == "new-uuid"
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints == ["firewall/category/searchItem", "firewall/category/addItem"]

    def test_creates_category_when_search_returns_other_names_only(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {"rows": [{"uuid": "x", "name": "other"}]},
            {"uuid": "new-uuid"},
        ]
        svc = NATRuleService(client)
        uuid = svc._ensure_infrafoundry_category()
        assert uuid == "new-uuid"

    def test_caches_uuid_across_calls(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": [{"uuid": "cached", "name": "infrafoundry"}]}
        svc = NATRuleService(client)
        first = svc._ensure_infrafoundry_category()
        second = svc._ensure_infrafoundry_category()
        assert first == second == "cached"
        # searchItem only called once; second invocation hits the cache.
        assert client.request.call_count == 1

    def test_raises_when_add_item_returns_no_uuid(self) -> None:
        from infrafoundry.core.exceptions import InfraFoundryError

        client = MagicMock()
        client.request.side_effect = [
            {"rows": []},
            {"result": "failed"},  # addItem: no uuid
        ]
        svc = NATRuleService(client)
        with pytest.raises(InfraFoundryError, match="infrafoundry"):
            svc._ensure_infrafoundry_category()

    def test_add_includes_category_in_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "cat-uuid"
        rule = _outbound("foo", target="wanip", interface="wan")
        svc.add(rule)
        # Capture the actual call data and check categories made it in.
        call = client.request.call_args
        sent_data = call.kwargs.get("data") or (call.args[2] if len(call.args) > 2 else None)
        assert sent_data is not None
        assert sent_data["rule"]["categories"] == "cat-uuid"

    def test_update_includes_category_in_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "cat-uuid"
        rule = _outbound("foo", target="wanip", interface="wan")
        svc.update("uuid-x", rule)
        call = client.request.call_args
        sent_data = call.kwargs.get("data") or (call.args[2] if len(call.args) > 2 else None)
        assert sent_data is not None
        assert sent_data["rule"]["categories"] == "cat-uuid"
