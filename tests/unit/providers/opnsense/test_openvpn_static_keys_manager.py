"""Unit tests for ``OpenVpnStaticKeyManager`` (#1319)."""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.openvpn_static_keys import (
    OpenVpnStaticKeyManager,
)
from infrafoundry.providers.opnsense.services.openvpn_static_keys import (
    OpenVpnStaticKeyService,
)

MATERIAL = "FAKEKEYMATERIAL"  # nosec B105  # test fixture
# Split so the detect-private-key hook does not flag these fake fixtures.
BEGIN = "-----BEGIN OpenVPN Static" + " key V1-----"
END = "-----END OpenVPN Static" + " key V1-----"

PEM = f"{BEGIN}\n{MATERIAL}\n{END}"
URI = "secret://env_secrets/vpn/key"


def _key(name: str = "vpn-key", **config: Any) -> ResourceConfig:
    config.setdefault("mode", "crypt")
    config.setdefault("key", URI)
    return ResourceConfig(name=name, type="openvpn.static_keys", provider="opnsense", config=config)


def _resolve(_d: Any, _e: Any, resources: list[ResourceConfig], _t: str) -> list[ResourceConfig]:
    return [
        ResourceConfig(
            name=r.name, type=r.type, provider=r.provider, config={**r.config, "key": PEM}
        )
        if r.type == "openvpn.static_keys"
        else r
        for r in resources
    ]


@pytest.fixture(autouse=True)
def _no_secret_lookup() -> Iterator[None]:
    with patch(
        "infrafoundry.providers.opnsense.components.openvpn_static_keys.resolve_resource_secrets",
        side_effect=_resolve,
    ):
        yield


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager(client: MagicMock, tmp_path: Any) -> Iterator[OpenVpnStaticKeyManager]:
    with patch.object(
        OpenVpnStaticKeyService, "from_environment", return_value=OpenVpnStaticKeyService(client)
    ):
        yield OpenVpnStaticKeyManager(tmp_path)


def _key_row(description: str, mode: str = "crypt") -> dict[str, Any]:
    return {"description": description, "mode": {mode: {"value": mode, "selected": 1}}}


def _set_live(
    client: MagicMock,
    *,
    keys: dict[str, dict[str, Any]] | None = None,
    instances: dict[str, dict[str, Any]] | None = None,
) -> None:
    keys = keys or {}
    instances = instances or {}

    def fake(method: str, path: str, data: Any = None) -> dict[str, Any]:
        if path == "openvpn/instances/searchStaticKey":
            return {"rows": [{"uuid": u} for u in keys]}
        if path.startswith("openvpn/instances/getStaticKey/"):
            return {"statickey": keys[path.rsplit("/", 1)[1]]}
        if path == "openvpn/instances/search":
            return {"rows": [{"uuid": u} for u in instances]}
        if path.startswith("openvpn/instances/get/"):
            return {"instance": instances[path.rsplit("/", 1)[1]]}
        return {"result": "saved"}

    client.request.side_effect = fake


def _paths(client: MagicMock) -> list[str]:
    return [c.args[1] for c in client.request.call_args_list]


def _instance(role: str, key_uuid: str) -> dict[str, Any]:
    return {
        "description": "inst",
        "role": {role: {"value": role, "selected": 1}},
        "tls_key": {key_uuid: {"value": key_uuid, "selected": 1}},
    }


def test_class_markers() -> None:
    assert OpenVpnStaticKeyManager.DELETE_SCOPE == "managed_set"
    assert OpenVpnStaticKeyManager.FINALIZATION_HOOK == "openvpn_reconfigure"
    assert not getattr(OpenVpnStaticKeyManager, "SPLIT_DELETE_PHASE", False)


