"""The orchestrator registers one provider per declared firewall (#1450)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.provider import ResourceConfig


class _Base:
    def __init__(self) -> None:
        self.name = "opnsense"
        self.spawned: list[str] = []

    def spawn_instance(self, name: str) -> Any:
        self.spawned.append(name)
        return Mock(name=f"opnsense@{name}")


def _orchestrator(tmp_path: Path, settings: Any, *, load_error: bool = False) -> Orchestrator:
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = tmp_path
    config_manager.get_all_resources_all_providers.return_value = [
        ResourceConfig(name="a", type="t", provider="opnsense", config={})
    ]
    config_manager.get_package_events.return_value = {}
    if load_error:
        config_manager.load_environment.side_effect = FileNotFoundError
    else:
        config_manager.load_environment.return_value = EnvironmentConfig(
            name="dev", provider_settings=settings
        )
    orchestrator = Orchestrator(config_manager=config_manager, output_dir=tmp_path / "out")
    orchestrator.providers["opnsense"] = _Base()  # type: ignore[assignment]
    return orchestrator


def test_declared_firewalls_are_registered_without_any_yaml(tmp_path: Path) -> None:
    settings = {"opnsense": {"primary": "fw-a", "firewalls": {"fw-a": {}, "fw-b": {}}}}
    orchestrator = _orchestrator(tmp_path, settings)
    orchestrator._load_resources("dev")
    assert "opnsense@fw-b" in orchestrator.providers
    assert "opnsense@fw-a" not in orchestrator.providers


def test_loading_twice_registers_each_instance_once(tmp_path: Path) -> None:
    settings = {"opnsense": {"primary": "fw-a", "firewalls": {"fw-a": {}, "fw-b": {}}}}
    orchestrator = _orchestrator(tmp_path, settings)
    orchestrator._load_resources("dev")
    orchestrator._load_resources("dev")
    assert orchestrator.providers["opnsense"].spawned == ["fw-b"]  # type: ignore[attr-defined]


@pytest.mark.parametrize("settings", [{}, {"opnsense": {"api_url": "https://fw.example.com"}}])
def test_flat_settings_register_nothing(tmp_path: Path, settings: dict[str, Any]) -> None:
    orchestrator = _orchestrator(tmp_path, settings)
    orchestrator._load_resources("dev")
    assert list(orchestrator.providers) == ["opnsense"]


def test_missing_settings_file_is_not_an_error(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, {}, load_error=True)
    _, by_provider = orchestrator._load_resources("dev")
    assert list(by_provider) == ["opnsense"]
