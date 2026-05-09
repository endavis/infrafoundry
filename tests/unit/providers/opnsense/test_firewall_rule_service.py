"""Unit tests for ``infrafoundry.providers.opnsense.services.firewall_rule``.

Coverage:
    - Identity-suffix encoder/parser (round-trip + malformed cases).
    - ``FirewallRuleConfig.to_payload`` envelope shape and wire-key
      serialization, including the hyphenated wire keys (``state-policy``,
      ``max-src-conn``, ``divert-to``, etc.) and bool/int stringification.
    - ``compute_diff`` add / update / delete / no-op / lock / add_only.
    - Unmanaged live rules silently ignored.
    - ``firewall_rule_configs_from_resources`` validation.
    - ``_row_to_live`` parses managed/unmanaged rows; raises on malformed.
    - ``FirewallRuleService`` API method dispatch via the mock client.
    - ``_ensure_infrafoundry_category`` lazy lookup + cache.
    - ``apply_diff`` orchestration: empty noop, write-then-apply, single
      apply per mutation batch.
    - ``export_to_yaml`` round-trip (managed only; marker UUID stripped;
      hyphenated wire keys mapped back to underscored YAML keys); the
      multi-valued categories field preserves operator UUIDs.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, AuthenticationError, InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._category_marker import (
    reset_cache_for_tests as _reset_marker_cache,
)
from infrafoundry.providers.opnsense.services.firewall_rule import (
    DEFAULT_SEQUENCE,
    Diff,
    FirewallRuleConfig,
    FirewallRuleService,
    LiveFirewallRule,
    OpnsenseDriftError,
    _row_to_live,
    compute_diff,
    encode_identity,
    firewall_rule_configs_from_resources,
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


def _rule(
    name: str,
    *,
    description: str = "",
    interface: str = "lan",
    sequence: int = DEFAULT_SEQUENCE,
    lock: bool = False,
    enabled: bool = True,
    log: bool = False,
    action: str = "pass",
    direction: str = "in",
    ipprotocol: str = "inet",
    protocol: str = "any",
    source_net: str = "any",
    destination_net: str = "any",
    state_policy: str = "",
    statetype: str = "",
    gateway: str = "",
    categories: tuple[str, ...] = (),
    quick: bool = True,
    tcpflags1: str = "",
    tcpflags2: str = "",
    tcpflags_any: bool = False,
    max_src_conn: str = "",
    set_prio: str = "",
    divert_to: str = "",
    udp_first: str = "",
) -> FirewallRuleConfig:
    return FirewallRuleConfig(
        name=name,
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        action=action,
        quick=quick,
        direction=direction,
        ipprotocol=ipprotocol,
        protocol=protocol,
        source_net=source_net,
        destination_net=destination_net,
        statetype=statetype,
        state_policy=state_policy,
        gateway=gateway,
        categories=categories,
        tcpflags1=tcpflags1,
        tcpflags2=tcpflags2,
        tcpflags_any=tcpflags_any,
        max_src_conn=max_src_conn,
        set_prio=set_prio,
        divert_to=divert_to,
        udp_first=udp_first,
    )


def _live(
    uuid: str,
    name: str | None,
    *,
    description: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveFirewallRule:
    descr_value = (
        (f"{description} [infrafoundry:{name}]" if description else f"[infrafoundry:{name}]")
        if name is not None
        else description
    )
    raw: dict[str, Any] = {
        "uuid": uuid,
        "description": descr_value,
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveFirewallRule(
        uuid=uuid,
        managed_name=name,
        description=description,
        raw=raw,
    )


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.rules", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# Identity-suffix helpers
# ---------------------------------------------------------------------------


class TestIdentityEncoder:
    def test_encode_with_user_description(self) -> None:
        assert encode_identity("foo", "user desc") == "user desc [infrafoundry:foo]"

    def test_encode_with_empty_user_description(self) -> None:
        # No leading whitespace when user description is empty.
        assert encode_identity("foo", "") == "[infrafoundry:foo]"


class TestIdentityParser:
    def test_parse_with_user_description(self) -> None:
        name, user = parse_identity("LAN allow [infrafoundry:lan-allow]")
        assert name == "lan-allow"
        assert user == "LAN allow"

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
        with pytest.raises(OpnsenseDriftError):
            parse_identity("user desc [infrafoundry:Foo]")

    def test_parse_malformed_underscore_raises(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            parse_identity("user desc [infrafoundry:foo_bar]")

    def test_parse_tag_in_middle_raises(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[infrafoundry:foo] trailing text")

    def test_parse_double_bracket_raises(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[[infrafoundry:foo]]")


# ---------------------------------------------------------------------------
# FirewallRuleConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayloadEnvelope:
    def test_payload_has_rule_envelope(self) -> None:
        payload = _rule("foo").to_payload()
        assert set(payload.keys()) == {"rule"}

    def test_categories_omitted_at_dataclass_layer(self) -> None:
        # ``to_payload`` excludes ``categories`` — it's special-cased at
        # the service layer via ``_payload_with_category``.
        payload = _rule("foo", categories=("op-uuid",)).to_payload()
        assert "categories" not in payload["rule"]


class TestPayloadBoolSerialization:
    def test_enabled_true_serializes_to_one(self) -> None:
        inner = _rule("foo", enabled=True).to_payload()["rule"]
        assert inner["enabled"] == "1"

    def test_enabled_false_serializes_to_zero(self) -> None:
        inner = _rule("foo", enabled=False).to_payload()["rule"]
        assert inner["enabled"] == "0"

    def test_log_quick_tcpflags_any_all_serialize_zero_one(self) -> None:
        inner = _rule(
            "foo",
            log=True,
            quick=False,
            tcpflags_any=True,
        ).to_payload()["rule"]
        assert inner["log"] == "1"
        assert inner["quick"] == "0"
        assert inner["tcpflags_any"] == "1"

    def test_default_bools_present(self) -> None:
        inner = _rule("foo").to_payload()["rule"]
        # All bools always appear (even at default).
        for key in (
            "enabled",
            "quick",
            "interfacenot",
            "source_not",
            "destination_not",
            "log",
            "disablereplyto",
            "tcpflags_any",
            "nopfsync",
            "nosync",
            "allowopts",
        ):
            assert inner[key] in ("0", "1")


class TestPayloadIntSerialization:
    def test_sequence_serializes_to_string(self) -> None:
        inner = _rule("foo", sequence=200).to_payload()["rule"]
        assert inner["sequence"] == "200"
        assert isinstance(inner["sequence"], str)

    def test_default_sequence_serializes(self) -> None:
        inner = _rule("foo").to_payload()["rule"]
        assert inner["sequence"] == str(DEFAULT_SEQUENCE)


class TestPayloadHyphenatedWireKeys:
    """Verify dataclass underscore attrs map to OPNsense's hyphenated wire keys."""

    def test_state_policy_uses_hyphen(self) -> None:
        inner = _rule("foo", state_policy="floating").to_payload()["rule"]
        assert inner["state-policy"] == "floating"
        assert "state_policy" not in inner

    def test_max_src_conn_uses_hyphen(self) -> None:
        rule = FirewallRuleConfig(
            name="foo",
            interface="lan",
            max_src_conn="100",
            max_src_conn_rate="10/5",
            max_src_conn_rates="20",
            max_src_nodes="50",
            max_src_states="200",
        )
        inner = rule.to_payload()["rule"]
        assert inner["max-src-conn"] == "100"
        assert inner["max-src-conn-rate"] == "10/5"
        assert inner["max-src-conn-rates"] == "20"
        assert inner["max-src-nodes"] == "50"
        assert inner["max-src-states"] == "200"
        # The Python attr names must NOT appear on the wire.
        assert "max_src_conn" not in inner
        assert "max_src_conn_rate" not in inner

    def test_set_prio_uses_hyphen(self) -> None:
        rule = FirewallRuleConfig(
            name="foo",
            interface="lan",
            set_prio="3",
            set_prio_low="1",
        )
        inner = rule.to_payload()["rule"]
        assert inner["set-prio"] == "3"
        assert inner["set-prio-low"] == "1"
        assert "set_prio" not in inner
        assert "set_prio_low" not in inner

    def test_divert_to_uses_hyphen(self) -> None:
        inner = _rule("foo", divert_to="127.0.0.1:3128").to_payload()["rule"]
        assert inner["divert-to"] == "127.0.0.1:3128"
        assert "divert_to" not in inner

    def test_udp_keys_use_hyphen(self) -> None:
        rule = FirewallRuleConfig(
            name="foo",
            interface="lan",
            udp_first="60",
            udp_multiple="60",
            udp_single="30",
        )
        inner = rule.to_payload()["rule"]
        assert inner["udp-first"] == "60"
        assert inner["udp-multiple"] == "60"
        assert inner["udp-single"] == "30"
        assert "udp_first" not in inner


