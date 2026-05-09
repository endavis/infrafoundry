"""Unit tests for ``GatewayManager``.

Coverage:
    - plan/apply/destroy delegate to GatewayService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - get_resource_ids maps live UUIDs to operator-facing names.
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - Dynamic / virtual gateways excluded from get_resource_ids and destroy.
    - add_only flag propagated to compute_diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.gateway import GatewayManager
from infrafoundry.providers.opnsense.services.gateway import (
    Diff,
    GatewayConfig,
    LiveGateway,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(name: str, *, lock: bool = False) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": "wan",
        "protocol": "inet",
        "gateway": "192.0.2.1",
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="routing.gateways", provider="opnsense", config=config)


def _live_managed(uuid: str, name: str) -> LiveGateway:
    return LiveGateway(
        uuid=uuid,
        name=name,
        is_managed=True,
        raw={"uuid": uuid, "name": name},
    )


def _live_dynamic(name: str) -> LiveGateway:
    return LiveGateway(
        uuid=name,  # dynamic gateways have synthetic uuid = name
        name=name,
        is_managed=False,
        raw={"uuid": name, "name": name, "dynamic": True, "virtual": True},
    )


def _gw(name: str, **overrides: Any) -> GatewayConfig:
    return GatewayConfig(
        name=name,
        interface=overrides.get("interface", "wan"),
        protocol=overrides.get("protocol", "inet"),
        gateway=overrides.get("gateway", "192.0.2.1"),
        enabled=overrides.get("enabled", True),
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.gateway.GatewayService"


def _make_service_mock(
    *,
    live: list[LiveGateway] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``GatewayService`` with sensible defaults."""
    service = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    return service


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_returns_diff(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_gw("foo")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_gw("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_gw("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_gateway.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        live = _live_managed("u1", "foo")
        want = _gw("foo")
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 1, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "foo"

    def test_apply_emits_delete_outcome(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live_managed("u1", "stale")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        assert outcomes[0].resource_name == "stale"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_managed_gateways(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("wan-survival", lock=True)]
        live = [_live_managed("u1", "wan-survival")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_ignores_dynamic_live(self, tmp_path: Path) -> None:
        # YAML lists ``WAN_DHCP``; live is dynamic — destroy must not touch it.
        manager = GatewayManager(tmp_path)
        resources = [_resource("WAN_DHCP")]
        live = [_live_dynamic("WAN_DHCP")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["resources_destroyed"] == 0


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo"), _resource("bar")]
        live = [_live_managed("u1", "foo"), _live_managed("u2", "bar")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        resources = [_resource("foo"), _resource("missing")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_dynamic_live_excluded(self, tmp_path: Path) -> None:
        # Dynamic live gateway with same name as a YAML resource: the
        # mapping never includes it (operator can't reference dynamics by
        # UUID for IaC purposes).
        manager = GatewayManager(tmp_path)
        resources = [_resource("WAN_DHCP")]
        live = [_live_dynamic("WAN_DHCP")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_gateways(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        live = [_live_managed("u1", "foo"), _live_dynamic("WAN_DHCP")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        # ``list`` doesn't filter — it surfaces both kinds for inspection.
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = GatewayManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