def test_apply_adds_with_resolved_key(manager: OpenVpnStaticKeyManager, client: MagicMock) -> None:
    _set_live(client)
    result = manager.apply("env", [_key()])
    assert result["resources_created"] == 1
    assert result["resource_outcomes"][0].address == "opnsense_openvpn_static_key.vpn-key"
    add = next(c for c in client.request.call_args_list if c.args[1].endswith("addStaticKey"))
    assert add.kwargs["data"]["statickey"]["key"] == PEM


@pytest.mark.parametrize("role", ["client", "server"])
def test_in_use_key_is_kept_and_unresolved(
    manager: OpenVpnStaticKeyManager, client: MagicMock, role: str
) -> None:
    _set_live(client, keys={"k1": _key_row("old")}, instances={"i1": _instance(role, "k1")})
    result = manager.apply("env", [], managed_resources=[_key("old")])
    assert result["resources_deleted"] == 0
    assert result["unresolved_managed"] == ["old"]
    assert any("kept" in w for w in result["warnings"])
    assert not [p for p in _paths(client) if "delStaticKey" in p]


def test_unreferenced_managed_key_is_deleted(
    manager: OpenVpnStaticKeyManager, client: MagicMock
) -> None:
    _set_live(client, keys={"k1": _key_row("old")}, instances={"i1": _instance("client", "kX")})
    result = manager.apply("env", [], managed_resources=[_key("old")])
    assert result["resources_deleted"] == 1
    assert "openvpn/instances/delStaticKey/k1" in _paths(client)


def test_instance_search_skipped_without_deletes(
    manager: OpenVpnStaticKeyManager, client: MagicMock
) -> None:
    _set_live(client, keys={"k1": _key_row("vpn-key")})
    manager.apply("env", [_key()], managed_resources=[_key()])
    assert "openvpn/instances/search" not in _paths(client)


def test_unmanaged_key_not_deleted(manager: OpenVpnStaticKeyManager, client: MagicMock) -> None:
    _set_live(client, keys={"k1": _key_row("hand")})
    result = manager.apply("env", [], managed_resources=[])
    assert result["resources_deleted"] == 0


def test_destroy_deletes_and_reconfigures(
    manager: OpenVpnStaticKeyManager, client: MagicMock
) -> None:
    _set_live(client, keys={"k1": _key_row("vpn-key")})
    result = manager.destroy("env", [_key()])
    assert result["resources_destroyed"] == 1
    assert "openvpn/service/reconfigure" in _paths(client)


def test_destroy_skips_locked_and_in_use_without_reconfigure(
    manager: OpenVpnStaticKeyManager, client: MagicMock
) -> None:
    _set_live(
        client,
        keys={"k1": _key_row("locked"), "k2": _key_row("busy")},
        instances={"i1": _instance("client", "k2")},
    )
    result = manager.destroy("env", [_key("locked", lock=True), _key("busy")])
    assert result["resources_destroyed"] == 0
    assert result["locked_skipped"] == 1
    assert any("kept" in w for w in result["warnings"])
    assert "openvpn/service/reconfigure" not in _paths(client)
    assert not [p for p in _paths(client) if "delStaticKey" in p]


def test_get_resource_ids(manager: OpenVpnStaticKeyManager, client: MagicMock) -> None:
    _set_live(client, keys={"k1": _key_row("vpn-key")})
    assert manager.get_resource_ids("env", [_key(), _key("missing")]) == {"vpn-key": "k1"}


def test_no_key_material_in_logs_warnings_or_results(
    manager: OpenVpnStaticKeyManager, client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _set_live(
        client,
        keys={"k1": _key_row("vpn-key", "auth"), "k2": _key_row("old")},
        instances={"i1": _instance("client", "k2")},
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = manager.plan("env", [_key()], managed_resources=[_key("old")])
        result = manager.apply("env", [_key()], managed_resources=[_key("old")])
    assert MATERIAL not in caplog.text
    assert MATERIAL not in repr(result)
    assert MATERIAL not in repr(plan)
    assert all(MATERIAL not in str(w.message) for w in caught)
    assert all(MATERIAL not in w for w in result["warnings"])
