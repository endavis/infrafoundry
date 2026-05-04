"""Unit tests for ``UnboundForwardManager``.

Coverage:
    - plan/apply/destroy delegate to UnboundForwardService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - delete outcomes use the synthesized ``forward-<type>-<domain>-<server>-<port>`` name.
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
from infrafoundry.providers.opnsense.components.unbound_forward import UnboundForwardManager
from infrafoundry.providers.opnsense.services.unbound_forward import (
    Diff,
    LiveUnboundForward,
    UnboundForwardConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    type: str = "forward",
    domain: str = "",
    server: str = "10.0.0.53",
    port: int | str = 53,
    lock: bool = False,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "type": type,
        "domain": domain,
        "server": server,
        "port": port,
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="unbound_forward", provider="opnsense", config=config)


def _live(
    uuid: str,
    *,
    type: str = "forward",
    domain: str = "",
    server: str = "10.0.0.53",
    port: str = "53",
) -> LiveUnboundForward:
    return LiveUnboundForward(
        uuid=uuid,
        type=type,
        domain=domain,
        server=server,
        port=port,
        raw={
            "uuid": uuid,
            "type": type,
            "domain": domain,
            "server": server,
            "port": port,
            "enabled": "1",
            "description": "",
            "verify": "",
            "forward_tcp_upstream": "0",
            "forward_first": "0",
        },
    )


def _forward(name: str, **overrides: Any) -> UnboundForwardConfig:
    return UnboundForwardConfig(
        name=name,
        type=overrides.get("type", "forward"),
        domain=overrides.get("domain", ""),
        server=overrides.get("server", "10.0.0.53"),
        port=overrides.get("port", "53"),
        enabled=overrides.get("enabled", True),
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.unbound_forward.UnboundForwardService"


def _make_service_mock(
    *,
    live: list[LiveUnboundForward] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``UnboundForwardService`` with sensible defaults."""
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
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_forward("foo")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
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
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_forward("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_forward("foo")])
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
        assert outcomes[0].address == "opnsense_unbound_forward.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1")
        want = _forward("foo")
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
        assert outcomes[0].address == "opnsense_unbound_forward.foo"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", type="forward", domain="x.example", server="10.0.0.99", port="53")
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
        assert outcomes[0].resource_name == "forward-forward-x-example-10-0-0-99-53"
        assert (
            outcomes[0].address == "opnsense_unbound_forward.forward-forward-x-example-10-0-0-99-53"
        )

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
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
    def test_destroy_deletes_matching_forwards(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
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
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_matches_by_natural_key(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [_resource("foo", server="10.0.0.53")]
        live = [
            _live("u1", server="10.0.0.53"),
            _live("u2", server="10.0.0.99"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids_by_tuple(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [
            _resource("foo", server="10.0.0.53"),
            _resource("bar", server="10.0.0.99"),
        ]
        live = [
            _live("u1", server="10.0.0.53"),
            _live("u2", server="10.0.0.99"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        resources = [
            _resource("foo", server="10.0.0.53"),
            _resource("missing", server="10.0.0.111"),
        ]
        live = [_live("u1", server="10.0.0.53")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_forwards(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        live = [_live("u1"), _live("u2", server="10.0.0.99")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = UnboundForwardManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
