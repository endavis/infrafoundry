"""Unit tests for ``TailscaleSubnetManager`` (#787)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_settings import PLUGIN_MISSING_WARNING
from infrafoundry.providers.opnsense.components.tailscale_subnets import TailscaleSubnetManager
from infrafoundry.providers.opnsense.services.tailscale_subnets import (
    LiveTailscaleSubnet,
    TailscaleSubnetService,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_subnets.TailscaleSubnetService"


def _res(name: str, subnet: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="tailscale.subnets",
        provider="opnsense",
        config={"subnet": subnet, **config},
    )


def _service(live: list[LiveTailscaleSubnet]) -> MagicMock:
    real = TailscaleSubnetService(MagicMock())
    service = MagicMock()
    service.search.return_value = live
    service.apply_diff.side_effect = lambda diff: {
        "created": len(diff.adds),
        "updated": len(diff.updates),
        "deleted": len(diff.deletes),
    }
    service.compute_diff = real.compute_diff
    return service


def _live(uuid: str, subnet: str, description: str = "") -> LiveTailscaleSubnet:
    return LiveTailscaleSubnet(uuid=uuid, subnet=subnet, description=description)


def _call(method: str, tmp_path: Path, service: MagicMock, *args: Any, **kwargs: Any) -> Any:
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        return getattr(TailscaleSubnetManager(tmp_path), method)("env", *args, **kwargs)


def test_class_vars() -> None:
    assert TailscaleSubnetManager.DELETE_SCOPE == "managed_set"
    assert TailscaleSubnetManager.FINALIZATION_HOOK == "tailscale_reconfigure"
    assert not getattr(TailscaleSubnetManager, "SPLIT_DELETE_PHASE", False)


def test_plan_deletes_managed_only(tmp_path: Path) -> None:
    service = _service([_live("u1", "192.0.2.0/24"), _live("u2", "198.51.100.0/24")])
    managed = [_res("old", "192.0.2.0/24")]
    diff = _call(
        "plan", tmp_path, service, [_res("new", "2001:db8::/64")], managed_resources=managed
    )
    assert [a.subnet for a in diff.adds] == ["2001:db8::/64"]
    assert [d.uuid for d in diff.deletes] == ["u1"]
    assert [d.uuid for d in diff.unmanaged] == ["u2"]


def test_apply_reports_outcomes_and_never_reconfigures(tmp_path: Path) -> None:
    service = _service([_live("u1", "192.0.2.0/24", "old")])
    result = _call(
        "apply",
        tmp_path,
        service,
        [_res("a", "192.0.2.0/24", description="new"), _res("b", "2001:db8::/64")],
        managed_resources=[],
    )
    assert result["resources_created"] == 1
    assert result["resources_updated"] == 1
    assert {(o.action, o.resource_name) for o in result["resource_outcomes"]} == {
        ("add", "b"),
        ("update", "a"),
    }
    service.reconfigure.assert_not_called()


def test_plan_404_makes_adds_with_warning(tmp_path: Path) -> None:
    service = _service([])
    service.search.side_effect = APIError("nope", status_code=404)
    diff = _call("plan", tmp_path, service, [_res("a", "192.0.2.0/24")])
    assert [a.name for a in diff.adds] == ["a"]
    assert diff.warnings == [PLUGIN_MISSING_WARNING]


def test_apply_404_raises(tmp_path: Path) -> None:
    service = _service([])
    service.search.side_effect = APIError("nope", status_code=404)
    with pytest.raises(APIError):
        _call("apply", tmp_path, service, [_res("a", "192.0.2.0/24")])


def test_destroy_reconfigures_once_when_deleted(tmp_path: Path) -> None:
    service = _service([_live("u1", "192.0.2.0/24"), _live("u2", "198.51.100.0/24")])
    result = _call(
        "destroy", tmp_path, service, [_res("a", "192.0.2.0/24"), _res("b", "203.0.113.0/24")]
    )
    assert result["resources_destroyed"] == 1
    service.reconfigure.assert_called_once()


def test_destroy_nothing_deleted_no_reconfigure(tmp_path: Path) -> None:
    service = _service([_live("u1", "192.0.2.0/24")])
    result = _call("destroy", tmp_path, service, [_res("a", "192.0.2.0/24", lock=True)])
    assert result["resources_destroyed"] == 0
    assert result["locked_skipped"] == 1
    service.reconfigure.assert_not_called()


def test_get_resource_ids(tmp_path: Path) -> None:
    service = _service([_live("u1", "2001:db8::/64")])
    ids = _call(
        "get_resource_ids",
        tmp_path,
        service,
        [_res("a", "2001:DB8::/64"), _res("b", "192.0.2.0/24")],
    )
    assert ids == {"a": "u1"}


def test_list(tmp_path: Path) -> None:
    live = [_live("u1", "192.0.2.0/24")]
    assert _call("list", tmp_path, _service(live)) == live
