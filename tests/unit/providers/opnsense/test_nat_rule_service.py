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

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._category_marker import (
    reset_cache_for_tests as _reset_marker_cache,
)
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


@pytest.fixture(autouse=True)
def _clear_category_marker_cache() -> None:
    """Reset the shared identity-marker cache before each test.

    Without this, cached UUIDs from earlier tests would leak into later
    tests that share the same module-level ``_category_marker._cache``,
    masking real assertions about ``searchItem``/``addItem`` call
    counts.
    """
    _reset_marker_cache()


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


def _port_forward(
    name: str,
    *,
    description: str = "",
    target: str = "10.0.0.10",
    interface: str = "wan",
    sequence: int = 100,
    lock: bool = False,
    enabled: bool = True,
    log: bool = False,
    source_net: str = "any",
    source_port: str = "",
    destination_net: str = "wanip",
    destination_port: str = "",
    local_port: str = "8080",
    protocol: str = "tcp",
    ipprotocol: str = "inet",
    nordr: bool = False,
    pass_action: str = "",
    poolopts: str = "",
    natreflection: str = "",
    tag: str = "",
    tagged: str = "",
    nosync: bool = False,
) -> NATRuleConfig:
    return NATRuleConfig(
        name=name,
        kind="port_forward",
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        ipprotocol=ipprotocol,
        protocol=protocol,
        source_net=source_net,
        source_port=source_port,
        destination_net=destination_net,
        destination_port=destination_port,
        target=target,
        local_port=local_port,
        nordr=nordr,
        pass_action=pass_action,
        poolopts=poolopts,
        natreflection=natreflection,
        tag=tag,
        tagged=tagged,
        nosync=nosync,
    )


