"""Unit tests for OPNsense provider extractor registration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.extractors import (
    ExtractorRegistry,
    get_extractor,
    list_extractor_providers,
    list_extractor_resource_types,
)
from infrafoundry.providers.opnsense import OPNsenseProvider, _ExtractorAdapter

EXPECTED_RESOURCE_TYPES = [
    "firewall.aliases",
    "firewall.rules",
    "routing.gateways",
    "interfaces.assignments",
    "isc_to_kea",
    "kea_dhcp",
    "firewall.nat",
    "routing.static",
    "unbound.forwards",
    "unbound.host_aliases",
    "unbound.host_overrides",
    "interfaces.virtual_ips",
    "interfaces.vlans",
]


@pytest.fixture
def provider(tmp_path: Path) -> OPNsenseProvider:
    """OPNsense provider instance whose ``__init__`` populates the registry."""
    return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)


@pytest.mark.usefixtures("provider")
def test_provider_registers_all_thirteen_components() -> None:
    """Instantiating the provider registers all 13 expected components."""
    registered = list_extractor_resource_types("opnsense")

    for resource_type in EXPECTED_RESOURCE_TYPES:
        assert resource_type in registered, f"{resource_type!r} not registered; got {registered}"


@pytest.mark.usefixtures("provider")
def test_provider_registers_no_unexpected_components() -> None:
    """Provider must not register components beyond the known list.

    Catches accidental registrations sneaking in via copy/paste.
    """
    registered = set(list_extractor_resource_types("opnsense"))
    expected = set(EXPECTED_RESOURCE_TYPES)

    extra = registered - expected
    assert not extra, f"Unexpected extractor registrations: {sorted(extra)}"


def test_provider_re_instantiation_does_not_error(tmp_path: Path) -> None:
    """Re-instantiating the provider must not error or duplicate entries.

    The registry is a module-level singleton; re-instantiation under
    test fixtures must overwrite the prior entry rather than append.
    """
    OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)
    OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)
    OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    registered = list_extractor_resource_types("opnsense")
    # Registry uses a dict — duplicates collapse to one entry per key.
    assert len(registered) == len(set(registered))


@pytest.mark.usefixtures("provider")
def test_provider_registers_under_lowercase_name() -> None:
    """Registry keys are case-sensitive; provider registers under lowercase."""
    assert "opnsense" in list_extractor_providers()
    assert list_extractor_resource_types("OPNsense") == []


def test_extractor_adapter_repr() -> None:
    """``_ExtractorAdapter.__repr__`` mentions the manager class and config dir."""

    class FakeManager:
        pass

    adapter = _ExtractorAdapter(FakeManager, Path("/etc/whatever"))

    rep = repr(adapter)
    assert "FakeManager" in rep
    assert "/etc/whatever" in rep


def test_extractor_adapter_extract_calls_manager_migrate(tmp_path: Path) -> None:
    """``_ExtractorAdapter.extract`` instantiates the manager and forwards args."""
    manager_class = MagicMock()
    manager_instance = MagicMock()
    manager_instance.migrate.return_value = "yaml: ok"
    manager_class.return_value = manager_instance

    adapter = _ExtractorAdapter(manager_class, tmp_path)

    result = adapter.extract("test_env", interfaces=["lan"])

    assert result == "yaml: ok"
    manager_class.assert_called_once_with(tmp_path)
    manager_instance.migrate.assert_called_once_with("test_env", interfaces=["lan"])


def test_extractor_adapter_extract_no_kwargs(tmp_path: Path) -> None:
    """``_ExtractorAdapter.extract`` works without keyword arguments."""
    manager_class = MagicMock()
    manager_instance = MagicMock()
    manager_instance.migrate.return_value = "yaml"
    manager_class.return_value = manager_instance

    adapter = _ExtractorAdapter(manager_class, tmp_path)

    result = adapter.extract("test_env")

    assert result == "yaml"
    manager_class.assert_called_once_with(tmp_path)
    manager_instance.migrate.assert_called_once_with("test_env")


@pytest.mark.usefixtures("provider")
def test_vlans_extractor_delegates_to_vlan_manager() -> None:
    """``opnsense:interfaces.vlans`` extractor delegates to ``VlanManager.migrate``."""
    extractor = get_extractor("opnsense", "interfaces.vlans")

    # The adapter holds a class reference; replacing the class's
    # ``__init__`` and ``migrate`` exercises the full extract path.
    assert isinstance(extractor, _ExtractorAdapter)

    with (
        patch.object(extractor.manager_class, "__init__", return_value=None) as init_mock,
        patch.object(
            extractor.manager_class, "migrate", return_value="vlans: stub"
        ) as migrate_mock,
    ):
        result = extractor.extract("env_test")

    init_mock.assert_called_once()
    migrate_mock.assert_called_once_with("env_test")
    assert result == "vlans: stub"


@pytest.mark.usefixtures("provider")
def test_aliases_extractor_delegates_to_alias_manager() -> None:
    """``opnsense:firewall.aliases`` extractor delegates to ``AliasManager.migrate``."""
    from infrafoundry.providers.opnsense.components.alias import AliasManager

    extractor = get_extractor("opnsense", "firewall.aliases")

    assert isinstance(extractor, _ExtractorAdapter)
    assert extractor.manager_class is AliasManager

    with (
        patch.object(extractor.manager_class, "__init__", return_value=None) as init_mock,
        patch.object(
            extractor.manager_class, "migrate", return_value="aliases: stub"
        ) as migrate_mock,
    ):
        result = extractor.extract("env_test")

    init_mock.assert_called_once()
    migrate_mock.assert_called_once_with("env_test")
    assert result == "aliases: stub"


@pytest.mark.usefixtures("provider")
def test_unbound_host_override_extractor_delegates_to_manager() -> None:
    """``opnsense:unbound.host_overrides`` delegates to ``UnboundHostOverrideManager.migrate``."""
    from infrafoundry.providers.opnsense.components.unbound_host_override import (
        UnboundHostOverrideManager,
    )

    extractor = get_extractor("opnsense", "unbound.host_overrides")

    assert isinstance(extractor, _ExtractorAdapter)
    assert extractor.manager_class is UnboundHostOverrideManager

    with (
        patch.object(extractor.manager_class, "__init__", return_value=None) as init_mock,
        patch.object(
            extractor.manager_class, "migrate", return_value="unbound_host_override: stub"
        ) as migrate_mock,
    ):
        result = extractor.extract("env_test")

    init_mock.assert_called_once()
    migrate_mock.assert_called_once_with("env_test")
    assert result == "unbound_host_override: stub"


@pytest.mark.usefixtures("provider")
def test_isc_to_kea_extractor_forwards_interfaces() -> None:
    """``opnsense:isc_to_kea`` extractor forwards ``interfaces`` kwarg."""
    extractor = get_extractor("opnsense", "isc_to_kea")

    assert isinstance(extractor, _ExtractorAdapter)

    with (
        patch.object(extractor.manager_class, "__init__", return_value=None),
        patch.object(extractor.manager_class, "migrate", return_value="yaml: stub") as migrate_mock,
    ):
        result = extractor.extract("env_test", interfaces=["lan", "wan"])

    migrate_mock.assert_called_once_with("env_test", interfaces=["lan", "wan"])
    assert result == "yaml: stub"


def test_isolated_registry_does_not_see_singleton_entries() -> None:
    """A fresh ``ExtractorRegistry`` instance is isolated from the singleton.

    Demonstrates the singleton-vs-per-instance separation: creating a new
    ``ExtractorRegistry`` doesn't see entries from the module-level one.
    """
    isolated = ExtractorRegistry()

    assert isolated.list_providers() == []
