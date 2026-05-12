"""Unit tests for ``RadvdManager`` and ``RadvdValidator`` (#788).

Coverage matches the test plan from the implementation plan comment:

Manager (``RadvdManager``):
    - test_plan_no_change
    - test_plan_add
    - test_plan_update
    - test_plan_delete
    - test_plan_full_reconcile
    - test_plan_add_only_skips_updates_and_deletes
    - test_apply_calls_per_record
    - test_destroy_deletes_all_live
    - test_get_resource_ids_returns_per_interface_uuids
    - test_finalization_hook_declared

Validator (``RadvdValidator``):
    - test_validator_rejects_invalid_mode
    - test_validator_rejects_min_gt_max
    - test_validator_xref_missing_interface
    - test_validator_xref_managed_assignment
    - test_validator_xref_live_only_interface (passes with INFO)

The manager tests patch ``RadvdService.from_environment`` so each test
hands the manager a pre-built mock with whatever live state is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.components.radvd import RadvdManager
from infrafoundry.providers.opnsense.services.radvd import RadvdService
from infrafoundry.providers.opnsense.validators.radvd_validator import RadvdValidator

SERVICE_PATH = "infrafoundry.providers.opnsense.components.radvd.RadvdService"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _resource(interfaces: dict[str, dict[str, Any]] | None = None) -> ResourceConfig:
    """Build a singleton ``radvd`` ResourceConfig from an interfaces mapping."""
    cfg: dict[str, Any] = {"interfaces": interfaces or {}}
    return ResourceConfig(name="settings", type="radvd", provider="opnsense", config=cfg)


def _opt1_record() -> dict[str, Any]:
    """Operator-form field map for opt1 — the canonical Infra-VLAN record."""
    return {
        "mode": "assist",
        "priority": "medium",
        "min_interval": "200",
        "max_interval": "600",
        "routes": ["fd00:3742:10:1::/64"],
        "dns_servers": [],
        "domain_search": [],
    }


def _opt2_record() -> dict[str, Any]:
    """Operator-form field map for opt2 — the PT-VLAN record."""
    return {
        "mode": "assist",
        "priority": "medium",
        "min_interval": "200",
        "max_interval": "600",
        "routes": ["fd00:3742:20:1::/64"],
    }


def _make_service_mock(
    *,
    live: dict[str, dict[str, Any]] | None = None,
    live_uuids: dict[str, str] | None = None,
) -> MagicMock:
    """Build a RadvdService mock with the given live state.

    The mock implements the diff/build helpers as their real counterparts
    would so the manager's plan/apply path exercises the actual diff
    algebra instead of relying on hardcoded mock returns.
    """
    live_records = live or {}
    uuids = live_uuids or {name: f"uuid-{name}" for name in live_records}

    service = MagicMock()
    service.extract_interface_records.return_value = live_records
    service.list_uuids_by_interface.return_value = uuids

    def _build_desired(resource: ResourceConfig) -> dict[str, dict[str, Any]]:
        # Mirror the real service: pull interfaces mapping, fill defaults.
        return RadvdService.build_desired_interface_records(service, resource)  # type: ignore[arg-type]

    service.build_desired_interface_records.side_effect = lambda r: (
        RadvdService.build_desired_interface_records(service, r)
    )
    service.compute_diff.side_effect = lambda live_, desired_: RadvdService.compute_diff(
        live_, desired_
    )
    service.wire_payload_for_interface.side_effect = lambda name, fields: (
        RadvdService.wire_payload_for_interface(name, fields)
    )
    service.add_record.return_value = {"result": "saved", "uuid": "new-uuid"}
    service.set_record.return_value = {"result": "saved"}
    service.del_record.return_value = {"result": "deleted"}
    return service


def _live_with(*pairs: tuple[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a fully-defaulted live state dict.

    Each (interface_name, partial_field_map) gets defaults applied so the
    diff equality check is symmetric with the desired side.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, partial in pairs:
        # Inject through build_desired_interface_records to apply defaults.
        # Use a tmp resource just for the defaults helper.
        defaulted = RadvdService.build_desired_interface_records(
            MagicMock(spec=RadvdService),
            _resource({name: partial}),
        )
        out[name] = defaulted[name]
    return out


# ---------------------------------------------------------------------------
# Manager: plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        """live + YAML match → empty diff."""
        manager = RadvdManager(tmp_path)
        live = _live_with(("opt1", _opt1_record()))
        service = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource({"opt1": _opt1_record()})])
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []

    def test_plan_add(self, tmp_path: Path) -> None:
        """YAML adds opt2 not in live → 1 add."""
        manager = RadvdManager(tmp_path)
        live = _live_with(("opt1", _opt1_record()))
        service = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                [_resource({"opt1": _opt1_record(), "opt2": _opt2_record()})],
            )
        assert len(diff.adds) == 1
        assert diff.adds[0][0] == "opt2"
        assert diff.updates == []
        assert diff.deletes == []

    def test_plan_update(self, tmp_path: Path) -> None:
        """YAML changes opt1.priority → 1 update."""
        manager = RadvdManager(tmp_path)
        live = _live_with(("opt1", _opt1_record()))
        service = _make_service_mock(live=live)
        changed = _opt1_record() | {"priority": "high"}
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource({"opt1": changed})])
        assert diff.adds == []
        assert len(diff.updates) == 1
        assert diff.updates[0][0] == "opt1"
        # update tuple is (name, desired_fields, live_fields)
        assert diff.updates[0][1]["priority"] == "high"
        assert diff.updates[0][2]["priority"] == "medium"
        assert diff.deletes == []

    def test_plan_delete(self, tmp_path: Path) -> None:
        """live has opt3, YAML doesn't → 1 delete."""
        manager = RadvdManager(tmp_path)
        live = _live_with(("opt3", _opt2_record()))
        service = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource({})])
        assert diff.adds == []
        assert diff.updates == []
        assert len(diff.deletes) == 1
        assert diff.deletes[0][0] == "opt3"

    def test_plan_full_reconcile(self, tmp_path: Path) -> None:
        """add + update + delete combined in one run."""
        manager = RadvdManager(tmp_path)
        # Live: opt1 (will be updated), opt3 (will be deleted).
        live = _live_with(
            ("opt1", _opt1_record()),
            ("opt3", _opt2_record()),
        )
        service = _make_service_mock(live=live)
        # Desired: opt1 changed, opt2 new, opt3 absent.
        desired_yaml = {
            "opt1": _opt1_record() | {"priority": "high"},
            "opt2": _opt2_record(),
        }
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(desired_yaml)])
        assert [name for name, _ in diff.adds] == ["opt2"]
        assert [name for name, _, _ in diff.updates] == ["opt1"]
        assert [name for name, _ in diff.deletes] == ["opt3"]

    def test_plan_add_only_skips_updates_and_deletes(self, tmp_path: Path) -> None:
        """add-only mode zeroes updates + deletes."""
        manager = RadvdManager(tmp_path)
        live = _live_with(
            ("opt1", _opt1_record()),
            ("opt3", _opt2_record()),
        )
        service = _make_service_mock(live=live)
        desired_yaml = {
            "opt1": _opt1_record() | {"priority": "high"},
            "opt2": _opt2_record(),
        }
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(desired_yaml)], add_only=True)
        # Adds preserved; updates and deletes suppressed.
        assert [name for name, _ in diff.adds] == ["opt2"]
        assert diff.updates == []
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# Manager: apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_calls_per_record(self, tmp_path: Path) -> None:
        """apply with adds=2, updates=1, deletes=1 → 4 service calls in correct order."""
        manager = RadvdManager(tmp_path)
        # Live: opt1 (update), opt3 (delete).
        live = _live_with(
            ("opt1", _opt1_record()),
            ("opt3", _opt2_record()),
        )
        service = _make_service_mock(live=live)
        # Desired: opt1 changed, opt2 + opt6 new, opt3 absent → 2 adds, 1 update, 1 delete.
        desired_yaml = {
            "opt1": _opt1_record() | {"priority": "high"},
            "opt2": _opt2_record(),
            "opt6": _opt2_record() | {"routes": ["fd00:3742:40:1::/64"]},
        }
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(desired_yaml)])

        assert result["resources_created"] == 2
        assert result["resources_updated"] == 1
        assert result["resources_deleted"] == 1

        # Per-record write counts.
        assert service.add_record.call_count == 2
        assert service.set_record.call_count == 1
        assert service.del_record.call_count == 1

        # Outcomes carry the right actions.
        actions = [(o.action, o.resource_name) for o in result["resource_outcomes"]]
        # Adds first (opt2, opt6, sorted), then update (opt1), then delete (opt3).
        assert actions == [
            ("add", "opt2"),
            ("add", "opt6"),
            ("update", "opt1"),
            ("delete", "opt3"),
        ]


