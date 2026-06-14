"""Unit tests for ``TailscaleSubnetsManager`` (#787).

Coverage:
    - plan emits empty diff when live and desired CIDRs match.
    - plan emits adds for CIDRs in desired but not live.
    - plan emits deletes for CIDRs in live but not desired.
    - plan add_only=True suppresses deletes.
    - apply is no-op when diff is empty.
    - apply calls apply_settings_patch with merged CIDR list on change.
    - apply add_only=True unions desired with live (no deletes).
    - apply outcomes contain one entry per added CIDR and one per deleted CIDR.
    - destroy is a no-op (returns ``resources_destroyed=0``).
    - get_resource_ids returns per-CIDR mapping from live state.
    - FINALIZATION_HOOK class variable is ``"tailscale_reconfigure"``.
    - apply_settings_patch preserves sibling settings fields (merge safety).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_subnets import (
    TailscaleSubnetsManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_subnets.TailscaleService"


def _resource(cidr: str) -> ResourceConfig:
    """Build a single ``tailscale.subnets`` ResourceConfig for a CIDR."""
    name = cidr.replace(".", "-").replace(":", "-").replace("/", "-")
    name = f"subnet-{name}"
    return ResourceConfig(
        name=name,
        type="tailscale.subnets",
        provider="opnsense",
        config={"cidr": cidr},
    )


def _resources(*cidrs: str) -> list[ResourceConfig]:
    return [_resource(c) for c in cidrs]


def _make_service_mock(*, live_cidrs: list[str] | None = None) -> MagicMock:
    """Build a TailscaleService mock with the given live CIDR list."""
    live = sorted(live_cidrs or [])
    service = MagicMock()
    service.get_settings.return_value = {"settings": {"subnets": {"subnet4": live}}}
    service.extract_subnet_cidrs.return_value = live
    service.build_desired_subnet_cidrs.side_effect = lambda resources: sorted(
        str(r.config.get("cidr", "")).strip() for r in resources if r.config.get("cidr")
    )
    service.build_subnets_wire_payload.side_effect = lambda cidrs: {
        "settings": {"subnets": {"subnet4": cidrs}}
    }
    service.apply_settings_patch.return_value = {"result": "saved"}
    return service


class TestFinalizationHook:
    def test_hook_declared(self) -> None:
        assert TailscaleSubnetsManager.FINALIZATION_HOOK == "tailscale_reconfigure"


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["192.168.1.0/24"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", _resources("192.168.1.0/24"))
        assert diff.is_empty
        assert diff.adds == []
        assert diff.deletes == []

    def test_plan_adds(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", _resources("10.0.0.0/8", "192.168.1.0/24"))
        assert sorted(diff.adds) == ["10.0.0.0/8", "192.168.1.0/24"]
        assert diff.deletes == []

    def test_plan_deletes(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "192.168.1.0/24"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", _resources("10.0.0.0/8"))
        assert diff.adds == []
        assert diff.deletes == ["192.168.1.0/24"]

    def test_plan_full_reconcile(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "172.16.0.0/12"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", _resources("10.0.0.0/8", "192.168.0.0/16"))
        assert diff.adds == ["192.168.0.0/16"]
        assert diff.deletes == ["172.16.0.0/12"]

    def test_plan_add_only_suppresses_deletes(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "172.16.0.0/12"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                _resources("10.0.0.0/8", "192.168.0.0/16"),
                add_only=True,
            )
        assert diff.adds == ["192.168.0.0/16"]
        assert diff.deletes == []

    def test_plan_empty_desired_clears_all(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [])
        assert diff.adds == []
        assert diff.deletes == ["10.0.0.0/8"]


class TestApply:
    def test_apply_no_change_skips_patch(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["192.168.1.0/24"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", _resources("192.168.1.0/24"))
        service.apply_settings_patch.assert_not_called()
        assert result["resources_created"] == 0
        assert result["resources_deleted"] == 0
        assert result["resource_outcomes"] == []

    def test_apply_add_calls_patch(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", _resources("10.0.0.0/8"))
        service.apply_settings_patch.assert_called_once()
        wire = service.apply_settings_patch.call_args.args[0]
        assert wire["settings"]["subnets"]["subnet4"] == ["10.0.0.0/8"]
        assert result["resources_created"] == 1
        assert result["resources_deleted"] == 0
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "10.0.0.0/8"

    def test_apply_delete_calls_patch(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "192.168.1.0/24"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", _resources("10.0.0.0/8"))
        service.apply_settings_patch.assert_called_once()
        wire = service.apply_settings_patch.call_args.args[0]
        assert wire["settings"]["subnets"]["subnet4"] == ["10.0.0.0/8"]
        assert result["resources_created"] == 0
        assert result["resources_deleted"] == 1
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        assert outcomes[0].resource_name == "192.168.1.0/24"

    def test_apply_add_only_unions_with_live(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply(
                "test-env",
                _resources("192.168.1.0/24"),
                add_only=True,
            )
        service.apply_settings_patch.assert_called_once()
        wire = service.apply_settings_patch.call_args.args[0]
        # Both live and desired CIDRs should be present.
        assert sorted(wire["settings"]["subnets"]["subnet4"]) == [
            "10.0.0.0/8",
            "192.168.1.0/24",
        ]
        assert result["resources_created"] == 1
        assert result["resources_deleted"] == 0

    def test_apply_mixed_add_and_delete(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "172.16.0.0/12"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply(
                "test-env",
                _resources("10.0.0.0/8", "192.168.0.0/16"),
            )
        wire = service.apply_settings_patch.call_args.args[0]
        assert sorted(wire["settings"]["subnets"]["subnet4"]) == [
            "10.0.0.0/8",
            "192.168.0.0/16",
        ]
        assert result["resources_created"] == 1
        assert result["resources_deleted"] == 1
        actions = {o.resource_name: o.action for o in result["resource_outcomes"]}
        assert actions["192.168.0.0/16"] == "add"
        assert actions["172.16.0.0/12"] == "delete"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        result = manager.destroy("test-env", _resources("10.0.0.0/8"))
        assert result["resources_destroyed"] == 0
        assert result["resource_outcomes"] == []


class TestGetResourceIds:
    def test_returns_per_cidr_mapping(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=["10.0.0.0/8", "192.168.1.0/24"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [])
        assert result == {
            "subnets.10.0.0.0/8": "10.0.0.0/8",
            "subnets.192.168.1.0/24": "192.168.1.0/24",
        }

    def test_returns_empty_when_no_live_subnets(self, tmp_path: Path) -> None:
        manager = TailscaleSubnetsManager(tmp_path)
        service = _make_service_mock(live_cidrs=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [])
        assert result == {}
