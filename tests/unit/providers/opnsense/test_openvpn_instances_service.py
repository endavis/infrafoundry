"""Unit tests for the OpenVPN client-instance service (#808)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.openvpn_instances import (
    ALLOWED_KEYS,
    LiveOpenVpnInstance,
    OpenVpnInstanceConfig,
    OpenVpnInstanceService,
    changed_fields,
    compute_diff,
    flatten_option,
    openvpn_instance_configs_from_resources,
)

SECRET_PW = "hunter2-not-real"  # test fixture


def _res(name: str = "vpn-a", **config: Any) -> ResourceConfig:
    config.setdefault("remote", ["vpn.example.com"])
    config.setdefault("ca_ref", "vpn-ca")
    return ResourceConfig(name=name, type="openvpn.instances", provider="opnsense", config=config)


def _cfg(name: str = "vpn-a", **config: Any) -> OpenVpnInstanceConfig:
    return openvpn_instance_configs_from_resources([_res(name, **config)])[0]


def _live(description: str = "vpn-a", /, role: str = "client", **raw: Any) -> LiveOpenVpnInstance:
    body = {"description": description, "role": role, **raw}
    return LiveOpenVpnInstance(
        uuid=f"u-{description}", description=description, role=role, raw=body
    )


def _opt(selected: str, *others: str) -> dict[str, Any]:
    return {k: {"value": k, "selected": 1 if k == selected else 0} for k in (selected, *others)}


class TestFlattenOption:
    def test_dict_selected_keys(self) -> None:
        assert (
            flatten_option({"a": {"selected": 1}, "b": {"selected": 0}, "c": {"selected": 1}})
            == "a,c"
        )

    def test_dict_empty_key_dropped(self) -> None:
        assert flatten_option({"": {"selected": 1}}) == ""

    def test_list_positional(self) -> None:
        assert flatten_option([{"selected": 0}, {"selected": 1}, {"selected": 0}]) == "1"

    def test_none_and_scalars(self) -> None:
        assert flatten_option(None) == ""
        assert flatten_option("x") == "x"
        assert flatten_option(5) == "5"


class TestParser:
    def test_minimal(self) -> None:
        cfg = _cfg()
        assert cfg.description == "vpn-a"
        assert cfg.fields == (("remote", "vpn.example.com"),)

    def test_description_override(self) -> None:
        assert _cfg(description="Office").diff_key == "Office"

    def test_wire_names_and_serialization(self) -> None:
        cfg = _cfg(
            data_ciphers=["B", "A", "A"],
            reneg_sec=3600,
            verify_x509_name="srv",
            enabled=True,
            remote_cert_tls=False,
            verb=5,
            data_ciphers_fallback="AES-256-GCM",
        )
        fields = dict(cfg.fields)
        assert fields["data-ciphers"] == "A,B"
        assert fields["reneg-sec"] == "3600"
        assert fields["verify-x509-name"] == "srv"
        assert fields["enabled"] == "1"
        assert fields["remote_cert_tls"] == "0"
        assert fields["verb"] == "5"
        assert fields["data-ciphers-fallback"] == "AES-256-GCM"

    def test_remote_order_kept(self) -> None:
        assert dict(_cfg(remote=["b.example.com", "a.example.com"]).fields)["remote"] == (
            "b.example.com,a.example.com"
        )

    @pytest.mark.parametrize(
        "bad",
        [
            {"bogus": 1},
            {"proto": "sctp"},
            {"dev_type": "x"},
            {"topology": "x"},
            {"port": 0},
            {"port": 70000},
            {"port": True},
            {"port": "1194"},
            {"verb": 12},
            {"verb": -1},
            {"enabled": "yes"},
            {"remote": []},
            {"remote": [1]},
            {"route": "10.0.0.0/8"},
            {"route": ["a,b"]},
            {"lock": "x"},
            {"update_password": "x"},
            {"password": 5},
            {"description": 5},
            {"ca_ref": ""},
            {"uuid": "x"},
            {"role": "server"},
        ],
    )
    def test_rejections(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            _cfg(**bad)

    def test_non_dict_config(self) -> None:
        res = ResourceConfig.model_construct(
            name="x", type="openvpn.instances", provider="opnsense", config=None
        )
        with pytest.raises(ValueError):
            openvpn_instance_configs_from_resources([res])

    def test_other_types_skipped(self) -> None:
        res = ResourceConfig(name="x", type="trust.cas", provider="opnsense", config={})
        assert openvpn_instance_configs_from_resources([res]) == []

    def test_errors_never_echo_values(self) -> None:
        with pytest.raises(ValueError) as exc:
            _cfg(password=12345, username="u")
        assert "12345" not in str(exc.value)
        with pytest.raises(ValueError) as exc2:
            _cfg(port=99999)
        assert "99999" not in str(exc2.value)

    def test_allowed_keys_include_fields(self) -> None:
        assert {"remote", "ca_ref", "username", "password", "reneg_sec"} <= ALLOWED_KEYS
        assert not {"role", "cert", "tls_key", "uuid", "ca"} & ALLOWED_KEYS
        assert "vpnid" in ALLOWED_KEYS


class TestPayload:
    def test_shape(self) -> None:
        cfg = _cfg(username="u", password=SECRET_PW, port=1194, proto="udp")
        body = cfg.to_payload("refid1", include_password=True)["instance"]
        assert body["role"] == "client"
        assert body["description"] == "vpn-a"
        assert body["ca"] == "refid1"
        assert body["remote"] == "vpn.example.com"
        assert body["port"] == "1194"
        assert body["username"] == "u"
        assert body["password"] == SECRET_PW

    def test_password_omitted_by_default(self) -> None:
        body = _cfg(password=SECRET_PW).to_payload("r")["instance"]
        assert "password" not in body

    def test_repr_hides_secrets(self) -> None:
        text = repr(_cfg(username="user-a", password=SECRET_PW))
        assert SECRET_PW not in text
        assert "user-a" not in text


class TestChangedFields:
    def _live_matching(self) -> LiveOpenVpnInstance:
        extra: dict[str, Any] = {
            "data-ciphers": {"A": {"selected": 1}, "B": {"selected": 1}, "C": {"selected": 0}}
        }
        return _live(
            remote=_opt("vpn.example.com"),
            ca=_opt("r1"),
            enabled="1",
            verb=[{"selected": 0}, {"selected": 0}, {"selected": 1}],
            username="u",
            **extra,
        )

    def test_no_change(self) -> None:
        cfg = _cfg(data_ciphers=["B", "A"], enabled=True, verb=2, username="u")
        assert changed_fields(self._live_matching(), cfg, "r1") == []

    def test_set_compare_ignores_order_remote_does_not(self) -> None:
        live = _live(remote=_opt("a.example.com", "b.example.com"))
        live.raw["remote"]["b.example.com"]["selected"] = 1
        assert changed_fields(live, _cfg(remote=["a.example.com", "b.example.com"])) == []
        assert changed_fields(live, _cfg(remote=["b.example.com", "a.example.com"])) == ["remote"]

    def test_bool_empty_live_is_false(self) -> None:
        assert changed_fields(_live(enabled=""), _cfg(enabled=False, remote=["x"]), "") == [
            "remote"
        ]

    def test_detects_changes(self) -> None:
        live = self._live_matching()
        cfg = _cfg(enabled=False, verb=3, username="other", remote=["vpn.example.com"])
        assert sorted(changed_fields(live, cfg, "r2")) == ["ca", "enabled", "username", "verb"]

    def test_unresolved_ca_skipped(self) -> None:
        assert "ca" not in changed_fields(_live(remote=_opt("vpn.example.com")), _cfg(), "")

    def test_password_never_compared(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), password="anything")
        assert changed_fields(live, _cfg(password=SECRET_PW)) == []

    def test_update_password_forces_change(self) -> None:
        live = _live(remote=_opt("vpn.example.com"))
        assert changed_fields(live, _cfg(password=SECRET_PW, update_password=True)) == ["password"]
        assert changed_fields(live, _cfg(update_password=True)) == []


class TestComputeDiff:
    def test_add_update_delete(self) -> None:
        same = _live("same", remote=_opt("vpn.example.com"))
        stale = _live("stale")
        diff = compute_diff(
            [_cfg("same"), _cfg("new")],
            [same, stale],
            managed_keys={"stale"},
        )
        assert [a.name for a in diff.adds] == ["new"]
        assert diff.updates == []
        assert [d.description for d in diff.deletes] == ["stale"]

    def test_update(self) -> None:
        live = _live("x", remote=_opt("old.example.com"))
        diff = compute_diff([_cfg("x")], [live])
        assert [w.name for _, w in diff.updates] == ["x"]

    def test_unmanaged_not_deleted(self) -> None:
        diff = compute_diff([], [_live("hand")], managed_keys=set())
        assert diff.deletes == []
        assert [u.description for u in diff.unmanaged] == ["hand"]

    def test_no_managed_keys_deletes_clients_only(self) -> None:
        diff = compute_diff([], [_live("c"), _live("s", role="server")])
        assert [d.description for d in diff.deletes] == ["c"]

    def test_servers_never_deleted_even_if_managed(self) -> None:
        diff = compute_diff([], [_live("s", role="server")], managed_keys={"s"})
        assert diff.deletes == [] and diff.unmanaged == []

    def test_add_only(self) -> None:
        diff = compute_diff([], [_live("c")], add_only=True)
        assert diff.deletes == []

    def test_lock(self) -> None:
        live = _live("x", remote=_opt("old.example.com"))
        diff = compute_diff([_cfg("x", lock=True)], [live])
        assert diff.updates == [] and len(diff.locked) == 1
        diff2 = compute_diff([_cfg("x", lock=True)], [])
        assert diff2.adds == [] and len(diff2.locked) == 1

    def test_locked_not_deleted_by_other_path(self) -> None:
        assert compute_diff([_cfg("x", lock=True)], [_live("x")]).deletes == []

    def test_duplicate_live_clients_raise(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            compute_diff([], [_live("d"), _live("d")])

    def test_duplicate_server_descriptions_ignored(self) -> None:
        compute_diff([], [_live("d", role="server"), _live("d", role="server")])

    def test_server_collision_raises(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            compute_diff([_cfg("s")], [_live("s", role="server")])


def _client_mock(rows: list[dict[str, Any]], instances: dict[str, dict[str, Any]]) -> MagicMock:
    client = MagicMock()

    def fake(method: str, path: str, data: Any = None) -> dict[str, Any]:
        if path == "openvpn/instances/search":
            return {"rows": rows}
        if path.startswith("openvpn/instances/get/"):
            return {"instance": instances[path.rsplit("/", 1)[1]]}
        return {"result": "saved"}

    client.request.side_effect = fake
    return client


class TestService:
    def test_search_reads_each_row(self) -> None:
        client = _client_mock(
            [{"uuid": "u1"}, {"uuid": "u2"}, {"nouuid": 1}],
            {
                "u1": {"description": "c", "role": _opt("client", "server")},
                "u2": {"description": "s", "role": _opt("server", "client")},
            },
        )
        live = OpenVpnInstanceService(client).search()
        assert [(x.uuid, x.description, x.role) for x in live] == [
            ("u1", "c", "client"),
            ("u2", "s", "server"),
        ]

    def test_search_tolerates_bad_bodies(self) -> None:
        client = MagicMock()
        client.request.return_value = "garbage"
        assert OpenVpnInstanceService(client).search() == []

    def test_search_skips_malformed_get(self) -> None:
        client = MagicMock()
        client.request.side_effect = [{"rows": [{"uuid": "u1"}]}, {"unexpected": 1}]
        assert OpenVpnInstanceService(client).search() == []

    def test_apply_diff_writes(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = OpenVpnInstanceService(client)
        diff = compute_diff(
            [_cfg("new", password=SECRET_PW), _cfg("upd", password=SECRET_PW)],
            [_live("upd", remote=_opt("old.example.com")), _live("gone")],
        )
        counts = svc.apply_diff(diff, {"vpn-ca": "r1"})
        assert counts == {"created": 1, "updated": 1, "deleted": 1}
        calls = {c.args[1]: c.kwargs.get("data") for c in client.request.call_args_list}
        assert calls["openvpn/instances/add"]["instance"]["password"] == SECRET_PW
        assert "password" not in calls["openvpn/instances/set/u-upd"]["instance"]
        assert calls["openvpn/instances/set/u-upd"]["instance"]["ca"] == "r1"
        assert "openvpn/instances/del/u-gone" in calls

    def test_update_password_sent_only_when_flagged(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        OpenVpnInstanceService(client).update(
            "u", _cfg(password=SECRET_PW, update_password=True), "r1"
        )
        assert client.request.call_args.kwargs["data"]["instance"]["password"] == SECRET_PW

    def test_unresolved_ca_raises_before_writes(self) -> None:
        client = MagicMock()
        svc = OpenVpnInstanceService(client)
        diff = compute_diff([_cfg("new")], [_live("gone")])
        with pytest.raises(ReferenceValidationError) as exc:
            svc.apply_diff(diff, {})
        client.request.assert_not_called()
        assert SECRET_PW not in str(exc.value)

    def test_failed_write_raises(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "failed", "validations": {"x": "bad"}}
        with pytest.raises(APIError):
            OpenVpnInstanceService(client).add(_cfg(), "r1")

    def test_delete_refuses_server(self) -> None:
        client = MagicMock()
        with pytest.raises(ValueError):
            OpenVpnInstanceService(client).delete(_live("s", role="server"))
        client.request.assert_not_called()

    def test_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"status": "ok"}
        OpenVpnInstanceService(client).reconfigure()
        assert client.request.call_args.args[:2] == ("POST", "openvpn/service/reconfigure")


class TestVpnid:
    @staticmethod
    def _sent(client: MagicMock) -> dict[str, dict[str, Any]]:
        return {c.args[1]: c.kwargs.get("data") for c in client.request.call_args_list}

    @staticmethod
    def _svc() -> tuple[OpenVpnInstanceService, MagicMock]:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        return OpenVpnInstanceService(client), client

    def test_explicit_vpnid_sent_on_add(self) -> None:
        svc, client = self._svc()
        svc.apply_diff(compute_diff([_cfg("new", vpnid=7)], []), {"vpn-ca": "r1"})
        assert self._sent(client)["openvpn/instances/add"]["instance"]["vpnid"] == "7"

    def test_omitted_allocates_max_plus_one_across_roles(self) -> None:
        svc, client = self._svc()
        live = [_live("c", vpnid="2"), _live("s", role="server", vpnid="5")]
        svc.apply_diff(compute_diff([_cfg("new")], live), {"vpn-ca": "r1"})
        assert self._sent(client)["openvpn/instances/add"]["instance"]["vpnid"] == "6"

    def test_allocation_starts_at_one(self) -> None:
        svc, client = self._svc()
        svc.apply_diff(compute_diff([_cfg("new")], []), {"vpn-ca": "r1"})
        assert self._sent(client)["openvpn/instances/add"]["instance"]["vpnid"] == "1"

    def test_multiple_omitted_get_distinct_ids(self) -> None:
        svc, client = self._svc()
        diff = compute_diff([_cfg("a"), _cfg("b"), _cfg("c")], [_live("x", vpnid="3")])
        svc.apply_diff(diff, {"vpn-ca": "r1"})
        ids = [
            c.kwargs["data"]["instance"]["vpnid"]
            for c in client.request.call_args_list
            if c.args[1] == "openvpn/instances/add"
        ]
        assert sorted(ids) == ["4", "5", "6"]

    def test_explicit_ids_skipped_by_allocation(self) -> None:
        svc, client = self._svc()
        diff = compute_diff([_cfg("auto"), _cfg("pinned", vpnid=9)], [_live("x", vpnid="1")])
        svc.apply_diff(diff, {"vpn-ca": "r1"})
        by_desc = {
            c.kwargs["data"]["instance"]["description"]: c.kwargs["data"]["instance"]["vpnid"]
            for c in client.request.call_args_list
            if c.args[1] == "openvpn/instances/add"
        }
        assert by_desc == {"pinned": "9", "auto": "10"}

    def test_explicit_mismatch_is_update(self) -> None:
        live = _live("x", remote=_opt("vpn.example.com"), vpnid="1")
        diff = compute_diff([_cfg("x", vpnid=2)], [live])
        assert [w.name for _, w in diff.updates] == ["x"]
        assert changed_fields(live, _cfg("x", vpnid=2)) == ["vpnid"]
        assert changed_fields(live, _cfg("x", vpnid=1)) == []

    def test_omitted_never_causes_update(self) -> None:
        live = _live("x", remote=_opt("vpn.example.com"), vpnid="4")
        assert changed_fields(live, _cfg("x")) == []
        assert compute_diff([_cfg("x")], [live]).updates == []

    def test_update_payload_carries_live_vpnid(self) -> None:
        svc, client = self._svc()
        live = _live("upd", remote=_opt("old.example.com"), vpnid="4")
        svc.apply_diff(compute_diff([_cfg("upd")], [live]), {"vpn-ca": "r1"})
        assert self._sent(client)["openvpn/instances/set/u-upd"]["instance"]["vpnid"] == "4"

    def test_update_payload_prefers_explicit_vpnid(self) -> None:
        svc, client = self._svc()
        live = _live("upd", remote=_opt("vpn.example.com"), vpnid="4")
        svc.apply_diff(compute_diff([_cfg("upd", vpnid=8)], [live]), {"vpn-ca": "r1"})
        assert self._sent(client)["openvpn/instances/set/u-upd"]["instance"]["vpnid"] == "8"

    @pytest.mark.parametrize("bad", ["1", 0, -2, True, 1.5])
    def test_parser_rejects_bad_vpnid(self, bad: Any) -> None:
        with pytest.raises(ValueError):
            _cfg(vpnid=bad)


class TestLoaderRoundTrip:
    """Configs parsed by the real nested loader are accepted (live-test regression)."""

    def test_loader_injected_name_is_accepted(self, tmp_path: Any) -> None:
        from infrafoundry.core.config.package_loader import PackageLoader

        data = {
            "opnsense": {
                "openvpn": {
                    "instances": [
                        {
                            "name": "vpn-a",
                            "config": {
                                "description": "Example VPN",
                                "remote": ["192.0.2.10"],
                                "ca_ref": "vpn-ca",
                            },
                        }
                    ]
                }
            }
        }
        resources = PackageLoader(tmp_path)._parse_resources_from_data(data, "fw.yaml", "opnsense")
        assert resources[0].config["name"] == "vpn-a"
        configs = openvpn_instance_configs_from_resources(resources)
        assert [c.description for c in configs] == ["Example VPN"]


class TestCertRef:
    """Optional ``cert_ref`` resolved to the wire ``cert`` (#1320)."""

    def test_parsed_and_defaulted(self) -> None:
        assert _cfg(cert_ref="vpn-cert").cert_ref == "vpn-cert"
        assert _cfg().cert_ref == ""
        assert "cert_ref" in ALLOWED_KEYS

    @pytest.mark.parametrize("bad", ["", 5])
    def test_bad_values_rejected(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="cert_ref"):
            _cfg(cert_ref=bad)

    def test_payload(self) -> None:
        cfg = _cfg(cert_ref="vpn-cert")
        assert cfg.to_payload("r1", cert_refid="c1")["instance"]["cert"] == "c1"
        assert "cert" not in cfg.to_payload("r1")["instance"]

    def test_changed_fields(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), cert=_opt("c1", "c2"))
        cfg = _cfg(cert_ref="vpn-cert")
        assert changed_fields(live, cfg, "r1", "c1") == []
        assert changed_fields(live, cfg, "r1", "c2") == ["cert"]
        assert changed_fields(live, cfg, "r1", "") == []

    def test_compute_diff_cert_only_update(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), cert=_opt("c1", "c2"))
        desired = [_cfg(cert_ref="vpn-cert")]
        diff = compute_diff(
            desired, [live], ca_refids={"vpn-ca": "r1"}, cert_refids={"vpn-cert": "c2"}
        )
        assert len(diff.updates) == 1
        same = compute_diff(
            desired, [live], ca_refids={"vpn-ca": "r1"}, cert_refids={"vpn-cert": "c1"}
        )
        assert same.updates == []

    def test_hand_set_cert_not_cleared_without_cert_ref(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), cert=_opt("c1"))
        diff = compute_diff([_cfg()], [live], ca_refids={"vpn-ca": "r1"})
        assert diff.updates == []

    def test_apply_diff_sends_cert_on_add_and_update(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        diff = compute_diff(
            [_cfg("new", cert_ref="vpn-cert"), _cfg("upd", cert_ref="vpn-cert")],
            [_live("upd", remote=_opt("old.example.com"))],
        )
        counts = OpenVpnInstanceService(client).apply_diff(
            diff, {"vpn-ca": "r1"}, {"vpn-cert": "c1"}
        )
        assert counts == {"created": 1, "updated": 1, "deleted": 0}
        calls = {c.args[1]: c.kwargs.get("data") for c in client.request.call_args_list}
        assert calls["openvpn/instances/add"]["instance"]["cert"] == "c1"
        assert calls["openvpn/instances/set/u-upd"]["instance"]["cert"] == "c1"

    def test_unresolved_cert_raises_before_writes(self) -> None:
        client = MagicMock()
        diff = compute_diff([_cfg("new", cert_ref="vpn-cert", password=SECRET_PW)], [])
        with pytest.raises(ReferenceValidationError, match="cert_ref 'vpn-cert'") as exc:
            OpenVpnInstanceService(client).apply_diff(diff, {"vpn-ca": "r1"}, {})
        client.request.assert_not_called()
        assert SECRET_PW not in str(exc.value)

    def test_no_cert_ref_needs_no_cert_refids(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        diff = compute_diff([_cfg("new")], [])
        counts = OpenVpnInstanceService(client).apply_diff(diff, {"vpn-ca": "r1"})
        assert counts["created"] == 1
        sent = client.request.call_args.kwargs["data"]["instance"]
        assert "cert" not in sent


class TestTlsKeyRef:
    """Optional ``tls_key_ref`` resolved to the wire ``tls_key`` (#1319)."""

    def test_parsed_and_defaulted(self) -> None:
        assert _cfg(tls_key_ref="vpn-key").tls_key_ref == "vpn-key"
        assert _cfg().tls_key_ref == ""
        assert "tls_key_ref" in ALLOWED_KEYS
        assert "tls_key" not in ALLOWED_KEYS

    @pytest.mark.parametrize("bad", ["", 5])
    def test_bad_values_rejected(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="tls_key_ref"):
            _cfg(tls_key_ref=bad)

    def test_payload(self) -> None:
        cfg = _cfg(tls_key_ref="vpn-key")
        assert cfg.to_payload("r1", tls_key_uuid="k1")["instance"]["tls_key"] == "k1"
        assert "tls_key" not in cfg.to_payload("r1")["instance"]

    def test_changed_fields(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), tls_key=_opt("k1", "k2"))
        cfg = _cfg(tls_key_ref="vpn-key")
        assert changed_fields(live, cfg, "r1", "", "k1") == []
        assert changed_fields(live, cfg, "r1", "", "k2") == ["tls_key"]
        assert changed_fields(live, cfg, "r1", "", "") == []

    def test_compute_diff_key_only_update(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), tls_key=_opt("k1", "k2"))
        desired = [_cfg(tls_key_ref="vpn-key")]
        diff = compute_diff(
            desired, [live], ca_refids={"vpn-ca": "r1"}, static_key_uuids={"vpn-key": "k2"}
        )
        assert len(diff.updates) == 1
        same = compute_diff(
            desired, [live], ca_refids={"vpn-ca": "r1"}, static_key_uuids={"vpn-key": "k1"}
        )
        assert same.updates == []

    def test_hand_set_key_not_cleared_without_ref(self) -> None:
        live = _live(remote=_opt("vpn.example.com"), ca=_opt("r1"), tls_key=_opt("k1"))
        assert compute_diff([_cfg()], [live], ca_refids={"vpn-ca": "r1"}).updates == []

    def test_apply_diff_sends_key_on_add_and_update(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        diff = compute_diff(
            [_cfg("new", tls_key_ref="vpn-key"), _cfg("upd", tls_key_ref="vpn-key")],
            [_live("upd", remote=_opt("old.example.com"))],
        )
        counts = OpenVpnInstanceService(client).apply_diff(
            diff, {"vpn-ca": "r1"}, None, {"vpn-key": "k1"}
        )
        assert counts == {"created": 1, "updated": 1, "deleted": 0}
        calls = {c.args[1]: c.kwargs.get("data") for c in client.request.call_args_list}
        assert calls["openvpn/instances/add"]["instance"]["tls_key"] == "k1"
        assert calls["openvpn/instances/set/u-upd"]["instance"]["tls_key"] == "k1"

    def test_unresolved_key_raises_before_writes(self) -> None:
        client = MagicMock()
        diff = compute_diff([_cfg("new", tls_key_ref="vpn-key", password=SECRET_PW)], [])
        with pytest.raises(ReferenceValidationError, match="tls_key_ref 'vpn-key'") as exc:
            OpenVpnInstanceService(client).apply_diff(diff, {"vpn-ca": "r1"}, {}, {})
        client.request.assert_not_called()
        assert SECRET_PW not in str(exc.value)