class TestDestroy:
    def test_destroy_deletes_all_live(self, tmp_path: Path) -> None:
        """destroy nukes every live radvd record."""
        manager = RadvdManager(tmp_path)
        live_uuids = {"opt1": "uuid-opt1", "opt2": "uuid-opt2", "opt3": "uuid-opt3"}
        service = _make_service_mock(live={}, live_uuids=live_uuids)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_resource({})])
        # del_record called once per live UUID.
        assert service.del_record.call_count == 3
        called_uuids = sorted(call.args[0] for call in service.del_record.call_args_list)
        assert called_uuids == sorted(live_uuids.values())
        assert result["resources_destroyed"] == 3
        assert result["locked_skipped"] == 0


class TestGetResourceIds:
    def test_get_resource_ids_returns_per_interface_uuids(self, tmp_path: Path) -> None:
        """get_resource_ids returns ``{"interfaces.<name>": uuid, ...}``."""
        manager = RadvdManager(tmp_path)
        live_uuids = {"opt1": "uuid-1", "opt2": "uuid-2"}
        service = _make_service_mock(live={}, live_uuids=live_uuids)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [_resource({})])
        assert result == {"interfaces.opt1": "uuid-1", "interfaces.opt2": "uuid-2"}


class TestFinalizationHook:
    def test_finalization_hook_declared(self) -> None:
        """RadvdManager.FINALIZATION_HOOK == 'radvd_reconfigure'."""
        assert RadvdManager.FINALIZATION_HOOK == "radvd_reconfigure"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


