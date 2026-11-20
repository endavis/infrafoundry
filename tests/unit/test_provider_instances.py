"""Provider instances: ``opnsense@<firewall>`` ids and their helpers (#1450)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import (
    declared_instances,
    entry_instance_provider,
    instance_label,
    instance_provider_id,
    instance_settings,
    instance_spec,
    is_primary_id,
    normalize_instance_providers,
    primary_instance,
    qualified_provider_id,
    register_instance_providers,
    split_provider_id,
    stamp_instance,
    stamp_selected,
    validate_instance_map,
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


def test_instance_spec_describes_opnsense() -> None:
    spec = instance_spec("opnsense")
    assert spec is not None
    assert (spec.map_key, spec.primary_key, spec.selector_key, spec.noun) == (
        "firewalls",
        "primary",
        "firewall",
        "firewall",
    )
    assert instance_spec("proxmox") is None


def test_stamp_selected_stamps_only_the_provider_owning_the_selector() -> None:
    resources = [_res("opnsense"), _res("proxmox"), _res("opnsense@fw-a")]
    stamp_selected(resources, {"firewall": "fw-b"}, "test")
    assert [r.provider for r in resources] == ["opnsense@fw-b", "proxmox", "opnsense@fw-a"]


def test_stamp_selected_ignores_unset_and_foreign_selectors() -> None:
    resources = [_res("opnsense")]
    stamp_selected(resources, {"firewall": None, "other": "x"}, "test")
    assert resources[0].provider == "opnsense"


def test_stamp_selected_rejects_invalid_name() -> None:
    with pytest.raises(InvalidConfigurationError, match="invalid firewall name"):
        stamp_selected([_res("opnsense")], {"firewall": "FW"}, "test")


def test_entry_instance_provider() -> None:
    item = {"name": "x", "firewall": "fw-b"}
    assert entry_instance_provider(item, "opnsense", "f.yaml", "t") == "opnsense@fw-b"
    assert entry_instance_provider({"name": "x"}, "opnsense", "f.yaml", "t") is None
    with pytest.raises(InvalidConfigurationError, match="only supported for provider"):
        entry_instance_provider(item, "proxmox", "f.yaml", "t")


def test_instance_settings_with_spec_merges_defaults_and_drops_keys() -> None:
    settings = {
        "verify_ssl": False,
        "primary": "fw-a",
        "firewalls": {"fw-a": {"api_url": "a", "ha_backup": "fw-b"}, "fw-b": {"api_url": "b"}},
    }
    merged = instance_settings("opnsense", settings, "opnsense", drop_keys=("ha_backup",))
    assert merged == {"verify_ssl": False, "api_url": "a"}
    assert instance_settings("opnsense", settings, "opnsense@fw-b") == {
        "verify_ssl": False,
        "api_url": "b",
    }
    assert instance_settings("opnsense", settings, "opnsense@nope") == {}


def test_instance_settings_returns_flat_settings_unchanged() -> None:
    flat = {"api_url": "a"}
    assert instance_settings("opnsense", flat, "opnsense") is flat
    assert instance_settings("opnsense", None, "opnsense") is None


def test_instance_label_and_primary_id() -> None:
    assert instance_label("opnsense", SETTINGS["opnsense"], "opnsense") == "fw-a"
    assert instance_label("opnsense", SETTINGS["opnsense"], "opnsense@fw-b") == "fw-b"
    assert instance_label("opnsense", {"api_url": "a"}, "opnsense") is None
    assert is_primary_id("opnsense")
    assert not is_primary_id("opnsense@fw-b")


def test_validate_instance_map_accepts_valid_and_flat() -> None:
    assert validate_instance_map("opnsense", None, ("api_url",)) == []
    assert validate_instance_map("opnsense", {"api_url": "a"}, ("api_url",)) == []
    assert validate_instance_map("opnsense", SETTINGS["opnsense"], ("api_url",)) == []


def test_validate_instance_map_reports_shape_errors() -> None:
    errors = validate_instance_map(
        "opnsense",
        {"api_url": "x", "firewalls": {"A_1": {}, "b": "no", "c": {}}, "primary": "z"},
        ("api_url",),
    )
    assert any("cannot combine 'firewalls' with top-level api_url" in e for e in errors)
    assert any("firewall name 'A_1' is invalid" in e for e in errors)
    assert any("firewall 'b' must be a mapping" in e for e in errors)
    assert any("primary 'z' is not declared under firewalls" in e for e in errors)
    assert validate_instance_map("opnsense", {"firewalls": {}}, ()) == [
        "provider_settings.opnsense.firewalls must be a non-empty mapping"
    ]
    assert validate_instance_map("opnsense", {"firewalls": {"a": {}, "b": {}}}, ()) == [
        "'primary' is required when more than one firewall is declared"
    ]


# --- kubernetes clusters (#1539) -----------------------------------------------

CLUSTERS: dict[str, Any] = {
    "kubernetes": {
        "primary": "edge",
        "clusters": {"edge": {"kubeconfig_path": "/k/edge.yaml"}, "cloud": {}},
    }
}


def test_kubernetes_cluster_ids_split_and_qualify() -> None:
    assert split_provider_id("kubernetes@cloud") == ("kubernetes", "cloud")
    assert qualified_provider_id("kubernetes", "cloud") == "kubernetes@cloud"
    assert declared_instances("kubernetes", CLUSTERS) == ["edge", "cloud"]
    assert primary_instance("kubernetes", CLUSTERS) == "edge"


def test_normalize_rewrites_the_primary_cluster_and_rejects_unknown() -> None:
    resources = [
        ResourceConfig(name="a", type="namespaces", provider="kubernetes@edge", config={}),
        ResourceConfig(name="b", type="namespaces", provider="kubernetes@cloud", config={}),
    ]
    normalize_instance_providers(resources, CLUSTERS)
    assert [r.provider for r in resources] == ["kubernetes", "kubernetes@cloud"]
    stray = [ResourceConfig(name="c", type="namespaces", provider="kubernetes@nope", config={})]
    with pytest.raises(InvalidConfigurationError, match="not declared under provider_settings"):
        normalize_instance_providers(stray, CLUSTERS)


def test_cluster_selector_is_rejected_for_other_providers_and_bad_names() -> None:
    other = ResourceConfig(name="vm", type="vm", provider="proxmox", config={})
    with pytest.raises(InvalidConfigurationError, match="only supported for provider"):
        stamp_instance(other, "cloud", "f.yaml", "cluster")
    ns = ResourceConfig(name="a", type="namespaces", provider="kubernetes", config={})
    with pytest.raises(InvalidConfigurationError, match="invalid cluster name"):
        stamp_instance(ns, "Bad_Name", "f.yaml", "cluster")


def test_register_instance_providers_spawns_non_primary_clusters_only() -> None:
    class _Base:
        def spawn_instance(self, name: str) -> str:
            return f"spawned-{name}"

    providers: dict[str, Any] = {"kubernetes": _Base()}
    register_instance_providers(providers, CLUSTERS)
    assert set(providers) == {"kubernetes", "kubernetes@cloud"}
    assert providers["kubernetes@cloud"] == "spawned-cloud"


def test_stamp_selected_uses_each_providers_own_selector() -> None:
    resources = [
        ResourceConfig(name="r", type="x", provider="opnsense", config={}),
        ResourceConfig(name="n", type="namespaces", provider="kubernetes", config={}),
        ResourceConfig(name="v", type="vm", provider="proxmox", config={}),
    ]
    stamp_selected(resources, {"firewall": "fw-b", "cluster": "cloud"}, "test")
    assert [r.provider for r in resources] == ["opnsense@fw-b", "kubernetes@cloud", "proxmox"]
