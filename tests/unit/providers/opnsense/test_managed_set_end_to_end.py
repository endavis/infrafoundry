"""End to end: removing the last forward deletes it, a hand-added one stays (#1256).

Uses the real runner, the real forward manager and diff engine, and a real SQLite
state database. Only the OPNsense service is mocked; no box is contacted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.managed_set import build_managed_resources
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.core.state import ResourceState, StateManager
from infrafoundry.providers.opnsense.components.unbound_forward import UnboundForwardManager
from infrafoundry.providers.opnsense.services import unbound_forward as forward_service

SERVICE_PATH = "infrafoundry.providers.opnsense.components.unbound_forward.UnboundForwardService"
TYPE = "unbound.forwards"


def _forward_config(domain: str) -> dict[str, Any]:
    return {"type": "dot", "domain": domain, "server": "1.1.1.1", "port": 853}


def _live(uuid: str, domain: str) -> forward_service.LiveUnboundForward:
    return forward_service.LiveUnboundForward(
        uuid=uuid, type="dot", domain=domain, server="1.1.1.1", port="853"
    )


@pytest.fixture
def state(tmp_path: Path) -> StateManager:
    manager = StateManager(connection_string=f"sqlite:///{tmp_path / 'state.db'}")
    manager.initialize()
    return manager


@pytest.fixture
def provider(tmp_path: Path) -> MagicMock:
    provider = MagicMock()
    provider.name = "opnsense"
    provider._current_environment = "dev"
    provider.config_dir = tmp_path
    provider.get_direct_api_resource_types.return_value = {TYPE: UnboundForwardManager}
    return provider


def _service(live: list[forward_service.LiveUnboundForward]) -> MagicMock:
    service = MagicMock()
    service.search.return_value = live
    service.compute_diff.side_effect = forward_service.compute_diff
    service.apply_diff.side_effect = lambda diff: {
        "created": len(diff.adds),
        "updated": len(diff.updates),
        "deleted": len(diff.deletes),
    }
    return service


def _managed(state: StateManager) -> Any:
    return build_managed_resources(state.get_managed_resources("dev", "opnsense"), "opnsense")


def _mark_applied(state: StateManager, deployment_id: int, name: str, domain: str) -> None:
    state.track_resource(
        deployment_id=deployment_id,
        environment="dev",
        provider="opnsense",
        resource_type=TYPE,
        name=name,
        state=ResourceState.ACTIVE,
        config=_forward_config(domain),
    )


def _release(state: StateManager, deployment_id: int, result: dict[str, Any], managed: Any) -> None:
    executor = DeploymentExecutor(
        runner_registry=MagicMock(),
        state_manager=state,
        event_manager=MagicMock(),
        providers={},
    )
    executor._record_released_resources(
        result.get("released_resources"),
        managed,
        deployment_id=deployment_id,
        env_name="dev",
        provider_name="opnsense",
    )


def test_removing_last_forward_deletes_it_and_keeps_hand_added(
    state: StateManager, provider: MagicMock
) -> None:
    deployment_id = state.create_deployment("dev", "apply")
    _mark_applied(state, deployment_id, "f1", "mine.lan")
    live = [_live("u-mine", "mine.lan"), _live("u-hand", "hand.lan")]
    runner = OPNsenseDirectRunner()

    # The YAML no longer has any forward; the managed set still has f1.
    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]),
        patch(SERVICE_PATH) as svc_cls,
    ):
        svc_cls.from_environment.return_value = _service(live)
        plan = runner.plan(provider, managed_resources=_managed(state))
        assert plan["has_changes"] is True
        assert "1 to delete" in plan["changes_summary"]
        assert "1 unmanaged (kept)" in plan["changes_summary"]

        service = _service(live)
        svc_cls.from_environment.return_value = service
        managed = _managed(state)
        result = runner.apply(provider, managed_resources=managed)

    assert result["resources_deleted"] == 1
    deleted = service.apply_diff.call_args.args[0].deletes
    assert [d.uuid for d in deleted] == ["u-mine"]
    assert result["released_resources"] == [{"resource_type": TYPE, "name": "f1"}]

    # The executor records the release; the next plan no longer dispatches the type.
    _release(state, deployment_id, dict(result), managed)
    assert _managed(state) == {}
    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]),
        patch(SERVICE_PATH) as svc_cls,
    ):
        again = runner.plan(provider, managed_resources=_managed(state))
    svc_cls.from_environment.assert_not_called()
    assert again["has_changes"] is False


def test_hand_added_forward_is_never_deleted_with_yaml_entries(
    state: StateManager, provider: MagicMock
) -> None:
    deployment_id = state.create_deployment("dev", "apply")
    _mark_applied(state, deployment_id, "f1", "mine.lan")
    yaml_rows = [
        ResourceConfig(
            name="f1", type=TYPE, provider="opnsense", config=_forward_config("mine.lan")
        )
    ]
    live = [_live("u-mine", "mine.lan"), _live("u-hand", "hand.lan")]
    service = _service(live)

    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=yaml_rows),
        patch(SERVICE_PATH) as svc_cls,
    ):
        svc_cls.from_environment.return_value = service
        result = OPNsenseDirectRunner().apply(provider, managed_resources=_managed(state))

    assert result["resources_deleted"] == 0
    assert service.apply_diff.call_args.args[0].deletes == []
    assert "released_resources" not in result


def test_hand_added_forward_is_never_deleted_without_yaml_entries(
    state: StateManager, provider: MagicMock
) -> None:
    """Nothing InfraFoundry applied: the type is not even dispatched."""
    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]),
        patch(SERVICE_PATH) as svc_cls,
    ):
        result = OPNsenseDirectRunner().apply(provider, managed_resources=_managed(state))

    svc_cls.from_environment.assert_not_called()
    assert result["resources_deleted"] == 0


def test_unresolvable_managed_row_is_not_released_and_stays_managed(
    state: StateManager, provider: MagicMock
) -> None:
    """A row that cannot yield a key keeps its ACTIVE row so the next run retries it."""
    deployment_id = state.create_deployment("dev", "apply")
    _mark_applied(state, deployment_id, "gone", "gone.lan")
    state.track_resource(
        deployment_id=deployment_id,
        environment="dev",
        provider="opnsense",
        resource_type=TYPE,
        name="stuck",
        state=ResourceState.ACTIVE,
        config={"type": "dot", "port": "not-a-port"},
    )
    runner = OPNsenseDirectRunner()
    managed = _managed(state)

    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]),
        patch(SERVICE_PATH) as svc_cls,
    ):
        svc_cls.from_environment.return_value = _service([_live("u-hand", "hand.lan")])
        result = runner.apply(provider, managed_resources=managed)

    # "gone" resolved to a key but is not live: released. "stuck" is kept.
    assert result["released_resources"] == [{"resource_type": TYPE, "name": "gone"}]
    _release(state, deployment_id, dict(result), managed)
    assert [r.name for r in state.get_managed_resources("dev", "opnsense")] == ["stuck"]
