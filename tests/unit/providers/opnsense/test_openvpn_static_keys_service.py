"""Unit tests for the OpenVPN static-key service (#1319)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.openvpn_static_keys import (
    LiveStaticKey,
    OpenVpnStaticKeyConfig,
    OpenVpnStaticKeyService,
    changed_fields,
    compute_diff,
    key_block,
    static_key_configs_from_resources,
    static_key_uuids_by_name,
)

# Split so the detect-private-key hook does not flag these fake fixtures.
BEGIN = "-----BEGIN OpenVPN Static" + " key V1-----"
END = "-----END OpenVPN Static" + " key V1-----"

PEM = f"{BEGIN}\nFAKEKEYMATERIAL\n{END}"
PEM_OTHER = f"{BEGIN}\nOTHERMATERIAL\n{END}"
PEM_COMMENTED = "#\n# 2048 bit OpenVPN static key\n#\n" + PEM + "\n"
URI = "secret://env_secrets/vpn/key"


def _res(name: str = "vpn-key", **config: Any) -> ResourceConfig:
    config.setdefault("mode", "crypt")
    config.setdefault("key", URI)
    return ResourceConfig(name=name, type="openvpn.static_keys", provider="opnsense", config=config)


def _cfg(name: str = "vpn-key", **config: Any) -> OpenVpnStaticKeyConfig:
    config.setdefault("key", PEM)
    return static_key_configs_from_resources([_res(name, **config)])[0]


def _live(
    description: str = "vpn-key", /, mode: str = "crypt", key: str = "", uuid: str = ""
) -> LiveStaticKey:
    return LiveStaticKey(
        uuid=uuid or f"u-{description}", description=description, mode=mode, key=key
    )


class TestParser:
    def test_minimal(self) -> None:
        cfg = _cfg()
        assert (cfg.name, cfg.description, cfg.mode) == ("vpn-key", "vpn-key", "crypt")
        assert cfg.update_key is False and cfg.lock is False

    def test_description_override(self) -> None:
        assert _cfg(description="Office key").diff_key == "Office key"

    @pytest.mark.parametrize("bad", [None, "", "tls", 5])
    def test_mode_required_and_valid(self, bad: Any) -> None:
        config: dict[str, Any] = {"key": URI}
        if bad is not None:
            config["mode"] = bad
        with pytest.raises(ValueError, match="mode"):
            static_key_configs_from_resources(
                [ResourceConfig(name="k", type="openvpn.static_keys", provider="o", config=config)]
            )

    @pytest.mark.parametrize("mode", ["auth", "crypt", "crypt-v2"])
    def test_all_modes_accepted(self, mode: str) -> None:
        assert _cfg(mode=mode).mode == mode

    @pytest.mark.parametrize("bad", [None, "", "  ", 5])
    def test_key_required(self, bad: Any) -> None:
        config: dict[str, Any] = {"mode": "crypt"}
        if bad is not None:
            config["key"] = bad
        with pytest.raises(ValueError, match="key"):
            static_key_configs_from_resources(
                [ResourceConfig(name="k", type="openvpn.static_keys", provider="o", config=config)]
            )

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg(uuid="x")

    def test_bad_flag_types(self) -> None:
        with pytest.raises(ValueError, match="lock"):
            _cfg(lock="yes")
        with pytest.raises(ValueError, match="update_key"):
            _cfg(update_key=1)

    def test_non_dict_config_rejected(self) -> None:
        res = ResourceConfig.model_construct(
            name="k", type="openvpn.static_keys", provider="o", config=[]
        )
        with pytest.raises(ValueError, match="non-dict"):
            static_key_configs_from_resources([res])

    def test_other_types_skipped(self) -> None:
        other = ResourceConfig(name="x", type="trust.cas", provider="o", config={})
        assert static_key_configs_from_resources([other]) == []

    def test_require_key_rejects_non_pem_without_leaking_value(self) -> None:
        secret = "not-a-pem-secret-value"  # nosec B105  # test fixture
        with pytest.raises(ValueError, match="PEM") as exc:
            static_key_configs_from_resources([_res(key=secret)], require_key=True)
        assert secret not in str(exc.value)

    def test_require_key_accepts_pem(self) -> None:
        assert static_key_configs_from_resources([_res(key=PEM)], require_key=True)

    def test_uri_accepted_without_require_key(self) -> None:
        assert static_key_configs_from_resources([_res()], require_key=False)[0].key == URI

    def test_require_key_accepts_commented_key_file(self) -> None:
        # genKey and `openvpn --genkey` write '#' comment lines before BEGIN.
        assert static_key_configs_from_resources([_res(key=PEM_COMMENTED)], require_key=True)

    def test_require_key_rejects_begin_without_end(self) -> None:
        with pytest.raises(ValueError, match="PEM"):
            static_key_configs_from_resources([_res(key=f"# c\n{BEGIN}\nX")], require_key=True)


class TestKeyBlock:
    def test_drops_comment_header_and_whitespace(self) -> None:
        assert key_block(PEM_COMMENTED) == PEM
        assert key_block("  " + PEM.replace("\n", "\r\n") + "\n\n") == PEM

    def test_no_markers_is_empty(self) -> None:
        assert key_block("") == ""
        assert key_block("# only a comment\nFAKE") == ""
        assert key_block(f"{END}\n-----BEGIN x") == ""

    def test_commented_and_bare_compare_equal(self) -> None:
        have = _live(key=PEM)
        assert changed_fields(have, _cfg(key=PEM_COMMENTED)) == []
        assert changed_fields(_live(key=PEM_COMMENTED), _cfg(key=PEM_OTHER)) == ["key"]


class TestPayloadAndRepr:
    def test_payload_shape(self) -> None:
        assert _cfg().to_payload() == {
            "statickey": {"description": "vpn-key", "mode": "crypt", "key": PEM}
        }

    def test_payload_without_key(self) -> None:
        assert _cfg().to_payload(include_key=False) == {
            "statickey": {"description": "vpn-key", "mode": "crypt"}
        }

    def test_repr_never_contains_key(self) -> None:
        assert "FAKEKEYMATERIAL" not in repr(_cfg())
        live = LiveStaticKey("u", "d", "crypt", key=PEM, raw={"key": PEM})
        assert "FAKEKEYMATERIAL" not in repr(live)


class TestChangedFields:
    def test_equal_with_no_live_key(self) -> None:
        assert changed_fields(_live(), _cfg()) == []

    def test_mode_change(self) -> None:
        assert changed_fields(_live(mode="auth"), _cfg()) == ["mode"]

    def test_live_key_differs(self) -> None:
        assert changed_fields(_live(key=PEM_OTHER), _cfg()) == ["key"]

    def test_whitespace_normalized(self) -> None:
        live = _live(key="  " + PEM.replace("\n", "\r\n\n") + "\n")
        assert changed_fields(live, _cfg()) == []

    def test_empty_live_key_update_key_flag(self) -> None:
        assert changed_fields(_live(), _cfg(update_key=True)) == ["key"]
        assert changed_fields(_live(), _cfg(update_key=False)) == []


class TestComputeDiff:
    def test_add_update_delete(self) -> None:
        diff = compute_diff(
            [_cfg("new"), _cfg("upd", mode="auth")],
            [_live("upd"), _live("old")],
        )
        assert [c.name for c in diff.adds] == ["new"]
        assert [w.name for _, w in diff.updates] == ["upd"]
        assert [d.description for d in diff.deletes] == ["old"]

    def test_managed_set_scopes_deletes(self) -> None:
        diff = compute_diff([], [_live("mine"), _live("hand")], managed_keys={"mine"})
        assert [d.description for d in diff.deletes] == ["mine"]
        assert [u.description for u in diff.unmanaged] == ["hand"]

    def test_add_only(self) -> None:
        diff = compute_diff([], [_live("old")], add_only=True)
        assert diff.deletes == []

    def test_lock(self) -> None:
        diff = compute_diff([_cfg(lock=True, mode="auth")], [_live()])
        assert diff.updates == [] and len(diff.locked) == 1

    def test_duplicate_live_descriptions_raise(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            compute_diff([], [_live("a", uuid="1"), _live("a", uuid="2")])

    def test_in_use_delete_is_blocked(self) -> None:
        diff = compute_diff([], [_live("old", uuid="k1")], in_use_uuids={"k1"})
        assert diff.deletes == []
        assert [live.description for live, _ in diff.blocked] == ["old"]
        assert any("kept" in w for w in diff.warnings)


def test_static_key_uuids_by_name() -> None:
    live = [_live("vpn-key", uuid="k1")]
    other = ResourceConfig(name="x", type="trust.cas", provider="o", config={})
    resources = [_res("vpn-key"), _res("missing"), other]
    assert static_key_uuids_by_name(resources, live) == {"vpn-key": "k1"}


class TestService:
    def _client(self, rows: dict[str, Any]) -> MagicMock:
        client = MagicMock()

        def fake(method: str, path: str, data: Any = None) -> Any:
            if path == "openvpn/instances/searchStaticKey":
                return {"rows": [{"uuid": u} for u in rows]}
            if path.startswith("openvpn/instances/getStaticKey/"):
                return {"statickey": rows[path.rsplit("/", 1)[1]]}
            return {"result": "saved"}

        client.request.side_effect = fake
        return client

    def test_search_reads_search_then_get(self) -> None:
        client = self._client(
            {"k1": {"description": "a", "mode": {"crypt": {"value": "crypt", "selected": 1}}}}
        )
        live = OpenVpnStaticKeyService(client).search()
        assert [(x.uuid, x.description, x.mode, x.key) for x in live] == [("k1", "a", "crypt", "")]
        first = client.request.call_args_list[0]
        assert first.args[:2] == ("POST", "openvpn/instances/searchStaticKey")
        assert client.request.call_args_list[1].args[:2] == (
            "GET",
            "openvpn/instances/getStaticKey/k1",
        )

    @pytest.mark.parametrize("body", [None, "x", {}, {"rows": "x"}, {"rows": [1, {}]}])
    def test_search_tolerates_malformed_body(self, body: Any) -> None:
        client = MagicMock()
        client.request.return_value = body
        assert OpenVpnStaticKeyService(client).search() == []

    def test_search_skips_malformed_get(self) -> None:
        client = MagicMock()
        client.request.side_effect = [{"rows": [{"uuid": "k1"}]}, {"statickey": "nope"}]
        assert OpenVpnStaticKeyService(client).search() == []

    def test_update_sends_key_only_when_changed(self) -> None:
        client = self._client({})
        svc = OpenVpnStaticKeyService(client)
        diff = compute_diff([_cfg(mode="auth")], [_live()])
        svc.apply_diff(diff)
        data = client.request.call_args.kwargs["data"]["statickey"]
        assert "key" not in data and data["mode"] == "auth"

        client.reset_mock()
        diff = compute_diff([_cfg(update_key=True)], [_live()])
        svc.apply_diff(diff)
        assert client.request.call_args.kwargs["data"]["statickey"]["key"] == PEM

        client.reset_mock()
        diff = compute_diff([_cfg()], [_live(key=PEM_OTHER)])
        svc.apply_diff(diff)
        assert client.request.call_args.kwargs["data"]["statickey"]["key"] == PEM

    def test_add_and_delete(self) -> None:
        client = self._client({})
        diff = compute_diff([_cfg("new")], [_live("old", uuid="k9")])
        counts = OpenVpnStaticKeyService(client).apply_diff(diff)
        assert counts == {"created": 1, "updated": 0, "deleted": 1}
        paths = [c.args[1] for c in client.request.call_args_list]
        assert paths == ["openvpn/instances/addStaticKey", "openvpn/instances/delStaticKey/k9"]

    def test_failed_write_raises_without_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "failed", "validations": {"x": "bad"}}
        with pytest.raises(APIError) as exc:
            OpenVpnStaticKeyService(client).add(_cfg())
        assert "FAKEKEYMATERIAL" not in str(exc.value)

    def test_reconfigure(self) -> None:
        client = self._client({})
        OpenVpnStaticKeyService(client).reconfigure()
        assert client.request.call_args.args[:2] == ("POST", "openvpn/service/reconfigure")
