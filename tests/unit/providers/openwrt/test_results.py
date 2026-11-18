"""Tests for parsing the JSON callback output of a run."""

from typing import Any

import pytest

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.openwrt.components.results import (
    ResultsError,
    RunSpec,
    interpret,
    parse_output,
)
from infrafoundry.providers.openwrt.schema import Desired, desired_from_resources

from .conftest import MGMT_IP, doc, fixture_text, lan, printer, task, web


def _items(*resources: Any) -> list[Desired]:
    return desired_from_resources(list(resources))


def _spec(*resources: Any, managed: set[tuple[str, str]] | None = None, **kw: Any) -> RunSpec:
    return RunSpec(mode="apply", items=_items(*resources), managed_names=managed or set(), **kw)


def _run(fixture: str, spec: RunSpec, check: bool = True) -> Any:
    return interpret(
        parse_output(fixture_text(fixture)),
        spec,
        address=MGMT_IP,
        check=check,
        resolve=lambda host: host,
    )


ALL = ("network.interface", "lan"), ("dhcp.host", "printer"), ("firewall.redirect", "web")


def test_clean_check_has_no_changes_and_adopts_unmanaged_resources() -> None:
    result = _run("check_clean", _spec(lan(), printer(), web()))
    assert result.success
    assert not result.has_changes
    assert result.counts == {"create": 0, "update": 0, "delete": 0}
    assert result.summary_lines() == []
    assert [(o.action, o.resource_name) for o in result.outcomes] == [
        ("create", "lan"),
        ("create", "printer"),
        ("create", "web"),
    ]


def test_clean_check_with_everything_managed_has_no_outcomes() -> None:
    result = _run("check_clean", _spec(lan(), printer(), web(), managed=set(ALL)))
    assert result.outcomes == []
    assert not result.has_changes


def test_changed_check_splits_create_and_update_by_the_managed_set() -> None:
    managed = {("firewall.redirect", "web"), ("network.interface", "lan")}
    result = _run("check_changed", _spec(lan(), printer(), web(), managed=managed))
    assert result.counts == {"create": 1, "update": 1, "delete": 0}
    assert result.has_changes
    assert {(o.resource_name, o.action) for o in result.outcomes} == {
        ("printer", "create"),
        ("web", "update"),
    }
    assert result.outcomes[0] == ResourceOutcome("openwrt_dhcp_host.printer", "create", "printer")
    assert "create: 1" in result.summary_lines()


def test_diffs_are_extracted_per_resource() -> None:
    result = _run("check_changed", _spec(printer(), web()))
    assert result.diffs["infrafoundry|dhcp.host|printer"] == {
        "before": {},
        "after": {"mac": "02:00:00:00:00:0a", "ip": "192.0.2.50"},
    }
    assert result.diffs["infrafoundry|firewall.redirect|web"]["after"] == {"dest_port": "80"}


def test_a_non_dict_diff_is_unknown_not_empty() -> None:
    output = doc(task("infrafoundry|network.interface|lan", changed=True, diff="text diff"))
    result = interpret(
        parse_output(output), _spec(lan()), address=MGMT_IP, check=True, resolve=lambda h: h
    )
    assert result.diffs == {}
    assert result.refusals, "an unreadable interface change must be refused"


def test_management_change_is_refused_in_a_check_pass_only() -> None:
    result = _run("check_management", _spec(lan(ipaddr="198.51.100.1")))
    assert any("management network" in r for r in result.refusals)
    real = _run("check_management", _spec(lan(ipaddr="198.51.100.1")), check=False)
    assert real.refusals == []


def test_management_change_with_the_flag_reconnects_to_the_new_address() -> None:
    spec = _spec(lan(ipaddr="198.51.100.1", confirm_management_change=True))
    tasks = parse_output(fixture_text("check_management"))
    # The settings address is the interface's own current address.
    result = interpret(tasks, spec, address="192.0.2.1", check=True, resolve=lambda h: h)
    assert result.refusals == []
    assert result.reconnect_host == "198.51.100.1"
    # A settings address elsewhere in the subnet stays reachable only if the subnet is kept.
    other = interpret(tasks, spec, address=MGMT_IP, check=True, resolve=lambda h: h)
    assert other.refusals == [] and other.reconnect_host is None


