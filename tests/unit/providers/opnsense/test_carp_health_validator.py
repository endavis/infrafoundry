"""Unit tests for the CARP pair health evaluator (#1393)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.carp_health_validator import CarpHealthValidator
from infrafoundry.providers.opnsense.validators.context import (
    HaPeerCheck,
    OPNsenseValidationContext,
)

PEER = "192.0.2.2"
CARP_OK = {"demotion": "0", "allow": "1", "maintenancemode": False, "status_msg": ""}


def _row(status: str, vhid: int = 1) -> dict[str, Any]:
    return {
        "interface": "lan",
        "vhid": str(vhid),
        "subnet": "198.51.100.1",
        "status": status,
        "mode": "carp",
    }


def _run(
    rows: list[Any],
    *,
    target: str = "",
    peer: HaPeerCheck | None = None,
    carp: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
    primary: str = "",
) -> ValidationReport:
    report = ValidationReport()
    live = status if status is not None else {"rows": rows, "carp": carp or CARP_OK}
    ctx = OPNsenseValidationContext(
        resources=[],
        live_carp_status=live,
        live_sync_target=target,
        peer_check=peer,
        ha_primary_label=primary,
    )
    CarpHealthValidator(report).validate(ctx)
    return report


def _by_name(report: ValidationReport) -> dict[str, Any]:
    return {r.check_name: r for r in report.results}


def test_single_node_is_silent() -> None:
    assert _run([]).results == []


def test_unread_status_adds_nothing() -> None:
    report = ValidationReport()
    ctx = OPNsenseValidationContext(resources=[], live_carp_status=None, live_sync_target=PEER)
    CarpHealthValidator(report).validate(ctx)
    assert report.results == []


def test_healthy_master() -> None:
    peer = HaPeerCheck(ok=True, version="26.1.11", answered=True)
    results = _by_name(_run([_row("MASTER"), _row("MASTER", 2)], target=PEER, peer=peer))
    assert all(r.passed for r in results.values())
    assert "MASTER" in results["opnsense_carp_vip_1"].message
    assert "198.51.100.1 vhid 2 on lan" in results["opnsense_carp_vip_2"].message
    assert "26.1.11" in results["opnsense_ha_peer"].message


def test_sync_source_backup_is_an_error() -> None:
    peer = HaPeerCheck(ok=True, answered=True)
    results = _by_name(_run([_row("BACKUP")], target=PEER, peer=peer))
    vip = results["opnsense_carp_vip_1"]
    assert not vip.passed
    assert vip.level == ValidationLevel.ERROR
    assert "expected MASTER" in vip.message


def test_mixed_states_on_unknown_role() -> None:
    results = _by_name(_run([_row("MASTER"), _row("BACKUP", 2)]))
    assert results["opnsense_carp_role"].level == ValidationLevel.WARNING
    split = results["opnsense_carp_split"]
    assert split.level == ValidationLevel.ERROR
    assert "1 VIP(s) MASTER" in split.message
    assert "1 VIP(s) BACKUP" in split.message


def test_backup_node_of_unknown_role() -> None:
    results = _by_name(_run([_row("BACKUP"), _row("BACKUP", 2)]))
    assert results["opnsense_carp_role"].level == ValidationLevel.WARNING
    assert results["opnsense_carp_vip_1"].passed
    assert "opnsense_carp_split" not in results


def test_init_and_disabled_are_errors_in_both_roles() -> None:
    for target in ("", PEER):
        results = _by_name(_run([_row("INIT"), _row("DISABLED", 2)], target=target))
        for key in ("opnsense_carp_vip_1", "opnsense_carp_vip_2"):
            assert not results[key].passed
            assert results[key].level == ValidationLevel.ERROR


def test_carp_block_findings() -> None:
    carp = {"demotion": "240", "allow": "0", "maintenancemode": True}
    results = _by_name(_run([_row("MASTER")], target=PEER, carp=carp))
    assert results["opnsense_carp_allow"].level == ValidationLevel.ERROR
    assert results["opnsense_carp_maintenance"].level == ValidationLevel.WARNING
    assert results["opnsense_carp_demotion"].level == ValidationLevel.WARNING
    assert "240" in results["opnsense_carp_demotion"].message


def test_zero_demotion_and_text_maintenance_flag() -> None:
    carp = {"demotion": "x", "allow": "1", "maintenancemode": "1"}
    results = _by_name(_run([_row("MASTER")], target=PEER, carp=carp))
    assert "opnsense_carp_demotion" not in results
    assert "opnsense_carp_maintenance" in results


def test_unreachable_peer_while_master() -> None:
    peer = HaPeerCheck(ok=False, message="fetch error. remote host down?")
    result = _by_name(_run([_row("MASTER")], target=PEER, peer=peer))["opnsense_ha_peer"]
    assert result.level == ValidationLevel.ERROR
    assert "remote host down?" in result.message
    assert "both-MASTER split cannot be ruled out" in result.message


def test_unreachable_peer_without_vips_has_no_split_note() -> None:
    peer = HaPeerCheck(ok=False, message="timeout")
    result = _by_name(_run([], target=PEER, peer=peer))["opnsense_ha_peer"]
    assert result.level == ValidationLevel.ERROR
    assert "split" not in result.message


def test_peer_without_version_is_a_warning() -> None:
    peer = HaPeerCheck(ok=True, answered=False)
    result = _by_name(_run([_row("MASTER")], target=PEER, peer=peer))["opnsense_ha_peer"]
    assert result.level == ValidationLevel.WARNING


def test_peer_success_without_firmware() -> None:
    peer = HaPeerCheck(ok=True, answered=True)
    result = _by_name(_run([], target=PEER, peer=peer))["opnsense_ha_peer"]
    assert result.passed
    assert "firmware" not in result.message


def test_sync_target_without_rows_reports_only_the_peer() -> None:
    peer = HaPeerCheck(ok=True, version="26.1.11", answered=True)
    results = _by_name(_run([], target=PEER, peer=peer))
    assert set(results) == {"opnsense_ha_peer"}


def test_sync_target_without_peer_result_adds_nothing_for_peer() -> None:
    assert "opnsense_ha_peer" not in _by_name(_run([_row("MASTER")], target=PEER))


def test_malformed_rows_are_skipped() -> None:
    report = _run(["junk", 3, {"vhid": "1"}, _row("MASTER")], target=PEER)
    results = _by_name(report)
    assert results["opnsense_carp_vip_1"].level == ValidationLevel.ERROR
    assert results["opnsense_carp_vip_2"].passed


def test_rows_not_a_list() -> None:
    assert _run([], status={"rows": "x", "carp": CARP_OK}).results == []


def test_declared_backup_all_backup_passes_without_warning() -> None:
    report = _run([_row("BACKUP"), _row("BACKUP", 2)], primary="fw-a")
    results = _by_name(report)
    assert results["opnsense_carp_role"].passed
    assert "fw-a" in results["opnsense_carp_role"].message
    assert results["opnsense_carp_vip_1"].passed
    assert not report.has_errors()
    assert not report.has_warnings()


def test_declared_backup_master_vip_is_an_error() -> None:
    report = _run([_row("MASTER")], primary="fw-a")
    result = _by_name(report)["opnsense_carp_vip_1"]
    assert result.level is ValidationLevel.ERROR
    assert "expected BACKUP on the ha_backup of fw-a" in result.message


def test_declared_backup_mixed_has_no_split_result() -> None:
    report = _run([_row("BACKUP"), _row("MASTER", 2)], primary="fw-a")
    names = _by_name(report)
    assert "opnsense_carp_split" not in names
    assert names["opnsense_carp_vip_2"].level is ValidationLevel.ERROR


def test_declared_backup_init_is_an_error() -> None:
    report = _run([_row("INIT")], primary="fw-a")
    assert _by_name(report)["opnsense_carp_vip_1"].level is ValidationLevel.ERROR


def test_declared_backup_with_sync_target_still_checks_the_peer() -> None:
    report = _run(
        [_row("BACKUP")], target=PEER, peer=HaPeerCheck(ok=True, answered=True), primary="fw-a"
    )
    results = _by_name(report)
    assert results["opnsense_ha_peer"].passed
    assert results["opnsense_carp_vip_1"].passed


def test_declared_backup_with_no_rows_is_silent() -> None:
    assert _run([], primary="fw-a").results == []
