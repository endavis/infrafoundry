"""Unit tests for ``HostDiscoveryService`` (#792)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import endpoints
from infrafoundry.providers.opnsense.services.hostdiscovery import (
    FIELD_MAP,
    HostDiscoveryService,
    _flatten,
)


def _live(**overrides: Any) -> dict[str, Any]:
    general: dict[str, Any] = {
        "enabled": "1",
        "promisc": "0",
        "verbose": "0",
        "skip_nets": "",
        "interface": {
            "lan": {"value": "LAN", "selected": 1},
            "opt1": {"value": "OPT1", "selected": 0},
        },
        "expire4_interval": "3600",
        "expire6_interval": "7200",
    }
    general.update(overrides)
    return general


def _svc(response: Any = None) -> HostDiscoveryService:
    service = HostDiscoveryService(MagicMock())
    service.client = MagicMock()
    service.client.request.return_value = response
    return service


def _req(svc: HostDiscoveryService) -> MagicMock:
    mock: MagicMock = svc.client.request  # type: ignore[assignment]
    return mock


def _res(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="hostdiscovery", type="hostdiscovery", provider="opnsense", config=config
    )


def test_field_map_keys() -> None:
    assert set(FIELD_MAP) == {
        "enabled",
        "promisc",
        "verbose",
        "skip_nets",
        "interface",
        "expire4_interval",
        "expire6_interval",
    }


def test_flatten_variants() -> None:
    assert _flatten({"a": {"selected": 1}, "b": {"selected": 0}}) == "a"
    assert _flatten([{"selected": 0}, {"selected": 1}]) == "1"
    assert _flatten(None) == ""
    assert _flatten([]) == ""
    assert _flatten("x") == "x"
    assert _flatten(5) == "5"


def test_build_desired_conversions() -> None:
    desired = _svc().build_desired(
        _res(
            {
                "enabled": True,
                "promisc": False,
                "skip_nets": ["192.0.2.0/24", "2001:db8::/32"],
                "interface": ["lan"],
                "expire4_interval": 60,
            }
        )
    )
    assert desired == {
        "enabled": "1",
        "promisc": "0",
        "skip_nets": ["192.0.2.0/24", "2001:db8::/32"],
        "interface": ["lan"],
        "expire4_interval": "60",
    }


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"bogus": 1}, "unknown key"),
        ({"enabled": "yes"}, "enabled must be a boolean"),
        ({"expire4_interval": -1}, "non-negative integer"),
        ({"expire6_interval": True}, "non-negative integer"),
        ({"skip_nets": "192.0.2.0/24"}, "list of strings"),
        ({"skip_nets": ["not-a-cidr"]}, "not a valid CIDR"),
        ({"interface": ["a,b"]}, "no comma"),
        ({"interface": [""]}, "non-empty"),
    ],
)
def test_build_desired_rejections(config: dict[str, Any], needle: str) -> None:
    with pytest.raises(InvalidConfigurationError, match=needle):
        _svc().build_desired(_res(config))


def test_live_general_missing_envelope_raises() -> None:
    with pytest.raises(APIError, match=r"no hostdiscovery\.general"):
        _svc().live_general({"hostdiscovery": {}})
    with pytest.raises(APIError):
        _svc().live_general(None)


def test_extract_live_flattens_multiselect() -> None:
    live = _svc().extract_live(_live(), list(FIELD_MAP))
    assert live["interface"] == frozenset({"lan"})
    assert live["skip_nets"] == frozenset()
    assert live["enabled"] == "1"
    assert live["expire6_interval"] == "7200"


def test_extract_live_missing_key_raises() -> None:
    general = _live()
    del general["promisc"]
    with pytest.raises(APIError, match="no 'promisc' field"):
        _svc().extract_live(general, ["promisc"])


def test_drift_sets_and_scalars() -> None:
    svc = _svc()
    live = svc.extract_live(_live(skip_nets="192.0.2.0/24,198.51.100.0/24"), list(FIELD_MAP))
    same = {"skip_nets": ["198.51.100.0/24", "192.0.2.0/24"], "enabled": "1"}
    assert svc.drift(live, same) is None
    other = {"skip_nets": ["192.0.2.0/24"]}
    assert svc.drift(live, other) == other
    assert svc.drift(live, {"enabled": "0"}) == {"enabled": "0"}


def test_build_set_payload_envelope() -> None:
    payload = _svc().build_set_payload(
        _live(), {"enabled": "0", "interface": ["lan", "opt1"], "skip_nets": []}
    )
    general = payload["hostdiscovery"]["general"]
    assert general["enabled"] == "0"
    assert general["interface"] == "lan,opt1"
    assert general["skip_nets"] == ""
    assert general["expire4_interval"] == "3600"


def test_get_and_set_use_endpoints() -> None:
    svc = _svc({"result": "saved"})
    svc.get_settings()
    svc.set_settings({"hostdiscovery": {"general": {}}})
    calls = _req(svc).call_args_list
    assert calls[0].args == ("GET", endpoints.HOSTDISCOVERY_SETTINGS_GET.path())
    assert calls[1].args == ("POST", endpoints.HOSTDISCOVERY_SETTINGS_SET.path())
    assert calls[1].kwargs["data"] == {"hostdiscovery": {"general": {}}}


def test_set_failed_raises() -> None:
    with pytest.raises(APIError, match="rejected set host discovery"):
        _svc({"result": "failed", "validations": {"x": "bad"}}).set_settings({})


def test_reconfigure_ok_and_failures() -> None:
    svc = _svc({"status": "ok"})
    assert svc.reconfigure() == {"status": "ok"}
    assert _req(svc).call_args.args == ("POST", endpoints.HOSTDISCOVERY_RECONFIGURE.path())
    with pytest.raises(APIError):
        _svc({"status": "failed"}).reconfigure()
    with pytest.raises(APIError):
        _svc({"result": "failed"}).reconfigure()


def test_export_to_yaml() -> None:
    text = _svc({"hostdiscovery": {"general": _live(skip_nets="192.0.2.0/24")}}).export_to_yaml()
    assert yaml.safe_load(text)["opnsense"]["hostdiscovery"] == {
        "enabled": True,
        "promisc": False,
        "verbose": False,
        "skip_nets": ["192.0.2.0/24"],
        "interface": ["lan"],
        "expire4_interval": 3600,
        "expire6_interval": 7200,
    }
