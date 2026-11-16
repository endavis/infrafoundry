"""Unit tests for ``KeaDHCPv4HAManager`` (#1392)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.kea_dhcp4_ha import KeaDHCPv4HAManager
from infrafoundry.providers.opnsense.services.kea_dhcp4_ha import KeaHASettingsService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp4_ha.KeaHASettingsService"


def _live(**overrides: Any) -> dict[str, Any]:
    ha: dict[str, Any] = {
        "enabled": "0",
        "this_server_name": "",
        "%this_server_name": "fw-a",
        "max_unacked_clients": "2",
    }
    ha.update(overrides)
    return {"dhcpv4": {"general": {"enabled": "1"}, "ha": ha}}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="kea.dhcp4.ha", type="kea.dhcp4.ha", provider="opnsense", config=config
    )


def _run(
    method: str, tmp_path: Path, config: dict[str, Any], live: dict[str, Any] | None = None
) -> tuple[Any, KeaHASettingsService]:
    service = KeaHASettingsService(MagicMock())
    service.client.request.return_value = live or _live()  # type: ignore[attr-defined]
    service.set_settings = MagicMock(return_value={"result": "saved"})  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(KeaDHCPv4HAManager(tmp_path), method)("env", [_resource(**config)])
    paths = [c.args[1] for c in service.client.request.call_args_list]  # type: ignore[attr-defined]
    assert "kea/service/reconfigure" not in paths
    return result, service


def test_hook_key() -> None:
    assert KeaDHCPv4HAManager.FINALIZATION_HOOK == "kea_reconfigure"


def test_in_sync_no_write(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, {"enabled": False, "max_unacked_clients": 2})
    assert diff.is_empty
    result, service = _run("apply", tmp_path, {"enabled": False})
    assert result["resources_updated"] == 0
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]


def test_drift_plans_one_update(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, {"enabled": True})
    assert not diff.is_empty
    assert len(diff.updates) == 1


def test_apply_posts_once_without_reconfigure(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"enabled": True, "this_server_name": "fw-a"})
    assert result["resources_updated"] == 1
    assert result["resource_outcomes"][0].action == "update"
    service.set_settings.assert_called_once()  # type: ignore[attr-defined]
    payload = service.set_settings.call_args.args[0]  # type: ignore[attr-defined]
    assert payload == {
        "dhcpv4": {
            "ha": {"enabled": "1", "this_server_name": "fw-a", "max_unacked_clients": "2"},
        }
    }


def test_destroy_is_noop(tmp_path: Path) -> None:
    result = KeaDHCPv4HAManager(tmp_path).destroy("env", [_resource(enabled=True)])
    assert result["resources_destroyed"] == 0


def test_two_resources_rejected(tmp_path: Path) -> None:
    manager = KeaDHCPv4HAManager(tmp_path)
    with pytest.raises(InvalidConfigurationError):
        manager.plan("env", [_resource(), _resource()])


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = KeaDHCPv4HAManager(tmp_path).get_resource_ids("env", [_resource()])
    assert ids == {"kea.dhcp4.ha": "global"}


def test_migrate_delegates(tmp_path: Path) -> None:
    service = MagicMock()
    service.export_to_yaml.return_value = "yaml"
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        assert KeaDHCPv4HAManager(tmp_path).migrate("env") == "yaml"
