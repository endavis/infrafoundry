"""Unit tests for ``UnboundSettingsManager`` (#1091)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.unbound_advanced import UnboundAdvancedManager
from infrafoundry.providers.opnsense.components.unbound_settings import UnboundSettingsManager
from infrafoundry.providers.opnsense.services.unbound_advanced import UnboundAdvancedService
from infrafoundry.providers.opnsense.services.unbound_settings import UnboundSettingsService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.unbound_settings.UnboundSettingsService"
ADV_SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.unbound_advanced.UnboundAdvancedService"
)

LIVE: dict[str, Any] = {
    "unbound": {
        "general": {"enabled": "1", "regdhcp": "0"},
        "advanced": {
            "hideidentity": "0",
            "privatedomain": {"a.example": {"selected": 1}},
            "insecuredomain": {"": {"selected": 1}},
            "privateaddress": {"10.0.0.0/8": {"selected": 1}},
        },
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="unbound.settings", type="unbound.settings", provider="opnsense", config=config
    )


def _service() -> UnboundSettingsService:
    service = UnboundSettingsService(MagicMock())
    service.client = MagicMock()
    service.client.request.return_value = LIVE
    return service


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = _service()
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(UnboundSettingsManager(tmp_path), method)("env", resources)
    return result, set_mock


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"general": {"enabled": True}})])
    assert diff.is_empty


def test_plan_drift_is_one_update_only(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"general": {"regdhcp": True}})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_apply_on_drift_writes_once(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"advanced": {"hideidentity": True}})])
    set_mock.assert_called_once()
    body = set_mock.call_args.args[0]["unbound"]
    assert set(body) == {"advanced"}
    assert body["advanced"]["hideidentity"] == "1"
    assert body["advanced"]["privateaddress"] == "10.0.0.0/8"
    assert result["resources_updated"] == 1
    assert result["resource_outcomes"][0].address == "opnsense_unbound_settings.settings"


def test_apply_in_sync_makes_no_write(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"general": {"enabled": True}})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_apply_logs_field_names(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    _run("apply", tmp_path, [_resource({"general": {"regdhcp": True}})])
    assert "general.regdhcp" in caplog.text


def test_owned_field_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match=r"unbound\.advanced"):
        _run("plan", tmp_path, [_resource({"advanced": {"privatedomain": ["x.example"]}})])


def test_finalization_hook() -> None:
    assert UnboundSettingsManager.FINALIZATION_HOOK == "unbound_reconfigure"


def test_destroy_is_a_noop(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = UnboundSettingsManager(tmp_path).destroy("env", [_resource({})])
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = UnboundSettingsManager(tmp_path).get_resource_ids("env", [_resource({})])
    assert ids == {"unbound.settings": "global"}


def test_two_resources_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError):
        _run("plan", tmp_path, [_resource({}), _resource({})])


def test_migrate_exports_yaml(tmp_path: Path) -> None:
    service = _service()
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        text = UnboundSettingsManager(tmp_path).migrate("env")
    assert "settings:" in text
    assert "enabled: true" in text


@pytest.mark.parametrize("settings_first", [True, False])
def test_coexists_with_unbound_advanced(tmp_path: Path, settings_first: bool) -> None:
    """Both managers write against one shared document; both declared sets survive."""
    document = copy.deepcopy(LIVE)

    def request(method: str, path: str, data: Any = None) -> Any:
        if data is not None:
            for section, flat in data["unbound"].items():
                document["unbound"][section] = flat
            return {"result": "saved"}
        return copy.deepcopy(document)

    def build(service_cls: Any) -> Any:
        service = service_cls(MagicMock())
        service.client = MagicMock()
        service.client.request.side_effect = request
        return service

    settings_res = _resource({"advanced": {"hideidentity": True}, "general": {"regdhcp": True}})
    advanced_res = ResourceConfig(
        name="unbound.advanced",
        type="unbound.advanced",
        provider="opnsense",
        config={"private_domains": ["b.example"]},
    )

    def run_settings() -> None:
        with patch(SERVICE_PATH) as cls:
            cls.from_environment.side_effect = lambda *a, **k: build(UnboundSettingsService)
            UnboundSettingsManager(tmp_path).apply("env", [settings_res])

    def run_advanced() -> None:
        with patch(ADV_SERVICE_PATH) as cls:
            cls.from_environment.side_effect = lambda *a, **k: build(UnboundAdvancedService)
            UnboundAdvancedManager(tmp_path).apply("env", [advanced_res])

    order = (run_settings, run_advanced) if settings_first else (run_advanced, run_settings)
    for step in order:
        step()

    assert document["unbound"]["advanced"]["hideidentity"] == "1"
    assert document["unbound"]["advanced"]["privatedomain"] == "b.example"
    assert document["unbound"]["advanced"]["privateaddress"] == "10.0.0.0/8"
    assert document["unbound"]["general"]["regdhcp"] == "1"
