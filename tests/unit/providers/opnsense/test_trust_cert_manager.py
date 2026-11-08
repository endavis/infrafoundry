"""Unit tests for ``TrustCertManager`` (#807)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.trust_cert import TrustCertManager
from infrafoundry.providers.opnsense.services.trust import TrustService

CRT = "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE" + " KEY-----\nFAKEKEY\n-----END PRIVATE" + " KEY-----"


def _cert(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("crt", CRT)
    return ResourceConfig(name=name, type="trust.certs", provider="opnsense", config=config)


def _ca(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("crt", CRT)
    return ResourceConfig(name=name, type="trust.cas", provider="opnsense", config=config)


def _row(descr: str, **kw: Any) -> dict[str, Any]:
    return {"uuid": f"u-{descr}", "refid": f"r-{descr}", "descr": descr, "crt_payload": CRT, **kw}


@pytest.fixture(autouse=True)
def _no_secret_lookup() -> Iterator[None]:
    """Treat resource configs as already resolved (no ConfigManager in unit tests)."""
    with patch(
        "infrafoundry.providers.opnsense.components.trust_cert.resolve_resource_secrets",
        side_effect=lambda _d, _e, resources, _t: resources,
    ):
        yield


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager(client: MagicMock, tmp_path: Any) -> Iterator[TrustCertManager]:
    with patch.object(TrustService, "from_environment", return_value=TrustService(client)):
        yield TrustCertManager(tmp_path)


def _set_rows(client: MagicMock, *, cas: list[dict[str, Any]], certs: list[dict[str, Any]]) -> None:
    def fake(method: str, path: str, data: Any = None) -> dict[str, Any]:
        if path == "trust/ca/search":
            return {"rows": cas}
        if path == "trust/cert/search":
            return {"rows": certs}
        return {"result": "saved"}

    client.request.side_effect = fake


def _writes(client: MagicMock) -> list[Any]:
    return [c for c in client.request.call_args_list if not c.args[1].endswith("/search")]


def test_class_markers() -> None:
    assert TrustCertManager.SIBLING_RESOURCE_TYPE == "trust.cas"
    assert TrustCertManager.SPLIT_DELETE_PHASE is True
    assert TrustCertManager.DELETE_SCOPE == "managed_set"
    assert not hasattr(TrustCertManager, "FINALIZATION_HOOK")


def test_ca_ref_resolves_to_refid(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[_row("vpn.example.com CA")], certs=[])
    result = manager.apply(
        "dev",
        [_cert("web-cert", ca_ref="vpn-ca")],
        sibling_resources=[_ca("vpn-ca", description="vpn.example.com CA")],
    )
    assert result["resources_created"] == 1
    body = _writes(client)[0].kwargs["data"]["cert"]
    assert body["caref"] == "r-vpn.example.com CA"


def test_pending_ca_warns_at_plan(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[], certs=[])
    diff = manager.plan(
        "dev", [_cert("web-cert", ca_ref="vpn-ca")], sibling_resources=[_ca("vpn-ca")]
    )
    assert len(diff.adds) == 1
    assert any("not on the box yet" in w for w in diff.warnings)


def test_unresolved_ca_ref_raises_at_apply(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[], certs=[])
    with pytest.raises(ReferenceValidationError):
        manager.apply(
            "dev", [_cert("web-cert", ca_ref="vpn-ca")], sibling_resources=[_ca("vpn-ca")]
        )
    assert _writes(client) == []


def test_managed_sibling_resolves_ref(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[_row("vpn-ca")], certs=[])
    diff = manager.plan(
        "dev",
        [_cert("web-cert", ca_ref="vpn-ca")],
        managed_sibling_resources=[_ca("vpn-ca")],
    )
    assert not diff.warnings


def test_deletes_only(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[], certs=[_row("gone"), _row("web-cert")])
    result = manager.apply(
        "dev",
        [_cert("new", ca_ref="vpn-ca"), _cert("web-cert")],
        deletes_only=True,
        managed_resources=[_cert("gone")],
        sibling_resources=[_ca("vpn-ca")],
    )
    assert (result["resources_created"], result["resources_updated"]) == (0, 0)
    assert result["resources_deleted"] == 1
    assert [c.args[1] for c in _writes(client)] == ["trust/cert/del/u-gone"]


def test_in_use_cert_blocked(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[], certs=[_row("busy", in_use="1")])
    result = manager.apply("dev", [_cert("x")], managed_resources=[_cert("busy")])
    assert result["resources_deleted"] == 0
    assert result["unresolved_managed"] == ["busy"]


def test_destroy_and_ids(manager: TrustCertManager, client: MagicMock) -> None:
    _set_rows(client, cas=[], certs=[_row("a"), _row("b")])
    result = manager.destroy("dev", [_cert("a"), _cert("b", lock=True)], sibling_resources=[])
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    assert manager.get_resource_ids("dev", [_cert("a"), _cert("zz")]) == {"a": "u-a"}


def test_no_key_material_in_logs(
    manager: TrustCertManager, client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    _set_rows(client, cas=[], certs=[_row("gone")])
    with caplog.at_level(logging.DEBUG):
        manager.apply("dev", [_cert("a", prv=KEY)], managed_resources=[_cert("gone")])
    assert "FAKEKEY" not in caplog.text
