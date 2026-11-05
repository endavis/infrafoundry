"""Unit tests for ``UnboundAdvancedService`` (#1254)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import endpoints
from infrafoundry.providers.opnsense.services.unbound_advanced import UnboundAdvancedService

LIVE_ADVANCED: dict[str, Any] = {
    "hideidentity": "0",
    "cacheflush": "1",
    "loglevel": {"0": {"value": "0", "selected": 0}, "2": {"value": "2", "selected": 1}},
    "privatedomain": {"a.example": {"selected": 1}, "b.example": {"selected": 1}},
    "insecuredomain": {"": {"selected": 1}},
    "privateaddress": {
        "10.0.0.0/8": {"selected": 1},
        "192.168.0.0/16": {"selected": 1},
        "172.16.0.0/12": {"selected": 0},
    },
}


def _svc() -> UnboundAdvancedService:
    return UnboundAdvancedService(MagicMock())


def _res(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="unbound.advanced", type="unbound.advanced", provider="opnsense", config=config
    )


def test_extract_live_reads_option_dicts_and_drops_empty_sentinel() -> None:
    live = _svc().extract_live(LIVE_ADVANCED)
    assert live["private_domains"] == frozenset({"a.example", "b.example"})
    assert live["insecure_domains"] == frozenset()
    assert live["private_addresses"] == frozenset({"10.0.0.0/8", "192.168.0.0/16"})


def test_extract_live_accepts_comma_string() -> None:
    live = _svc().extract_live({"privatedomain": "a.example, b.example,", "insecuredomain": ""})
    assert live["private_domains"] == frozenset({"a.example", "b.example"})
    assert live["insecure_domains"] == frozenset()


def test_build_desired_keeps_declared_keys_strips_and_dedupes() -> None:
    desired = _svc().build_desired(_res({"private_domains": [" a.example ", "a.example", ""]}))
    assert desired == {"private_domains": ["a.example"]}


def test_build_desired_rejects_unknown_key() -> None:
    with pytest.raises(InvalidConfigurationError, match="unknown"):
        _svc().build_desired(_res({"bogus": []}))


def test_build_desired_rejects_non_list() -> None:
    with pytest.raises(InvalidConfigurationError, match="list of strings"):
        _svc().build_desired(_res({"private_domains": "a.example"}))


def test_drift_none_when_sets_equal_in_any_order() -> None:
    svc = _svc()
    live = svc.extract_live(LIVE_ADVANCED)
    assert svc.drift(live, {"private_domains": ["b.example", "a.example"]}) is None


def test_drift_none_when_only_undeclared_field_differs() -> None:
    svc = _svc()
    live = svc.extract_live(LIVE_ADVANCED)
    assert svc.drift(live, {"private_domains": ["a.example", "b.example"]}) is None


def test_drift_returns_desired_on_difference() -> None:
    svc = _svc()
    live = svc.extract_live(LIVE_ADVANCED)
    desired = {"insecure_domains": ["x.example"]}
    assert svc.drift(live, desired) == desired


def test_drift_empty_list_against_empty_live_is_in_sync() -> None:
    svc = _svc()
    assert svc.drift(svc.extract_live(LIVE_ADVANCED), {"insecure_domains": []}) is None


def test_drift_empty_list_clears_populated_live() -> None:
    svc = _svc()
    assert svc.drift(svc.extract_live(LIVE_ADVANCED), {"private_domains": []}) == {
        "private_domains": []
    }


def test_build_set_payload_preserves_undeclared_fields() -> None:
    payload = _svc().build_set_payload(LIVE_ADVANCED, {"insecure_domains": ["x.example"]})
    assert list(payload) == ["unbound"]
    assert list(payload["unbound"]) == ["advanced"]
    flat = payload["unbound"]["advanced"]
    assert flat["hideidentity"] == "0"
    assert flat["cacheflush"] == "1"
    assert flat["loglevel"] == "2"
    assert flat["privatedomain"] == "a.example,b.example"
    assert flat["privateaddress"] == "10.0.0.0/8,192.168.0.0/16"
    assert flat["insecuredomain"] == "x.example"


def test_build_set_payload_flattens_none_and_scalars() -> None:
    flat = _svc().build_set_payload({"a": None, "b": 5, "c": []}, {})["unbound"]["advanced"]
    assert flat == {"a": "", "b": "5", "c": ""}


def test_get_and_set_use_the_settings_endpoints() -> None:
    svc = _svc()
    client = MagicMock()
    client.request.return_value = {"result": "saved"}
    svc.client = client
    svc.get_settings()
    client.request.assert_called_with(
        endpoints.UNBOUND_SETTINGS_GET.method, endpoints.UNBOUND_SETTINGS_GET.path()
    )
    svc.set_settings({"unbound": {"advanced": {}}})
    client.request.assert_called_with(
        endpoints.UNBOUND_SETTINGS_SET.method,
        endpoints.UNBOUND_SETTINGS_SET.path(),
        data={"unbound": {"advanced": {}}},
    )


def test_set_settings_raises_on_failed_result() -> None:
    svc = _svc()
    svc.client = MagicMock()
    svc.client.request.return_value = {"result": "failed", "validations": {"x": "bad"}}
    with pytest.raises(APIError):
        svc.set_settings({})


@pytest.mark.parametrize("response", [{}, {"unbound": {}}, {"unbound": {"advanced": []}}, None])
def test_live_advanced_raises_when_section_missing(response: Any) -> None:
    with pytest.raises(APIError):
        _svc().live_advanced(response)


def test_live_advanced_returns_section() -> None:
    assert _svc().live_advanced({"unbound": {"advanced": LIVE_ADVANCED}}) is LIVE_ADVANCED
