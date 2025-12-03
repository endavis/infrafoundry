"""Unit tests for environment configuration diff utilities."""

from infrafoundry.core.config.diff import diff_environments
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig


class DummyConfigManager:
    """Simple stub for ConfigManager."""

    def __init__(
        self,
        envs: dict[str, EnvironmentConfig],
        resources: dict[str, list[ResourceConfig]],
    ) -> None:
        self._envs = envs
        self._resources = resources

    def load_environment(self, env_name: str) -> EnvironmentConfig:
        return self._envs[env_name]

    def get_all_resources_all_providers(self, env_name: str) -> list[ResourceConfig]:
        return list(self._resources.get(env_name, []))


def test_diff_environments_no_changes():
    """No differences are reported when environments match."""
    env_a = EnvironmentConfig(name="dev", providers=["proxmox"], variables={"version": "1.0"})
    env_b = EnvironmentConfig(name="prod", providers=["proxmox"], variables={"version": "1.0"})

    manager = DummyConfigManager(
        {"dev": env_a, "prod": env_b},
        {"dev": [], "prod": []},
    )

    result = diff_environments(manager, "dev", "prod")

    assert result.is_empty()
    assert result.settings_changes == []
    assert result.resources_added == []
    assert result.resources_removed == []
    assert result.resources_changed == []


def test_diff_environments_settings_and_resources():
    """Detect settings changes and resource add/remove/modify."""
    env_a = EnvironmentConfig(
        name="dev",
        description="Development",
        providers=["proxmox"],
        variables={"version": "1.0"},
    )
    env_b = EnvironmentConfig(
        name="prod",
        description="Production",
        providers=["proxmox"],
        variables={"version": "2.0"},
    )

    dev_resources = [
        ResourceConfig(name="vm-dev", type="vm", provider="proxmox", config={"cpu": 2}),
        ResourceConfig(name="vm-keep", type="vm", provider="proxmox", config={"cpu": 4}),
    ]
    prod_resources = [
        ResourceConfig(name="vm-prod", type="vm", provider="proxmox", config={"cpu": 4}),
        ResourceConfig(name="vm-keep", type="vm", provider="proxmox", config={"cpu": 6}),
    ]

    manager = DummyConfigManager(
        {"dev": env_a, "prod": env_b},
        {"dev": dev_resources, "prod": prod_resources},
    )

    result = diff_environments(manager, "dev", "prod")

    assert not result.is_empty()
    assert any("description" in change for change in result.settings_changes)
    assert any("variables" in change for change in result.settings_changes)
    assert result.resources_added == ["proxmox:vm-prod"]
    assert result.resources_removed == ["proxmox:vm-dev"]
    assert result.resources_changed == ["proxmox:vm-keep"]


def test_diff_environments_provider_filter():
    """Provider filter limits resource comparison."""
    env_a = EnvironmentConfig(name="dev", providers=["proxmox", "opnsense"])
    env_b = EnvironmentConfig(name="prod", providers=["proxmox", "opnsense"])

    dev_resources = [
        ResourceConfig(name="vm-dev", type="vm", provider="proxmox", config={"cpu": 2}),
        ResourceConfig(name="fw-dev", type="firewall_rule", provider="opnsense", config={}),
    ]
    prod_resources = [
        ResourceConfig(name="vm-dev", type="vm", provider="proxmox", config={"cpu": 4}),
        ResourceConfig(name="fw-dev", type="firewall_rule", provider="opnsense", config={}),
    ]

    manager = DummyConfigManager(
        {"dev": env_a, "prod": env_b},
        {"dev": dev_resources, "prod": prod_resources},
    )

    result = diff_environments(manager, "dev", "prod", provider_filter="opnsense")
    assert result.resources_changed == []
    assert result.resources_added == []
    assert result.resources_removed == []

    result_proxmox = diff_environments(manager, "dev", "prod", provider_filter="proxmox")
    assert result_proxmox.resources_changed == ["proxmox:vm-dev"]
