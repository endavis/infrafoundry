"""Unit tests for ``SourceNatService`` (#1333)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.source_nat import SourceNatService

LIVE_AUTOMATIC: dict[str, Any] = {
    "filter": {
        "general": {
            "snat_mode": {
                "automatic": {"value": "Automatic", "selected": 1},
                "hybrid": {"value": "Hybrid", "selected": 0},
            }
        }
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="firewall.source_nat", type="firewall.source_nat", provider="opnsense", config=config
    )


def _service(response: Any = None) -> tuple[SourceNatService, MagicMock]:
    client = MagicMock()
    client.request.return_value = response
    return SourceNatService(client), client


def test_build_desired_rejects_unknown_key() -> None:
    svc, _ = _service()
    with pytest.raises(InvalidConfigurationError, match="unknown key"):
        svc.build_desired(_resource({"mode": "hybrid"}))


@pytest.mark.parametrize("mode", ["manual", "", 1, None])
def test_build_desired_rejects_bad_mode(mode: Any) -> None:
    svc, _ = _service()
    with pytest.raises(InvalidConfigurationError, match="snat_mode must be one of"):
        svc.build_desired(_resource({"snat_mode": mode}))


def test_disabled_goes_on_the_wire_as_disabled() -> None:
    svc, client = _service({"result": "saved"})
    desired = svc.build_desired(_resource({"snat_mode": "disabled"}))
    assert desired == {"snat_mode": "disabled"}
    svc.set_settings(desired)
    client.request.assert_called_once_with(
        "POST",
        "firewall/source_nat/set",
        data={"filter": {"general": {"snat_mode": "disabled"}}},
    )


def test_build_desired_empty_config_is_empty() -> None:
    svc, _ = _service()
    assert svc.build_desired(_resource({})) == {}


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"filter": {}},
        {"filter": {"general": {}}},
        {"filter": {"general": {"other": "x"}}},
        "garbage",
    ],
)
def test_live_general_requires_snat_mode(response: Any) -> None:
    svc, _ = _service()
    with pytest.raises(APIError, match=r"needs OPNsense 26\.1 or later"):
        svc.live_general(response)


def test_extract_live_flattens_the_option_dict() -> None:
    svc, _ = _service()
    general = svc.live_general(LIVE_AUTOMATIC)
    assert svc.extract_live(general, ["snat_mode"]) == {"snat_mode": "automatic"}


def test_drift_only_compares_declared_keys() -> None:
    svc, _ = _service()
    assert svc.drift({"snat_mode": "hybrid"}, {"snat_mode": "hybrid"}) is None
    assert svc.drift({"snat_mode": "automatic"}, {"snat_mode": "hybrid"}) == {"snat_mode": "hybrid"}
    assert svc.drift({}, {}) is None


def test_set_settings_posts_exact_payload() -> None:
    svc, client = _service({"result": "saved"})
    svc.set_settings({"snat_mode": "hybrid"})
    client.request.assert_called_once_with(
        "POST",
        "firewall/source_nat/set",
        data={"filter": {"general": {"snat_mode": "hybrid"}}},
    )


def test_set_settings_raises_on_failed() -> None:
    svc, _ = _service({"result": "failed", "validations": {"filter.general.snat_mode": "bad"}})
    with pytest.raises(APIError, match="rejected set outbound NAT mode"):
        svc.set_settings({"snat_mode": "hybrid"})


def test_apply_posts_to_apply_endpoint() -> None:
    svc, client = _service({"status": "OK"})
    assert svc.apply() == {"status": "OK"}
    client.request.assert_called_once_with("POST", "firewall/source_nat/apply")


def test_apply_raises_on_status_failed() -> None:
    svc, _ = _service({"status": "failed"})
    with pytest.raises(APIError, match="status failed"):
        svc.apply()


def test_export_to_yaml_emits_the_mode() -> None:
    import yaml

    svc, _ = _service(LIVE_AUTOMATIC)
    data = yaml.safe_load(svc.export_to_yaml())
    assert data == {"opnsense": {"firewall": {"source_nat": {"snat_mode": "automatic"}}}}
