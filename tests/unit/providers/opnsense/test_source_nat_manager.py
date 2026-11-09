"""Unit tests for ``SourceNatManager`` (#1333)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.source_nat import SourceNatManager
from infrafoundry.providers.opnsense.services.source_nat import SourceNatService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.source_nat.SourceNatService"

LIVE = {"filter": {"general": {"snat_mode": {"automatic": {"selected": 1}}}}}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="firewall.source_nat", type="firewall.source_nat", provider="opnsense", config=config
    )


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = SourceNatService(MagicMock())
    client = MagicMock()
    client.request.return_value = LIVE
    service.client = client
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    service.apply = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(SourceNatManager(tmp_path), method)("env", resources)
    assert not service.apply.called
    return result, set_mock


def test_hook_name() -> None:
    assert SourceNatManager.FINALIZATION_HOOK == "source_nat_apply"


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"snat_mode": "automatic"})])
    assert diff.is_empty


def test_plan_drift_is_one_update(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"snat_mode": "hybrid"})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_apply_in_sync_makes_no_set_call(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"snat_mode": "automatic"})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_apply_on_drift_sets_once_and_returns_an_outcome(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"snat_mode": "hybrid"})])
    set_mock.assert_called_once_with({"snat_mode": "hybrid"})
    assert result["resources_updated"] == 1
    outcome = result["resource_outcomes"][0]
    assert outcome.action == "update"
    assert outcome.address == "opnsense_firewall_source_nat.general"


def test_destroy_is_a_no_op(tmp_path: Path) -> None:
    result = SourceNatManager(tmp_path).destroy("env", [_resource({"snat_mode": "hybrid"})])
    assert result["resources_destroyed"] == 0
    assert result["resource_outcomes"] == []


def test_get_resource_ids_is_global(tmp_path: Path) -> None:
    ids = SourceNatManager(tmp_path).get_resource_ids("env", [_resource({})])
    assert ids == {"firewall.source_nat": "global"}


def test_migrate_yaml_loads_back_as_one_resource(tmp_path: Path) -> None:
    client = MagicMock()
    client.request.return_value = LIVE
    service = SourceNatService(client)
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        text = SourceNatManager(tmp_path).migrate("env")
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        yaml.safe_load(text), "m.yaml", "opnsense"
    )
    assert [(r.type, r.config) for r in resources] == [
        ("firewall.source_nat", {"snat_mode": "automatic"})
    ]
