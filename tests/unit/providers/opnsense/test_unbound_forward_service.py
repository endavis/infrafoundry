"""Unit tests for ``infrafoundry.providers.opnsense.services.unbound_forward``.

Coverage:
    - ``UnboundForwardConfig.to_payload`` envelope (note: ``dot`` envelope
      key regardless of ``type`` value) + boolean stringification.
    - ``compute_diff`` with adds / updates / deletes / lock + add-only.
    - Identity is the ``(type, domain, server, port)`` natural-key tuple —
      YAML ``name`` changes don't trigger updates; same domain/server/port
      with different ``type`` is a distinct record.
    - ``unbound_forward_configs_from_resources`` validation: ``type`` enum,
      ``domain`` empty allowed, port int-or-string accepted, IP not
      checked here (that is the validator's job).
    - ``UnboundForwardService`` API method dispatch.
    - ``apply_diff`` orchestration (single ``reconfigure`` if any mutation).
    - ``_normalize_field`` for OPNsense select dicts and bool variants.
    - ``export_to_yaml`` round-trip with synthetic name generation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.unbound_forward import (
    Diff,
    LiveUnboundForward,
    UnboundForwardConfig,
    UnboundForwardService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
    compute_diff,
    unbound_forward_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _forward(
    name: str,
    *,
    server: str = "10.0.0.53",
    type: str = "forward",
    domain: str = "",
    port: str = "53",
    verify: str = "",
    forward_tcp_upstream: bool = False,
    forward_first: bool = False,
    enabled: bool = True,
    description: str = "",
    lock: bool = False,
) -> UnboundForwardConfig:
    return UnboundForwardConfig(
        name=name,
        server=server,
        type=type,  # type: ignore[arg-type]
        domain=domain,
        port=port,
        verify=verify,
        forward_tcp_upstream=forward_tcp_upstream,
        forward_first=forward_first,
        enabled=enabled,
        description=description,
        lock=lock,
    )


def _live(
    uuid: str,
    *,
    type: str = "forward",
    domain: str = "",
    server: str = "10.0.0.53",
    port: str = "53",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveUnboundForward:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "type": type,
        "domain": domain,
        "server": server,
        "port": port,
        "verify": "",
        "forward_tcp_upstream": "0",
        "forward_first": "0",
        "enabled": "1",
        "description": "",
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveUnboundForward(
        uuid=uuid,
        type=type,
        domain=domain,
        server=server,
        port=port,
        raw=raw,
    )


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(name=name, type="unbound_forward", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# UnboundForwardConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_has_dot_envelope(self) -> None:
        payload = _forward("foo").to_payload()
        # Envelope key is always ``dot`` even for type=forward.
        assert set(payload.keys()) == {"dot"}

    def test_payload_field_set_for_forward_type(self) -> None:
        forward = _forward(
            "corp",
            type="forward",
            domain="corp.example",
            server="10.0.0.53",
            port="53",
            description="forward corp",
        )
        inner = forward.to_payload()["dot"]
        assert inner["type"] == "forward"
        assert inner["domain"] == "corp.example"
        assert inner["server"] == "10.0.0.53"
        assert inner["port"] == "53"
        assert inner["description"] == "forward corp"

    def test_payload_field_set_for_dot_type(self) -> None:
        forward = _forward("dot", type="dot", server="9.9.9.9", port="853", verify="dns.quad9.net")
        inner = forward.to_payload()["dot"]
        assert inner["type"] == "dot"
        assert inner["verify"] == "dns.quad9.net"
        assert inner["port"] == "853"

    def test_enabled_true_serializes_one(self) -> None:
        inner = _forward("foo", enabled=True).to_payload()["dot"]
        assert inner["enabled"] == "1"

    def test_enabled_false_serializes_zero(self) -> None:
        inner = _forward("foo", enabled=False).to_payload()["dot"]
        assert inner["enabled"] == "0"

    def test_forward_tcp_upstream_serializes_bool(self) -> None:
        inner = _forward("foo", forward_tcp_upstream=True).to_payload()["dot"]
        assert inner["forward_tcp_upstream"] == "1"

    def test_forward_first_serializes_bool(self) -> None:
        inner = _forward("foo", forward_first=True).to_payload()["dot"]
        assert inner["forward_first"] == "1"

    def test_name_not_sent_on_wire(self) -> None:
        inner = _forward("operator-friendly-name").to_payload()["dot"]
        assert "name" not in inner
        assert set(inner.keys()) == {
            "type",
            "domain",
            "server",
            "port",
            "verify",
            "forward_tcp_upstream",
            "forward_first",
            "enabled",
            "description",
        }

    def test_default_description_empty(self) -> None:
        inner = _forward("foo").to_payload()["dot"]
        assert inner["description"] == ""


class TestDiffKey:
    def test_diff_key_is_tuple(self) -> None:
        forward = _forward("foo", type="forward", domain="x", server="1.1.1.1", port="53")
        assert forward.diff_key == ("forward", "x", "1.1.1.1", "53")

    def test_live_diff_key_is_tuple(self) -> None:
        live = _live("u1", type="forward", domain="x", server="1.1.1.1", port="53")
        assert live.diff_key == ("forward", "x", "1.1.1.1", "53")

    def test_yaml_name_does_not_affect_diff_key(self) -> None:
        a = _forward("name-one", type="forward", domain="x", server="1.1.1.1", port="53")
        b = _forward("name-two", type="forward", domain="x", server="1.1.1.1", port="53")
        assert a.diff_key == b.diff_key

    def test_type_distinguishes_records(self) -> None:
        # Same domain/server/port but different type — distinct identities.
        a = _forward("a", type="forward", server="9.9.9.9", port="53")
        b = _forward("b", type="dot", server="9.9.9.9", port="53")
        assert a.diff_key != b.diff_key


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
    def test_new_forward_adds(self) -> None:
        diff = compute_diff([_forward("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].server == "10.0.0.53"


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        forward = _forward("foo", description="new")
        live = _live(
            "u1",
            raw_overrides={"description": "old"},
        )
        diff = compute_diff([forward], [live])
        assert len(diff.updates) == 1

    def test_update_when_enabled_flips(self) -> None:
        forward = _forward("foo", enabled=False)
        live = _live("u1")  # enabled "1" by default
        diff = compute_diff([forward], [live])
        assert len(diff.updates) == 1

    def test_update_when_verify_changes(self) -> None:
        forward = _forward("foo", verify="cn.example")
        live = _live("u1", raw_overrides={"verify": ""})
        diff = compute_diff([forward], [live])
        assert len(diff.updates) == 1

    def test_no_update_when_payload_matches(self) -> None:
        forward = _forward("foo")
        live_raw = {"uuid": "u1", **forward.to_payload()["dot"]}
        live = LiveUnboundForward(
            uuid="u1",
            type="forward",
            domain="",
            server="10.0.0.53",
            port="53",
            raw=live_raw,
        )
        diff = compute_diff([forward], [live])
        assert diff.is_empty

    def test_yaml_name_change_alone_is_noop(self) -> None:
        forward = _forward("renamed-forward")
        live_raw = {"uuid": "u1", **forward.to_payload()["dot"]}
        live = LiveUnboundForward(
            uuid="u1",
            type="forward",
            domain="",
            server="10.0.0.53",
            port="53",
            raw=live_raw,
        )
        diff = compute_diff([forward], [live])
        assert diff.is_empty

    def test_changing_type_is_delete_plus_add(self) -> None:
        old_live = _live("u1", type="forward")
        new_forward = _forward("foo", type="dot")
        diff = compute_diff([new_forward], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].type == "dot"
        assert len(diff.deletes) == 1

    def test_changing_server_is_delete_plus_add(self) -> None:
        old_live = _live("u1", server="10.0.0.53")
        new_forward = _forward("foo", server="10.0.0.54")
        diff = compute_diff([new_forward], [old_live])
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 1


class TestComputeDiffDeletes:
    def test_live_with_no_desired_is_deleted(self) -> None:
        diff = compute_diff([], [_live("u1")])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_still_emits_updates(self) -> None:
        forward = _forward("foo", description="changed")
        live = _live("u1", raw_overrides={"description": "old"})
        diff = compute_diff([forward], [live], add_only=True)
        assert len(diff.updates) == 1


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        forward = _forward("survival", description="locked", lock=True)
        live = _live("u1", raw_overrides={"description": "drift!"})
        diff = compute_diff([forward], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        forward = _forward("missing", lock=True)
        diff = compute_diff([forward], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None

    def test_locked_resource_does_not_appear_as_delete_when_only_in_yaml(self) -> None:
        forward = _forward("locked-name", lock=True)
        live_other = _live("u2", server="10.0.0.99")
        diff = compute_diff([forward], [live_other])
        # Other live still deleted.
        assert len(diff.deletes) == 1
        assert diff.deletes[0].server == "10.0.0.99"


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_forward("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_forward("foo")])
        assert not diff.is_empty

    def test_non_empty_when_updates(self) -> None:
        diff = Diff(updates=[(_live("u1"), _forward("foo"))])
        assert not diff.is_empty

    def test_non_empty_when_deletes(self) -> None:
        diff = Diff(deletes=[_live("u1")])
        assert not diff.is_empty


# ---------------------------------------------------------------------------
# _normalize_field
# ---------------------------------------------------------------------------


class TestNormalizeField:
    def test_none_becomes_empty(self) -> None:
        assert _normalize_field(None) == ""

    def test_bool_true_becomes_one(self) -> None:
        assert _normalize_field(True) == "1"

    def test_bool_false_becomes_zero(self) -> None:
        assert _normalize_field(False) == "0"

    def test_string_passthrough(self) -> None:
        assert _normalize_field("forward") == "forward"

    def test_int_stringified(self) -> None:
        assert _normalize_field(53) == "53"

    def test_select_dict_extracts_selected_key(self) -> None:
        # getForward returns ``type`` as a select dict.
        value = {
            "forward": {"value": "Plain", "selected": 1},
            "dot": {"value": "DoT", "selected": 0},
        }
        assert _normalize_field(value) == "forward"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"forward": {"value": "Plain", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# unbound_forward_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_valid_parses(self) -> None:
        r = _resource(
            "corp-forward",
            {
                "type": "forward",
                "domain": "corp.example",
                "server": "10.0.0.53",
                "port": 53,
                "description": "lan",
            },
        )
        result = unbound_forward_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "corp-forward"
        assert cfg.type == "forward"
        assert cfg.domain == "corp.example"
        assert cfg.server == "10.0.0.53"
        assert cfg.port == "53"
        assert cfg.description == "lan"

    def test_default_type_is_forward(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.type == "forward"

    def test_empty_domain_allowed_global_forwarder(self) -> None:
        r = _resource("global", {"server": "1.1.1.1"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.domain == ""

    def test_default_port_53(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.port == "53"

    def test_port_int_normalized_to_string(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1", "port": 853})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.port == "853"

    def test_port_string_passthrough(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1", "port": "8053"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.port == "8053"

    def test_default_enabled_true(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.enabled is True

    def test_explicit_enabled_false(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1", "enabled": False})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.enabled is False

    def test_lock_passthrough(self) -> None:
        r = _resource("foo", {"server": "1.1.1.1", "lock": True})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.lock is True

    def test_dot_type_accepted(self) -> None:
        r = _resource("dot", {"server": "9.9.9.9", "type": "dot"})
        cfg = unbound_forward_configs_from_resources([r])[0]
        assert cfg.type == "dot"

    def test_invalid_type_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "type": "bogus"})
        with pytest.raises(ValueError, match="type"):
            unbound_forward_configs_from_resources([r])

    def test_non_string_type_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "type": 12345})
        with pytest.raises(ValueError, match="type"):
            unbound_forward_configs_from_resources([r])

    def test_missing_server_rejected(self) -> None:
        r = _resource("bad", {"domain": "x"})
        with pytest.raises(ValueError, match="server"):
            unbound_forward_configs_from_resources([r])

    def test_empty_server_rejected(self) -> None:
        r = _resource("bad", {"server": ""})
        with pytest.raises(ValueError, match="server"):
            unbound_forward_configs_from_resources([r])

    def test_non_string_domain_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "domain": 12345})
        with pytest.raises(ValueError, match="domain"):
            unbound_forward_configs_from_resources([r])

    def test_non_string_verify_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "verify": 12345})
        with pytest.raises(ValueError, match="verify"):
            unbound_forward_configs_from_resources([r])

    def test_invalid_port_type_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "port": [53]})
        with pytest.raises(ValueError, match="port"):
            unbound_forward_configs_from_resources([r])

    def test_non_string_description_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "description": 12345})
        with pytest.raises(ValueError, match="description"):
            unbound_forward_configs_from_resources([r])

    def test_non_bool_enabled_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "enabled": "yes"})
        with pytest.raises(ValueError, match="enabled"):
            unbound_forward_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "lock": "yes"})
        with pytest.raises(ValueError, match="lock"):
            unbound_forward_configs_from_resources([r])

    def test_non_bool_forward_tcp_upstream_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "forward_tcp_upstream": "yes"})
        with pytest.raises(ValueError, match="forward_tcp_upstream"):
            unbound_forward_configs_from_resources([r])

    def test_non_bool_forward_first_rejected(self) -> None:
        r = _resource("bad", {"server": "1.1.1.1", "forward_first": "yes"})
        with pytest.raises(ValueError, match="forward_first"):
            unbound_forward_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound_forward",
            provider="opnsense",
            config={"server": "1.1.1.1"},
        )
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            unbound_forward_configs_from_resources([r])

    def test_non_unbound_forward_resources_ignored(self) -> None:
        ok = _resource("ok", {"server": "1.1.1.1"})
        other = ResourceConfig(name="x", type="aliases", provider="opnsense", config={})
        result = unbound_forward_configs_from_resources([ok, other])
        assert len(result) == 1
        assert result[0].name == "ok"


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_basic_row(self) -> None:
        row = {
            "uuid": "u1",
            "type": "forward",
            "domain": "x",
            "server": "10.0.0.53",
            "port": "53",
        }
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.type == "forward"
        assert live.domain == "x"
        assert live.server == "10.0.0.53"
        assert live.port == "53"
        assert live.raw == row

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.type == ""
        assert live.domain == ""
        assert live.server == ""
        assert live.port == ""

    def test_type_as_select_dict_normalizes(self) -> None:
        row = {
            "uuid": "u1",
            "type": {"forward": {"value": "Plain", "selected": 1}},
            "server": "1.1.1.1",
            "port": "53",
        }
        live = _row_to_live(row)
        assert live.type == "forward"


# ---------------------------------------------------------------------------
# _synthesize_name
# ---------------------------------------------------------------------------


class TestSynthesizeName:
    def test_v4_domain(self) -> None:
        live = _live("u1", type="forward", domain="x.example", server="10.0.0.53", port="53")
        assert _synthesize_name(live) == "forward-forward-x-example-10-0-0-53-53"

    def test_global_forwarder(self) -> None:
        # Empty domain → ``global``.
        live = _live("u1", type="forward", domain="", server="10.0.0.53", port="53")
        assert _synthesize_name(live) == "forward-forward-global-10-0-0-53-53"

    def test_v6_server(self) -> None:
        live = _live("u1", type="dot", domain="x", server="2001:db8::53", port="853")
        # Colons replaced with hyphens.
        assert _synthesize_name(live) == "forward-dot-x-2001-db8--53-853"

    def test_lowercase(self) -> None:
        live = _live("u1", type="forward", domain="X.EXAMPLE", server="10.0.0.53", port="53")
        assert _synthesize_name(live) == "forward-forward-x-example-10-0-0-53-53"


# ---------------------------------------------------------------------------
# UnboundForwardService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = UnboundForwardService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "unbound/settings/searchForward")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "type": "forward",
                    "domain": "x",
                    "server": "1.1.1.1",
                    "port": "53",
                },
                "not-a-dict",
                {
                    "uuid": "u2",
                    "type": "dot",
                    "domain": "",
                    "server": "9.9.9.9",
                    "port": "853",
                },
            ]
        }
        svc = UnboundForwardService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].uuid == "u1"
        assert result[1].uuid == "u2"

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = UnboundForwardService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = UnboundForwardService(client)
        assert svc.search() == []


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"dot": {"server": "1.1.1.1"}}
        svc = UnboundForwardService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "unbound/settings/getForward/u1")
        assert result == {"dot": {"server": "1.1.1.1"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = UnboundForwardService(client)
        forward = _forward("foo")
        svc.add(forward)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/addForward", data=forward.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundForwardService(client)
        forward = _forward("foo")
        svc.update("uuid-abc", forward)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/setForward/uuid-abc", data=forward.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundForwardService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "unbound/settings/delForward/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundForwardService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "unbound/service/reconfigure")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = UnboundForwardService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundForwardService(client)
        diff = Diff(adds=[_forward("foo"), _forward("bar", server="10.0.0.54")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("unbound/settings/addForward") == 2
        assert endpoints.count("unbound/service/reconfigure") == 1
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundForwardService(client)
        live = _live("u1")
        forward = _forward("foo")
        diff = Diff(updates=[(live, forward)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/setForward/u1" in endpoints
        assert endpoints.count("unbound/service/reconfigure") == 1
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        svc = UnboundForwardService(client)
        diff = Diff(
            deletes=[
                _live("u1"),
                _live("u2", server="10.0.0.54"),
            ]
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/delForward/u1" in endpoints
        assert "unbound/settings/delForward/u2" in endpoints
        assert endpoints.count("unbound/service/reconfigure") == 1
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_single_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundForwardService(client)
        live_for_update = _live("u1")
        live_for_delete = _live("u2", server="10.0.0.54")
        new = _forward("new", server="10.0.0.55")
        update_target = _forward("foo", description="changed")
        diff = Diff(
            adds=[new],
            updates=[(live_for_update, update_target)],
            deletes=[live_for_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("unbound/service/reconfigure") == 1
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


class TestComputeDiffServiceWrapper:
    def test_service_wrapper_delegates(self) -> None:
        client = MagicMock()
        svc = UnboundForwardService(client)
        diff = svc.compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# export_to_yaml + _live_to_export_config
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_forwards_appear_in_export(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            # searchForward
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "type": "forward",
                        "domain": "x.example",
                        "server": "10.0.0.53",
                        "port": "53",
                        "verify": "",
                        "forward_tcp_upstream": "0",
                        "forward_first": "0",
                        "enabled": "1",
                        "description": "lan",
                    },
                ]
            },
            # getForward/u1
            {
                "dot": {
                    "type": {
                        "forward": {"value": "Plain", "selected": 1},
                        "dot": {"value": "DoT", "selected": 0},
                    },
                    "domain": "x.example",
                    "server": "10.0.0.53",
                    "port": "53",
                    "verify": "",
                    "forward_tcp_upstream": "0",
                    "forward_first": "0",
                    "enabled": "1",
                    "description": "lan",
                }
            },
        ]
        svc = UnboundForwardService(client)
        text = svc.export_to_yaml()
        # Synthetic name appears.
        assert "forward-forward-x-example-10-0-0-53-53" in text
        # Field decoding worked.
        assert "type: forward" in text
        assert "domain: x.example" in text
        assert "server: 10.0.0.53" in text
        assert "description: lan" in text
        assert "enabled: true" in text

    def test_export_with_no_forwards_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = UnboundForwardService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text


class TestLiveToExportConfig:
    def test_decoding_select_dict_and_bools(self) -> None:
        get_response = {
            "dot": {
                "type": {
                    "forward": {"value": "Plain", "selected": 0},
                    "dot": {"value": "DoT", "selected": 1},
                },
                "domain": "x",
                "server": "9.9.9.9",
                "port": "853",
                "verify": "dns.quad9.net",
                "forward_tcp_upstream": "1",
                "forward_first": "0",
                "enabled": "0",
                "description": "DoT to quad9",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["type"] == "dot"
        assert cfg["domain"] == "x"
        assert cfg["server"] == "9.9.9.9"
        assert cfg["port"] == "853"
        assert cfg["verify"] == "dns.quad9.net"
        assert cfg["forward_tcp_upstream"] is True
        assert cfg["forward_first"] is False
        assert cfg["enabled"] is False
        assert cfg["description"] == "DoT to quad9"

    def test_missing_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config({})
        # Defensive defaults: type defaults to ``forward`` and port to ``53``.
        assert cfg["type"] == "forward"
        assert cfg["port"] == "53"
        assert cfg["domain"] == ""
        assert cfg["server"] == ""

    def test_non_dict_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config(None)  # type: ignore[arg-type]
        assert cfg["type"] == "forward"
        assert cfg["server"] == ""
