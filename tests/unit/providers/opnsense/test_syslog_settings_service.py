"""Unit tests for ``SyslogSettingsService`` (#804)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.syslog_settings import SyslogSettingsService

GENERAL = {"enabled": "1", "loglocal": "1", "maxpreserve": "31", "maxfilesize": "10"}
LIVE = {"syslog": {"general": GENERAL, "destinations": {"rows": []}}}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="syslog.settings", type="syslog.settings", provider="opnsense", config=config
    )


def _service() -> SyslogSettingsService:
    service = SyslogSettingsService(MagicMock())
    service.client = MagicMock()
    return service


def test_build_desired_types() -> None:
    desired = _service().build_desired(
        _resource({"enabled": False, "log_local": True, "max_preserve": 5, "max_file_size": 0})
    )
    assert desired == {
        "enabled": "0",
        "log_local": "1",
        "max_preserve": "5",
        "max_file_size": "0",
    }


def test_build_desired_empty_is_sparse() -> None:
    assert _service().build_desired(_resource({})) == {}


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": 1},
        {"enabled": 1},
        {"log_local": "yes"},
        {"max_preserve": True},
        {"max_preserve": -1},
        {"max_file_size": "10"},
    ],
)
def test_build_desired_rejects_bad_input(config: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError):
        _service().build_desired(_resource(config))


@pytest.mark.parametrize("response", [None, {}, {"syslog": {}}, {"syslog": {"general": []}}])
def test_live_general_requires_envelope(response: Any) -> None:
    with pytest.raises(APIError):
        _service().live_general(response)


def test_live_general_returns_general() -> None:
    assert _service().live_general(LIVE) == GENERAL


def test_extract_live_and_missing_field() -> None:
    service = _service()
    assert service.extract_live(GENERAL, ["enabled", "max_file_size"]) == {
        "enabled": "1",
        "max_file_size": "10",
    }
    with pytest.raises(APIError):
        service.extract_live({"enabled": "1"}, ["max_preserve"])


def test_drift() -> None:
    service = _service()
    assert service.drift({"enabled": "1"}, {"enabled": "1"}) is None
    assert service.drift({"enabled": "1"}, {"enabled": "0"}) == {"enabled": "0"}


def test_build_set_payload_envelope_omits_destinations() -> None:
    payload = _service().build_set_payload({**GENERAL, "destinations": {"x": 1}}, {"enabled": "0"})
    assert payload == {"syslog": {"general": {**GENERAL, "enabled": "0"}}}


def test_get_set_reconfigure_use_endpoints() -> None:
    service = _service()
    service.client.request.return_value = {"result": "saved"}  # type: ignore[attr-defined]
    service.get_settings()
    service.set_settings({"syslog": {}})
    service.reconfigure()
    calls = service.client.request.call_args_list  # type: ignore[attr-defined]
    assert [c.args for c in calls] == [
        ("GET", "syslog/settings/get"),
        ("POST", "syslog/settings/set"),
        ("POST", "syslog/service/reconfigure"),
    ]


def test_set_failure_raises() -> None:
    service = _service()
    service.client.request.return_value = {"result": "failed"}  # type: ignore[attr-defined]
    with pytest.raises(APIError):
        service.set_settings({})
