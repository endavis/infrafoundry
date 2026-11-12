"""Unit tests for ``OpenVpnInstanceManager`` (#808)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.openvpn_instances import OpenVpnInstanceManager
from infrafoundry.providers.opnsense.services.openvpn_instances import OpenVpnInstanceService

CRT = "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----"
SECRET_PW = "hunter2-not-real"  # test fixture


def _inst(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("remote", ["vpn.example.com"])
    config.setdefault("ca_ref", "vpn-ca")
    return ResourceConfig(name=name, type="openvpn.instances", provider="opnsense", config=config)


def _ca(name: str = "vpn-ca") -> ResourceConfig:
    return ResourceConfig(name=name, type="trust.cas", provider="opnsense", config={"crt": CRT})


def _cert(name: str = "vpn-cert") -> ResourceConfig:
    return ResourceConfig(
        name=name, type="trust.certs", provider="opnsense", config={"crt": CRT, "ca_ref": "vpn-ca"}
    )


@pytest.fixture(autouse=True)
def _no_secret_lookup() -> Iterator[None]:
    with patch(
        "infrafoundry.providers.opnsense.components.openvpn_instances.resolve_resource_secrets",
        side_effect=lambda _d, _e, resources, _t: resources,
    ):
        yield


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager(client: MagicMock, tmp_path: Any) -> Iterator[OpenVpnInstanceManager]:
    with patch.object(
        OpenVpnInstanceService, "from_environment", return_value=OpenVpnInstanceService(client)
    ):
        yield OpenVpnInstanceManager(tmp_path)


def _set_live(
    client: MagicMock,
    *,
    cas: list[dict[str, Any]] | None = None,
    certs: list[dict[str, Any]] | None = None,
    instances: dict[str, dict[str, Any]] | None = None,
    static_keys: dict[str, dict[str, Any]] | None = None,
) -> None:
    instances = instances or {}
    static_keys = static_keys or {}

    def fake(method: str, path: str, data: Any = None) -> dict[str, Any]:
        if path == "trust/ca/search":
            return {"rows": cas or []}
        if path == "trust/cert/search":
            return {"rows": certs or []}
        if path == "openvpn/instances/searchStaticKey":
            return {"rows": [{"uuid": u} for u in static_keys]}
        if path.startswith("openvpn/instances/getStaticKey/"):
            return {"statickey": static_keys[path.rsplit("/", 1)[1]]}
        if path == "openvpn/instances/search":
            return {"rows": [{"uuid": u} for u in instances]}
        if path.startswith("openvpn/instances/get/"):
            return {"instance": instances[path.rsplit("/", 1)[1]]}
        return {"result": "saved"}

    client.request.side_effect = fake


def _writes(client: MagicMock) -> list[str]:
    return [
        c.args[1]
        for c in client.request.call_args_list
        if c.args[0] == "POST" or "/set/" in c.args[1] or c.args[1].endswith("/add")
    ]


def _ca_row(descr: str = "vpn-ca") -> dict[str, Any]:
    return {"uuid": "cu", "refid": "ref-1", "descr": descr, "crt_payload": CRT}


def _server(description: str) -> dict[str, Any]:
    return {"description": description, "role": {"server": {"selected": 1}}}


def _client_row(description: str, **extra: Any) -> dict[str, Any]:
    return {"description": description, "role": {"client": {"selected": 1}}, **extra}


def test_class_markers() -> None:
    assert OpenVpnInstanceManager.SIBLING_RESOURCE_TYPE == (
        "trust.cas",
        "trust.certs",
        "openvpn.static_keys",
    )
    assert OpenVpnInstanceManager.SPLIT_DELETE_PHASE is True
    assert OpenVpnInstanceManager.DELETE_SCOPE == "managed_set"
    assert OpenVpnInstanceManager.FINALIZATION_HOOK == "openvpn_reconfigure"


def _cert_row(descr: str = "vpn-cert") -> dict[str, Any]:
    return {"uuid": "ku", "refid": "cert-1", "descr": descr, "crt_payload": CRT}


def _searched(client: MagicMock, path: str) -> bool:
    return any(c.args[1] == path for c in client.request.call_args_list)


def test_apply_adds_with_ca_refid(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()])
    result = manager.apply("env", [_inst("a", password=SECRET_PW)], sibling_resources=[_ca()])
    assert result["resources_created"] == 1
    add = next(c for c in client.request.call_args_list if c.args[1] == "openvpn/instances/add")
    assert add.kwargs["data"]["instance"]["ca"] == "ref-1"
    assert add.kwargs["data"]["instance"]["password"] == SECRET_PW
    assert [o.action for o in result["resource_outcomes"]] == ["add"]


def test_managed_sibling_resolves(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()])
    result = manager.apply("env", [_inst("a")], managed_sibling_resources=[_ca()])
    assert result["resources_created"] == 1


def test_pending_ca_warns_in_plan(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client)
    diff = manager.plan("env", [_inst("a")], sibling_resources=[_ca()])
    assert [a.name for a in diff.adds] == ["a"]
    assert any("not on the box yet" in w for w in diff.warnings)


def test_unresolved_ca_raises_before_writes(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client)
    with pytest.raises(ReferenceValidationError):
        manager.apply("env", [_inst("a")], sibling_resources=[_ca()])
    assert not [p for p in _writes(client) if "/add" in p or "/set/" in p or "/del/" in p]


def test_deletes_only_drops_adds_and_warning(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, instances={"u1": _client_row("old")})
    result = manager.apply(
        "env",
        [_inst("a")],
        deletes_only=True,
        managed_resources=[_inst("old")],
        sibling_resources=[_ca()],
    )
    assert result["resources_created"] == 0
    assert result["resources_deleted"] == 1
    assert result["warnings"] == []


def test_managed_set_scopes_deletes(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(
        client,
        cas=[_ca_row()],
        instances={"u1": _client_row("hand"), "u2": _server("srv")},
    )
    diff = manager.plan("env", [], managed_resources=[], sibling_resources=[_ca()])
    assert diff.deletes == []
    assert [u.description for u in diff.unmanaged] == ["hand"]


def test_unparseable_managed_row_reported(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()])
    bad = ResourceConfig(
        name="bad", type="openvpn.instances", provider="opnsense", config={"bogus": 1}
    )
    result = manager.apply("env", [], managed_resources=[bad], sibling_resources=[_ca()])
    assert result["unresolved_managed"] == ["bad"]


def test_destroy_skips_locked_and_reconfigures(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(
        client,
        instances={"u1": _client_row("a"), "u2": _client_row("b"), "u3": _server("c")},
    )
    result = manager.destroy("env", [_inst("a"), _inst("b", lock=True), _inst("c")])
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    paths = [c.args[1] for c in client.request.call_args_list]
    assert "openvpn/instances/del/u1" in paths
    assert "openvpn/instances/del/u2" not in paths
    assert "openvpn/instances/del/u3" not in paths
    assert paths[-1] == "openvpn/service/reconfigure"


def test_destroy_without_deletion_does_not_reconfigure(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client)
    manager.destroy("env", [_inst("a")])
    assert "openvpn/service/reconfigure" not in [c.args[1] for c in client.request.call_args_list]


def test_get_resource_ids_clients_only(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, instances={"u1": _client_row("Office"), "u2": _server("srv")})
    ids = manager.get_resource_ids("env", [_inst("a", description="Office"), _inst("srv")])
    assert ids == {"a": "u1"}


def test_no_secrets_in_logs(
    manager: OpenVpnInstanceManager, client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    _set_live(
        client,
        cas=[_ca_row()],
        instances={"u1": _client_row("a", remote={"old.example.com": {"selected": 1}})},
    )
    with caplog.at_level(logging.DEBUG):
        result = manager.apply(
            "env",
            [_inst("a", password=SECRET_PW, username="user-a", update_password=True)],
            sibling_resources=[_ca()],
        )
    assert result["resources_updated"] == 1
    assert SECRET_PW not in caplog.text
    assert "user-a" not in caplog.text
    assert SECRET_PW not in repr(result)


def test_apply_adds_with_cert_refid(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()], certs=[_cert_row()])
    result = manager.apply(
        "env", [_inst("a", cert_ref="vpn-cert")], sibling_resources=[_ca(), _cert()]
    )
    assert result["resources_created"] == 1
    add = next(c for c in client.request.call_args_list if c.args[1] == "openvpn/instances/add")
    assert add.kwargs["data"]["instance"]["ca"] == "ref-1"
    assert add.kwargs["data"]["instance"]["cert"] == "cert-1"


def test_managed_sibling_resolves_cert(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()], certs=[_cert_row()])
    result = manager.apply(
        "env",
        [_inst("a", cert_ref="vpn-cert")],
        managed_sibling_resources=[_ca(), _cert()],
    )
    assert result["resources_created"] == 1


def test_pending_cert_warns_in_plan(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()])
    diff = manager.plan(
        "env", [_inst("a", cert_ref="vpn-cert")], sibling_resources=[_ca(), _cert()]
    )
    assert [a.name for a in diff.adds] == ["a"]
    assert any("certificate 'vpn-cert' is not on the box yet" in w for w in diff.warnings)


def test_unresolved_cert_raises_before_writes(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()])
    with pytest.raises(ReferenceValidationError, match="cert_ref 'vpn-cert'"):
        manager.apply("env", [_inst("a", cert_ref="vpn-cert")], sibling_resources=[_ca(), _cert()])
    assert not [p for p in _writes(client) if "/add" in p or "/set/" in p or "/del/" in p]


def test_deletes_only_drops_cert_warning(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()], instances={"u1": _client_row("old")})
    result = manager.apply(
        "env",
        [_inst("a", cert_ref="vpn-cert")],
        deletes_only=True,
        managed_resources=[_inst("old")],
        sibling_resources=[_ca(), _cert()],
    )
    assert result["resources_created"] == 0
    assert result["warnings"] == []


def test_cert_change_updates_instance(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(
        client,
        cas=[_ca_row()],
        certs=[_cert_row()],
        instances={"u1": _client_row("a", ca={"ref-1": {"value": "ref-1", "selected": 1}})},
    )
    diff = manager.plan(
        "env", [_inst("a", cert_ref="vpn-cert")], sibling_resources=[_ca(), _cert()]
    )
    assert [w.name for _, w in diff.updates] == ["a"]


def test_no_cert_search_without_cert_ref(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()])
    manager.apply("env", [_inst("a")], sibling_resources=[_ca(), _cert()])
    assert not _searched(client, "trust/cert/search")


def _key(name: str = "vpn-key") -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="openvpn.static_keys",
        provider="opnsense",
        config={"mode": "crypt", "key": "secret://env_secrets/vpn/key"},
    )


def _key_row(description: str = "vpn-key") -> dict[str, Any]:
    return {"description": description, "mode": {"crypt": {"value": "crypt", "selected": 1}}}


def test_apply_sends_resolved_tls_key_uuid(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()], static_keys={"k1": _key_row()})
    result = manager.apply(
        "env", [_inst("a", tls_key_ref="vpn-key")], sibling_resources=[_ca(), _key()]
    )
    assert result["resources_created"] == 1
    add = next(c for c in client.request.call_args_list if c.args[1] == "openvpn/instances/add")
    assert add.kwargs["data"]["instance"]["tls_key"] == "k1"


def test_managed_sibling_resolves_key(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()], static_keys={"k1": _key_row()})
    result = manager.apply(
        "env",
        [_inst("a", tls_key_ref="vpn-key")],
        managed_sibling_resources=[_ca(), _key()],
    )
    assert result["resources_created"] == 1


def test_pending_key_warns_in_plan(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()])
    diff = manager.plan(
        "env", [_inst("a", tls_key_ref="vpn-key")], sibling_resources=[_ca(), _key()]
    )
    assert [a.name for a in diff.adds] == ["a"]
    assert any("static key 'vpn-key' is not on the box yet" in w for w in diff.warnings)


def test_unresolved_key_raises_before_writes(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()])
    with pytest.raises(ReferenceValidationError, match="tls_key_ref 'vpn-key'"):
        manager.apply("env", [_inst("a", tls_key_ref="vpn-key")], sibling_resources=[_ca(), _key()])
    assert not [p for p in _writes(client) if "/add" in p or "/set/" in p or "/del/" in p]


def test_deletes_only_drops_key_warning(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(client, cas=[_ca_row()], instances={"u1": _client_row("old")})
    result = manager.apply(
        "env",
        [_inst("a", tls_key_ref="vpn-key")],
        deletes_only=True,
        managed_resources=[_inst("old")],
        sibling_resources=[_ca(), _key()],
    )
    assert result["resources_created"] == 0
    assert result["warnings"] == []


def test_key_change_updates_instance(manager: OpenVpnInstanceManager, client: MagicMock) -> None:
    _set_live(
        client,
        cas=[_ca_row()],
        static_keys={"k2": _key_row()},
        instances={
            "u1": _client_row(
                "a",
                ca={"ref-1": {"value": "ref-1", "selected": 1}},
                tls_key={"k1": {"value": "k1", "selected": 1}},
            )
        },
    )
    diff = manager.plan(
        "env", [_inst("a", tls_key_ref="vpn-key")], sibling_resources=[_ca(), _key()]
    )
    assert [w.name for _, w in diff.updates] == ["a"]


def test_no_static_key_search_without_tls_key_ref(
    manager: OpenVpnInstanceManager, client: MagicMock
) -> None:
    _set_live(client, cas=[_ca_row()])
    manager.apply("env", [_inst("a")], sibling_resources=[_ca(), _key()])
    assert not _searched(client, "openvpn/instances/searchStaticKey")