class TestPayloadDescriptionIdentity:
    def test_description_carries_identity_suffix(self) -> None:
        inner = _rule("foo", description="LAN allow").to_payload()["rule"]
        assert inner["description"] == "LAN allow [infrafoundry:foo]"

    def test_empty_description_yields_tag_only(self) -> None:
        inner = _rule("foo", description="").to_payload()["rule"]
        assert inner["description"] == "[infrafoundry:foo]"


class TestPayloadFieldCoverage:
    """Sanity check: every documented attribute is on the wire."""

    def test_full_field_set_present(self) -> None:
        rule = FirewallRuleConfig(name="foo", interface="lan")
        inner = rule.to_payload()["rule"]
        expected_keys = {
            # Core / match
            "enabled",
            "sequence",
            "sort_order",
            "action",
            "quick",
            "interface",
            "interfacenot",
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
            # State
            "statetype",
            "state-policy",
            "statetimeout",
            "adaptivestart",
            "adaptiveend",
            # Routing
            "gateway",
            "divert-to",
            "replyto",
            "disablereplyto",
            # Categorization (sans "categories" — service layer adds it)
            "tag",
            "tagged",
            # ICMP / TCP
            "icmptype",
            "icmp6type",
            "tcpflags1",
            "tcpflags2",
            "tcpflags_any",
            # Limits
            "max",
            "max-src-conn",
            "max-src-conn-rate",
            "max-src-conn-rates",
            "max-src-nodes",
            "max-src-states",
            "overload",
            # QoS
            "prio",
            "prio_group",
            "set-prio",
            "set-prio-low",
            "tos",
            # UDP / pfsync
            "udp-first",
            "udp-multiple",
            "udp-single",
            "nopfsync",
            "nosync",
            # Misc
            "allowopts",
        }
        assert set(inner.keys()) == expected_keys


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
    def test_new_rule_adds(self) -> None:
        diff = compute_diff([_rule("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "foo"


class TestComputeDiffUpdates:
    def test_update_when_action_changes(self) -> None:
        # Build live raw matching defaults except for ``action``.
        rule = _rule("foo", interface="lan")
        live_raw = {"uuid": "u1", **rule.to_payload()["rule"]}
        live_raw["action"] = "block"  # divergent
        live = LiveFirewallRule(
            uuid="u1",
            managed_name="foo",
            description="",
            raw=live_raw,
        )
        diff = compute_diff([rule], [live])
        assert len(diff.updates) == 1
        assert len(diff.adds) == 0
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.action == "pass"

    def test_no_update_when_payload_matches(self) -> None:
        rule = _rule("foo", interface="lan")
        payload_inner = rule.to_payload()["rule"]
        live_raw: dict[str, Any] = {"uuid": "u1", **payload_inner}
        live = LiveFirewallRule(
            uuid="u1",
            managed_name="foo",
            description="",
            raw=live_raw,
        )
        diff = compute_diff([rule], [live])
        assert diff.is_empty


class TestComputeDiffDeletes:
    def test_managed_live_with_no_desired_is_deleted(self) -> None:
        live = _live("u1", "stale")
        diff = compute_diff([], [live])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_unmanaged_live_silently_ignored(self) -> None:
        # No InfraFoundry tag → unmanaged → never deleted by the diff engine.
        live = LiveFirewallRule(
            uuid="u-unmanaged",
            managed_name=None,
            description="manually-created rule",
            raw={"uuid": "u-unmanaged", "description": "manually-created rule"},
        )
        diff = compute_diff([], [live])
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_suppresses_deletes(self) -> None:
        live = _live("u1", "stale")
        diff = compute_diff([], [live], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        live = _live(
            "u1",
            "wan-survival",
            raw_overrides={"interface": "lan"},
        )
        # Different action, but locked → no update emitted.
        rule = _rule("wan-survival", action="block", lock=True)
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
        rule = _rule("missing", lock=True)
        diff = compute_diff([rule], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        rule = _rule("foo", lock=True)
        diff = Diff(locked=[(rule, None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_rule("foo")])
        assert not diff.is_empty


# ---------------------------------------------------------------------------
# firewall_rule_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_minimal_valid_parses(self) -> None:
        r = _resource(
            "lan-allow",
            {"interface": "lan", "description": "LAN allow"},
        )
        result = firewall_rule_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "lan-allow"
        assert cfg.interface == "lan"
        assert cfg.description == "LAN allow"
        # Defaults applied.
        assert cfg.action == "pass"
        assert cfg.direction == "in"
        assert cfg.ipprotocol == "inet"
        assert cfg.protocol == "any"
        assert cfg.source_net == "any"
        assert cfg.destination_net == "any"
        assert cfg.enabled is True
        assert cfg.quick is True
        assert cfg.lock is False

    def test_invalid_action_rejected(self) -> None:
        r = _resource("bad", {"interface": "lan", "action": "drop"})
        with pytest.raises(ValueError, match="action"):
            firewall_rule_configs_from_resources([r])

    def test_invalid_direction_rejected(self) -> None:
        r = _resource("bad", {"interface": "lan", "direction": "diagonal"})
        with pytest.raises(ValueError, match="direction"):
            firewall_rule_configs_from_resources([r])

    def test_invalid_ipprotocol_rejected(self) -> None:
        r = _resource("bad", {"interface": "lan", "ipprotocol": "ipv7"})
        with pytest.raises(ValueError, match="ipprotocol"):
            firewall_rule_configs_from_resources([r])

    def test_invalid_state_policy_rejected(self) -> None:
        r = _resource("bad", {"interface": "lan", "state_policy": "freestyle"})
        with pytest.raises(ValueError, match="state_policy"):
            firewall_rule_configs_from_resources([r])

    def test_invalid_statetype_rejected(self) -> None:
        r = _resource("bad", {"interface": "lan", "statetype": "frozen"})
        with pytest.raises(ValueError, match="statetype"):
            firewall_rule_configs_from_resources([r])

    def test_lock_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "lock": "yes"})
        with pytest.raises(ValueError, match="lock"):
            firewall_rule_configs_from_resources([r])

    def test_log_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "log": "yes"})
        with pytest.raises(ValueError, match="log"):
            firewall_rule_configs_from_resources([r])

    def test_enabled_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "enabled": "yes"})
        with pytest.raises(ValueError, match="enabled"):
            firewall_rule_configs_from_resources([r])

    def test_quick_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "quick": "yes"})
        with pytest.raises(ValueError, match="quick"):
            firewall_rule_configs_from_resources([r])

    def test_tcpflags_any_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "tcpflags_any": "yes"})
        with pytest.raises(ValueError, match="tcpflags_any"):
            firewall_rule_configs_from_resources([r])

    def test_disablereplyto_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "disablereplyto": "yes"})
        with pytest.raises(ValueError, match="disablereplyto"):
            firewall_rule_configs_from_resources([r])

    def test_allowopts_must_be_bool(self) -> None:
        r = _resource("bad", {"interface": "lan", "allowopts": "1"})
        with pytest.raises(ValueError, match="allowopts"):
            firewall_rule_configs_from_resources([r])

    def test_sequence_default_when_omitted(self) -> None:
        r = _resource("ok", {"interface": "lan"})
        result = firewall_rule_configs_from_resources([r])
        assert result[0].sequence == DEFAULT_SEQUENCE

    def test_sequence_must_be_int(self) -> None:
        r = _resource("bad", {"interface": "lan", "sequence": "not-int"})
        with pytest.raises(ValueError, match="sequence"):
            firewall_rule_configs_from_resources([r])

    def test_categories_list_form_accepted(self) -> None:
        r = _resource(
            "ok",
            {"interface": "lan", "categories": ["uuid-1", "uuid-2"]},
        )
        result = firewall_rule_configs_from_resources([r])
        assert result[0].categories == ("uuid-1", "uuid-2")

    def test_categories_csv_form_accepted(self) -> None:
        # Comma-separated string form is normalized to a tuple.
        r = _resource(
            "ok",
            {"interface": "lan", "categories": "uuid-1, uuid-2"},
        )
        result = firewall_rule_configs_from_resources([r])
        assert result[0].categories == ("uuid-1", "uuid-2")

    def test_categories_invalid_type_rejected(self) -> None:
        r = _resource(
            "bad",
            {"interface": "lan", "categories": {"k": "v"}},
        )
        with pytest.raises(ValueError, match="categories"):
            firewall_rule_configs_from_resources([r])

    def test_description_with_identity_tag_rejected(self) -> None:
        # Forging the InfraFoundry tag is rejected at parse time.
        r = _resource(
            "evil",
            {"interface": "lan", "description": "forged [infrafoundry:other]"},
        )
        with pytest.raises(ValueError, match="reserved"):
            firewall_rule_configs_from_resources([r])

    def test_description_must_be_string(self) -> None:
        r = _resource("bad", {"interface": "lan", "description": 123})
        with pytest.raises(ValueError, match="description"):
            firewall_rule_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.rules",
            provider="opnsense",
            config={"interface": "lan"},
        )
        # Bypass pydantic to exercise the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            firewall_rule_configs_from_resources([r])

    def test_non_firewall_resources_ignored(self) -> None:
        fw = _resource("ok", {"interface": "lan"})
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        result = firewall_rule_configs_from_resources([fw, other])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_managed_row_parses(self) -> None:
        row = {"uuid": "u1", "description": "LAN allow [infrafoundry:lan-allow]"}
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.managed_name == "lan-allow"
        assert live.description == "LAN allow"

    def test_managed_row_no_user_description(self) -> None:
        row = {"uuid": "u1", "description": "[infrafoundry:foo]"}
        live = _row_to_live(row)
        assert live.managed_name == "foo"
        assert live.description == ""

    def test_unmanaged_row_managed_name_none(self) -> None:
        row = {"uuid": "u1", "description": "regular description"}
        live = _row_to_live(row)
        assert live.managed_name is None
        assert live.description == "regular description"

    def test_malformed_tag_raises(self) -> None:
        row = {"uuid": "u1", "description": "[infrafoundry:]"}
        with pytest.raises(OpnsenseDriftError):
            _row_to_live(row)

    def test_missing_keys_default_cleanly(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.managed_name is None
        assert live.description == ""

    def test_none_description_treated_as_empty(self) -> None:
        # Some live rows return ``None`` instead of ``""`` for absent
        # text fields; the parser must coerce safely.
        row = {"uuid": "u1", "description": None}
        live = _row_to_live(row)
        assert live.managed_name is None
        assert live.description == ""


# ---------------------------------------------------------------------------
# FirewallRuleService — API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = FirewallRuleService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "firewall/filter/searchRule")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "description": "desc [infrafoundry:a]"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "description": "unmanaged"},
            ]
        }
        svc = FirewallRuleService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].managed_name == "a"
        assert result[1].managed_name is None

    def test_search_with_no_rows_key_returns_empty(self) -> None:
        client = MagicMock()
        client.request.return_value = {"other": "data"}
        svc = FirewallRuleService(client)
        result = svc.search()
        assert result == []

    def test_search_propagates_drift_error(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "description": "X [infrafoundry:]"},  # malformed
            ]
        }
        svc = FirewallRuleService(client)
        with pytest.raises(OpnsenseDriftError):
            svc.search()


