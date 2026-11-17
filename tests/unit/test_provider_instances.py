"""Provider instances: ``opnsense@<firewall>`` ids and their helpers (#1450)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import (
    declared_instances,
    instance_provider_id,
    normalize_instance_providers,
    primary_instance,
    qualified_provider_id,
    register_instance_providers,
    split_provider_id,
    stamp_instance,
)

SETTINGS: dict[str, Any] = {
    "opnsense": {
        "primary": "fw-a",
        "firewalls": {"fw-a": {"api_url": "https://fw-a.example.com"}, "fw-b": {}},
    }
}


def _res(provider: str, name: str = "r") -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.aliases", provider=provider, config={})


def test_split_and_qualify_round_trip() -> None:
    assert split_provider_id("opnsense") == ("opnsense", None)
    assert split_provider_id("opnsense@fw-b") == ("opnsense", "fw-b")
    assert qualified_provider_id("opnsense", "fw-b") == "opnsense@fw-b"
    assert qualified_provider_id("opnsense", None) == "opnsense"


def test_stamp_instance_rewrites_unstamped_resource() -> None:
    resource = _res("opnsense")
    stamp_instance(resource, "fw-b", "test")
    assert resource.provider == "opnsense@fw-b"


def test_stamp_instance_keeps_the_more_specific_selection() -> None:
    resource = _res("opnsense@fw-a")
    stamp_instance(resource, "fw-b", "test")
    assert resource.provider == "opnsense@fw-a"


def test_stamp_instance_rejects_unsupported_provider() -> None:
    with pytest.raises(InvalidConfigurationError, match="only supported for provider"):
        stamp_instance(_res("proxmox"), "fw-b", "test")


@pytest.mark.parametrize("name", ["FW", "-fw", "fw_b", "a" * 33, "fw b", ""])
def test_stamp_instance_rejects_invalid_names(name: str) -> None:
    with pytest.raises(InvalidConfigurationError, match="invalid firewall name"):
        stamp_instance(_res("opnsense"), name, "test")


def test_declared_and_primary_instances() -> None:
    assert declared_instances("opnsense", SETTINGS) == ["fw-a", "fw-b"]
    assert primary_instance("opnsense", SETTINGS) == "fw-a"
    assert declared_instances("opnsense", {}) == []
    assert declared_instances("proxmox", SETTINGS) == []
    assert declared_instances("opnsense", None) == []


def test_single_declared_firewall_is_the_primary() -> None:
    settings: dict[str, Any] = {"opnsense": {"firewalls": {"only": {}}}}
    assert primary_instance("opnsense", settings) == "only"


def test_two_firewalls_without_primary_have_none() -> None:
    settings: dict[str, Any] = {"opnsense": {"firewalls": {"a": {}, "b": {}}}}
    assert primary_instance("opnsense", settings) is None


def test_instance_provider_id_maps_primary_to_base() -> None:
    assert instance_provider_id("opnsense", "fw-a", SETTINGS) == "opnsense"
    assert instance_provider_id("opnsense", "fw-b", SETTINGS) == "opnsense@fw-b"


def test_normalize_rewrites_primary_and_keeps_secondary() -> None:
    resources = [_res("opnsense@fw-a"), _res("opnsense@fw-b"), _res("opnsense"), _res("proxmox")]
    normalize_instance_providers(resources, SETTINGS)
    assert [r.provider for r in resources] == ["opnsense", "opnsense@fw-b", "opnsense", "proxmox"]


def test_normalize_rejects_undeclared_firewall() -> None:
    with pytest.raises(InvalidConfigurationError, match="not declared"):
        normalize_instance_providers([_res("opnsense@nope")], SETTINGS)


def test_normalize_rejects_firewall_without_a_firewalls_map() -> None:
    with pytest.raises(InvalidConfigurationError, match="none declared"):
        normalize_instance_providers([_res("opnsense@fw-b")], {"opnsense": {"api_url": "x"}})


class _Base:
    def __init__(self) -> None:
        self.spawned: list[str] = []

    def spawn_instance(self, name: str) -> str:
        self.spawned.append(name)
        return f"instance-{name}"


def test_register_adds_only_missing_non_primary_instances() -> None:
    base = _Base()
    providers: dict[str, Any] = {"opnsense": base}
    register_instance_providers(providers, SETTINGS)
    assert providers["opnsense@fw-b"] == "instance-fw-b"
    assert "opnsense@fw-a" not in providers
    register_instance_providers(providers, SETTINGS)
    assert base.spawned == ["fw-b"]


@pytest.mark.parametrize("settings", [None, {}, {"opnsense": "not-a-dict"}, {"opnsense": {}}])
def test_register_ignores_settings_without_firewalls(settings: Any) -> None:
    providers: dict[str, Any] = {"opnsense": _Base()}
    register_instance_providers(providers, settings)
    assert list(providers) == ["opnsense"]


def test_register_needs_a_spawning_base_provider() -> None:
    providers: dict[str, Any] = {"opnsense": object()}
    register_instance_providers(providers, SETTINGS)
    assert list(providers) == ["opnsense"]
    empty: dict[str, Any] = {}
    register_instance_providers(empty, SETTINGS)
    assert empty == {}
