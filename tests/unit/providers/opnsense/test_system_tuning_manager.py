"""Unit tests for ``SystemTuningManager`` (#806, #1149).

The manager runs over a real ``SystemTuningService`` with a mocked
``SystemClient`` answering the live uuid-keyed ``core/tunables/get`` shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_tuning import SystemTuningManager
from infrafoundry.providers.opnsense.services.system_tuning import SystemTuningService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_tuning.SystemTuningService"

LIVE_ITEMS: dict[str, dict[str, str]] = {
    "uuid-1": {
        "tunable": "net.inet.ip.redirect",
        "value": "0",
        "descr": "Disable redirects",
        "default_value": "1",
    },
    "uuid-2": {"tunable": "vm.overcommit", "value": "0", "descr": "", "default_value": "0"},
    "uuid-3": {"tunable": "kern.maxfiles", "value": "100", "descr": "", "default_value": "100"},
}


def _resource(items: list[dict[str, Any]] | None = None) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.tuning",
        provider="opnsense",
        config={"items": items or []},
    )


def _service(live: dict[str, dict[str, str]] | None = None) -> SystemTuningService:
    service = SystemTuningService(MagicMock())
    client = MagicMock()
    client.get_tunables.return_value = {
        "sysctl": {"item": live if live is not None else LIVE_ITEMS}
    }
    client.add_tunable.return_value = {"result": "saved"}
    client.set_tunable.return_value = {"result": "saved"}
    service.system_client = client
    return service


def _client(service: SystemTuningService) -> MagicMock:
    return cast(MagicMock, service.system_client)


def _run(method: str, service: SystemTuningService, tmp_path: Path, items: Any) -> Any:
    manager = SystemTuningManager(tmp_path)
    with patch(SERVICE_PATH) as svc_cls:
        svc_cls.from_environment.return_value = service
        return getattr(manager, method)("test-env", [_resource(items)])


class TestPlan:
    def test_matching_tunable_among_many_defaults_is_empty(self, tmp_path: Path) -> None:
        items = [{"tunable": "net.inet.ip.redirect", "value": 0}]
        assert _run("plan", _service(), tmp_path, items).is_empty

    def test_one_add_and_one_update(self, tmp_path: Path) -> None:
        items = [
            {"tunable": "net.inet.ip.redirect", "value": 1},
            {"tunable": "net.new.thing", "value": "5"},
        ]
        diff = _run("plan", _service(), tmp_path, items)
        assert len(diff.adds) == 1
        assert len(diff.updates) == 1
        assert diff.deletes == []
        assert diff.locked == []
        assert not diff.is_empty

    def test_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidConfigurationError):
            SystemTuningManager(tmp_path).plan("test-env", [_resource(), _resource()])

    def test_duplicate_yaml_names_raise(self, tmp_path: Path) -> None:
        items = [{"tunable": "a", "value": 1}, {"tunable": "a", "value": 2}]
        with pytest.raises(InvalidConfigurationError):
            _run("plan", _service(), tmp_path, items)


class TestApply:
    def test_payloads_and_outcomes(self, tmp_path: Path) -> None:
        service = _service()
        items = [
            {"tunable": "net.inet.ip.redirect", "value": 1},
            {"tunable": "net.new.thing", "value": True, "descr": "new"},
        ]
        result = _run("apply", service, tmp_path, items)
        client = _client(service)
        client.add_tunable.assert_called_once_with(
            {"sysctl": {"tunable": "net.new.thing", "value": "1", "descr": "new"}}
        )
        # YAML omitted descr, so the live one is kept.
        client.set_tunable.assert_called_once_with(
            "uuid-1",
            {
                "sysctl": {
                    "tunable": "net.inet.ip.redirect",
                    "value": "1",
                    "descr": "Disable redirects",
                }
            },
        )
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 1
        addresses = [o.address for o in result["resource_outcomes"]]
        assert addresses == [
            "opnsense_system_tunable.net.new.thing",
            "opnsense_system_tunable.net.inet.ip.redirect",
        ]
        assert [o.action for o in result["resource_outcomes"]] == ["add", "update"]
        client.reconfigure_tunables.assert_not_called()

    def test_no_writes_when_no_changes(self, tmp_path: Path) -> None:
        service = _service()
        result = _run("apply", service, tmp_path, [{"tunable": "vm.overcommit", "value": 0}])
        client = _client(service)
        client.add_tunable.assert_not_called()
        client.set_tunable.assert_not_called()
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0

    def test_duplicate_yaml_names_raise(self, tmp_path: Path) -> None:
        items = [{"tunable": "a", "value": 1}, {"tunable": "a", "value": 2}]
        with pytest.raises(InvalidConfigurationError):
            _run("apply", _service(), tmp_path, items)

    def test_failed_write_raises_api_error(self, tmp_path: Path) -> None:
        service = _service()
        _client(service).add_tunable.return_value = {"result": "failed", "validations": {}}
        with pytest.raises(APIError):
            _run("apply", service, tmp_path, [{"tunable": "new.one", "value": 1}])


class TestMisc:
    def test_finalization_hook_key(self) -> None:
        assert SystemTuningManager.FINALIZATION_HOOK == "tunables_reconfigure"

    def test_destroy_noop(self, tmp_path: Path) -> None:
        result = SystemTuningManager(tmp_path).destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0

    def test_get_resource_ids(self, tmp_path: Path) -> None:
        result = SystemTuningManager(tmp_path).get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}

    def test_migrate_delegates_to_export(self, tmp_path: Path) -> None:
        service = MagicMock()
        service.export_to_yaml.return_value = "yaml"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            assert SystemTuningManager(tmp_path).migrate("test-env") == "yaml"
