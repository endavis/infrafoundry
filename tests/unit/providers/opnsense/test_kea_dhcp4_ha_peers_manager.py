"""Unit tests for ``KeaDHCPv4HAPeerManager`` (#1392)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.kea_dhcp4_ha_peers import (
    KeaDHCPv4HAPeerManager,
)
from infrafoundry.providers.opnsense.services.kea_dhcp4_ha import (
    KeaHAPeerService,
    LiveKeaHAPeer,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp4_ha_peers.KeaHAPeerService"


def _res(name: str, role: str = "primary", url: str = "http://192.0.2.1:8001/", **kw: Any) -> Any:
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.ha_peers",
        provider="opnsense",
        config={"role": role, "url": url, **kw},
    )


def _live(uuid: str, name: str, role: str = "primary", url: str = "http://192.0.2.1:8001/") -> Any:
    return LiveKeaHAPeer(uuid=uuid, name=name, role=role, url=url)


def _service(live: list[LiveKeaHAPeer]) -> MagicMock:
    real = KeaHAPeerService(MagicMock())
    service = MagicMock()
    service.search.return_value = live
    service.apply_diff.side_effect = lambda diff: {
        "created": len(diff.adds),
        "updated": len(diff.updates),
        "deleted": len(diff.deletes),
    }
    service.compute_diff = real.compute_diff
    return service


def _call(method: str, tmp_path: Path, service: MagicMock, *args: Any, **kwargs: Any) -> Any:
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        return getattr(KeaDHCPv4HAPeerManager(tmp_path), method)("env", *args, **kwargs)


def test_class_vars() -> None:
    assert KeaDHCPv4HAPeerManager.DELETE_SCOPE == "managed_set"
    assert KeaDHCPv4HAPeerManager.FINALIZATION_HOOK == "kea_reconfigure"
    assert not getattr(KeaDHCPv4HAPeerManager, "SPLIT_DELETE_PHASE", False)


def test_plan_without_managed_set_deletes_all_extras(tmp_path: Path) -> None:
    service = _service([_live("u1", "fw-a"), _live("u2", "stray")])
    diff = _call("plan", tmp_path, service, [_res("fw-a")], managed_resources=None)
    assert diff.is_empty is False
    assert [d.uuid for d in diff.deletes] == ["u2"]


def test_plan_with_managed_set_scopes_deletes(tmp_path: Path) -> None:
    service = _service([_live("u1", "old"), _live("u2", "stray")])
    diff = _call(
        "plan", tmp_path, service, [_res("fw-a")], managed_resources=[_res("old", "standby")]
    )
    assert [a.name for a in diff.adds] == ["fw-a"]
    assert [d.uuid for d in diff.deletes] == ["u1"]
    assert [d.uuid for d in diff.unmanaged] == ["u2"]


def test_apply_reports_outcomes_and_never_reconfigures(tmp_path: Path) -> None:
    service = _service([_live("u1", "fw-a", "standby"), _live("u2", "gone")])
    result = _call(
        "apply",
        tmp_path,
        service,
        [_res("fw-a"), _res("fw-b", "standby", "http://192.0.2.2:8001/")],
        managed_resources=[_res("gone")],
    )
    assert (result["resources_created"], result["resources_updated"]) == (1, 1)
    assert result["resources_deleted"] == 1
    assert {(o.action, o.resource_name) for o in result["resource_outcomes"]} == {
        ("add", "fw-b"),
        ("update", "fw-a"),
        ("delete", "gone"),
    }
    assert {o.address for o in result["resource_outcomes"]} == {
        "opnsense_kea_ha_peer.fw-a",
        "opnsense_kea_ha_peer.fw-b",
        "opnsense_kea_ha_peer.gone",
    }
    service.reconfigure.assert_not_called()


def test_destroy_reconfigures_only_when_deleted(tmp_path: Path) -> None:
    service = _service([_live("u1", "fw-a"), _live("u2", "other")])
    result = _call("destroy", tmp_path, service, [_res("fw-a"), _res("absent")])
    assert result["resources_destroyed"] == 1
    service.reconfigure.assert_called_once()

    service = _service([_live("u1", "fw-a")])
    result = _call("destroy", tmp_path, service, [_res("fw-a", lock=True)])
    assert result["resources_destroyed"] == 0
    assert result["locked_skipped"] == 1
    service.reconfigure.assert_not_called()


def test_get_resource_ids_maps_name_to_uuid(tmp_path: Path) -> None:
    service = _service([_live("u1", "fw-a")])
    ids = _call("get_resource_ids", tmp_path, service, [_res("fw-a"), _res("fw-b")])
    assert ids == {"fw-a": "u1"}


def test_list(tmp_path: Path) -> None:
    live = [_live("u1", "fw-a")]
    assert _call("list", tmp_path, _service(live)) == live


def test_migrate_excludes_own_type_from_reserved(tmp_path: Path) -> None:
    service = _service([])
    service.export_to_yaml.return_value = "yaml"
    with patch(
        "infrafoundry.providers.opnsense.components.kea_dhcp4_ha_peers.env_provider_resources",
        return_value=[],
    ):
        assert _call("migrate", tmp_path, service) == "yaml"
    service.export_to_yaml.assert_called_once_with(reserved=set())