def _passes(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and c.passed and c.level == ValidationLevel.INFO
    ]


class TestValidator:
    def test_validator_rejects_invalid_mode(self) -> None:
        report = ValidationReport()
        validator = RadvdValidator(report)
        validator.validate(
            [_resource({"opt1": {"mode": "bogus"}})],
            interface_assignment_names={"opt1"},
            existing_interfaces={},
        )
        assert _failures(report, "radvd_opt1_mode")

    def test_validator_rejects_min_gt_max(self) -> None:
        report = ValidationReport()
        validator = RadvdValidator(report)
        validator.validate(
            [_resource({"opt1": {"min_interval": 600, "max_interval": 200}})],
            interface_assignment_names={"opt1"},
            existing_interfaces={},
        )
        assert _failures(report, "radvd_opt1_interval_order")

    def test_validator_xref_missing_interface(self) -> None:
        report = ValidationReport()
        validator = RadvdValidator(report)
        validator.validate(
            [_resource({"optZZ": {"mode": "assist"}})],
            interface_assignment_names=set(),
            existing_interfaces={},
        )
        assert _failures(report, "radvd_optZZ_interface")

    def test_validator_xref_managed_assignment(self) -> None:
        report = ValidationReport()
        validator = RadvdValidator(report)
        validator.validate(
            [_resource({"opt1": {"mode": "assist"}})],
            interface_assignment_names={"opt1"},
            existing_interfaces={},
        )
        assert not _failures(report, "radvd_opt1_interface")
        # Managed assignment should produce a passing INFO check.
        assert _passes(report, "radvd_opt1_interface")

    def test_validator_xref_live_only_interface(self) -> None:
        """Interface only in live overview (not managed YAML) passes with INFO."""
        report = ValidationReport()
        validator = RadvdValidator(report)
        validator.validate(
            [_resource({"opt99": {"mode": "assist"}})],
            interface_assignment_names=set(),
            existing_interfaces={"opt99": {"if_type": "vlan"}},
        )
        assert not _failures(report, "radvd_opt99_interface")
        assert _passes(report, "radvd_opt99_interface")
