"""End to end: state and deletes are kept per firewall (#1450).

Real runner, real forward manager and diff engine, and a real SQLite state database.
Only the OPNsense service is mocked; no box is contacted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.managed_set import build_managed_resources
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.core.state import ResourceState, StateManager
from infrafoundry.providers.opnsense.components.unbound_forward import UnboundForwardManager
from infrafoundry.providers.opnsense.services import unbound_forward as forward_service

SERVICE_PATH = "infrafoundry.providers.opnsense.components.unbound_forward.UnboundForwardService"
TYPE = "unbound.forwards"
PROVIDERS = ("opnsense", "opnsense@fw-b")


def _config(domain: str) -> dict[str, Any]:
    return {"type": "dot", "domain": domain, "server": "1.1.1.1", "port": 853}


def _live(uuid: str, domain: str) -> forward_service.LiveUnboundForward:
    return forward_service.LiveUnboundForward(
        uuid=uuid, type="dot", domain=domain, server="1.1.1.1", port="853"
    )


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


@pytest.fixture
def state(tmp_path: Path) -> StateManager:
    manager = StateManager(connection_string=f"sqlite:///{tmp_path / 'state.db'}")
    manager.initialize()
    return manager


def _provider(tmp_path: Path, name: str) -> MagicMock:
    provider = MagicMock()
    provider.name = name
    provider._current_environment = "dev"
    provider.config_dir = tmp_path
    provider.firewall_label.return_value = None
    provider.get_direct_api_resource_types.return_value = {TYPE: UnboundForwardManager}
    return provider


def _managed(state: StateManager, name: str) -> Any:
    return build_managed_resources(state.get_managed_resources("dev", name), name)


def _track_on_both(state: StateManager, domain: str) -> None:
    deployment_id = state.create_deployment("dev", "apply")
    for provider in PROVIDERS:
        state.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider=provider,
            resource_type=TYPE,
            name="f1",
            state=ResourceState.ACTIVE,
            config=_config(domain),
        )


def test_state_rows_are_kept_under_each_firewalls_provider_id(state: StateManager) -> None:
    _track_on_both(state, "mine.lan")
    assert {r.name for r in _managed(state, "opnsense")[TYPE]} == {"f1"}
    assert {r.name for r in _managed(state, "opnsense@fw-b")[TYPE]} == {"f1"}
    assert len(state.get_managed_resources("dev", "opnsense")) == 1
    assert len(state.get_managed_resources("dev", "opnsense@fw-b")) == 1


def test_removing_a_resource_on_fw_b_deletes_only_from_fw_b(
    state: StateManager, tmp_path: Path
) -> None:
    _track_on_both(state, "mine.lan")
    live = [_live("u-mine", "mine.lan"), _live("u-hand", "hand.lan")]
    runner = OPNsenseDirectRunner()
    services: dict[str, MagicMock] = {}

    def from_environment(env: str, provider_name: str, config_dir: Path) -> MagicMock:
        services[provider_name] = _service(live)
        return services[provider_name]

    # fw-a still declares f1; fw-b's YAML no longer has it.
    fw_a = _provider(tmp_path, "opnsense")
    fw_b = _provider(tmp_path, "opnsense@fw-b")
    kept = ResourceConfig(name="f1", type=TYPE, provider="opnsense", config=_config("mine.lan"))
    with patch(SERVICE_PATH) as svc_cls:
        svc_cls.from_environment.side_effect = from_environment
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[kept]):
            result_a = runner.apply(fw_a, managed_resources=_managed(state, "opnsense"))
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result_b = runner.apply(fw_b, managed_resources=_managed(state, "opnsense@fw-b"))

    assert result_a["resources_deleted"] == 0
    assert result_b["resources_deleted"] == 1
    deleted = services["opnsense@fw-b"].apply_diff.call_args.args[0].deletes
    assert [d.uuid for d in deleted] == ["u-mine"]
    assert result_b["released_resources"] == [{"resource_type": TYPE, "name": "f1"}]
    # Each firewall's service was addressed under its own provider id.
    assert set(services) == {"opnsense", "opnsense@fw-b"}
