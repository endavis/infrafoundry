"""Unit tests for the monit list managers (#791)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.providers.opnsense.components import monit as comp
from tests.helpers.opnsense_monit import FakeMonitBox, res

A, T, S = "monit.alerts", "monit.tests", "monit.services"


@pytest.fixture
def box() -> FakeMonitBox:
    return FakeMonitBox()


def _manager(cls: type[comp._MonitListManager], box: FakeMonitBox, tmp_path: Path) -> Any:
    client = MagicMock()
    client.request.side_effect = box.request
    service_cls = cls.SERVICE
    patch.object(service_cls, "from_environment", return_value=service_cls(client)).start()
    return cls(tmp_path)


@pytest.fixture
def make(
    box: FakeMonitBox, tmp_path: Path
) -> Iterator[Callable[[type[comp._MonitListManager]], Any]]:
    yield lambda cls: _manager(cls, box, tmp_path)
    patch.stopall()


# -- shared behaviour ----------------------------------------------------------------


def test_class_attributes() -> None:
    for cls in (comp.MonitAlertsManager, comp.MonitTestsManager, comp.MonitServicesManager):
        assert cls.DELETE_SCOPE == "managed_set"
        assert cls.FINALIZATION_HOOK == "monit_reconfigure"
        assert callable(cls.migrate)
    assert comp.MonitServicesManager.SPLIT_DELETE_PHASE is True
    assert not getattr(comp.MonitAlertsManager, "SPLIT_DELETE_PHASE", False)
    assert not getattr(comp.MonitTestsManager, "SPLIT_DELETE_PHASE", False)
    assert comp.MonitServicesManager.SIBLING_RESOURCE_TYPE == (T,)


def test_alert_crud(make: Any, box: FakeMonitBox) -> None:
    box.seed("alert", {"recipient": "chg@example.com", "enabled": "0", "events": ""})
    box.seed("alert", {"recipient": "gone@example.com"})
    manager = make(comp.MonitAlertsManager)
    resources = [
        res(A, "new", recipient="new@example.com", events=["link"]),
        res(A, "chg", recipient="chg@example.com", enabled=True),
    ]
    diff = manager.plan("env", resources)
    assert [c.name for c in diff.adds] == ["new"]
    assert [w.name for _, w in diff.updates] == ["chg"]
    assert [d.name for d in diff.deletes] == ["gone@example.com"]
    managed = [res(A, "gone", recipient="gone@example.com")]
    result = manager.apply("env", resources, managed_resources=managed)
    assert (result["resources_created"], result["resources_updated"]) == (1, 1)
    assert result["resources_deleted"] == 1
    assert [o.address for o in result["resource_outcomes"]] == [
        "opnsense_monit_alert.new",
        "opnsense_monit_alert.chg",
        "opnsense_monit_alert.gone@example.com",  # deletes use the wire identity
    ]
    assert sorted(box.names("alert")) == ["chg@example.com", "new@example.com"]
    assert manager.plan("env", resources, managed_resources=managed).is_empty
    assert box.count("monit/service/reconfigure") == 0


def test_test_crud_and_get_resource_ids(make: Any, box: FakeMonitBox) -> None:
    manager = make(comp.MonitTestsManager)
    resources = [res(T, "ping", test_name="Ping", type="NetworkPing", condition="failed ping")]
    manager.apply("env", resources)
    assert box.names("test") == ["Ping"]
    ids = manager.get_resource_ids("env", [*resources, res(T, "absent")])
    assert ids == {"ping": box.uuid_of("test", "Ping")}
    assert manager.plan("env", resources).is_empty


def test_add_only_suppresses_deletes(make: Any, box: FakeMonitBox) -> None:
    box.seed("test", {"name": "Gone"})
    manager = make(comp.MonitTestsManager)
    managed = [res(T, "gone", test_name="Gone")]
    assert manager.plan("env", [], managed_resources=managed).deletes
    diff = manager.plan("env", [], add_only=True, managed_resources=managed)
    assert not diff.deletes
    manager.apply("env", [], add_only=True, managed_resources=managed)
    assert box.names("test") == ["Gone"]


def test_unmanaged_live_rows_are_kept(make: Any, box: FakeMonitBox) -> None:
    box.seed("test", {"name": "Hand"})
    manager = make(comp.MonitTestsManager)
    diff = manager.plan("env", [], managed_resources=[])
    assert [u.name for u in diff.unmanaged] == ["Hand"] and not diff.deletes
    manager.apply("env", [], managed_resources=[])
    assert box.names("test") == ["Hand"]


def test_lock_leaves_the_row_alone(make: Any, box: FakeMonitBox) -> None:
    box.seed("test", {"name": "Locked", "type": "Custom"})
    manager = make(comp.MonitTestsManager)
    resources = [res(T, "locked", test_name="Locked", type="UID", lock=True)]
    diff = manager.plan("env", resources)
    assert len(diff.locked) == 1 and diff.is_empty
    manager.apply("env", resources)
    assert not box.writes()


def test_unparsable_managed_row_is_kept_and_reported(make: Any, box: FakeMonitBox) -> None:
    box.seed("alert", {"recipient": "x@example.com"})
    manager = make(comp.MonitAlertsManager)
    bad = res(A, "bad")  # no recipient
    result = manager.apply("env", [], managed_resources=[bad])
    assert result["resources_deleted"] == 0 and result["unresolved_managed"] == ["bad"]


# -- services and references ----------------------------------------------------------


def _tests(*names: str) -> list[Any]:
    return [res(T, n.lower(), test_name=n, type="Custom", condition="c") for n in names]


def test_tests_reference_resolves_to_comma_joined_uuids(make: Any, box: FakeMonitBox) -> None:
    ta = box.seed("test", {"name": "A"})
    tb = box.seed("test", {"name": "B"})
    manager = make(comp.MonitServicesManager)
    resources = [res(S, "svc", service_name="Svc", tests=["a", "tests.b"])]
    siblings = _tests("A", "B")
    manager.apply("env", resources, sibling_resources=siblings)
    row = box.rows["service"][box.uuid_of("service", "Svc")]
    assert row["tests"] == f"{ta},{tb}"
    assert manager.plan("env", resources, sibling_resources=siblings).is_empty


def test_managed_sibling_resources_also_resolve_references(make: Any, box: FakeMonitBox) -> None:
    t = box.seed("test", {"name": "A"})
    manager = make(comp.MonitServicesManager)
    manager.apply(
        "env",
        [res(S, "svc", service_name="Svc", tests=["a"])],
        managed_sibling_resources=_tests("A"),
    )
    assert box.rows["service"][box.uuid_of("service", "Svc")]["tests"] == t


def test_missing_test_is_a_plan_warning_and_an_apply_error_before_any_write(
    make: Any, box: FakeMonitBox
) -> None:
    manager = make(comp.MonitServicesManager)
    resources = [res(S, "svc", service_name="Svc", tests=["ghost"])]
    diff = manager.plan("env", resources, sibling_resources=[])
    assert any("tests 'ghost' is not on the box yet" in w for w in diff.warnings)
    with pytest.raises(ReferenceValidationError, match=r"tests\.ghost"):
        manager.apply("env", resources, sibling_resources=[])
    assert not box.writes()


def test_depends_on_a_service_added_in_the_same_apply(make: Any, box: FakeMonitBox) -> None:
    manager = make(comp.MonitServicesManager)
    resources = [
        res(S, "child", service_name="Child", depends=["base"]),
        res(S, "base", service_name="Base"),
    ]
    diff = manager.plan("env", resources)
    assert not diff.warnings
    result = manager.apply("env", resources)
    assert result["resources_created"] == 2
    assert box.names("service") == ["Base", "Child"]
    assert manager.plan("env", resources).is_empty


def test_depends_forms_and_managed_row_resolution(make: Any, box: FakeMonitBox) -> None:
    base = box.seed("service", {"name": "Base"})
    manager = make(comp.MonitServicesManager)
    # ``base`` left the YAML but is a managed row: a reference to it still resolves, and
    # the row is kept (blocked) because a declared service depends on it.
    managed = [res(S, "base", service_name="Base")]
    resources = [res(S, "c1", depends=["monit.services.base"])]
    diff = manager.plan("env", resources, managed_resources=managed)
    assert [live.name for live, _ in diff.blocked] == ["Base"]
    result = manager.apply("env", resources, managed_resources=managed)
    assert box.rows["service"][box.uuid_of("service", "c1")]["depends"] == base
    assert box.names("service") == ["Base", "c1"]
    assert result["unresolved_managed"] == ["base"]


def test_deletes_only_phase_does_no_adds_or_updates(make: Any, box: FakeMonitBox) -> None:
    box.seed("service", {"name": "Gone"})
    manager = make(comp.MonitServicesManager)
    result = manager.apply(
        "env",
        [res(S, "new", service_name="New", tests=["ghost"])],
        deletes_only=True,
        managed_resources=[res(S, "gone", service_name="Gone")],
        sibling_resources=[],
    )
    assert result["resources_created"] == 0 and result["resources_deleted"] == 1
    assert box.names("service") == []
    assert not any("is not on the box yet" in w for w in result["warnings"])


def test_service_deletes_run_dependents_first(make: Any, box: FakeMonitBox) -> None:
    base = box.seed("service", {"name": "Base", "depends": ""})
    box.seed("service", {"name": "Top", "depends": base})
    manager = make(comp.MonitServicesManager)
    managed = [res(S, "base", service_name="Base"), res(S, "top", service_name="Top")]
    result = manager.apply("env", [], deletes_only=True, managed_resources=managed)
    assert result["resources_deleted"] == 2 and box.names("service") == []
    assert len([p for p in box.paths() if "/delService/" in p]) == 2


def test_service_still_depended_on_by_a_survivor_is_blocked(make: Any, box: FakeMonitBox) -> None:
    base = box.seed("service", {"name": "Base", "depends": ""})
    box.seed("service", {"name": "Keeper", "depends": base})
    manager = make(comp.MonitServicesManager)
    resources = [res(S, "keeper", service_name="Keeper", depends=["base"])]
    managed = [res(S, "base", service_name="Base"), res(S, "keeper", service_name="Keeper")]
    diff = manager.plan("env", resources, managed_resources=managed)
    assert [live.name for live, _ in diff.blocked] == ["Base"] and not diff.deletes
    assert any("still a dependency of service(s) Keeper" in w for w in diff.warnings)
    result = manager.apply("env", resources, managed_resources=managed)
    assert result["resources_deleted"] == 0 and box.names("service") == ["Base", "Keeper"]
    assert result["unresolved_managed"] == ["base"]


def test_deleting_a_service_and_its_only_dependent_together_is_not_blocked(
    make: Any, box: FakeMonitBox
) -> None:
    base = box.seed("service", {"name": "Base", "depends": ""})
    box.seed("service", {"name": "Top", "depends": base})
    manager = make(comp.MonitServicesManager)
    managed = [res(S, "base", service_name="Base"), res(S, "top", service_name="Top")]
    diff = manager.plan("env", [], managed_resources=managed)
    assert len(diff.deletes) == 2 and not diff.blocked


def test_test_still_used_by_a_surviving_service_is_blocked(make: Any, box: FakeMonitBox) -> None:
    t = box.seed("test", {"name": "Used"})
    box.seed("test", {"name": "Free"})
    box.seed("service", {"name": "Svc", "tests": t})
    manager = make(comp.MonitTestsManager)
    managed = [res(T, "used", test_name="Used"), res(T, "free", test_name="Free")]
    diff = manager.plan("env", [], managed_resources=managed)
    assert [live.name for live, _ in diff.blocked] == ["Used"]
    assert [d.name for d in diff.deletes] == ["Free"]
    assert any("still used by service(s) Svc" in w for w in diff.warnings)
    result = manager.apply("env", [], managed_resources=managed)
    assert box.names("test") == ["Used"]
    assert result["unresolved_managed"] == ["used"] and result["resources_deleted"] == 1


def test_blocked_delete_is_retried_once_the_reference_is_gone(make: Any, box: FakeMonitBox) -> None:
    t = box.seed("test", {"name": "Used"})
    box.seed("service", {"name": "Svc", "tests": t})
    manager = make(comp.MonitTestsManager)
    managed = [res(T, "used", test_name="Used")]
    manager.apply("env", [], managed_resources=managed)
    assert box.names("test") == ["Used"]
    box.rows["service"].clear()
    manager.apply("env", [], managed_resources=managed)
    assert box.names("test") == []


# -- destroy -------------------------------------------------------------------------


def test_destroy_deletes_listed_rows_and_reconfigures_once(make: Any, box: FakeMonitBox) -> None:
    box.seed("test", {"name": "A"})
    box.seed("test", {"name": "Keep"})
    manager = make(comp.MonitTestsManager)
    result = manager.destroy("env", _tests("A"))
    assert result["resources_destroyed"] == 1 and box.names("test") == ["Keep"]
    assert box.count("monit/service/reconfigure") == 1


def test_destroy_skips_locked_and_does_not_reconfigure_when_nothing_deleted(
    make: Any, box: FakeMonitBox
) -> None:
    box.seed("test", {"name": "A"})
    manager = make(comp.MonitTestsManager)
    result = manager.destroy("env", [res(T, "a", test_name="A", lock=True)])
    assert result["resources_destroyed"] == 0 and result["locked_skipped"] == 1
    assert box.count("monit/service/reconfigure") == 0


def test_destroy_services_removes_dependents_first(make: Any, box: FakeMonitBox) -> None:
    base = box.seed("service", {"name": "Base", "depends": ""})
    box.seed("service", {"name": "Top", "depends": base})
    manager = make(comp.MonitServicesManager)
    result = manager.destroy(
        "env", [res(S, "base", service_name="Base"), res(S, "top", service_name="Top")]
    )
    assert result["resources_destroyed"] == 2 and box.names("service") == []


# -- migrate -------------------------------------------------------------------------


def _seed_stock(box: FakeMonitBox) -> None:
    t = box.seed(
        "test",
        {
            "name": "LoadAvg1",
            "type": "SystemResource",
            "condition": "c",
            "action": "alert",
            "path": "",
        },
    )
    box.seed(
        "service", {"name": "$HOST", "enabled": "1", "type": "system", "tests": t, "depends": ""}
    )
    box.seed("alert", {"recipient": "ops@example.com", "enabled": "0", "events": ""})


def test_migrate_emits_handles_that_match_across_types(make: Any, box: FakeMonitBox) -> None:
    _seed_stock(box)
    with patch.object(comp, "env_provider_resources", return_value=[]):
        services = yaml.safe_load(make(comp.MonitServicesManager).migrate("env"))
        tests = yaml.safe_load(make(comp.MonitTestsManager).migrate("env"))
        alerts = yaml.safe_load(make(comp.MonitAlertsManager).migrate("env"))
    svc_row = services["opnsense"]["monit"]["services"][0]
    test_row = tests["opnsense"]["monit"]["tests"][0]
    assert svc_row["config"]["tests"] == [test_row["name"]] == ["load-avg-1"]
    assert alerts["opnsense"]["monit"]["alerts"][0]["name"] == "ops-example-com"


def test_migrate_avoids_names_already_in_the_environment(make: Any, box: FakeMonitBox) -> None:
    _seed_stock(box)
    existing = [res("firewall.aliases", "load-avg-1", type="host")]
    with patch.object(comp, "env_provider_resources", return_value=existing):
        out = yaml.safe_load(make(comp.MonitTestsManager).migrate("env"))
    assert out["opnsense"]["monit"]["tests"][0]["name"] == "load-avg-1-2"


def test_migrate_pins_to_an_existing_handle(make: Any, box: FakeMonitBox) -> None:
    _seed_stock(box)
    existing = [res(T, "my-load", test_name="LoadAvg1")]
    with patch.object(comp, "env_provider_resources", return_value=existing):
        services = yaml.safe_load(make(comp.MonitServicesManager).migrate("env"))
    assert services["opnsense"]["monit"]["services"][0]["config"]["tests"] == ["my-load"]
