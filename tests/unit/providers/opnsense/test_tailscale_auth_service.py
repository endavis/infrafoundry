"""Unit tests for ``TailscaleAuthService`` (#787)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.tailscale_auth import (
    KEY_PLACEHOLDER,
    REDACTED,
    TailscaleAuthService,
    key_unreadable,
    redacted,
    wants_key_update,
)

SENTINEL = "tskey-auth-SENTINEL-0001"  # nosec B105
OTHER = "tskey-auth-OTHER-0002"  # nosec B105


def _live(key: str = "", server: str = "https://controlplane.example.com") -> dict[str, Any]:
    return {"loginServer": server, "preAuthKey": key}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.auth", type="tailscale.auth", provider="opnsense", config=config
    )


def _service(response: Any = None) -> TailscaleAuthService:
    client = MagicMock()
    client.request.return_value = response
    return TailscaleAuthService(client)


def test_build_desired_and_flag() -> None:
    svc = _service()
    res = _resource(login_server="https://a.example.com", pre_auth_key=SENTINEL)
    assert svc.build_desired(res) == {
        "login_server": "https://a.example.com",
        "pre_auth_key": SENTINEL,
    }
    assert wants_key_update(_resource(update_pre_auth_key=True))
    assert not wants_key_update(_resource())


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": 1},
        {"update_pre_auth_key": "yes"},
        {"login_server": 5},
        {"pre_auth_key": "  "},
    ],
)
def test_build_desired_rejects_bad_config(config: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError):
        _service().build_desired(_resource(**config))


def test_changed_fields_readable_equal_and_different() -> None:
    svc = _service()
    desired = {"pre_auth_key": SENTINEL}
    assert svc.changed_fields(_live(SENTINEL), desired, False) == []
    assert svc.changed_fields(_live(f" {SENTINEL} "), desired, False) == []
    assert svc.changed_fields(_live(OTHER), desired, False) == ["pre_auth_key"]


def test_changed_fields_unreadable_needs_flag() -> None:
    svc = _service()
    desired = {"pre_auth_key": SENTINEL}
    assert svc.changed_fields(_live(""), desired, False) == []
    assert svc.changed_fields(_live("********"), desired, False) == []
    assert svc.changed_fields(_live(""), desired, True) == ["pre_auth_key"]


def test_flag_with_equal_readable_key_counts_as_change() -> None:
    assert _service().changed_fields(_live(SENTINEL), {"pre_auth_key": SENTINEL}, True) == [
        "pre_auth_key"
    ]


def test_login_server_change_and_names_only() -> None:
    svc = _service()
    desired = {"login_server": "https://b.example.com", "pre_auth_key": SENTINEL}
    changed = svc.changed_fields(_live(OTHER), desired, False)
    assert changed == ["login_server", "pre_auth_key"]
    assert SENTINEL not in " ".join(changed)


def test_payload_never_echoes_live_key() -> None:
    svc = _service()
    payload = svc.build_set_payload(
        _live(OTHER), {"login_server": "https://b.example.com", "pre_auth_key": SENTINEL}, False
    )
    assert payload == {"authentication": {"loginServer": "https://b.example.com"}}
    assert OTHER not in str(payload)
    assert SENTINEL not in str(payload)


def test_payload_with_empty_live_and_login_only_has_no_key() -> None:
    payload = _service().build_set_payload(
        _live(""), {"login_server": "https://b.example.com"}, False
    )
    assert "preAuthKey" not in payload["authentication"]


def test_payload_sends_key_when_asked() -> None:
    payload = _service().build_set_payload(_live(""), {"pre_auth_key": SENTINEL}, True)
    assert payload["authentication"]["preAuthKey"] == SENTINEL
    assert payload["authentication"]["loginServer"] == "https://controlplane.example.com"


def test_redacted_and_unreadable() -> None:
    assert redacted({"login_server": "x", "pre_auth_key": SENTINEL}) == {
        "login_server": "x",
        "pre_auth_key": REDACTED,
    }
    assert key_unreadable(_live(""))
    assert key_unreadable(_live("****"))
    assert not key_unreadable(_live(SENTINEL))


def test_live_auth_missing_envelope_keys_only() -> None:
    with pytest.raises(APIError) as exc:
        _service().live_auth({"preAuthKey": SENTINEL})
    assert SENTINEL not in str(exc.value)
    assert SENTINEL not in str(exc.value.response)


def test_set_auth_failed_write_raises() -> None:
    svc = _service({"result": "failed", "validations": {"loginServer": "bad"}})
    with pytest.raises(APIError):
        svc.set_auth({"authentication": {}})


def test_export_placeholder_only_with_live_key(tmp_path: Path) -> None:
    with_key = _service({"authentication": _live(SENTINEL)}).export_to_yaml()
    assert SENTINEL not in with_key
    data = yaml.safe_load(with_key)["opnsense"]["tailscale"]["auth"]
    assert data == {
        "login_server": "https://controlplane.example.com",
        "pre_auth_key": KEY_PLACEHOLDER,
    }
    resources = PackageLoader(tmp_path)._parse_nested_provider_format(
        yaml.safe_load(with_key)["opnsense"], "opnsense", "a.yaml"
    )
    assert [r.type for r in resources] == ["tailscale.auth"]
    without = yaml.safe_load(_service({"authentication": _live("")}).export_to_yaml())
    assert "pre_auth_key" not in without["opnsense"]["tailscale"]["auth"]
