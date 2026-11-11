"""Unit tests for the monit list engine (#791)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import (
    APIError,
    InvalidConfigurationError,
    ReferenceValidationError,
)
from infrafoundry.providers.opnsense.services import monit as svc
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from tests.helpers.opnsense_monit import FakeMonitBox, res

A, T, S = "monit.alerts", "monit.tests", "monit.services"


def _service(cls: type[svc.MonitListService], box: FakeMonitBox) -> svc.MonitListService:
    client = MagicMock()
    client.request.side_effect = box.request
    return cls(client)


def _cfg(spec: svc.MonitListSpec, name: str, **config: Any) -> svc.MonitItemConfig:
    resource = res(spec.type_name, name, **config)
    return svc.configs_from_resources(spec, [resource])[0]


# -- identity and parsing ------------------------------------------------------------


def test_identity_defaults_to_handle_and_service_name_overrides() -> None:
    assert svc.wire_name_of(svc.TESTS, "ping", {}) == "ping"
    assert svc.wire_name_of(svc.TESTS, "ping", {"test_name": "Ping"}) == "Ping"
    assert svc.wire_name_of(svc.SERVICES, "host", {"service_name": "$HOST"}) == "$HOST"


def test_alert_identity_is_recipient_and_required() -> None:
    assert svc.wire_name_of(svc.ALERTS, "a", {"recipient": "a@example.com"}) == "a@example.com"
    assert svc.wire_name_of(svc.ALERTS, "a", {}) == ""
    with pytest.raises(ValueError, match="requires a non-empty string 'recipient'"):
        _cfg(svc.ALERTS, "a")


def test_payload_uses_identity_wire_and_wire_names() -> None:
    cfg = _cfg(
        svc.SERVICES,
        "host",
        service_name="$HOST",
        start_timeout=30,
        poll_time=5,
        tests=["tests.cpu", "monit.tests.mem", "load"],
        depends=["other"],
    )
    payload = cfg.to_payload(
        svc.SERVICES,
        {
            ("tests", "cpu"): "u1",
            ("tests", "mem"): "u2",
            ("tests", "load"): "u3",
            ("services", "other"): "u4",
        },
    )
    body = payload["service"]
    assert body["name"] == "$HOST"
    assert (body["starttimeout"], body["polltime"]) == ("30", "5")
    assert body["tests"] == "u1,u2,u3"
    assert body["depends"] == "u4"
    alert = _cfg(svc.ALERTS, "a", recipient="a@example.com", events=["link", "pid"])
    assert alert.to_payload(svc.ALERTS, {}) == {
        "alert": {"recipient": "a@example.com", "events": "link,pid"}
    }


def test_unknown_key_and_mistyped_values_name_the_field_not_the_value() -> None:
    with pytest.raises(ValueError, match="unknown keys"):
        _cfg(svc.TESTS, "t", bogus=1)
    with pytest.raises(ValueError) as exc:
        _cfg(svc.SERVICES, "s", timeout="soon-sentinel")
    assert "timeout" in str(exc.value) and "soon-sentinel" not in str(exc.value)
    with pytest.raises(ValueError, match="boolean"):
        _cfg(svc.SERVICES, "s", enabled="yes")
    with pytest.raises(ValueError, match="lock must be a boolean"):
        _cfg(svc.TESTS, "t", lock="x")


def test_wire_spelling_permisssion_is_accepted_and_permission_rejected() -> None:
    assert _cfg(svc.TESTS, "t", type="Permisssion").fields
    with pytest.raises(ValueError, match="type must be one of"):
        _cfg(svc.TESTS, "t", type="Permission")


def test_enums() -> None:
    assert len(svc.TEST_TYPES) == 23 and len(svc.SERVICE_TYPES) == 9
    assert len(svc.TEST_ACTIONS) == 6 and len(svc.ALERT_EVENTS) == 29
    for action in svc.TEST_ACTIONS:
        assert _cfg(svc.TESTS, "t", action=action)
    for kind in svc.SERVICE_TYPES:
        assert _cfg(svc.SERVICES, "s", type=kind)
    with pytest.raises(ValueError):
        _cfg(svc.TESTS, "t", action="reboot")
    with pytest.raises(ValueError):
        _cfg(svc.SERVICES, "s", type="nope")


def test_alert_events_are_checked_and_may_be_empty() -> None:
    assert _cfg(svc.ALERTS, "a", recipient="r@example.com", events=[]).fields == (
        ("events", "", "list"),
    )
    with pytest.raises(ValueError, match="entries must be among"):
        _cfg(svc.ALERTS, "a", recipient="r@example.com", events=["bogus"])
    with pytest.raises(ValueError, match="list of non-empty strings"):
        _cfg(svc.ALERTS, "a", recipient="r@example.com", events="link")


def test_integer_ranges() -> None:
    with pytest.raises(ValueError, match="integer"):
        _cfg(svc.SERVICES, "s", timeout=True)
    with pytest.raises(ValueError, match="integer"):
        _cfg(svc.ALERTS, "a", recipient="r@example.com", reminder="5")


# -- references ----------------------------------------------------------------------


def test_ref_handle_forms() -> None:
    assert svc.ref_handle("x", "tests") == "x"
    assert svc.ref_handle("tests.x", "tests") == "x"
    assert svc.ref_handle("monit.tests.x", "tests") == "x"
    for bad in ("services.x", "monit.services.x", "a.b.c.d", "tests."):
        with pytest.raises(InvalidConfigurationError):
            svc.ref_handle(bad, "tests")


# -- handles -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wire", "handle"),
    [
        ("CPUUsage", "cpu-usage"),
        ("LoadAvg1", "load-avg-1"),
        ("LoadAvg15", "load-avg-15"),
        ("$HOST", "host"),
        ("RootFs", "root-fs"),
        ("carp_status_change", "carp-status-change"),
        ("MemoryUsage", "memory-usage"),
        ("ops@example.com", "ops-example-com"),
        ("$$", ""),
    ],
)
def test_kebab_handle(wire: str, handle: str) -> None:
    assert svc.kebab_handle(wire) == handle


def _live(name: str, uuid: str) -> svc.LiveMonitItem:
    return svc.LiveMonitItem(uuid=uuid, name=name)


def test_assign_migrate_handles_avoids_collisions_across_types() -> None:
    live = {
        "alerts": [_live("ops@example.com", "a1")],
        "tests": [_live("Host", "t1"), _live("host", "t2")],
        "services": [_live("$HOST", "s1"), _live("$$", "s2")],
    }
    result = svc.assign_migrate_handles(live, reserved={"reserved"})
    assert result["tests"] == {"t1": "host", "t2": "host-2"}
    assert result["services"] == {"s1": "host-3", "s2": "services-2"}
    assert result["alerts"] == {"a1": "ops-example-com"}
    assert len({h for per in result.values() for h in per.values()}) == 5


def test_assign_migrate_handles_pins_existing_and_honours_reserved() -> None:
    live = {"tests": [_live("Ping", "t1"), _live("Other", "t2")]}
    result = svc.assign_migrate_handles(
        live, existing={"tests": {"Ping": "my-ping"}}, reserved={"other"}
    )
    assert result["tests"] == {"t1": "my-ping", "t2": "other-2"}


# -- diff ----------------------------------------------------------------------------


def _raw(**kw: str) -> dict[str, Any]:
    return dict(kw)


def test_sparse_comparison_ignores_undeclared_fields() -> None:
    live = svc.LiveMonitItem("u", "Ping", _raw(name="Ping", type="NetworkPing", path="/x"))
    want = _cfg(svc.TESTS, "ping", test_name="Ping", type="NetworkPing")
    assert svc.changed_fields(live, want) == []
    want2 = _cfg(svc.TESTS, "ping", test_name="Ping", type="Custom")
    assert svc.changed_fields(live, want2) == ["type"]


def test_events_and_refsets_compare_as_sets() -> None:
    live = svc.LiveMonitItem("u", "r", _raw(recipient="r", events="pid,link"))
    want = _cfg(svc.ALERTS, "a", recipient="r", events=["link", "pid"])
    assert svc.changed_fields(live, want) == []
    srv = svc.LiveMonitItem("s", "S", _raw(name="S", tests="u2,u1"))
    cfg = _cfg(svc.SERVICES, "s", service_name="S", tests=["a", "b"])
    known = {("tests", "a"): "u1", ("tests", "b"): "u2"}
    assert svc.changed_fields(srv, cfg, known) == []
    assert svc.changed_fields(srv, cfg, {("tests", "a"): "u1"}) == ["tests"]
    assert svc.changed_fields(srv, cfg, {("tests", "a"): "u1", ("tests", "b"): "u9"}) == ["tests"]


def test_bool_compare_treats_missing_as_false() -> None:
    live = svc.LiveMonitItem("u", "r", _raw(recipient="r"))
    assert svc.changed_fields(live, _cfg(svc.ALERTS, "a", recipient="r", noton=False)) == []
    assert svc.changed_fields(live, _cfg(svc.ALERTS, "a", recipient="r", noton=True)) == ["noton"]


def test_compute_diff_buckets_and_managed_scope() -> None:
    current = [_live("Keep", "1"), _live("Gone", "2"), _live("Hand", "3")]
    desired = [_cfg(svc.TESTS, "keep", test_name="Keep"), _cfg(svc.TESTS, "new")]
    diff = svc.compute_diff(svc.TESTS, desired, current, managed_keys={"Keep", "Gone"})
    assert [c.name for c in diff.adds] == ["new"]
    assert [d.name for d in diff.deletes] == ["Gone"]
    assert [d.name for d in diff.unmanaged] == ["Hand"]
    only = svc.compute_diff(svc.TESTS, desired, current, add_only=True)
    assert not only.deletes and not only.unmanaged


def test_locked_row_is_not_touched() -> None:
    current = [_live("Keep", "1")]
    desired = [_cfg(svc.TESTS, "keep", test_name="Keep", type="Custom", lock=True)]
    diff = svc.compute_diff(svc.TESTS, desired, current)
    assert diff.is_empty and len(diff.locked) == 1


def test_duplicate_live_identity_raises_drift_error() -> None:
    with pytest.raises(OpnsenseDriftError, match="more than one live row"):
        svc.compute_diff(svc.TESTS, [], [_live("Dup", "1"), _live("Dup", "2")])


# -- ordering ------------------------------------------------------------------------


def test_topo_order_adds_puts_dependencies_first() -> None:
    a = _cfg(svc.SERVICES, "a", depends=["b"])
    b = _cfg(svc.SERVICES, "b", depends=["c"])
    c = _cfg(svc.SERVICES, "c")
    assert [x.name for x in svc.topo_order_adds([a, b, c], "services")] == ["c", "b", "a"]
    cyc1 = _cfg(svc.SERVICES, "x", depends=["y"])
    cyc2 = _cfg(svc.SERVICES, "y", depends=["x"])
    with pytest.raises(InvalidConfigurationError, match="cycle"):
        svc.topo_order_adds([cyc1, cyc2], "services")


def test_order_deletes_removes_dependents_first() -> None:
    base = svc.LiveMonitItem("b", "Base", _raw(depends=""))
    mid = svc.LiveMonitItem("m", "Mid", _raw(depends="b"))
    top = svc.LiveMonitItem("t", "Top", _raw(depends="m"))
    assert [i.name for i in svc.order_deletes([base, mid, top], "services")] == [
        "Top",
        "Mid",
        "Base",
    ]
    assert svc.order_deletes([base, mid], "tests") == [base, mid]
    loop_a = svc.LiveMonitItem("a", "A", _raw(depends="b"))
    loop_b = svc.LiveMonitItem("b", "B", _raw(depends="a"))
    assert len(svc.order_deletes([loop_a, loop_b], "services")) == 2


# -- live model ----------------------------------------------------------------------


def test_live_items_reads_sections_and_flattens_identity() -> None:
    box = FakeMonitBox()
    box.seed("test", {"name": "Ping", "type": "NetworkPing"})
    model = _service(svc.MonitTestsService, box).get_model()
    items = svc.live_items(model, svc.TESTS)
    assert [i.name for i in items] == ["Ping"]
    assert svc.live_items(model, svc.ALERTS) == []  # PHP renders an empty map as []


def test_live_items_rejects_a_missing_or_malformed_section() -> None:
    with pytest.raises(APIError, match="no test section"):
        svc.live_items({"general": {}}, svc.TESTS)
    with pytest.raises(APIError, match="malformed"):
        svc.live_items({"test": "x"}, svc.TESTS)


def test_get_model_rejects_a_missing_envelope() -> None:
    client = MagicMock()
    client.request.return_value = {"other": 1}
    with pytest.raises(APIError, match="no monit object"):
        svc.MonitTestsService(client).get_model()


def test_references_to_maps_targets_to_services() -> None:
    box = FakeMonitBox()
    t = box.seed("test", {"name": "T"})
    box.seed("service", {"name": "S", "tests": t, "depends": ""})
    model = _service(svc.MonitServicesService, box).get_model()
    users = svc.references_to(model, "tests")
    assert [s.name for s in users[t]] == ["S"]
    assert svc.references_to(model, "depends") == {}


# -- service writes ------------------------------------------------------------------


def test_apply_diff_adds_updates_and_deletes() -> None:
    box = FakeMonitBox()
    box.seed("test", {"name": "Old", "type": "Custom"})
    box.seed("test", {"name": "Chg", "type": "Custom"})
    service = _service(svc.MonitTestsService, box)
    live = service.live()
    desired = [_cfg(svc.TESTS, "new"), _cfg(svc.TESTS, "chg", test_name="Chg", type="UID")]
    diff = svc.compute_diff(svc.TESTS, desired, live, managed_keys={"Old", "Chg"})
    counts = service.apply_diff(diff)
    assert counts == {"created": 1, "updated": 1, "deleted": 1}
    assert sorted(box.names("test")) == ["Chg", "new"]
    assert box.count("monit/service/reconfigure") == 0  # the hook does that


def test_write_rejection_raises_with_validation_keys() -> None:
    client = MagicMock()
    client.request.return_value = {"result": "failed", "validations": {"x": "bad"}}
    service = svc.MonitTestsService(client)
    with pytest.raises(APIError, match="rejected add monit test"):
        service.add(_cfg(svc.TESTS, "t"), {})


def test_missing_reference_raises_before_any_write() -> None:
    box = FakeMonitBox()
    service = _service(svc.MonitServicesService, box)
    diff = svc.Diff(adds=[_cfg(svc.SERVICES, "s", tests=["nope"])])
    with pytest.raises(ReferenceValidationError, match=r"tests\.nope"):
        service.apply_diff(diff, {})
    assert not box.writes()


def test_depends_on_a_service_added_in_the_same_apply_uses_the_returned_uuid() -> None:
    box = FakeMonitBox()
    service = _service(svc.MonitServicesService, box)
    child = _cfg(svc.SERVICES, "child", depends=["base"])
    base = _cfg(svc.SERVICES, "base")
    service.apply_diff(svc.Diff(adds=[child, base]), {})
    assert box.names("service") == ["base", "child"]
    base_uuid = box.uuid_of("service", "base")
    assert box.rows["service"][box.uuid_of("service", "child")]["depends"] == base_uuid


def test_depends_falls_back_to_rereading_when_the_add_returns_no_uuid() -> None:
    box = FakeMonitBox()
    box.omit_uuid_on_add = True
    service = _service(svc.MonitServicesService, box)
    service.apply_diff(
        svc.Diff(adds=[_cfg(svc.SERVICES, "child", depends=["base"]), _cfg(svc.SERVICES, "base")]),
        {},
    )
    child = box.rows["service"][box.uuid_of("service", "child")]
    assert child["depends"] == box.uuid_of("service", "base")


def test_service_deletes_run_dependents_first() -> None:
    box = FakeMonitBox()
    base = box.seed("service", {"name": "Base", "depends": ""})
    box.seed("service", {"name": "Top", "depends": base})
    service = _service(svc.MonitServicesService, box)
    service.apply_diff(svc.Diff(deletes=service.live()), {})
    assert box.names("service") == []  # the fake rejects a referenced delete


# -- export --------------------------------------------------------------------------


def test_export_rows_for_each_type_round_trip_through_yaml() -> None:
    box = FakeMonitBox()
    t1 = box.seed(
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
        "alert",
        {
            "recipient": "ops@example.com",
            "enabled": "1",
            "noton": "0",
            "events": "pid,link",
            "reminder": "10",
            "format": "",
            "description": "",
        },
    )
    box.seed(
        "service",
        {
            "name": "$HOST",
            "enabled": "1",
            "type": "system",
            "timeout": "300",
            "tests": t1,
            "depends": "",
            "interface": "",
        },
    )
    model = box.request("GET", "monit/settings/get")["monit"]
    live = {sub: svc.live_items(model, cls.SPEC) for sub, cls in svc.LIST_SERVICES.items()}
    handles = svc.assign_migrate_handles(live)
    refs = {"tests": handles["tests"], "services": handles["services"]}
    out = _service(svc.MonitServicesService, box).export_to_yaml(
        refs, items=live["services"], handles=handles["services"]
    )
    row = yaml.safe_load(out)["opnsense"]["monit"]["services"][0]
    assert row["name"] == "host"
    assert row["config"]["service_name"] == "$HOST"
    assert row["config"]["tests"] == ["load-avg-1"]
    assert row["config"]["timeout"] == 300 and row["config"]["enabled"] is True
    assert "depends" not in row["config"] and "interface" not in row["config"]
    alert = yaml.safe_load(
        _service(svc.MonitAlertsService, box).export_to_yaml(
            items=live["alerts"], handles=handles["alerts"]
        )
    )["opnsense"]["monit"]["alerts"][0]
    assert alert["config"]["recipient"] == "ops@example.com"
    assert alert["config"]["events"] == ["link", "pid"] and alert["config"]["reminder"] == 10
    test = yaml.safe_load(
        _service(svc.MonitTestsService, box).export_to_yaml(
            items=live["tests"], handles=handles["tests"]
        )
    )["opnsense"]["monit"]["tests"][0]
    assert test["name"] == "load-avg-1" and test["config"]["test_name"] == "LoadAvg1"
    assert "path" not in test["config"]


def test_export_handles_unknown_reference_and_bad_integer(caplog: pytest.LogCaptureFixture) -> None:
    box = FakeMonitBox()
    box.seed("service", {"name": "S", "tests": "ghost", "timeout": "soon", "depends": ""})
    service = _service(svc.MonitServicesService, box)
    with caplog.at_level(logging.WARNING):
        rows = service.export_rows(service.live(), {"tests": {}})
    assert "tests" not in rows[0]["config"] and "timeout" not in rows[0]["config"]
    assert "unknown tests row" in caplog.text and "non-integer" in caplog.text


def test_export_computes_handles_when_omitted() -> None:
    box = FakeMonitBox()
    box.seed("test", {"name": "CPUUsage"})
    service = _service(svc.MonitTestsService, box)
    assert service.export_rows(service.live())[0]["name"] == "cpu-usage"
