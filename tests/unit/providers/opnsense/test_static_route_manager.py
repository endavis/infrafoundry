"""Unit tests for ``StaticRouteManager``.

Coverage:
    - plan/apply/destroy delegate to StaticRouteService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - delete outcomes use the synthesized ``route-<network>-via-<gateway>`` name.
    - get_resource_ids maps live UUIDs to operator-facing names by tuple match.
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - add_only flag propagated to compute_diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.static_route import StaticRouteManager
from infrafoundry.providers.opnsense.services.static_route import (
    Diff,
    LiveStaticRoute,
    StaticRouteConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    network: str = "10.0.0.0/24",
    gateway: str = "WAN_DHCP",
    lock: bool = False,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "network": network,
        "gateway": gateway,
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="routing.static", provider="opnsense", config=config)


def _live(
    uuid: str,
    *,
    network: str = "10.0.0.0/24",
    gateway: str = "WAN_DHCP",
) -> LiveStaticRoute:
    return LiveStaticRoute(
        uuid=uuid,
        network=network,
        gateway=gateway,
        raw={
            "uuid": uuid,
            "network": network,
            "gateway": gateway,
            "disabled": "0",
            "descr": "",
        },
    )


def _route(name: str, **overrides: Any) -> StaticRouteConfig:
    return StaticRouteConfig(
        name=name,
        network=overrides.get("network", "10.0.0.0/24"),
        gateway=overrides.get("gateway", "WAN_DHCP"),
        enabled=overrides.get("enabled", True),
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.static_route.StaticRouteService"


def _make_service_mock(
    *,
    live: list[LiveStaticRoute] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``StaticRouteService`` with sensible defaults."""
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
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_route("foo")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
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
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_route("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_route("foo")])
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
        assert outcomes[0].address == "opnsense_static_route.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1")
        want = _route("foo")
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
        assert outcomes[0].address == "opnsense_static_route.foo"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", network="172.16.0.0/24", gateway="WAN_DHCP")
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
        # Live records carry no operator-facing name; address uses the
        # synthetic ``route-<network>-via-<gateway>`` form.
        assert outcomes[0].resource_name == "route-172-16-0-0-24-via-wan_dhcp"
        assert outcomes[0].address == "opnsense_static_route.route-172-16-0-0-24-via-wan_dhcp"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
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
    def test_destroy_deletes_matching_routes(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_matches_by_natural_key(self, tmp_path: Path) -> None:
        # YAML name is ``foo``, but identity matches by tuple — verify
        # that two tuples that don't match each other don't accidentally
        # collide on names.
        manager = StaticRouteManager(tmp_path)
        resources = [_resource("foo", network="10.0.0.0/24", gateway="WAN_DHCP")]
        live = [
            _live("u1", network="10.0.0.0/24", gateway="WAN_DHCP"),
            _live("u2", network="172.16.0.0/24", gateway="WAN_DHCP"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the matching tuple is deleted.
        service_mock.delete.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids_by_tuple(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [
            _resource("foo", network="10.0.0.0/24", gateway="WAN_DHCP"),
            _resource("bar", network="172.16.0.0/24", gateway="WAN_DHCP"),
        ]
        live = [
            _live("u1", network="10.0.0.0/24", gateway="WAN_DHCP"),
            _live("u2", network="172.16.0.0/24", gateway="WAN_DHCP"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        resources = [
            _resource("foo", network="10.0.0.0/24", gateway="WAN_DHCP"),
            _resource("missing", network="192.168.0.0/24", gateway="WAN_DHCP"),
        ]
        live = [_live("u1", network="10.0.0.0/24", gateway="WAN_DHCP")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_routes(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        live = [_live("u1"), _live("u2", network="172.16.0.0/24")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = StaticRouteManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