def _live(
    uuid: str,
    name: str | None,
    kind: str,
    *,
    description: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveNATRule:
    descr_value = (
        (f"{description} [infrafoundry:{name}]" if description else f"[infrafoundry:{name}]")
        if name is not None
        else description
    )
    # port_forward uses ``descr`` on the wire (DNat schema); outbound +
    # 1:1 use ``description``.
    raw_key = "descr" if kind == "port_forward" else "description"
    raw: dict[str, Any] = {
        "uuid": uuid,
        raw_key: descr_value,
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
    return ResourceConfig(name=name, type="firewall.nat", provider="opnsense", config=config)


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


# ---------------------------------------------------------------------------
# Port-forward payload (#725)
# ---------------------------------------------------------------------------


class TestPortForwardPayload:
    """``_to_port_forward_payload`` shape and quirks."""

    def test_payload_has_rule_envelope(self) -> None:
        payload = _port_forward("web").to_payload()
        assert set(payload.keys()) == {"rule"}

    def test_dotted_source_destination_keys(self) -> None:
        # DNat schema uses dotted keys ``source.network`` / ``source.port``
        # / ``source.not`` / ``destination.*`` (not the underscored
        # ``source_net`` etc. that outbound and 1:1 use).
        rule = _port_forward(
            "web",
            source_net="10.0.0.0/24",
            source_port="1024:65535",
            destination_net="wanip",
            destination_port="80",
        )
        inner = rule.to_payload()["rule"]
        assert inner["source.network"] == "10.0.0.0/24"
        assert inner["source.port"] == "1024:65535"
        assert inner["source.not"] == "0"
        assert inner["destination.network"] == "wanip"
        assert inner["destination.port"] == "80"
        assert inner["destination.not"] == "0"
        # The outbound/1:1 underscored forms must NOT appear in the
        # port_forward payload.
        assert "source_net" not in inner
        assert "destination_net" not in inner

    def test_disabled_polarity_flip(self) -> None:
        # enabled=True → disabled="0" (DNat negative polarity).
        rule = _port_forward("web", enabled=True)
        assert rule.to_payload()["rule"]["disabled"] == "0"
        # enabled=False → disabled="1".
        rule = _port_forward("web", enabled=False)
        assert rule.to_payload()["rule"]["disabled"] == "1"

    def test_local_port_uses_hyphenated_wire_key(self) -> None:
        # ``local_port`` (YAML/dataclass) → ``local-port`` (wire).
        rule = _port_forward("web", local_port="8080")
        inner = rule.to_payload()["rule"]
        assert inner["local-port"] == "8080"
        assert "local_port" not in inner

    def test_pass_action_uses_pass_wire_key(self) -> None:
        # ``pass_action`` (Python; ``pass`` is a keyword) → ``pass`` (wire).
        rule = _port_forward("web", pass_action="pass")
        inner = rule.to_payload()["rule"]
        assert inner["pass"] == "pass"
        assert "pass_action" not in inner

    def test_descr_wire_key_carries_identity_tag(self) -> None:
        # DNat schema uses ``descr``, not ``description``. Identity-tag
        # suffix is added at serialization, same as outbound + 1:1.
        rule = _port_forward("web", description="HTTP -> 10.0.0.10")
        inner = rule.to_payload()["rule"]
        assert inner["descr"] == "HTTP -> 10.0.0.10 [infrafoundry:web]"
        assert "description" not in inner

    def test_empty_description_yields_tag_only_in_descr(self) -> None:
        rule = _port_forward("web", description="")
        inner = rule.to_payload()["rule"]
        assert inner["descr"] == "[infrafoundry:web]"

    def test_booleans_serialize_to_zero_one_strings(self) -> None:
        rule = _port_forward(
            "web",
            log=True,
            nordr=True,
            nosync=True,
            source_port="",
        )
        inner = rule.to_payload()["rule"]
        assert inner["log"] == "1"
        assert inner["nordr"] == "1"
        assert inner["nosync"] == "1"

    def test_default_field_set_complete(self) -> None:
        # Confirm every wire field documented in the plan is present.
        rule = _port_forward("web")
        inner = rule.to_payload()["rule"]
        expected_keys = {
            "disabled",
            "log",
            "sequence",
            "interface",
            "ipprotocol",
            "protocol",
            "source.network",
            "source.port",
            "source.not",
            "destination.network",
            "destination.port",
            "destination.not",
            "target",
            "local-port",
            "nordr",
            "pass",
            "poolopts",
            "natreflection",
            "tag",
            "tagged",
            "nosync",
            "descr",
        }
        assert set(inner.keys()) == expected_keys


class TestDiffKey:
    def test_outbound_and_one_to_one_same_name_have_different_keys(self) -> None:
        out = _outbound("foo", target="wanip")
        oto = _one_to_one("foo")
        assert out.diff_key != oto.diff_key
        assert out.diff_key == ("outbound", "foo")
        assert oto.diff_key == ("one_to_one", "foo")

    def test_port_forward_has_distinct_diff_key(self) -> None:
        out = _outbound("foo", target="wanip")
        oto = _one_to_one("foo")
        pf = _port_forward("foo")
        keys = {out.diff_key, oto.diff_key, pf.diff_key}
        # All three are distinct.
        assert len(keys) == 3
        assert pf.diff_key == ("port_forward", "foo")


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


class TestPortForwardDiff:
    """Per-kind isolation for the third kind (#725)."""

    def test_new_port_forward_adds(self) -> None:
        diff = compute_diff([_port_forward("web")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "web"
        assert diff.adds[0].kind == "port_forward"

    def test_no_update_when_port_forward_payload_matches(self) -> None:
        rule = _port_forward("web", target="10.0.0.10", interface="wan", local_port="8080")
        payload_inner = rule.to_payload()["rule"]
        live_raw: dict[str, Any] = {"uuid": "u1", **payload_inner}
        live = LiveNATRule(
            uuid="u1",
            kind="port_forward",
            managed_name="web",
            description="",
            raw=live_raw,
        )
        diff = compute_diff([rule], [live])
        assert diff.is_empty

    def test_update_when_port_forward_target_changes(self) -> None:
        rule_have = _port_forward("web", target="10.0.0.10", local_port="8080")
        live_raw = {"uuid": "u1", **rule_have.to_payload()["rule"]}
        live = LiveNATRule(
            uuid="u1",
            kind="port_forward",
            managed_name="web",
            description="",
            raw=live_raw,
        )
        rule_want = _port_forward("web", target="10.0.0.99", local_port="8080")
        diff = compute_diff([rule_want], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.target == "10.0.0.99"

    def test_managed_port_forward_with_no_desired_is_deleted(self) -> None:
        live = _live("u1", "stale", "port_forward")
        diff = compute_diff([], [live])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"
        assert diff.deletes[0].kind == "port_forward"

    def test_unmanaged_port_forward_silently_ignored(self) -> None:
        live = LiveNATRule(
            uuid="u-unmanaged",
            kind="port_forward",
            managed_name=None,
            description="manually-created port forward",
            raw={"uuid": "u-unmanaged", "descr": "manually-created port forward"},
        )
        diff = compute_diff([], [live])
        assert diff.deletes == []
        assert diff.is_empty

    def test_locked_port_forward_skipped(self) -> None:
        live = _live(
            "u1",
            "ssh-fwd",
            "port_forward",
            raw_overrides={"target": "10.0.0.5", "interface": "wan"},
        )
        rule = _port_forward("ssh-fwd", target="changed", lock=True)
        diff = compute_diff([rule], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1

    def test_three_kinds_with_same_name_are_independent(self) -> None:
        # All three kinds share name "shared"; each lives in its own
        # diff bucket.
        out_live = _live("u-out", "shared", "outbound")
        oto_live = _live("u-oto", "shared", "one_to_one")
        pf_live = _live("u-pf", "shared", "port_forward")
        rule_out = _outbound("shared", target="wanip", interface="wan")
        rule_oto = _one_to_one("shared")
        rule_pf = _port_forward("shared")
        diff = compute_diff([rule_out, rule_oto, rule_pf], [out_live, oto_live, pf_live])
        # No deletes — each kind's desired matches its own live name.
        assert diff.deletes == []

    def test_outbound_diff_does_not_match_port_forward_live(self) -> None:
        # YAML has outbound "foo"; box has port_forward "foo".
        pf_live = _live("u-pf", "foo", "port_forward")
        rule_out = _outbound("foo", target="wanip", interface="wan")
        diff = compute_diff([rule_out], [pf_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].kind == "outbound"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].kind == "port_forward"

    def test_add_only_suppresses_port_forward_deletes(self) -> None:
        live = _live("u1", "stale", "port_forward")
        diff = compute_diff([], [live], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


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


class TestConfigsFromResourcesPortForward:
    """Parser checks for ``kind: port_forward`` (#725)."""

    def test_valid_port_forward_parses(self) -> None:
        r = _resource(
            "web",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "local_port": "8080",
                "destination_net": "wanip",
                "destination_port": "80",
                "protocol": "tcp",
                "description": "HTTP -> 10.0.0.10",
            },
        )
        result = nat_rule_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.kind == "port_forward"
        assert cfg.target == "10.0.0.10"
        assert cfg.local_port == "8080"
        assert cfg.destination_net == "wanip"
        assert cfg.destination_port == "80"
        assert cfg.protocol == "tcp"
        assert cfg.description == "HTTP -> 10.0.0.10"

    def test_port_forward_missing_target_rejected(self) -> None:
        r = _resource("bad", {"kind": "port_forward", "interface": "wan"})
        with pytest.raises(ValueError, match="target"):
            nat_rule_configs_from_resources([r])

    def test_port_forward_missing_interface_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "port_forward",
                "target": "10.0.0.10",
            },
        )
        with pytest.raises(ValueError, match="interface"):
            nat_rule_configs_from_resources([r])

    def test_port_forward_invalid_pass_action_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "pass_action": "invalid",
            },
        )
        with pytest.raises(ValueError, match="pass_action"):
            nat_rule_configs_from_resources([r])

    def test_port_forward_invalid_poolopts_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "poolopts": "not-an-algorithm",
            },
        )
        with pytest.raises(ValueError, match="poolopts"):
            nat_rule_configs_from_resources([r])

    def test_port_forward_invalid_natreflection_rejected(self) -> None:
        # DNat allows "" / "purenat" / "disable"; "enable" (the 1:1 value)
        # must be rejected here.
        r = _resource(
            "bad",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "natreflection": "enable",
            },
        )
        with pytest.raises(ValueError, match="natreflection"):
            nat_rule_configs_from_resources([r])

    def test_port_forward_purenat_natreflection_accepted(self) -> None:
        # The DNat-only value should pass the parser.
        r = _resource(
            "ok",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "natreflection": "purenat",
            },
        )
        result = nat_rule_configs_from_resources([r])
        assert result[0].natreflection == "purenat"

    def test_port_forward_pass_pass_action_accepted(self) -> None:
        r = _resource(
            "ok",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "pass_action": "pass",
            },
        )
        result = nat_rule_configs_from_resources([r])
        assert result[0].pass_action == "pass"

    def test_port_forward_nordr_must_be_bool(self) -> None:
        r = _resource(
            "bad",
            {
                "kind": "port_forward",
                "interface": "wan",
                "target": "10.0.0.10",
                "nordr": "true",  # string, not bool
            },
        )
        with pytest.raises(ValueError, match="nordr"):
            nat_rule_configs_from_resources([r])


