"""End to end: the real runner and the real monit managers against a fake box (#791).

Only the API client is faked; nothing contacts a firewall.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.opnsense.services import monit as monit_svc
from infrafoundry.providers.opnsense.services.monit_settings import MonitSettingsService
from tests.helpers.opnsense_monit import FakeMonitBox, single, stock_resources

TYPES = ("monit.settings", "monit.alerts", "monit.tests", "monit.services")
SERVICE_CLASSES: tuple[type[Any], ...] = (
    MonitSettingsService,
    monit_svc.MonitAlertsService,
    monit_svc.MonitTestsService,
    monit_svc.MonitServicesService,
)


@pytest.fixture
def box() -> FakeMonitBox:
    return FakeMonitBox()


@pytest.fixture
def provider(box: FakeMonitBox, tmp_path: Path) -> Iterator[MagicMock]:
    real = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)
    table = {t: m for t, m in real.get_direct_api_resource_types().items() if t in TYPES}
    client = MagicMock()
    client.request.side_effect = box.request
    patchers: list[Any] = [
        patch.object(cls, "from_environment", return_value=cls(client)) for cls in SERVICE_CLASSES
    ]
    env = MagicMock()
    env.secrets = {}
    config_manager = MagicMock()
    config_manager.return_value.load_environment.return_value = env
    patchers.append(
        patch("infrafoundry.providers.opnsense.components._secrets.ConfigManager", config_manager)
    )
    for p in patchers:
        p.start()
    mock = MagicMock()
    mock.name = "opnsense"
    mock._current_environment = "dev"
    mock.config_dir = tmp_path
    mock.get_direct_api_resource_types.return_value = table
    mock.get_finalization_hooks.return_value = real.get_finalization_hooks()
    yield mock
    patch.stopall()


def _run(method: str, provider: MagicMock, resources: list[ResourceConfig], **kw: Any) -> Any:
    with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
        return getattr(OPNsenseDirectRunner(), method)(provider, **kw)


def test_plan_apply_replan_is_clean_and_reconfigures_once(
    provider: MagicMock, box: FakeMonitBox
) -> None:
    resources = stock_resources()
    plan = _run("plan", provider, resources)
    assert plan["has_changes"] is True
    assert "monit.alerts: 1 to add" in plan["changes_summary"]
    assert "monit.tests: 11 to add" in plan["changes_summary"]
    assert "monit.services: 4 to add" in plan["changes_summary"]
    assert "monit.settings: 0 to add, 0 to update" in plan["changes_summary"]

    result = _run("apply", provider, resources)
    assert result["success"] is True
    assert result["resources_created"] == 16  # settings is stock already: no write
    assert result["resources_updated"] == 0
    assert len(box.rows["alert"]) == 1 and len(box.rows["test"]) == 11
    assert len(box.rows["service"]) == 4
    assert box.count("monit/service/reconfigure") == 1
    assert box.count("monit/settings/set") == 0

    host = box.rows["service"][box.uuid_of("service", "$HOST")]
    expected = {
        box.uuid_of("test", n)
        for n in ("MemoryUsage", "CPUUsage", "LoadAvg1", "LoadAvg5", "LoadAvg15")
    }
    assert set(host["tests"].split(",")) == expected

    replan = _run("plan", provider, resources)
    assert replan["has_changes"] is False
    again = _run("apply", provider, resources)
    assert again["resources_created"] == again["resources_updated"] == 0
    assert box.count("monit/service/reconfigure") == 1  # no change, no second hook


def test_settings_only_drift_fires_the_hook_once(provider: MagicMock, box: FakeMonitBox) -> None:
    resources = [single("monit.settings", enabled=True, interval=60)]
    result = _run("apply", provider, resources)
    assert result["resources_updated"] == 1
    assert box.paths() == ["monit/settings/set", "monit/service/reconfigure"]
    assert box.general["enabled"] == "1" and box.general["interval"] == "60"
    assert _run("plan", provider, resources)["has_changes"] is False


def test_destroy_deletes_services_before_tests(provider: MagicMock, box: FakeMonitBox) -> None:
    resources = stock_resources()
    _run("apply", provider, resources)
    box.calls.clear()
    result = _run("destroy", provider, resources)
    assert result["success"] is True
    assert result["resources_destroyed"] == 16
    assert not any(box.rows.values())
    kinds = [p.split("/")[2] for p in box.paths() if "/del" in p]
    assert kinds[:4] == ["delService"] * 4
    assert "delService" not in kinds[4:]
    assert kinds.count("delTest") == 11 and kinds.count("delAlert") == 1


def test_removing_a_service_and_its_test_together_deletes_both_in_order(
    provider: MagicMock, box: FakeMonitBox
) -> None:
    resources = stock_resources()
    _run("apply", provider, resources)
    managed = {t: [r for r in resources if r.type == t] for t in TYPES}
    box.calls.clear()
    trimmed = [r for r in resources if r.name not in {"gateway-alert", "non-zero-status"}]
    result = _run("apply", provider, trimmed, managed_resources=managed)
    assert result["success"] is True
    assert result["resources_deleted"] == 2
    assert "gateway_alert" not in box.names("service") and "NonZeroStatus" not in box.names("test")
    deletes = [p for p in box.paths() if "/del" in p]
    assert "delService" in deletes[0] and "delTest" in deletes[1]


def test_a_test_dropped_while_its_service_keeps_it_is_kept_then_removed_next_apply(
    provider: MagicMock, box: FakeMonitBox
) -> None:
    resources = stock_resources()
    _run("apply", provider, resources)
    managed = {t: [r for r in resources if r.type == t] for t in TYPES}
    no_test = [r for r in resources if r.name != "changed-status"]
    # the carp service still lists the test in the box and in the YAML
    result = _run("apply", provider, no_test, managed_resources=managed)
    assert result["success"] is True
    assert "ChangedStatus" in box.names("test")
    for service in no_test:
        if service.name == "carp-status-change":
            service.config["tests"] = []
    result = _run("apply", provider, no_test, managed_resources=managed)
    assert result["success"] is True
    _run("apply", provider, no_test, managed_resources=managed)
    assert "ChangedStatus" not in box.names("test")
