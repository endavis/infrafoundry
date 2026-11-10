"""Tests for TailscaleProvider metadata, registration and package loading."""

from pathlib import Path

import infrafoundry.providers as providers_pkg
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_registry import ProviderRegistry
from infrafoundry.providers.tailscale import TailscaleProvider

EXPECTED_TYPES = [
    "acl",
    "tailnet_key",
    "device_subnet_routes",
    "device_tags",
    "dns_nameservers",
    "dns_preferences",
    "dns_search_paths",
]


class TestMetadata:
    def test_name(self, provider: TailscaleProvider) -> None:
        assert provider.name == "tailscale"

    def test_resource_types(self, provider: TailscaleProvider) -> None:
        assert provider.get_resource_types() == EXPECTED_TYPES

    def test_terraform_type_map(self, provider: TailscaleProvider) -> None:
        mapping = provider.get_terraform_resource_types()
        assert set(mapping) == set(EXPECTED_TYPES)
        assert mapping["device_subnet_routes"] == ["tailscale_device_subnet_routes"]
        assert mapping["acl"] == ["tailscale_acl"]

    def test_unsupported_types_carry_a_reason(self, provider: TailscaleProvider) -> None:
        unsupported = provider.get_unsupported_resource_types()
        assert set(unsupported) == {"dns_configuration", "dns_split_nameservers"}
        assert all("must not be mixed" in reason for reason in unsupported.values())
        assert not set(unsupported) & set(provider.get_resource_types())

    def test_dependencies(self, provider: TailscaleProvider) -> None:
        deps = provider.get_dependencies()
        assert deps["tailnet_key"] == ["acl"]
        assert deps["device_tags"] == ["acl"]
        assert deps["device_subnet_routes"] == ["acl"]
        assert deps["acl"] == []

    def test_validate_config_requires_name(self, provider: TailscaleProvider) -> None:
        assert provider.validate_config({"name": "x"})
        assert not provider.validate_config({})

    def test_generate_ansible_only_creates_directories(self, provider: TailscaleProvider) -> None:
        provider.generate_ansible([])
        assert provider.ansible_dir.is_dir()


class TestRegistration:
    def test_discovery_registers_tailscale(self, tmp_path: Path) -> None:
        registry = ProviderRegistry(tmp_path, tmp_path / "out")
        registry.discover_and_register_all()
        assert isinstance(registry.get_provider("tailscale"), TailscaleProvider)

    def test_exported_from_providers_package(self) -> None:
        assert "TailscaleProvider" in providers_pkg.__all__
        assert providers_pkg.TailscaleProvider is TailscaleProvider


class TestPackageLoading:
    """The control-plane provider does not collide with ``opnsense.tailscale.*``."""

    def test_provider_centric_acl(self, tmp_path: Path) -> None:
        loader = PackageLoader(tmp_path)
        resources = loader._parse_resources_from_data(
            {"acl": [{"name": "main", "hujson": "{}"}]}, "acl.yaml", "tailscale"
        )
        assert [(r.provider, r.type, r.name) for r in resources] == [("tailscale", "acl", "main")]

    def test_underscored_filename_keeps_full_type(self, tmp_path: Path) -> None:
        loader = PackageLoader(tmp_path)
        resources = loader._parse_resources_from_data(
            {"device_subnet_routes": [{"name": "r", "device_id": "1", "routes": []}]},
            "device_subnet_routes.yaml",
            "tailscale",
        )
        assert [(r.provider, r.type) for r in resources] == [("tailscale", "device_subnet_routes")]

    def test_opnsense_namespace_stays_opnsense(self, tmp_path: Path) -> None:
        loader = PackageLoader(tmp_path)
        resources = loader._parse_resources_from_data(
            {"opnsense": {"tailscale": {"settings": {"enabled": True}}}},
            "node.yaml",
            "tailscale",
        )
        assert [(r.provider, r.type) for r in resources] == [("opnsense", "tailscale.settings")]


class TestKeptOnDestroy:
    """device_tags opt out of destroy with keep_tags_on_destroy (#1349)."""

    @staticmethod
    def _r(name: str, rtype: str, **config: object) -> ResourceConfig:
        return ResourceConfig(name=name, type=rtype, provider="tailscale", config=dict(config))

    def test_opted_in_device_tags(self, provider: TailscaleProvider) -> None:
        r = self._r("fw-test-tags", "device_tags", keep_tags_on_destroy=True)
        assert provider.get_state_addresses_kept_on_destroy([r]) == [
            "tailscale_device_tags.fw_test_tags"
        ]

    def test_missing_or_false_is_empty(self, provider: TailscaleProvider) -> None:
        rs = [
            self._r("a", "device_tags"),
            self._r("b", "device_tags", keep_tags_on_destroy=False),
        ]
        assert provider.get_state_addresses_kept_on_destroy(rs) == []

    def test_other_type_ignored(self, provider: TailscaleProvider) -> None:
        r = self._r("a", "device_subnet_routes", keep_tags_on_destroy=True)
        assert provider.get_state_addresses_kept_on_destroy([r]) == []

    def test_mix_returns_only_opted_in(self, provider: TailscaleProvider) -> None:
        rs = [
            self._r("a", "device_tags", keep_tags_on_destroy=True),
            self._r("b", "device_tags"),
        ]
        assert provider.get_state_addresses_kept_on_destroy(rs) == ["tailscale_device_tags.a"]
