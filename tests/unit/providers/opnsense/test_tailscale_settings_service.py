"""Unit tests for ``TailscaleSettingsService`` (#787)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.tailscale_settings import (
    TailscaleSettingsService,
    serialize_setting,
)


def _live(**overrides: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "enabled": "0",
        "loginTimeout": "10",
        "listenPort": "41641",
        "acceptDNS": "1",
        "advertiseExitNode": "0",
        "useExitNode": {"": {"value": "None", "selected": 1}},
        "acceptSubnetRoutes": "0",
        "enableSSH": "0",
        "disableSNAT": "0",
        "subnets": {"subnet4": []},
    }
    settings.update(overrides)
    return {"settings": settings}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.settings", type="tailscale.settings", provider="opnsense", config=config
    )


def _service(response: Any = None) -> TailscaleSettingsService:
    client = MagicMock()
    client.request.return_value = response if response is not None else _live()
    return TailscaleSettingsService(client)


def test_enable_snat_inverts_both_ways() -> None:
    assert serialize_setting("enable_snat", True) == "0"
    assert serialize_setting("enable_snat", False) == "1"
    assert serialize_setting("enabled", True) == "1"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("enabled", "yes"),
        ("listen_port", 70000),
        ("listen_port", -1),
        ("listen_port", True),
        ("login_timeout", -5),
        ("login_timeout", "5"),
        ("use_exit_node", 3),
    ],
)
def test_serialize_rejects_bad_values(key: str, value: Any) -> None:
    with pytest.raises(InvalidConfigurationError):
        serialize_setting(key, value)


def test_port_zero_accepted() -> None:
    assert serialize_setting("listen_port", 0) == "0"


@pytest.mark.parametrize("key", ["subnets", "disable_snat", "hostname", "exit_node", "bogus"])
def test_build_desired_rejects_unknown_and_refused(key: str) -> None:
    with pytest.raises(InvalidConfigurationError, match=key):
        _service().build_desired(_resource(**{key: 1}))


def test_extract_live_flattens_exit_node_option_dict() -> None:
    svc = _service()
    settings = svc.live_settings(_live(useExitNode={"": {"selected": 0}, "peer": {"selected": 1}}))
    assert svc.extract_live(settings, ["use_exit_node"]) == {"use_exit_node": "peer"}
    only_empty = svc.live_settings(_live())
    assert svc.extract_live(only_empty, ["use_exit_node"]) == {"use_exit_node": ""}


def test_extract_live_keeps_inverted_wire_value() -> None:
    svc = _service()
    settings = svc.live_settings(_live(disableSNAT="1"))
    assert svc.extract_live(settings, ["enable_snat"]) == {"enable_snat": "1"}


def test_extract_live_missing_field_raises() -> None:
    svc = _service()
    with pytest.raises(APIError):
        svc.extract_live({"enabled": "1"}, ["listen_port"])


def test_build_set_payload_omits_subnets_and_echoes_rest() -> None:
    svc = _service()
    settings = svc.live_settings(_live())
    payload = svc.build_set_payload(settings, {"listen_port": "5000", "enable_snat": "1"})
    body = payload["settings"]
    assert "subnets" not in body
    assert body["listenPort"] == "5000"
    assert body["disableSNAT"] == "1"
    assert body["acceptDNS"] == "1"
    assert body["useExitNode"] == ""


def test_exit_node_offers() -> None:
    svc = _service()
    assert svc.exit_node_offers({"useExitNode": {"": {}, "peer": {}}}) == {"", "peer"}
    assert svc.exit_node_offers({}) == {""}


def test_live_settings_missing_envelope_raises_without_body() -> None:
    with pytest.raises(APIError) as exc:
        _service().live_settings({"other": {"x": "SENTINEL"}})
    assert "SENTINEL" not in str(exc.value)
    assert "SENTINEL" not in str(exc.value.response)


def test_drift() -> None:
    svc = _service()
    assert svc.drift({"enabled": "0"}, {"enabled": "0"}) is None
    assert svc.drift({"enabled": "0"}, {"enabled": "1"}) == {"enabled": "1"}


def test_set_settings_raises_on_failed_write() -> None:
    svc = _service({"result": "failed", "validations": {"x": "bad"}})
    with pytest.raises(APIError):
        svc.set_settings({"settings": {}})


def test_reconfigure_posts() -> None:
    svc = _service({"status": "ok"})
    svc.reconfigure()
    args = svc.client.request.call_args  # type: ignore[attr-defined]
    assert args.args[0] == "POST"
    assert args.args[1] == "tailscale/service/reconfigure"


def test_export_yaml_inverts_and_has_no_subnets(tmp_path: Path) -> None:
    svc = _service(_live(disableSNAT="1", enabled="1"))
    text = svc.export_to_yaml()
    assert "subnets" not in text
    data = yaml.safe_load(text)["opnsense"]["tailscale"]["settings"]
    assert data["enable_snat"] is False
    assert data["enabled"] is True
    assert data["listen_port"] == 41641
    assert data["use_exit_node"] == ""
    resources = PackageLoader(tmp_path)._parse_nested_provider_format(
        yaml.safe_load(text)["opnsense"], "opnsense", "s.yaml"
    )
    assert [(r.name, r.type) for r in resources] == [("tailscale.settings", "tailscale.settings")]
