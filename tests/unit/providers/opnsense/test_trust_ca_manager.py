"""Unit tests for ``TrustCaManager`` (#807)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.trust_ca import TrustCaManager
from infrafoundry.providers.opnsense.services.trust import TrustService
from infrafoundry.secrets.resolver import SecretResolutionError

CRT = "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE" + " KEY-----\nFAKEKEY\n-----END PRIVATE" + " KEY-----"
MOD = "infrafoundry.providers.opnsense.components.trust_ca"


def _res(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("crt", CRT)
    return ResourceConfig(name=name, type="trust.cas", provider="opnsense", config=config)


def _row(descr: str, **kw: Any) -> dict[str, Any]:
    return {"uuid": f"u-{descr}", "refid": f"r-{descr}", "descr": descr, "crt_payload": CRT, **kw}


@pytest.fixture(autouse=True)
def _no_secret_lookup() -> Iterator[None]:
    """Treat resource configs as already resolved (no ConfigManager in unit tests)."""
    with patch(
        "infrafoundry.providers.opnsense.components.trust_ca.resolve_resource_secrets",
        side_effect=lambda _d, _e, resources, _t: resources,
    ):
        yield


@pytest.fixture
def client() -> MagicMock:
    c = MagicMock()
    c.request.return_value = {"rows": [], "result": "saved"}
    return c


@pytest.fixture
def manager(client: MagicMock, tmp_path: Any) -> Iterator[TrustCaManager]:
    with patch.object(TrustService, "from_environment", return_value=TrustService(client)):
        yield TrustCaManager(tmp_path)


def _set_rows(client: MagicMock, rows: list[dict[str, Any]]) -> None:
    client.request.side_effect = lambda method, path, data=None: (
        {"rows": rows} if path.endswith("/search") else {"result": "saved"}
    )


def _writes(client: MagicMock) -> list[str]:
    return [c.args[1] for c in client.request.call_args_list if not c.args[1].endswith("/search")]


def test_plan_add(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(client, [])
    diff = manager.plan("dev", [_res("vpn-ca")])
    assert [c.name for c in diff.adds] == ["vpn-ca"]
    assert _writes(client) == []


def test_apply_add_update_delete(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(
        client,
        [
            _row("chg", crt_payload="-----BEGIN CERTIFICATE-----\nOLD\n-----END CERTIFICATE-----"),
            _row("gone"),
        ],
    )
    result = manager.apply(
        "dev",
        [_res("new"), _res("chg")],
        managed_resources=[_res("gone")],
    )
    assert (
        result["resources_created"],
        result["resources_updated"],
        result["resources_deleted"],
    ) == (1, 1, 1)
    assert {o.action for o in result["resource_outcomes"]} == {"add", "update", "delete"}
    assert _writes(client) == ["trust/ca/add", "trust/ca/set/u-chg", "trust/ca/del/u-gone"]


def test_unmanaged_kept(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(client, [_row("other")])
    result = manager.apply("dev", [_res("a")], managed_resources=[])
    assert result["resources_deleted"] == 0


def test_blocked_reported_unresolved(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(client, [_row("busy", in_use="1"), _row("R10")])
    result = manager.apply(
        "dev",
        [_res("a")],
        managed_resources=[_res("busy"), _res("R10")],
    )
    assert result["resources_deleted"] == 0
    assert result["unresolved_managed"] == ["R10", "busy"]
    assert len(result["warnings"]) == 2


def test_destroy_skips_locked_and_in_use(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(client, [_row("a"), _row("locked"), _row("busy", in_use="1")])
    result = manager.destroy("dev", [_res("a"), _res("locked", lock=True), _res("busy")])
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    assert _writes(client) == ["trust/ca/del/u-a"]


def test_get_resource_ids(manager: TrustCaManager, client: MagicMock) -> None:
    _set_rows(client, [_row("vpn.example.com CA")])
    ids = manager.get_resource_ids(
        "dev", [_res("vpn-ca", description="vpn.example.com CA"), _res("absent")]
    )
    assert ids == {"vpn-ca": "u-vpn.example.com CA"}


def test_secrets_resolved_and_sent(client: MagicMock, tmp_path: Any) -> None:
    _set_rows(client, [])
    res = _res("vpn-ca", crt="secret://env_secrets/ca/crt", prv="secret://env_secrets/ca/prv")

    def fake_resolve(
        config_dir: Any, env: str, resources: list[ResourceConfig], rtype: str
    ) -> list[ResourceConfig]:
        return [_res("vpn-ca", crt=CRT, prv=KEY)]

    with (
        patch.object(TrustService, "from_environment", return_value=TrustService(client)),
        patch(f"{MOD}.resolve_resource_secrets", side_effect=fake_resolve),
    ):
        TrustCaManager(tmp_path).apply("dev", [res])
    sent = next(c for c in client.request.call_args_list if c.args[1] == "trust/ca/add")
    assert sent.kwargs["data"]["ca"]["prv_payload"] == KEY


def test_missing_secret_error(client: MagicMock, tmp_path: Any) -> None:
    with (
        patch.object(TrustService, "from_environment", return_value=TrustService(client)),
        patch(f"{MOD}.resolve_resource_secrets", side_effect=SecretResolutionError("missing path")),
        pytest.raises(SecretResolutionError),
    ):
        TrustCaManager(tmp_path).plan("dev", [_res("vpn-ca")])
    client.request.assert_not_called()


def test_no_pem_in_logs(
    manager: TrustCaManager, client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    _set_rows(client, [_row("gone")])
    with caplog.at_level(logging.DEBUG):
        manager.apply("dev", [_res("a", prv=KEY)], managed_resources=[_res("gone")])
    assert "FAKEKEY" not in caplog.text
    assert "BEGIN" not in caplog.text


def test_non_pem_after_resolution_raises(manager: TrustCaManager) -> None:
    with pytest.raises(ValueError, match="vpn-ca"):
        manager.plan("dev", [_res("vpn-ca", crt="garbage")])


def test_resolve_resource_secrets_uses_env_secrets() -> None:
    import contextlib
    from pathlib import Path

    from infrafoundry.core.plugin_system import get_registry
    from infrafoundry.core.plugin_system.exceptions import PluginConflictError
    from infrafoundry.core.plugin_system.plugin_type import PluginMetadata
    from infrafoundry.providers.opnsense.components._secrets import resolve_resource_secrets
    from infrafoundry.secrets.backends.env_secrets import EnvSecretsBackend

    with contextlib.suppress(PluginConflictError):
        get_registry().register(
            PluginMetadata(
                name="env_secrets",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretsBackend,
            )
        )

    env_config = MagicMock()
    env_config.secrets = {"ca": {"crt": CRT, "prv": KEY}}
    other = ResourceConfig(name="o", type="trust.certs", provider="opnsense", config={"crt": "x"})
    res = _res("vpn-ca", crt="secret://env_secrets/ca/crt", prv="secret://env_secrets/ca/prv")
    with patch("infrafoundry.providers.opnsense.components._secrets.ConfigManager") as cm:
        cm.return_value.load_environment.return_value = env_config
        out = resolve_resource_secrets(Path("."), "dev", [res, other], "trust.cas")
    assert out[0].config == {"crt": CRT, "prv": KEY}
    assert out[1] is other
