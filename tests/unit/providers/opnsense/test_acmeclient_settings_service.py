"""Unit tests for ``AcmeClientSettingsService`` (#790)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.acmeclient_settings import (
    FIELD_MAP,
    AcmeClientSettingsService,
)

CRON_UUID = "11111111-2222-3333-4444-555555555555"

LIVE_SETTINGS: dict[str, Any] = {
    "enabled": "1",
    "autoRenewal": "1",
    "UpdateCron": {
        "": {"value": "None", "selected": 0},
        CRON_UUID: {"value": "acme cron", "selected": 1},
    },
    "environment": {"": {"value": "", "selected": 0}, "prod": {"value": "Prod", "selected": 1}},
    "challengePort": "43580",
    "TLSchallengePort": "43581",
    "restartTimeout": "300",
    "haproxyIntegration": "0",
    "haproxyAclRef": "",
    "haproxyActionRef": "",
    "haproxyServerRef": "",
    "haproxyBackendRef": "",
    "logLevel": {"normal": {"value": "Normal", "selected": 1}, "debug": {"selected": 0}},
    "showIntro": "0",
}
LIVE = {"acmeclient": {"settings": LIVE_SETTINGS, "accounts": {"account": []}}}


def _service() -> AcmeClientSettingsService:
    return AcmeClientSettingsService(MagicMock())


def _res(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="acmeclient.settings", type="acmeclient.settings", provider="opnsense", config=config
    )


def test_build_desired_serializes_declared_keys_only() -> None:
    desired = _service().build_desired(
        _res(enabled=True, challenge_port=8080, log_level="debug", environment="")
    )
    assert desired == {
        "enabled": "1",
        "challenge_port": "8080",
        "log_level": "debug",
        "environment": "",
    }


@pytest.mark.parametrize(
    "config",
    [
        {"enabled": "yes"},
        {"environment": "dev"},
        {"log_level": "loud"},
        {"challenge_port": 0},
        {"tls_challenge_port": 70000},
        {"restart_timeout": -1},
        {"restart_timeout": True},
        {"haproxy_acl_ref": 1},
        {"bogus": 1},
    ],
)
def test_build_desired_rejects_bad_values(config: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError):
        _service().build_desired(_res(**config))


def test_update_cron_is_not_a_yaml_key() -> None:
    assert "update_cron" not in FIELD_MAP
    with pytest.raises(InvalidConfigurationError, match="managed by the plugin"):
        _service().build_desired(_res(update_cron="x"))


def test_drift_is_sparse() -> None:
    service = _service()
    settings = service.live_settings(LIVE)
    desired = service.build_desired(_res(enabled=True))
    assert service.drift(service.extract_live(settings, desired), desired) is None
    desired = service.build_desired(_res(enabled=True, log_level="debug"))
    assert service.drift(service.extract_live(settings, desired), desired) == desired


def test_extract_live_flattens_option_dicts() -> None:
    live = _service().extract_live(LIVE_SETTINGS, ["environment", "log_level"])
    assert live == {"environment": "prod", "log_level": "normal"}


def test_extract_live_missing_field_is_an_error() -> None:
    with pytest.raises(APIError, match="enabled"):
        _service().extract_live({}, ["enabled"])


def test_live_settings_requires_the_envelope() -> None:
    with pytest.raises(APIError):
        _service().live_settings({"acmeclient": {}})


def test_write_body_echoes_whole_live_settings_with_update_cron_unchanged() -> None:
    service = _service()
    payload = service.build_set_payload(LIVE_SETTINGS, {"log_level": "debug"})
    flat = payload["acmeclient"]["settings"]
    assert flat["logLevel"] == "debug"
    assert flat["UpdateCron"] == CRON_UUID
    assert flat["challengePort"] == "43580"
    assert set(payload["acmeclient"]) == {"settings"}
    assert service.renewal_effective(payload)
    off = service.build_set_payload(LIVE_SETTINGS, {"auto_renewal": "0"})
    assert not service.renewal_effective(off)


def test_export_to_yaml_round_trips_through_the_loader(tmp_path: Any) -> None:
    service = _service()
    service.client.request.return_value = LIVE  # type: ignore[attr-defined]
    text = service.export_to_yaml()
    data = yaml.safe_load(text)
    config = data["opnsense"]["acmeclient"]["settings"]
    assert config["enabled"] is True
    assert config["environment"] == "prod"
    assert config["challenge_port"] == 43580
    assert "haproxy_acl_ref" not in config  # empty refs omitted
    assert "update_cron" not in config
    resources = PackageLoader(tmp_path)._parse_resources_from_data(data, "x.yaml", "opnsense")
    (found,) = [r for r in resources if r.type == "acmeclient.settings"]
    assert service.build_desired(found)["environment"] == "prod"


def test_service_calls_use_the_registered_endpoints() -> None:
    service = _service()
    client: MagicMock = service.client  # type: ignore[assignment]
    client.request.return_value = {"result": "saved"}
    service.set_settings({"acmeclient": {"settings": {}}})
    service.fetch_cron_integration()
    service.reconfigure()
    assert [(c.args[0], c.args[1]) for c in client.request.call_args_list] == [
        ("POST", "acmeclient/settings/set"),
        ("POST", "acmeclient/settings/fetchCronIntegration"),
        ("POST", "acmeclient/service/reconfigure"),
    ]
    client.request.return_value = {"result": "failed"}
    with pytest.raises(APIError):
        service.reconfigure()