class TestConfigsFromResourcesGeneral:
    def test_invalid_kind_rejected(self) -> None:
        # ``port_forward`` was previously rejected as out-of-scope; #725
        # added it as a third valid kind. ``unknown`` stands in for the
        # "bad kind" negative-test coverage now.
        r = _resource("bad", {"kind": "unknown"})
        with pytest.raises(ValueError, match="kind"):
            nat_rule_configs_from_resources([r])

    def test_missing_kind_rejected(self) -> None:
        r = _resource("bad", {"interface": "wan", "target": "wanip"})
        with pytest.raises(ValueError, match="kind"):
            nat_rule_configs_from_resources([r])

    def test_non_nat_resources_ignored(self) -> None:
        nat = _resource("ok", {"kind": "outbound", "interface": "wan", "target": "wanip"})
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
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
            type="firewall.nat",
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

    def test_port_forward_row_uses_descr_field(self) -> None:
        # DNat schema uses ``descr`` (not ``description``).
        row = {"uuid": "u1", "descr": "HTTP fwd [infrafoundry:web]"}
        live = _row_to_live(row, "port_forward")
        assert live.uuid == "u1"
        assert live.kind == "port_forward"
        assert live.managed_name == "web"
        assert live.description == "HTTP fwd"

    def test_port_forward_row_descr_tag_only(self) -> None:
        row = {"uuid": "u1", "descr": "[infrafoundry:web]"}
        live = _row_to_live(row, "port_forward")
        assert live.managed_name == "web"
        assert live.description == ""

    def test_port_forward_unmanaged_row(self) -> None:
        row = {"uuid": "u1", "descr": "manual port forward"}
        live = _row_to_live(row, "port_forward")
        assert live.managed_name is None
        assert live.description == "manual port forward"

    def test_port_forward_falls_back_to_description_key(self) -> None:
        # Defensive: if a hand-built row uses ``description`` instead of
        # ``descr`` (e.g., from a unit test), parsing still succeeds.
        row = {"uuid": "u1", "description": "X [infrafoundry:web]"}
        live = _row_to_live(row, "port_forward")
        assert live.managed_name == "web"

    def test_port_forward_malformed_descr_raises(self) -> None:
        row = {"uuid": "u1", "descr": "[infrafoundry:]"}
        with pytest.raises(OpnsenseDriftError):
            _row_to_live(row, "port_forward")


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

    def test_search_all_calls_all_controllers(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        svc.search_all()
        endpoints = [c.args[1] for c in client.request.call_args_list]
        # All three kinds queried (#725).
        assert "firewall/source_nat/searchRule" in endpoints
        assert "firewall/one_to_one/searchRule" in endpoints
        assert "firewall/d_nat/searchRule" in endpoints


def _make_per_kind_request(
    *,
    outbound_response: Any = None,
    one_to_one_response: Any = None,
    port_forward_response: Any = None,
) -> Any:
    """Build a ``client.request`` side-effect that routes by URL substring.

    Returns a callable that, when invoked with ``(method, url, **kwargs)``,
    inspects ``url`` and returns (or raises) the response configured for
    the matching NAT kind. Each ``*_response`` may be either a value to
    return or an ``Exception`` instance to raise. ``None`` causes an
    ``AssertionError`` (which surfaces as an unexpected call).

    The URL substrings are the per-kind controller bases used by
    :class:`NATRuleService`: ``firewall/source_nat`` (outbound),
    ``firewall/one_to_one`` (1:1), ``firewall/d_nat`` (port_forward).
    """

    def side_effect(method: str, url: str, **_kwargs: Any) -> Any:
        if "firewall/source_nat" in url:
            response = outbound_response
        elif "firewall/one_to_one" in url:
            response = one_to_one_response
        elif "firewall/d_nat" in url:
            response = port_forward_response
        else:  # pragma: no cover - defensive: unexpected URL
            raise AssertionError(f"Unexpected URL routed to mock client: {url!r}")
        if isinstance(response, BaseException):
            raise response
        if response is None:  # pragma: no cover - defensive
            raise AssertionError(f"No mock response configured for URL {url!r}")
        return response

    return side_effect


# ---------------------------------------------------------------------------
# search_all_tolerant — migrate-only per-kind 404 tolerance (#754)
# ---------------------------------------------------------------------------


class TestSearchAllTolerant:
    """``search_all_tolerant`` skips per-kind 404s with WARNING; non-404s raise."""

    def test_only_port_forward_404s(self, caplog: pytest.LogCaptureFixture) -> None:
        # outbound + 1:1 return rows; port_forward 404s. Result should
        # contain rows from the two surviving kinds only, and a single
        # WARNING should fire naming ``port_forward``.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response={"rows": [{"uuid": "u-out", "description": "out [infrafoundry:o1]"}]},
            one_to_one_response={
                "rows": [{"uuid": "u-oto", "description": "oto [infrafoundry:t1]"}]
            },
            port_forward_response=APIError(
                "Not Found",
                status_code=404,
                response="Controller missing",
                provider="opnsense",
            ),
        )
        svc = NATRuleService(client)

        with caplog.at_level(logging.WARNING):
            result = svc.search_all_tolerant()

        managed_names = sorted(r.managed_name for r in result if r.managed_name is not None)
        assert managed_names == ["o1", "t1"]
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "port_forward" in message
        assert "404" in message

    def test_two_kinds_404(self, caplog: pytest.LogCaptureFixture) -> None:
        # outbound + port_forward 404; only 1:1 survives. Two warnings.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response=APIError("404", status_code=404),
            one_to_one_response={
                "rows": [{"uuid": "u-oto", "description": "oto [infrafoundry:t1]"}]
            },
            port_forward_response=APIError("404", status_code=404),
        )
        svc = NATRuleService(client)

        with caplog.at_level(logging.WARNING):
            result = svc.search_all_tolerant()

        managed_names = [r.managed_name for r in result]
        assert managed_names == ["t1"]
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 2
        kinds_in_messages = {
            kind
            for rec in warnings
            for kind in ("outbound", "one_to_one", "port_forward")
            if kind in rec.getMessage()
        }
        assert kinds_in_messages == {"outbound", "port_forward"}

    def test_all_three_kinds_404(self, caplog: pytest.LogCaptureFixture) -> None:
        # All three controllers 404. Result is empty; three warnings.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response=APIError("404", status_code=404),
            one_to_one_response=APIError("404", status_code=404),
            port_forward_response=APIError("404", status_code=404),
        )
        svc = NATRuleService(client)

        with caplog.at_level(logging.WARNING):
            result = svc.search_all_tolerant()

        assert result == []
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 3

    def test_non_404_api_error_propagates(self) -> None:
        # 500 errors must not be swallowed — apply-time and migrate
        # alike should fail loudly on a real server-side error.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response={"rows": []},
            one_to_one_response=APIError("Internal Server Error", status_code=500),
            port_forward_response={"rows": []},
        )
        svc = NATRuleService(client)
        with pytest.raises(APIError) as exc_info:
            svc.search_all_tolerant()
        assert exc_info.value.status_code == 500

    def test_authentication_error_propagates(self) -> None:
        # AuthenticationError is a subclass of APIError with 401/403 —
        # it must NOT be swallowed even though it is an APIError.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response=AuthenticationError("Unauthorized", status_code=401),
            one_to_one_response={"rows": []},
            port_forward_response={"rows": []},
        )
        svc = NATRuleService(client)
        with pytest.raises(AuthenticationError) as exc_info:
            svc.search_all_tolerant()
        assert exc_info.value.status_code == 401

    def test_success_path_matches_search_all(self, caplog: pytest.LogCaptureFixture) -> None:
        # When no kind 404s, the tolerant variant returns the same rows
        # as ``search_all`` (same input data) and emits no warnings.
        rows_outbound = [{"uuid": "u-out", "description": "out [infrafoundry:o1]"}]
        rows_one_to_one = [{"uuid": "u-oto", "description": "oto [infrafoundry:t1]"}]
        rows_port_forward = [{"uuid": "u-pf", "descr": "pf [infrafoundry:p1]"}]

        # Run search_all_tolerant.
        client_a = MagicMock()
        client_a.request.side_effect = _make_per_kind_request(
            outbound_response={"rows": rows_outbound},
            one_to_one_response={"rows": rows_one_to_one},
            port_forward_response={"rows": rows_port_forward},
        )
        svc_a = NATRuleService(client_a)
        with caplog.at_level(logging.WARNING):
            tolerant = svc_a.search_all_tolerant()
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert warnings == []

        # Run search_all on a separate client/instance with the same
        # configured responses to compare outputs.
        client_b = MagicMock()
        client_b.request.side_effect = _make_per_kind_request(
            outbound_response={"rows": rows_outbound},
            one_to_one_response={"rows": rows_one_to_one},
            port_forward_response={"rows": rows_port_forward},
        )
        svc_b = NATRuleService(client_b)
        strict = svc_b.search_all()

        # Same managed-name sequence and per-kind ordering.
        assert [(r.kind, r.managed_name) for r in tolerant] == [
            (r.kind, r.managed_name) for r in strict
        ]

    def test_export_to_yaml_uses_tolerant_path(self, caplog: pytest.LogCaptureFixture) -> None:
        # End-to-end: when port_forward 404s, ``export_to_yaml`` produces
        # YAML containing the outbound + 1:1 managed rules and a
        # WARNING is logged naming ``port_forward``.
        client = MagicMock()
        client.request.side_effect = _make_per_kind_request(
            outbound_response={
                "rows": [
                    {
                        "uuid": "u-out",
                        "description": "LAN out [infrafoundry:lan-out]",
                        "interface": "wan",
                        "target": "wanip",
                    }
                ]
            },
            one_to_one_response={
                "rows": [
                    {
                        "uuid": "u-oto",
                        "description": "DMZ [infrafoundry:dmz]",
                        "interface": "wan",
                        "external": "198.51.100.10",
                    }
                ]
            },
            port_forward_response=APIError("404", status_code=404),
        )
        svc = NATRuleService(client)

        with caplog.at_level(logging.WARNING):
            text = svc.export_to_yaml()

        assert "lan-out" in text
        assert "dmz" in text
        # No port-forward managed rules emitted.
        assert "kind: port_forward" not in text
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "port_forward" in warnings[0].getMessage()


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

    def test_add_port_forward_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        rule = _port_forward("web")
        svc.add(rule)
        client.request.assert_called_once_with(
            "POST", "firewall/d_nat/addRule", data=_expected_with_category(rule)
        )

    def test_update_port_forward(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        rule = _port_forward("web")
        svc.update("uuid-pf", rule)
        client.request.assert_called_once_with(
            "POST", "firewall/d_nat/setRule/uuid-pf", data=_expected_with_category(rule)
        )

    def test_delete_port_forward_uses_d_nat_endpoint(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.delete("u-pf", "port_forward")
        client.request.assert_called_once_with("POST", "firewall/d_nat/delRule/u-pf")

    def test_apply_changes_port_forward(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        svc.apply_changes("port_forward")
        client.request.assert_called_once_with("POST", "firewall/d_nat/apply")

    def test_port_forward_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = NATRuleService(client)
        svc.search("port_forward")
        client.request.assert_called_once_with("POST", "firewall/d_nat/searchRule")


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

    def test_port_forward_only_apply_calls_d_nat_apply(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        diff = Diff(adds=[_port_forward("web")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/d_nat/addRule" in endpoints
        assert "firewall/d_nat/apply" in endpoints
        # Other kinds' apply endpoints must not be called.
        assert "firewall/source_nat/apply" not in endpoints
        assert "firewall/one_to_one/apply" not in endpoints
        assert counts["created"] == 1

    def test_three_kind_apply_calls_all_three_apply_endpoints(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = NATRuleService(client)
        svc._category_uuid = "fake-cat"
        diff = Diff(
            adds=[
                _outbound("a", target="wanip", interface="wan"),
                _one_to_one("b"),
                _port_forward("c"),
            ]
        )
        svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/source_nat/apply" in endpoints
        assert "firewall/one_to_one/apply" in endpoints
        assert "firewall/d_nat/apply" in endpoints

    def test_port_forward_delete_uses_d_nat_endpoint(self) -> None:
        client = MagicMock()
        svc = NATRuleService(client)
        live_pf = _live("u-pf", "stale", "port_forward")
        diff = Diff(deletes=[live_pf])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/d_nat/delRule/u-pf" in endpoints
        assert counts["deleted"] == 1


# ---------------------------------------------------------------------------
# export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_managed_rules_appear_in_export(self) -> None:
        client = MagicMock()
        # ``search_all`` iterates ALLOWED_KINDS in order:
        # outbound → one_to_one → port_forward.
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
            # port_forward rows use ``descr`` (DNat schema) and dotted
            # source/destination keys.
            {
                "rows": [
                    {
                        "uuid": "u4",
                        "descr": "Web fwd [infrafoundry:web-fwd]",
                        "interface": "wan",
                        "target": "10.0.0.10",
                        "local-port": "8080",
                        "disabled": "0",
                        "source.network": "any",
                        "destination.network": "wanip",
                    },
                    {"uuid": "u5", "descr": "manual pf"},  # unmanaged
                ]
            },
        ]
        svc = NATRuleService(client)
        text = svc.export_to_yaml()
        assert "lan-out" in text
        assert "dmz" in text
        assert "web-fwd" in text
        assert "manual" not in text  # unmanaged rule excluded
        assert "kind: outbound" in text
        assert "kind: one_to_one" in text
        assert "kind: port_forward" in text

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

    def test_ensure_infrafoundry_category_uses_shared_cache(self) -> None:
        # Two distinct service instances against the same client share the
        # process-wide cache: only the first instance triggers searchItem;
        # the second hits the cache via the shared helper (#746).
        client = MagicMock()
        client.request.return_value = {"rows": [{"uuid": "shared-uuid", "name": "infrafoundry"}]}
        svc_a = NATRuleService(client)
        svc_b = NATRuleService(client)
        assert svc_a._ensure_infrafoundry_category() == "shared-uuid"
        assert svc_b._ensure_infrafoundry_category() == "shared-uuid"
        # Only one searchItem across both instances; the second hits the
        # process-wide cache in ``_category_marker``.
        assert client.request.call_count == 1

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
