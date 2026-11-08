"""Unit tests for ``HostDiscoveryManager`` (#792)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.hostdiscovery import HostDiscoveryManager
from infrafoundry.providers.opnsense.services.hostdiscovery import HostDiscoveryService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.hostdiscovery.HostDiscoveryService"

LIVE = {
    "hostdiscovery": {
        "general": {
            "enabled": "1",
            "promisc": "0",
            "verbose": "0",
            "skip_nets": "",
            "interface": {"lan": {"value": "LAN", "selected": 1}},
            "expire4_interval": "3600",
            "expire6_interval": "7200",
        }
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="hostdiscovery", type="hostdiscovery", provider="opnsense", config=config
    )


def _service() -> HostDiscoveryService:
    service = HostDiscoveryService(MagicMock())
    client = MagicMock()
    client.request.return_value = LIVE
    service.client = client
    return service


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = _service()
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(HostDiscoveryManager(tmp_path), method)("env", resources)
    return result, set_mock


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"enabled": True, "interface": ["lan"]})])
    assert diff.is_empty


def test_plan_drift_is_one_update_only(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"verbose": True})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_apply_on_drift_writes_once(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"interface": ["lan", "opt1"]})])
    set_mock.assert_called_once()
    general = set_mock.call_args.args[0]["hostdiscovery"]["general"]
    assert general["interface"] == "lan,opt1"
    assert general["expire4_interval"] == "3600"
    assert result["resources_updated"] == 1
    assert [o.action for o in result["resource_outcomes"]] == ["update"]


def test_apply_in_sync_makes_no_write(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"expire4_interval": 3600})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_apply_never_reconfigures(tmp_path: Path) -> None:
    service = _service()
    reconfigure = MagicMock()
    service.reconfigure = reconfigure  # type: ignore[method-assign]
    service.set_settings = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        HostDiscoveryManager(tmp_path).apply("env", [_resource({"verbose": True})])
    reconfigure.assert_not_called()


def test_finalization_hook() -> None:
    assert HostDiscoveryManager.FINALIZATION_HOOK == "hostdiscovery_reconfigure"


def test_destroy_is_a_noop(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = HostDiscoveryManager(tmp_path).destroy("env", [_resource({"verbose": True})])
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = HostDiscoveryManager(tmp_path).get_resource_ids("env", [_resource({})])
    assert ids == {"hostdiscovery": "global"}


def test_two_resources_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError):
        _run("plan", tmp_path, [_resource({}), _resource({})])


def test_migrate_exports_live_fields(tmp_path: Path) -> None:
    service = _service()
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        text = HostDiscoveryManager(tmp_path).migrate("env")
    exported = yaml.safe_load(text)["opnsense"]["hostdiscovery"]
    assert exported["enabled"] is True
    assert exported["interface"] == ["lan"]


def test_split_delete_phase_declared() -> None:
    assert HostDiscoveryManager.SPLIT_DELETE_PHASE is True
