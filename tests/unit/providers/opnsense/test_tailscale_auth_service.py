"""Unit tests for ``TailscaleAuthService`` (#787)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.tailscale_auth import (
    KEY_PLACEHOLDER,
    MINT_DESCRIPTION,
    REDACTED,
    MintSpec,
    TailscaleAuthService,
    key_unreadable,
    parse_mint,
    redacted,
    wants_key_update,
)

SENTINEL = "tskey-auth-SENTINEL-0001"
OTHER = "tskey-auth-OTHER-0002"


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


FAKE_ID = "fake-client-id"
FAKE_CLIENT_SECRET = "tskey-client-FAKE-0003"
FAKE_KEY = "tskey-auth-FAKEKEY-0004"
TAILSCALE_CORE = "infrafoundry.providers.opnsense.services.tailscale_auth.tailscale_core"


def _mint_cfg(**overrides: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "oauth_client_id": FAKE_ID,
        "oauth_client_secret": FAKE_CLIENT_SECRET,
        "tags": ["tag:example"],
    }
    block.update(overrides)
    return {"mint": block}


def test_parse_mint_absent_is_none() -> None:
    assert parse_mint({"login_server": "https://x.example.com"}) is None


def test_parse_mint_defaults() -> None:
    spec = parse_mint(_mint_cfg())
    assert spec is not None
    assert spec.tags == ("tag:example",)
    assert spec.ephemeral is False
    assert spec.preauthorized is True
    assert spec.expiry_seconds == 3600


def test_parse_mint_overrides() -> None:
    spec = parse_mint(_mint_cfg(ephemeral=True, preauthorized=False, expiry_seconds=60))
    assert spec is not None
    assert (spec.ephemeral, spec.preauthorized, spec.expiry_seconds) == (True, False, 60)


@pytest.mark.parametrize(
    "overrides",
    [
        {"tags": []},
        {"tags": ["bad"]},
        {"ephemeral": "x"},
        {"preauthorized": 0},
        {"expiry_seconds": 0},
        {"expiry_seconds": 7776001},
        {"extra": 1},
        {"oauth_client_secret": ""},
    ],
)
def test_parse_mint_rejections_show_no_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError) as info:
        parse_mint(_mint_cfg(**overrides))
    assert FAKE_CLIENT_SECRET not in str(info.value)


@pytest.mark.parametrize("other", ["pre_auth_key", "update_pre_auth_key"])
def test_parse_mint_excludes_key_fields(other: str) -> None:
    cfg = {**_mint_cfg(), other: "x"}
    with pytest.raises(InvalidConfigurationError, match="mutually exclusive"):
        parse_mint(cfg)


def test_mint_spec_repr_hides_credentials() -> None:
    spec = parse_mint(_mint_cfg())
    assert isinstance(spec, MintSpec)
    assert FAKE_CLIENT_SECRET not in repr(spec)
    assert FAKE_ID not in repr(spec)


def test_build_desired_ignores_mint() -> None:
    service = TailscaleAuthService(MagicMock())
    resource = ResourceConfig(
        name="a", type="tailscale.auth", provider="opnsense", config=_mint_cfg()
    )
    assert service.build_desired(resource) == {}


@pytest.mark.parametrize(
    ("response", "state", "running"),
    [
        ({"BackendState": "Running"}, "Running", True),
        ({"BackendState": "NeedsLogin"}, "NeedsLogin", False),
        ({"status": {"BackendState": "Running"}}, "Running", True),
        ({}, "", False),
        ("garbage", "", False),
        ({"BackendState": 3}, "", False),
    ],
)
def test_backend_state_and_is_running(response: Any, state: str, running: bool) -> None:
    service = TailscaleAuthService(MagicMock())
    assert service.backend_state(response) == state
    service.client.request.return_value = response  # type: ignore[attr-defined]
    assert service.is_running() is running
    assert service.client.request.call_args.args[1] == "tailscale/status/status"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"settings": {"enabled": "1"}}, True),
        ({"settings": {"enabled": "0"}}, False),
        ({"settings": {}}, False),
        ({}, False),
    ],
)
def test_service_enabled(response: Any, expected: bool) -> None:
    service = TailscaleAuthService(MagicMock())
    service.client.request.return_value = response  # type: ignore[attr-defined]
    assert service.service_enabled() is expected


def test_reconfigure_posts_and_raises_on_failure() -> None:
    service = TailscaleAuthService(MagicMock())
    service.client.request.return_value = {"status": "ok"}  # type: ignore[attr-defined]
    service.reconfigure()
    assert service.client.request.call_args.args[1] == "tailscale/service/reconfigure"  # type: ignore[attr-defined]
    service.client.request.return_value = {"result": "failed"}  # type: ignore[attr-defined]
    with pytest.raises(APIError):
        service.reconfigure()


def test_mint_key_returns_key_and_passes_spec() -> None:
    service = TailscaleAuthService(MagicMock())
    spec = parse_mint(_mint_cfg(expiry_seconds=90))
    assert spec is not None
    with patch(TAILSCALE_CORE) as core:
        core.TAILSCALE_API_BASE = "https://api.example.com"
        core.request_oauth_token.return_value = "fake-token"
        core.create_auth_key.return_value = FAKE_KEY
        assert service.mint_key(spec, session=MagicMock()) == FAKE_KEY
    assert core.request_oauth_token.call_args.args[2:4] == (FAKE_ID, FAKE_CLIENT_SECRET)
    kwargs = core.create_auth_key.call_args.kwargs
    assert kwargs["tags"] == ["tag:example"]
    assert kwargs["expiry_seconds"] == 90
    assert kwargs["preauthorized"] is True


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("token request failed with HTTP 401"),
        requests.ConnectionError(f"boom {FAKE_CLIENT_SECRET} {FAKE_KEY}"),
        KeyError(FAKE_KEY),
        ValueError(FAKE_KEY),
        TypeError(FAKE_KEY),
    ],
)
def test_mint_key_wraps_errors_without_secrets(error: Exception) -> None:
    service = TailscaleAuthService(MagicMock())
    spec = parse_mint(_mint_cfg())
    assert spec is not None
    with patch(TAILSCALE_CORE) as core:
        core.TAILSCALE_API_BASE = "https://api.example.com"
        core.request_oauth_token.side_effect = error
        with pytest.raises(APIError) as info:
            service.mint_key(spec, session=MagicMock())
    text = f"{info.value} {info.value!r} {info.value.context}"
    assert FAKE_CLIENT_SECRET not in text
    assert FAKE_KEY not in text
    assert info.value.__cause__ is None


def test_mint_description_is_accepted_by_tailscale() -> None:
    """Tailscale rejects other characters or more than 50 characters (#1514)."""
    assert re.fullmatch(r"[A-Za-z0-9 -]+", MINT_DESCRIPTION)
    assert len(MINT_DESCRIPTION) <= 50