def test_apply_ok_reports_outcomes() -> None:
    result = _run("apply_ok", _spec(lan(), printer(), web()), check=False)
    assert result.success
    assert result.counts == {"create": 2, "update": 0, "delete": 0}


def test_failed_lease_guard_surfaces_a_clear_error() -> None:
    result = _run("lease_duplicate", _spec(printer()))
    assert not result.success
    assert "more than one dhcp host section has MAC 02:00:00:00:00:0a" in (result.error or "")
    assert "infrafoundry|guard|printer|duplicate-fail" in (result.error or "")


def test_rollback_marker_gives_the_rollback_pending_message() -> None:
    result = _run("apply_rollback", _spec(printer()), check=False)
    assert not result.success
    assert result.rollback_pending
    assert "reverts it by itself" in (result.error or "")


def test_unreachable_host_is_a_failure() -> None:
    output = doc(task("infrafoundry|preflight|network", unreachable=True, msg="no route to host"))
    result = interpret(parse_output(output), _spec(lan()), address=MGMT_IP, check=True)
    assert not result.success
    assert "unreachable" in (result.error or "")
    assert "no route to host" in (result.error or "")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"plays": 3}'])
def test_malformed_output_raises_results_error_not_anything_else(raw: str) -> None:
    with pytest.raises(ResultsError):
        parse_output(raw)


def test_absent_resources_count_as_deletes_and_release_managed_rows() -> None:
    items = _items(printer())
    gone = Desired(items[0].spec, "printer", items[0].key, {}, absent=True)
    spec = RunSpec(
        mode="apply",
        items=[gone],
        managed_names={("dhcp.host", "printer")},
        removal_names={"printer"},
    )
    output = doc(task("infrafoundry|absent|dhcp.host|printer", changed=True))
    result = interpret(parse_output(output), spec, address=MGMT_IP, check=False)
    assert result.counts["delete"] == 1
    assert result.released == [ReleasedResource(resource_type="dhcp.host", name="printer")]
    assert result.outcomes == []


def test_a_declared_absent_resource_reports_a_delete_outcome_when_it_changes() -> None:
    items = _items(printer(absent=True))
    spec = RunSpec(mode="apply", items=items, managed_names=set())
    result = interpret(
        parse_output(doc(task("infrafoundry|absent|dhcp.host|printer", changed=True))),
        spec,
        address=MGMT_IP,
        check=False,
    )
    assert [(o.action, o.resource_name) for o in result.outcomes] == [("delete", "printer")]
    unchanged = interpret(
        parse_output(doc(task("infrafoundry|absent|dhcp.host|printer", changed=False))),
        spec,
        address=MGMT_IP,
        check=False,
    )
    assert unchanged.outcomes == []
    assert unchanged.counts["delete"] == 0


def test_destroy_reports_delete_outcomes_and_forgets_the_rest() -> None:
    declared = _items(printer(), lan())
    absent = Desired(declared[0].spec, "printer", declared[0].key, {}, absent=True)
    spec = RunSpec(mode="destroy", items=[absent], forgotten_items=[declared[1]])
    output = doc(task("infrafoundry|absent|dhcp.host|printer", changed=False))
    result = interpret(parse_output(output), spec, address=MGMT_IP, check=False)
    assert [(o.action, o.resource_name) for o in result.outcomes] == [
        ("delete", "printer"),
        ("delete", "lan"),
    ]
    assert result.released == []


def test_forgotten_rows_are_released_without_a_device_change() -> None:
    forgotten = [ReleasedResource(resource_type="dhcp.pool", name="lan")]
    spec = RunSpec(mode="apply", items=[], forgotten=forgotten)
    result = interpret(parse_output(doc()), spec, address=MGMT_IP, check=False)
    assert result.released == forgotten
    assert not result.has_changes


def test_tasks_missing_from_the_output_are_ignored() -> None:
    result = interpret(parse_output(doc()), _spec(printer()), address=MGMT_IP, check=True)
    assert result.outcomes == []
    assert result.success