# ---------------------------------------------------------------------------
# search_tolerant — migrate-only 404 tolerance (#754)
# ---------------------------------------------------------------------------


class TestSearchTolerant:
    """``search_tolerant`` swallows 404 with WARNING; non-404s raise; success matches strict."""

    def test_404_returns_empty_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        # 404 from the filter controller must not abort migrate; result
        # is ``[]`` and a single WARNING is emitted.
        client = MagicMock()
        client.request.side_effect = APIError(
            "Not Found",
            status_code=404,
            response="Controller missing",
            provider="opnsense",
        )
        svc = FirewallRuleService(client)

        with caplog.at_level(logging.WARNING):
            result = svc.search_tolerant()

        assert result == []
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert "404" in message
        assert "firewall/filter" in message

    def test_non_404_api_error_propagates(self) -> None:
        # 500 errors must not be swallowed.
        client = MagicMock()
        client.request.side_effect = APIError("Internal Server Error", status_code=500)
        svc = FirewallRuleService(client)
        with pytest.raises(APIError) as exc_info:
            svc.search_tolerant()
        assert exc_info.value.status_code == 500

    def test_authentication_error_propagates(self) -> None:
        # AuthenticationError (401/403) is a subclass of APIError; it
        # must NOT be swallowed even though it is an APIError.
        client = MagicMock()
        client.request.side_effect = AuthenticationError("Unauthorized", status_code=401)
        svc = FirewallRuleService(client)
        with pytest.raises(AuthenticationError) as exc_info:
            svc.search_tolerant()
        assert exc_info.value.status_code == 401

    def test_success_matches_search(self, caplog: pytest.LogCaptureFixture) -> None:
        # When search() returns rows normally, search_tolerant returns
        # the exact same list and does not emit any warning.
        rows = [
            {"uuid": "u1", "description": "desc [infrafoundry:a]"},
            {"uuid": "u2", "description": "unmanaged"},
        ]

        client_a = MagicMock()
        client_a.request.return_value = {"rows": rows}
        svc_a = FirewallRuleService(client_a)
        with caplog.at_level(logging.WARNING):
            tolerant = svc_a.search_tolerant()
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert warnings == []

        client_b = MagicMock()
        client_b.request.return_value = {"rows": rows}
        svc_b = FirewallRuleService(client_b)
        strict = svc_b.search()

        assert [(r.uuid, r.managed_name) for r in tolerant] == [
            (r.uuid, r.managed_name) for r in strict
        ]

    def test_export_to_yaml_yields_empty_resources_on_404(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # End-to-end: when the controller is missing, ``export_to_yaml``
        # produces ``resources: []`` and logs a WARNING.
        client = MagicMock()
        client.request.side_effect = APIError("Not Found", status_code=404)
        svc = FirewallRuleService(client)

        with caplog.at_level(logging.WARNING):
            text = svc.export_to_yaml()

        # Nested format: empty leaf list at opnsense.firewall.rules.
        assert "rules: []" in text
        warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
        assert len(warnings) == 1


class TestServiceCRUD:
    def test_add_posts_to_addrule(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "fake-cat"  # short-circuit category bootstrap
        rule = _rule("foo", interface="lan")
        svc.add(rule)
        call = client.request.call_args
        assert call.args[0] == "POST"
        assert call.args[1] == "firewall/filter/addRule"
        sent_data = call.kwargs.get("data") or (call.args[2] if len(call.args) > 2 else None)
        assert sent_data is not None
        # Marker UUID appears in categories.
        assert sent_data["rule"]["categories"] == "fake-cat"

    def test_update_posts_to_setrule_with_uuid(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "fake-cat"
        rule = _rule("foo", interface="lan")
        svc.update("uuid-abc", rule)
        call = client.request.call_args
        assert call.args[1] == "firewall/filter/setRule/uuid-abc"

    def test_delete_posts_to_delrule(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        svc = FirewallRuleService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "firewall/filter/delRule/u1")

    def test_apply_changes_posts_to_apply(self) -> None:
        client = MagicMock()
        client.request.return_value = {"status": "ok"}
        svc = FirewallRuleService(client)
        svc.apply_changes()
        client.request.assert_called_once_with("POST", "firewall/filter/apply")

    def test_savepoint_posts_to_savepoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"revision": "abc"}
        svc = FirewallRuleService(client)
        svc.savepoint()
        client.request.assert_called_once_with("POST", "firewall/filter/savepoint")


# ---------------------------------------------------------------------------
# Multi-valued categories: append, not overwrite (load-bearing for #742)
# ---------------------------------------------------------------------------


class TestMultiValuedCategories:
    def test_operator_categories_preserved_on_add(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "marker-uuid"
        rule = _rule("foo", interface="lan", categories=("op-a", "op-b"))
        svc.add(rule)
        sent = client.request.call_args.kwargs["data"]
        # Operator UUIDs in original order, marker appended.
        assert sent["rule"]["categories"] == "op-a,op-b,marker-uuid"

    def test_marker_already_in_operator_list_not_duplicated(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "marker-uuid"
        # Operator inadvertently lists the marker UUID — the service must
        # not duplicate it.
        rule = _rule("foo", interface="lan", categories=("marker-uuid", "op-other"))
        svc.add(rule)
        sent = client.request.call_args.kwargs["data"]
        assert sent["rule"]["categories"] == "marker-uuid,op-other"

    def test_no_operator_categories_marker_alone(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "marker-uuid"
        rule = _rule("foo", interface="lan", categories=())
        svc.add(rule)
        sent = client.request.call_args.kwargs["data"]
        assert sent["rule"]["categories"] == "marker-uuid"

    def test_update_includes_marker_in_categories(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "marker-uuid"
        rule = _rule("foo", interface="lan", categories=("op-a",))
        svc.update("uuid-abc", rule)
        sent = client.request.call_args.kwargs["data"]
        assert sent["rule"]["categories"] == "op-a,marker-uuid"


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
        svc = FirewallRuleService(client)
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
        svc = FirewallRuleService(client)
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
        svc = FirewallRuleService(client)
        uuid = svc._ensure_infrafoundry_category()
        assert uuid == "new-uuid"

    def test_caches_uuid_across_calls(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": [{"uuid": "cached", "name": "infrafoundry"}]}
        svc = FirewallRuleService(client)
        first = svc._ensure_infrafoundry_category()
        second = svc._ensure_infrafoundry_category()
        assert first == second == "cached"
        # searchItem only called once; second invocation hits the cache.
        assert client.request.call_count == 1

    def test_raises_when_add_item_returns_no_uuid(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {"rows": []},
            {"result": "failed"},  # addItem: no uuid
        ]
        svc = FirewallRuleService(client)
        with pytest.raises(InfraFoundryError, match="infrafoundry"):
            svc._ensure_infrafoundry_category()

    def test_add_item_payload_shape(self) -> None:
        # Verify the addItem payload uses ``category`` envelope with name.
        client = MagicMock()
        client.request.side_effect = [
            {"rows": []},
            {"uuid": "new-uuid"},
        ]
        svc = FirewallRuleService(client)
        svc._ensure_infrafoundry_category()
        add_call = client.request.call_args_list[1]
        sent = add_call.kwargs.get("data") or add_call.args[2]
        assert sent["category"]["name"] == "infrafoundry"

    def test_ensure_infrafoundry_category_uses_shared_cache(self) -> None:
        # Two distinct service instances against the same client share the
        # process-wide cache: only the first instance triggers searchItem;
        # the second hits the cache via the shared helper (#746).
        client = MagicMock()
        client.request.return_value = {"rows": [{"uuid": "shared-uuid", "name": "infrafoundry"}]}
        svc_a = FirewallRuleService(client)
        svc_b = FirewallRuleService(client)
        assert svc_a._ensure_infrafoundry_category() == "shared-uuid"
        assert svc_b._ensure_infrafoundry_category() == "shared-uuid"
        # Only one searchItem across both instances; the second hits the
        # process-wide cache in ``_category_marker``.
        assert client.request.call_count == 1


# ---------------------------------------------------------------------------
# apply_diff orchestration
# ---------------------------------------------------------------------------


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = FirewallRuleService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_only_calls_addrule_then_apply_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "fake-cat"
        diff = Diff(adds=[_rule("foo", interface="lan")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/filter/addRule" in endpoints
        # Apply called exactly once.
        assert endpoints.count("firewall/filter/apply") == 1
        assert counts["created"] == 1

    def test_update_only_calls_setrule_then_apply(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "fake-cat"
        live = _live("u1", "foo")
        diff = Diff(updates=[(live, _rule("foo", interface="lan"))])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/filter/setRule/u1" in endpoints
        assert endpoints.count("firewall/filter/apply") == 1
        assert counts["updated"] == 1

    def test_delete_only_calls_delrule_then_apply(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        svc = FirewallRuleService(client)
        live = _live("u1", "foo")
        diff = Diff(deletes=[live])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/filter/delRule/u1" in endpoints
        assert endpoints.count("firewall/filter/apply") == 1
        assert counts["deleted"] == 1

    def test_mixed_operations_call_apply_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = FirewallRuleService(client)
        svc._category_uuid = "fake-cat"
        live_update = _live("u-up", "to-update")
        live_delete = _live("u-del", "to-delete")
        diff = Diff(
            adds=[_rule("new-a", interface="lan"), _rule("new-b", interface="wan")],
            updates=[(live_update, _rule("to-update", interface="lan"))],
            deletes=[live_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        # apply called only once even though many mutations happened.
        assert endpoints.count("firewall/filter/apply") == 1
        assert counts == {"created": 2, "updated": 1, "deleted": 1}

    def test_locked_only_does_not_call_apply(self) -> None:
        # A diff containing only ``locked`` entries (no adds/updates/deletes)
        # is a no-op — apply must NOT be called.
        client = MagicMock()
        svc = FirewallRuleService(client)
        diff = Diff(locked=[(_rule("foo", lock=True), None)])
        counts = svc.apply_diff(diff)
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}


# ---------------------------------------------------------------------------
# export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_managed_rules_appear_in_export_unmanaged_excluded(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "description": "LAN allow [infrafoundry:lan-allow]",
                    "interface": "lan",
                    "action": "pass",
                    "enabled": "1",
                },
                {"uuid": "u2", "description": "manual rule"},  # unmanaged
            ]
        }
        svc = FirewallRuleService(client)
        text = svc.export_to_yaml()
        assert "lan-allow" in text
        assert "manual" not in text  # unmanaged excluded
        # Nested format per ADR-0016 (#793 Phase 4).
        assert "opnsense:" in text
        assert "firewall:" in text
        assert "rules:" in text

    def test_export_with_no_managed_rules_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = FirewallRuleService(client)
        text = svc.export_to_yaml()
        # Nested format: empty leaf list at opnsense.firewall.rules.
        assert "rules: []" in text

    def test_export_strips_marker_from_categories(self) -> None:
        client = MagicMock()
        # Live row with multi-valued categories dict containing the marker
        # plus an operator UUID. The export must keep the operator UUID
        # but strip the marker.
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "description": "LAN allow [infrafoundry:lan-allow]",
                    "interface": "lan",
                    "action": "pass",
                    "categories": {
                        "marker-uuid": {"value": "infrafoundry", "selected": 1},
                        "op-uuid": {"value": "operator-cat", "selected": 1},
                        "unselected-uuid": {"value": "other", "selected": 0},
                    },
                },
            ]
        }
        svc = FirewallRuleService(client)
        # Pre-populate the marker UUID cache so export_to_yaml can strip it.
        svc._category_uuid = "marker-uuid"
        text = svc.export_to_yaml()
        # Operator UUID survives.
        assert "op-uuid" in text
        # Marker UUID is filtered out.
        assert "marker-uuid" not in text

    def test_export_maps_hyphenated_wire_keys_back_to_underscored_yaml(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "description": "[infrafoundry:foo]",
                    "interface": "lan",
                    "state-policy": "floating",
                    "max-src-conn": "100",
                    "set-prio": "3",
                    "divert-to": "127.0.0.1:3128",
                    "udp-first": "60",
                },
            ]
        }
        svc = FirewallRuleService(client)
        text = svc.export_to_yaml()
        # Underscored YAML keys present.
        assert "state_policy: floating" in text
        assert "max_src_conn: '100'" in text or 'max_src_conn: "100"' in text
        assert "set_prio: '3'" in text or 'set_prio: "3"' in text
        assert "divert_to: 127.0.0.1:3128" in text
        assert "udp_first: '60'" in text or 'udp_first: "60"' in text
        # Hyphenated wire keys must NOT leak into the YAML output.
        assert "state-policy:" not in text
        assert "max-src-conn:" not in text
