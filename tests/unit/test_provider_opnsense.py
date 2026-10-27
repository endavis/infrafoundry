"""Unit tests for OPNsense provider reset and migrate functionality."""

import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.protocols import ValidatesReferencesInContext
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.proxmox import ProxmoxProvider


class TestOPNsenseProviderReset:
    """Tests for OPNsense provider reset methods (delegation to manager)."""

    @pytest.fixture
    def provider(self) -> OPNsenseProvider:
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    @pytest.fixture
    def mock_manager(self) -> Iterator[MagicMock]:
        """Mock KeaDHCPManager for component operations."""
        with patch("infrafoundry.providers.opnsense.components.kea_dhcp.KeaDHCPManager") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_reset_kea_dhcpv4_delegates_to_manager(
        self, provider: OPNsenseProvider, mock_manager: MagicMock
    ) -> None:
        """Test reset_kea_dhcpv4 delegates to manager."""
        provider.reset_kea_dhcpv4("test_env")
        mock_manager.reset_dhcpv4.assert_called_once_with("test_env", "opnsense")

    def test_reset_kea_dhcpv4_handles_errors(
        self, provider: OPNsenseProvider, mock_manager: MagicMock
    ) -> None:
        """Test reset_kea_dhcpv4 propagates errors from manager."""
        mock_manager.reset_dhcpv4.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            provider.reset_kea_dhcpv4("test_env")

    def test_reset_kea_dhcpv6_delegates_to_manager(
        self, provider: OPNsenseProvider, mock_manager: MagicMock
    ) -> None:
        """Test reset_kea_dhcpv6 delegates to manager."""
        provider.reset_kea_dhcpv6("test_env")
        mock_manager.reset_dhcpv6.assert_called_once_with("test_env", "opnsense")

    def test_reset_kea_dhcpv6_handles_errors(
        self, provider: OPNsenseProvider, mock_manager: MagicMock
    ) -> None:
        """Test reset_kea_dhcpv6 propagates errors from manager."""
        mock_manager.reset_dhcpv6.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            provider.reset_kea_dhcpv6("test_env")


class TestOPNsenseProviderMigrate:
    """Tests for the deprecated ``migrate_kea_dhcp`` shim.

    After #726 the shim delegates through the extractor registry rather
    than constructing a manager directly. These tests verify the shim
    still returns the manager's YAML payload and emits the
    ``DeprecationWarning``; the registry-driven dispatch contract is
    covered in ``tests/unit/providers/opnsense/test_provider_extractors.py``.
    """

    @pytest.fixture
    def provider(self) -> OPNsenseProvider:
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    def test_migrate_kea_dhcp_delegates_via_registry(self, provider: OPNsenseProvider) -> None:
        """``migrate_kea_dhcp`` returns the registry extractor's YAML."""
        from infrafoundry.core.extractors import get_extractor

        extractor: Any = get_extractor("opnsense", "kea_dhcp")

        with (
            patch.object(extractor.manager_class, "__init__", return_value=None),
            patch.object(
                extractor.manager_class,
                "migrate",
                return_value="resources:\n  - type: test\n",
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            result = provider.migrate_kea_dhcp("test_env")

        assert result == "resources:\n  - type: test\n"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) >= 1

    def test_migrate_kea_dhcp_handles_errors(self, provider: OPNsenseProvider) -> None:
        """``migrate_kea_dhcp`` propagates errors from the manager."""
        from infrafoundry.core.extractors import get_extractor

        extractor: Any = get_extractor("opnsense", "kea_dhcp")

        with (
            patch.object(extractor.manager_class, "__init__", return_value=None),
            patch.object(
                extractor.manager_class,
                "migrate",
                side_effect=ValueError("Test error"),
            ),
            pytest.raises(ValueError, match="Test error"),
        ):
            provider.migrate_kea_dhcp("test_env")


class TestOPNsenseProviderBasic:
    """Basic OPNsense provider tests."""

    def test_provider_initialization(self) -> None:
        """Test provider initializes correctly."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        assert provider.config_dir == Path(".")
        assert provider.output_dir == Path(".")

    def test_provider_name(self) -> None:
        """Test provider name is correct."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        assert provider.name == "opnsense"


def test_opnsense_resolves_references_in_context(tmp_path: Path) -> None:
    """OPNsense opts into context-aware validation; Proxmox keeps the plain hook (#1133)."""
    opnsense: ValidatesReferencesInContext = OPNsenseProvider(tmp_path, tmp_path)

    assert isinstance(opnsense, ValidatesReferencesInContext)
    assert not isinstance(ProxmoxProvider(tmp_path, tmp_path), ValidatesReferencesInContext)


def test_opnsense_in_context_passes_reference_resources(tmp_path: Path) -> None:
    """The provider hands both lists to its validator."""
    provider = OPNsenseProvider(tmp_path, tmp_path)
    checked = [
        ResourceConfig(name="r", type="kea.dhcp4.reservations", provider="opnsense", config={})
    ]
    references = [
        *checked,
        ResourceConfig(name="s", type="kea.dhcp4.subnets", provider="opnsense", config={}),
    ]

    with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator_cls:
        provider.validate_references_in_context(checked, references, MagicMock(), MagicMock())

    validator_cls.return_value.validate_references.assert_called_once_with(checked, references)


class TestOPNsenseResourceTypes:
    """Supported types track the manager table, less the unverified set (#1144)."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> OPNsenseProvider:
        return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    def test_every_manager_is_supported_or_explicitly_unverified(
        self, provider: OPNsenseProvider
    ) -> None:
        managed = set(provider.get_direct_api_resource_types())
        supported = set(provider.get_resource_types())
        unverified = OPNsenseProvider.UNVERIFIED_RESOURCE_TYPES

        assert supported | unverified == managed
        assert not supported & unverified

    @pytest.mark.parametrize("resource_type", ["radvd", "cron.jobs"])
    def test_previously_rejected_types_are_supported(
        self, provider: OPNsenseProvider, resource_type: str
    ) -> None:
        assert resource_type in provider.get_resource_types()

    def test_system_types_stay_rejected_until_verified(self, provider: OPNsenseProvider) -> None:
        supported = provider.get_resource_types()

        assert not [t for t in supported if t.startswith("system.")]

    def test_every_supported_type_has_a_loader_shape(self, provider: OPNsenseProvider) -> None:
        from infrafoundry.core.config.package_loader import DOTTED_RESOURCE_SHAPES

        assert set(provider.get_resource_types()) <= set(DOTTED_RESOURCE_SHAPES)

    def test_every_supported_type_has_a_dependency_entry(self, provider: OPNsenseProvider) -> None:
        deps = provider.get_dependencies()
        supported = set(provider.get_resource_types())

        assert set(deps) == supported
        for required in deps.values():
            assert set(required) <= supported
