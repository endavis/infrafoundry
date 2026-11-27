"""The pure LIF diff: what is created, updated, deleted, kept, warned about or refused."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.ontap.components.interface import (
    CREATE,
    DELETE,
    UPDATE,
    InterfaceDiff,
    compute_interface_diff,
)
from infrafoundry.providers.ontap.schema import desired_from_resources

from .conftest import HOST_IP, lif, record

pytestmark = pytest.mark.unit


def _diff(
    resources: list[Any],
    rows: list[dict[str, Any]],
    *,
    add_only: bool = False,
    managed: set[tuple[str, str]] | None = None,
    host_ip: str | None = "192.0.2.250",
) -> InterfaceDiff:
    desired = desired_from_resources(resources)
    return compute_interface_diff(
        desired,
        rows,
        add_only=add_only,
        managed_keys=managed,
        report_svms={d.svm for d in desired},
        host="cluster1.example.com",
        resolve_management=lambda: host_ip,
    )


def test_converged_cluster_plans_clean() -> None:
    diff = _diff([lif(netmask="255.255.255.0")], [record(netmask="24")])
    assert diff.is_empty and not diff.unmanaged and not diff.refusals


def test_missing_lif_is_created() -> None:
    diff = _diff([lif()], [])
    [change] = diff.changes
    assert change.kind == CREATE and change.key == ("svm1", "lif1")
    assert change.after["address"] == "192.0.2.10"


def test_only_declared_fields_are_compared() -> None:
    diff = _diff([lif(auto_revert=None)], [record(auto_revert=True, policy="custom")])
    assert diff.changes[0].changed == ("service_policy",)
    assert _diff([lif(service_policy=None)], [record(policy="custom")]).is_empty


def test_changed_fields_are_listed_in_schema_order() -> None:
    diff = _diff(
        [lif(address="192.0.2.11", home_port="e0e", auto_revert=True)], [record(auto_revert=False)]
    )
    [change] = diff.changes
    assert change.kind == UPDATE
    assert change.changed == ("address", "home_port", "auto_revert")


def test_absent_deletes_an_existing_lif_and_skips_a_missing_one() -> None:
    gone = lif("lif1", absent=True)
    assert [c.kind for c in _diff([_absent(gone)], [record()]).changes] == [DELETE]
    assert _diff([_absent(gone)], []).is_empty


def _absent(resource: Any) -> Any:
    return lif(
        resource.name,
        svm="svm1",
        absent=True,
        address=None,
        netmask=None,
        home_node=None,
        home_port=None,
        service_policy=None,
    )


def test_add_only_keeps_an_absent_lif() -> None:
    diff = _diff([_absent(lif())], [record()], add_only=True)
    assert diff.is_empty and "absent: true, skipped: add-only" in diff.unmanaged[0]


def test_managed_lif_that_left_the_yaml_is_deleted() -> None:
    rows = [record(), record("old", address="192.0.2.20")]
    diff = _diff([lif()], rows, managed={("svm1", "old")})
    [change] = diff.changes
    assert change.kind == DELETE and change.key == ("svm1", "old")


def test_unmanaged_and_add_only_lifs_are_kept_and_reported() -> None:
    rows = [record(), record("other", address="192.0.2.20")]
    assert _diff([lif()], rows).unmanaged == ["svm1/other"]
    assert _diff([lif()], rows, managed=set()).unmanaged == ["svm1/other"]
    diff = _diff([lif()], rows, managed={("svm1", "other")}, add_only=True)
    assert diff.is_empty and diff.unmanaged == ["svm1/other"]


def test_cluster_scope_and_undeclared_svms_are_ignored() -> None:
    rows = [
        record(),
        record("mgmt", scope="cluster", svm=""),
        record("node-mgmt", scope="cluster", svm=""),
        record("elsewhere", svm="svm9"),
    ]
    diff = _diff([lif()], rows, managed={("", "mgmt"), ("svm9", "elsewhere")})
    assert diff.changes and all(c.key == ("svm9", "elsewhere") for c in diff.changes)
    assert diff.unmanaged == []


def test_off_home_lif_gets_a_warning_and_no_change() -> None:
    diff = _diff([lif()], [record(is_home=False)])
    assert diff.is_empty and "not on its home port" in diff.warnings[0]


def test_updating_the_management_lif_is_refused() -> None:
    diff = _diff([lif(auto_revert=True)], [record(address=HOST_IP)], host_ip=HOST_IP)
    assert len(diff.refusals) == 1 and "refusing to update LIF 'svm1/lif1'" in diff.refusals[0]


def test_deleting_the_management_lif_is_refused() -> None:
    diff = _diff([_absent(lif())], [record(address=HOST_IP)], host_ip=HOST_IP)
    assert "refusing to delete" in diff.refusals[0]


def test_other_lifs_and_creates_are_not_refused() -> None:
    assert _diff([lif(auto_revert=True)], [record()], host_ip=HOST_IP).refusals == []
    assert _diff([lif(address=HOST_IP)], [], host_ip=HOST_IP).refusals == []


def test_unresolvable_host_refuses_only_when_it_matters() -> None:
    refused = _diff([lif(auto_revert=True)], [record()], host_ip=None)
    assert "cannot resolve the management host" in refused.refusals[0]
    assert _diff([lif()], [], host_ip=None).refusals == []
    assert _diff([lif()], [record()], host_ip=None).refusals == []
