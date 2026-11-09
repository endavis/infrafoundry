"""Unit tests for the nested ``opnsense:`` provider-namespace YAML format.

Covers ``PackageLoader._parse_nested_provider_format`` and the
``_parse_resources_from_data`` detection branch added in #793 Phase 2 per
ADR-0016. The flat (resource-centric / provider-centric) parse paths are
covered by ``tests/unit/test_package_loader.py`` and remain unchanged in
this phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.package_loader import (
    DOTTED_RESOURCE_SHAPES,
    DOTTED_RESOURCE_TYPES,
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader
from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader
from infrafoundry.core.exceptions import InvalidConfigurationError


@pytest.mark.unit
class TestNestedFormatConstants:
    """Sanity checks for the ADR-0016 dotted-path tables."""

    def test_namespace_is_opnsense(self) -> None:
        """Top-level YAML key is ``opnsense:`` per ADR-0016."""
        assert NESTED_PROVIDER_NAMESPACE == "opnsense"

    def test_dotted_shapes_includes_existing_list_types(self) -> None:
        """The 15 currently-shipped direct-OPNsense paths are list-shape."""
        assert DOTTED_RESOURCE_SHAPES["firewall.aliases"] == "list"
        assert DOTTED_RESOURCE_SHAPES["firewall.rules"] == "list"
        assert DOTTED_RESOURCE_SHAPES["routing.gateways"] == "list"
        assert DOTTED_RESOURCE_SHAPES["routing.static"] == "list"
        assert DOTTED_RESOURCE_SHAPES["interfaces.vlans"] == "list"
        assert DOTTED_RESOURCE_SHAPES["unbound.host_overrides"] == "list"
        assert DOTTED_RESOURCE_SHAPES["kea.dhcp4.subnets"] == "list"
        assert DOTTED_RESOURCE_SHAPES["kea.dhcp6.reservations"] == "list"
        assert DOTTED_RESOURCE_SHAPES["trust.cas"] == "list"
        assert DOTTED_RESOURCE_SHAPES["trust.certs"] == "list"
        assert DOTTED_RESOURCE_SHAPES["openvpn.instances"] == "list"

    def test_dotted_shapes_includes_documented_singletons(self) -> None:
        """ADR-0016 future singletons are registered as dict-shape."""
        # #786 firewall_log
        assert DOTTED_RESOURCE_SHAPES["firewall.log"] == "dict"
        # #787 tailscale settings
        assert DOTTED_RESOURCE_SHAPES["tailscale.settings"] == "dict"
        # #788 radvd
        assert DOTTED_RESOURCE_SHAPES["radvd"] == "dict"

    def test_dotted_resource_types_matches_shapes(self) -> None:
        """``DOTTED_RESOURCE_TYPES`` mirrors ``DOTTED_RESOURCE_SHAPES`` keys."""
        assert frozenset(DOTTED_RESOURCE_SHAPES) == DOTTED_RESOURCE_TYPES


@pytest.mark.unit
class TestParseNestedSingleton:
    """Singleton (dict-leaf) shape — emits one ResourceConfig with name=<dotted type>."""

    def test_firewall_log_singleton_emits_one_dotted_name(self, temp_dir: Path) -> None:
        """``opnsense.firewall.log`` dict leaf becomes a resource named ``firewall.log``."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "log": {
                        "log_default_block": False,
                        "log_default_pass": False,
                    }
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "test.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "firewall.log"
        assert resources[0].type == "firewall.log"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == {
            "log_default_block": False,
            "log_default_pass": False,
        }

    def test_tailscale_settings_singleton(self, temp_dir: Path) -> None:
        """``opnsense.tailscale.settings`` is a registered singleton."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "tailscale": {
                    "settings": {"enabled": True, "exit_node": False},
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "ts.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "tailscale.settings"
        assert resources[0].type == "tailscale.settings"
        assert resources[0].config == {"enabled": True, "exit_node": False}

    def test_radvd_singleton_at_first_level(self, temp_dir: Path) -> None:
        """``opnsense.radvd`` is a registered single-segment singleton."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"radvd": {"interfaces": ["lan"], "ra_lifetime": 1800}}}
        resources = loader._parse_resources_from_data(data, "radvd.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "radvd"
        assert resources[0].type == "radvd"
        assert resources[0].config == {"interfaces": ["lan"], "ra_lifetime": 1800}

    def test_radvd_singleton_multi_interface_round_trip(self, temp_dir: Path) -> None:
        """``opnsense.radvd`` carries a multi-interface inner mapping (#788).

        The operator-facing shape is a dict-shape singleton whose
        ``interfaces`` mapping holds one inner mapping per interface
        (e.g. ``opt1``, ``opt2``, ``opt6``). Verifies the loader carries
        the nested mapping verbatim into a single ``radvd`` ``ResourceConfig``.
        """
        loader = PackageLoader(temp_dir)
        radvd_config = {
            "interfaces": {
                "opt1": {
                    "mode": "assist",
                    "priority": "medium",
                    "min_interval": 200,
                    "max_interval": 600,
                    "routes": ["fd00:db8:10:1::/64"],
                },
                "opt2": {
                    "mode": "assist",
                    "priority": "medium",
                    "routes": ["fd00:db8:20:1::/64"],
                },
                "opt6": {
                    "mode": "assist",
                    "priority": "medium",
                    "routes": ["fd00:db8:40:1::/64"],
                },
            },
        }
        data = {"opnsense": {"radvd": radvd_config}}
        resources = loader._parse_resources_from_data(data, "radvd.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "radvd"
        assert resources[0].type == "radvd"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == radvd_config
        # All three interfaces preserved with their inner field maps.
        assert set(resources[0].config["interfaces"].keys()) == {"opt1", "opt2", "opt6"}
        assert resources[0].config["interfaces"]["opt1"]["routes"] == ["fd00:db8:10:1::/64"]

    def test_singleton_config_is_a_copy(self, temp_dir: Path) -> None:
        """Mutating the emitted ``config`` does not leak into source data."""
        loader = PackageLoader(temp_dir)
        original = {"log_default_block": False}
        data = {"opnsense": {"firewall": {"log": original}}}
        resources = loader._parse_resources_from_data(data, "test.yaml", "opnsense")
        resources[0].config["log_default_block"] = True
        assert original == {"log_default_block": False}

    def test_system_hostname_singleton_round_trip(self, temp_dir: Path) -> None:
        """``opnsense.system.hostname`` (#806) emits exactly one singleton resource.

        Round-trip check: the nested YAML dict at ``opnsense.system.hostname``
        becomes one ``ResourceConfig`` with ``type="system.hostname"``,
        ``name="system.hostname"``, and the dict carried verbatim as ``.config``.
        Confirms the seven ``system.*`` singletons added in #806 work
        through the nested-format loader.
        """
        loader = PackageLoader(temp_dir)
        hostname_config = {
            "hostname": "fw-prod",
            "domain": "example.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        data = {"opnsense": {"system": {"hostname": hostname_config}}}
        resources = loader._parse_resources_from_data(data, "system.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "system.hostname"
        assert resources[0].type == "system.hostname"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == hostname_config


@pytest.mark.unit
class TestParseNestedList:
    """List (sequence-leaf) shape — emits one ResourceConfig per entry."""

    def test_system_users_and_groups_lists(self, temp_dir: Path) -> None:
        """``opnsense.system.{users,groups}`` list leaves round-trip, secret URIs intact (#805)."""
        loader = PackageLoader(temp_dir)
        uri = "secret://env_secrets/users/example-user/password"
        data = {
            "opnsense": {
                "system": {
                    "users": [{"name": "example-user", "config": {"uid": 2000, "password": uri}}],
                    "groups": [{"name": "admins", "config": {"member_refs": ["example-user"]}}],
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        by_type = {r.type: r for r in resources}
        assert set(by_type) == {"system.users", "system.groups"}
        assert by_type["system.users"].name == "example-user"
        assert by_type["system.users"].config["password"] == uri
        assert by_type["system.groups"].config["member_refs"] == ["example-user"]

    def test_firewall_aliases_list(self, temp_dir: Path) -> None:
        """``opnsense.firewall.aliases`` list leaf emits one config per entry."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [
                        {
                            "name": "web-servers",
                            "config": {"type": "host", "content": "172.21.0.1"},
                        },
                        {
                            "name": "db-servers",
                            "config": {"type": "host", "content": "172.21.0.5"},
                        },
                    ]
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        assert len(resources) == 2
        names = {r.name for r in resources}
        assert names == {"web-servers", "db-servers"}
        for resource in resources:
            assert resource.type == "firewall.aliases"
            assert resource.provider == "opnsense"

    def test_kea_dhcp4_subnets_three_levels_deep(self, temp_dir: Path) -> None:
        """Three-level dotted path (kea.dhcp4.subnets) walks correctly."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "kea": {
                    "dhcp4": {
                        "subnets": [
                            {"name": "lan", "config": {"subnet": "172.21.0.0/24"}},
                        ]
                    }
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "kea.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea.dhcp4.subnets"
        assert resources[0].name == "lan"

    def test_routing_gateways_list_carries_per_entry_metadata(self, temp_dir: Path) -> None:
        """List entries' ``provider`` / ``import_id`` / ``events`` propagate."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "routing": {
                    "gateways": [
                        {
                            "name": "wan-gw",
                            "import_id": "GWID_WAN",
                            "config": {"gateway": "1.2.3.4"},
                            "events": {
                                "AFTER_APPLY": [{"type": "webhook", "url": "https://x"}],
                            },
                        }
                    ]
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "gw.yaml", "opnsense")
        assert len(resources) == 1
        gw = resources[0]
        assert gw.import_id == "GWID_WAN"
        assert gw.events is not None
        assert gw.events["AFTER_APPLY"][0]["url"] == "https://x"

    def test_empty_list_emits_nothing(self, temp_dir: Path) -> None:
        """An empty list at a known list-shape path emits zero resources."""
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"firewall": {"aliases": []}}}
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestParseNestedMixed:
    """Mixed dict + list shapes coexisting under the same plugin sub-tree."""

    def test_dict_singleton_and_list_collection_under_firewall(self, temp_dir: Path) -> None:
        """``firewall: {log: {...}, aliases: [...], rules: [...]}`` works."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "log": {"log_default_block": False},
                    "aliases": [{"name": "trusted", "config": {"type": "host"}}],
                    "rules": [{"name": "allow-web", "config": {"interface": "lan"}}],
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        types = {r.type for r in resources}
        assert types == {"firewall.log", "firewall.aliases", "firewall.rules"}
        # Singleton has name=<dotted type>; list entries keep their own names.
        log_resource = next(r for r in resources if r.type == "firewall.log")
        assert log_resource.name == "firewall.log"
        alias_resource = next(r for r in resources if r.type == "firewall.aliases")
        assert alias_resource.name == "trusted"

    def test_multi_plugin_under_opnsense(self, temp_dir: Path) -> None:
        """Multiple plugins (firewall, routing, kea, unbound) coexist."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [{"name": "a1", "config": {}}],
                },
                "routing": {
                    "gateways": [{"name": "g1", "config": {}}],
                    "static": [{"name": "s1", "config": {}}],
                },
                "unbound": {
                    "host_overrides": [{"name": "h1", "config": {}}],
                },
                "kea": {
                    "dhcp4": {
                        "subnets": [{"name": "k1", "config": {}}],
                    }
                },
            }
        }
        resources = loader._parse_resources_from_data(data, "all.yaml", "opnsense")
        types = {r.type for r in resources}
        assert types == {
            "firewall.aliases",
            "routing.gateways",
            "routing.static",
            "unbound.host_overrides",
            "kea.dhcp4.subnets",
        }
        assert len(resources) == 5


@pytest.mark.unit
class TestParseNestedEmpty:
    """Empty / missing nested structures."""

    def test_empty_namespace_emits_nothing(self, temp_dir: Path) -> None:
        """``opnsense: {}`` returns an empty list."""
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {}}
        resources = loader._parse_resources_from_data(data, "empty.yaml", "opnsense")
        assert resources == []

    def test_empty_data_returns_empty_list(self, temp_dir: Path) -> None:
        """Empty data dict returns an empty list (existing behaviour)."""
        loader = PackageLoader(temp_dir)
        resources = loader._parse_resources_from_data({}, "empty.yaml", "opnsense")
        assert resources == []

    def test_namespace_value_none_falls_through_to_flat(self, temp_dir: Path) -> None:
        """``opnsense: null`` does not trigger nested parsing.

        ``null`` is not a dict, so the existing flat-format code path is
        used. Filename stem ``opnsense`` is not a known type so nothing
        is emitted (consistent with passing through to the flat branch).
        """
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": None}
        resources = loader._parse_resources_from_data(data, "opnsense.yaml", "opnsense")
        # Flat path treats opnsense: null as an empty resource list for the
        # filename-derived stem.
        assert resources == []


@pytest.mark.unit
class TestParseNestedUnknownPath:
    """Unknown dotted paths under ``opnsense:`` are rejected."""

    def test_unknown_top_level_plugin_with_list_leaf(self, temp_dir: Path) -> None:
        """``opnsense.bogus.thing: [...]`` raises with the bad path."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"bogus": {"thing": [{"name": "x"}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bogus.yaml", "opnsense")
        assert "bogus.thing" in str(excinfo.value)
        assert "unknown nested resource path" in str(excinfo.value)

    def test_unknown_path_under_known_plugin(self, temp_dir: Path) -> None:
        """``opnsense.firewall.unknown: [...]`` is rejected."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"unknown": [{"name": "x"}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        assert "firewall.unknown" in str(excinfo.value)


@pytest.mark.unit
class TestParseNestedShapeMismatch:
    """Shape mismatches (list vs dict) are rejected with a clear error."""

    def test_known_list_path_with_dict_leaf_rejected(self, temp_dir: Path) -> None:
        """``firewall.aliases: {...}`` (dict where list expected) errors."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {"aliases": {"name": "oops", "config": {}}},
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "list" in msg

    def test_unbound_advanced_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``unbound.advanced`` loads as one singleton next to the forwards list."""
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert "unbound.advanced" in SINGLETON_RESOURCE_TYPES
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "unbound": {
                    "advanced": {"private_domains": ["test.example.net"]},
                    "forwards": [{"name": "f1", "server": "172.21.0.53"}],
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        adv = [r for r in resources if r.type == "unbound.advanced"]
        assert len(adv) == 1
        assert adv[0].name == "unbound.advanced"
        assert adv[0].config == {"private_domains": ["test.example.net"]}
        assert any(r.type == "unbound.forwards" for r in resources)

    def test_unbound_advanced_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"unbound": {"advanced": [{"private_domains": []}]}}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_unbound_settings_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``unbound.settings`` loads as one singleton next to advanced and forwards."""
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert "unbound.settings" in SINGLETON_RESOURCE_TYPES
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "unbound": {
                    "settings": {
                        "general": {"enabled": True},
                        "advanced": {"prefetch": True},
                    },
                    "advanced": {"private_domains": ["test.example.net"]},
                    "forwards": [{"name": "f1", "server": "192.0.2.53"}],
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "unbound.settings"]
        assert len(found) == 1
        assert found[0].name == "unbound.settings"
        assert found[0].config == {"general": {"enabled": True}, "advanced": {"prefetch": True}}
        assert any(r.type == "unbound.advanced" for r in resources)
        assert any(r.type == "unbound.forwards" for r in resources)

    def test_unbound_settings_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"unbound": {"settings": [{"general": {}}]}}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_interfaces_settings_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``interfaces.settings`` loads as one singleton."""
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert "interfaces.settings" in SINGLETON_RESOURCE_TYPES
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"interfaces": {"settings": {"vlan_hardware_filtering": "disable"}}}}
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "interfaces.settings"]
        assert len(found) == 1
        assert found[0].name == "interfaces.settings"
        assert found[0].config == {"vlan_hardware_filtering": "disable"}

    def test_interfaces_settings_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"interfaces": {"settings": [{"dhcp6_debug": True}]}}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_syslog_settings_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``syslog.settings`` loads as one singleton."""
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert "syslog.settings" in SINGLETON_RESOURCE_TYPES
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"syslog": {"settings": {"enabled": True, "max_preserve": 7}}}}
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "syslog.settings"]
        assert len(found) == 1
        assert found[0].name == "syslog.settings"
        assert found[0].config == {"enabled": True, "max_preserve": 7}

    def test_syslog_settings_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"syslog": {"settings": [{"enabled": True}]}}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_syslog_settings_docs_example_loads_and_validates(self, temp_dir: Path) -> None:
        """The coverage doc's syslog example parses through the loader and the validator."""
        import re

        import yaml

        from infrafoundry.core.validation import ValidationLevel, ValidationReport
        from infrafoundry.providers.opnsense.validators import SyslogSettingsValidator
        from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

        doc = Path(__file__).parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"
        section = doc.read_text().split("## Syslog settings (#804)", 1)[1]
        match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
        assert match is not None
        data = yaml.safe_load(match.group(1))
        resources = PackageLoader(temp_dir)._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "syslog.settings"]
        assert len(found) == 1
        report = ValidationReport()
        SyslogSettingsValidator(report).validate(OPNsenseValidationContext(resources=found))
        assert not [r for r in report.results if r.level == ValidationLevel.ERROR]

    def test_source_nat_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``firewall.source_nat`` loads as one singleton next to the ``firewall.nat`` list."""
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert "firewall.source_nat" in SINGLETON_RESOURCE_TYPES
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "nat": [
                        {
                            "name": "out",
                            "kind": "outbound",
                            "interface": "wan",
                            "target": "wanip",
                        }
                    ],
                    "source_nat": {"snat_mode": "hybrid"},
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "firewall.source_nat"]
        assert len(found) == 1
        assert found[0].config == {"snat_mode": "hybrid"}
        assert [r.name for r in resources if r.type == "firewall.nat"] == ["out"]

    def test_source_nat_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"firewall": {"source_nat": [{"snat_mode": "hybrid"}]}}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_hostdiscovery_is_a_singleton_dict(self, temp_dir: Path) -> None:
        """``hostdiscovery`` loads as one singleton named and typed ``hostdiscovery``."""
        from infrafoundry.core.config.package_loader import (
            DOTTED_RESOURCE_SHAPES,
            SINGLETON_RESOURCE_TYPES,
        )

        assert "hostdiscovery" in SINGLETON_RESOURCE_TYPES
        assert "hostwatch" not in DOTTED_RESOURCE_SHAPES
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"hostdiscovery": {"enabled": True, "skip_nets": ["192.0.2.0/24"]}}}
        resources = loader._parse_resources_from_data(data, "t.yaml", "opnsense")
        found = [r for r in resources if r.type == "hostdiscovery"]
        assert len(found) == 1
        assert found[0].name == "hostdiscovery"
        assert found[0].config == {"enabled": True, "skip_nets": ["192.0.2.0/24"]}

    def test_hostdiscovery_list_rejected(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data: dict[str, Any] = {"opnsense": {"hostdiscovery": [{"enabled": True}]}}
        with pytest.raises(InvalidConfigurationError, match="declared as a dict"):
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")

    def test_known_dict_path_with_list_leaf_rejected(self, temp_dir: Path) -> None:
        """``firewall.log: [...]`` (list where dict expected) errors."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"log": [{"x": 1}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.log" in msg
        assert "dict" in msg


@pytest.mark.unit
class TestParseNestedMalformedLeaf:
    """Scalar / malformed leaves at known paths are rejected."""

    def test_string_leaf_rejected(self, temp_dir: Path) -> None:
        """A string at a leaf raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"aliases": "not-a-list"}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "str" in msg

    def test_int_leaf_rejected(self, temp_dir: Path) -> None:
        """An int at a leaf raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"log": 42}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.log" in msg

    def test_top_level_list_under_namespace_rejected(self, temp_dir: Path) -> None:
        """A bare list directly under ``opnsense:`` is rejected.

        ``opnsense:`` itself is not a dict in this case, so the nested
        branch is not entered. The existing flat path treats ``opnsense:``
        like a top-level list keyed off the filename stem.
        """
        loader = PackageLoader(temp_dir)
        data = {"opnsense": ["a", "b"]}
        # Not a dict — falls through to flat parsing. Filename stem
        # 'opnsense' is not a known type, so we look up data['opnsense'],
        # which is a list of non-dicts; result is an empty list (existing
        # behaviour for non-dict items).
        resources = loader._parse_resources_from_data(data, "opnsense.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestParseNestedListEntryValidation:
    """Each list entry must be a dict with a ``name:`` field."""

    def test_missing_name_in_list_entry_raises(self, temp_dir: Path) -> None:
        """List entry without ``name:`` raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [{"config": {"type": "host"}}],
                }
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "name" in msg

    def test_non_dict_list_entry_raises(self, temp_dir: Path) -> None:
        """List entry that is a scalar raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {"aliases": ["bare-string-not-dict"]},
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "str" in msg

    def test_list_entry_index_in_error_message(self, temp_dir: Path) -> None:
        """Error message references the offending list entry index."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [
                        {"name": "ok", "config": {}},
                        {"config": {}},  # missing name at index 1
                    ]
                }
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        # Either order of stack pop is fine as long as index 1 is named.
        assert "1" in str(excinfo.value)


@pytest.mark.unit
class TestNestedFlatAmbiguity:
    """Mixing nested ``opnsense:`` with other top-level keys is rejected."""

    def test_nested_alongside_flat_aliases_rejected(self, temp_dir: Path) -> None:
        """``opnsense:`` plus a flat top-level key is ambiguous."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {"firewall": {"log": {"log_default_block": False}}},
            "aliases": [{"name": "x", "config": {}}],
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "mixed.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "cannot mix" in msg
        assert "aliases" in msg

    def test_nested_alongside_resource_centric_rejected(self, temp_dir: Path) -> None:
        """``opnsense:`` plus ``resources:`` is ambiguous."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {"firewall": {"log": {"log_default_block": False}}},
            "resources": [{"provider": "opnsense", "type": "x", "name": "y", "config": {}}],
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "mixed.yaml", "opnsense")
        assert "cannot mix" in str(excinfo.value)


@pytest.mark.unit
class TestFlatFormatNoLongerTranslated:
    """After Phase 5 hard cutover (#793), legacy flat OPNsense type names
    no longer auto-translate to dotted paths. Operators must use the nested
    ``opnsense:`` schema (or already-dotted types in resource-centric files);
    the conversion script in #793 Phase 6 does the one-shot migration.
    """

    def test_flat_provider_centric_keeps_stem_type(self, temp_dir: Path) -> None:
        """``aliases.yaml`` with top-level ``aliases:`` no longer translates.

        The loader still parses the document but emits ``ResourceConfig.type
        == 'aliases'`` (the filename stem). Dispatch will not match any
        OPNsense direct-API component — the operator sees a clear "unknown
        type" error downstream rather than silent acceptance.
        """
        loader = PackageLoader(temp_dir)
        data = {"aliases": [{"name": "trusted", "config": {"type": "host"}}]}
        resources = loader._parse_resources_from_data(data, "aliases.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "aliases"
        assert resources[0].name == "trusted"

    def test_flat_resource_centric_keeps_raw_type(self, temp_dir: Path) -> None:
        """``resources:`` with legacy ``type: kea_subnet`` no longer translates."""
        loader = PackageLoader(temp_dir)
        data = {
            "resources": [
                {
                    "provider": "opnsense",
                    "type": "kea_subnet",
                    "name": "lan",
                    "config": {"subnet": "172.21.0.0/24"},
                }
            ]
        }
        resources = loader._parse_resources_from_data(data, "rc.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea_subnet"
        assert resources[0].name == "lan"

    def test_resource_centric_dotted_type_passes_through(self, temp_dir: Path) -> None:
        """``resources:`` with already-dotted ``type:`` is unchanged."""
        loader = PackageLoader(temp_dir)
        data = {
            "resources": [
                {
                    "provider": "opnsense",
                    "type": "kea.dhcp4.subnets",
                    "name": "lan",
                    "config": {"subnet": "172.21.0.0/24"},
                }
            ]
        }
        resources = loader._parse_resources_from_data(data, "rc.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea.dhcp4.subnets"

    def test_unknown_nested_key_with_dict_value_recurses(self, temp_dir: Path) -> None:
        """Unknown interior dict key recurses without error if no leaves."""
        loader = PackageLoader(temp_dir)
        # ``opnsense.foo.bar`` has no list/dict leaf at a known path —
        # walking finds nothing and returns empty.
        data: dict[str, Any] = {"opnsense": {"foo": {"bar": {"baz": {}}}}}
        resources = loader._parse_resources_from_data(data, "x.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestNestedFormatProviderCentricLoader:
    """ProviderCentricLoader recognises the nested format too."""

    def _write_yaml(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_provider_centric_loader_parses_nested_singleton(self, temp_dir: Path) -> None:
        """Top-level ``opnsense:`` in a flat-style provider file is parsed."""
        loader = ProviderCentricLoader(temp_dir)
        # Filename stem is 'log' but the file is nested-format. The
        # nested branch should win regardless.
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "log.yaml",
            "opnsense:\n  firewall:\n    log:\n      log_default_block: false\n",
        )
        resources = loader.load_resources("dev", "opnsense", "log")
        assert len(resources) == 1
        assert resources[0].type == "firewall.log"
        assert resources[0].name == "firewall.log"
        assert resources[0].provider == "opnsense"

    def test_provider_centric_loader_parses_nested_list(self, temp_dir: Path) -> None:
        """Top-level ``opnsense:`` with list leaves works."""
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "fw.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    aliases:\n"
                "      - name: a1\n"
                "        config:\n"
                "          type: host\n"
            ),
        )
        resources = loader.load_resources("dev", "opnsense", "fw")
        assert len(resources) == 1
        assert resources[0].type == "firewall.aliases"
        assert resources[0].name == "a1"

    def test_provider_centric_loader_rejects_mixed_format(self, temp_dir: Path) -> None:
        """Mixing ``opnsense:`` with other top-level keys raises."""
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "fw.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "aliases:\n"
                "  - name: x\n"
                "    config: {}\n"
            ),
        )
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader.load_resources("dev", "opnsense", "fw")
        assert "cannot mix" in str(excinfo.value)

    def test_provider_centric_loader_flat_keeps_stem_type(self, temp_dir: Path) -> None:
        """After #793 Phase 5, flat OPNsense YAML no longer auto-translates.

        The file parses (so existing test/blueprint fixtures don't break
        outright), but the emitted ``ResourceConfig.type`` is the filename
        stem (``aliases``) rather than the dotted path (``firewall.aliases``).
        Dispatch will reject it downstream — operators must convert to the
        nested ``opnsense:`` schema (see #793 Phase 6 conversion script).
        """
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "aliases.yaml",
            ("aliases:\n  - name: trusted\n    type: host\n    content: 172.21.0.1\n"),
        )
        resources = loader.load_resources("dev", "opnsense", "aliases")
        assert len(resources) == 1
        assert resources[0].type == "aliases"


@pytest.mark.unit
class TestNestedFormatResourceCentricLoader:
    """ResourceCentricLoader recognises the nested format too."""

    def _write_yaml(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_resource_centric_loader_parses_nested(self, temp_dir: Path) -> None:
        """A resource-centric file with ``opnsense:`` at the top is nested."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "opnsense.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "      log_default_pass: true\n"
            ),
        )
        resources = loader.load_resources("dev")
        assert len(resources) == 1
        assert resources[0].type == "firewall.log"
        assert resources[0].name == "firewall.log"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == {
            "log_default_block": False,
            "log_default_pass": True,
        }

    def test_resource_centric_loader_rejects_mixed_format(self, temp_dir: Path) -> None:
        """Mixing ``opnsense:`` with ``resources:`` raises."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "mixed.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "resources:\n"
                "  - provider: opnsense\n"
                "    type: kea_subnet\n"
                "    name: lan\n"
                "    config:\n"
                "      subnet: 172.21.0.0/24\n"
            ),
        )
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader.load_resources("dev")
        assert "cannot mix" in str(excinfo.value)

    def test_resource_centric_loader_flat_still_works(self, temp_dir: Path) -> None:
        """Existing resource-centric YAML still parses through the loader."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "vms.yaml",
            (
                "resources:\n"
                "  - provider: proxmox\n"
                "    type: vm\n"
                "    name: web-01\n"
                "    config:\n"
                "      cores: 4\n"
            ),
        )
        resources = loader.load_resources("dev")
        assert len(resources) == 1
        assert resources[0].name == "web-01"
        assert resources[0].provider == "proxmox"
        assert resources[0].type == "vm"


@pytest.mark.unit
class TestParseNestedDirect:
    """Direct calls to ``_parse_nested_provider_format`` for edge cases."""

    def test_direct_call_with_empty_namespace(self, temp_dir: Path) -> None:
        """Calling with an empty dict returns an empty list."""
        loader = PackageLoader(temp_dir)
        result = loader._parse_nested_provider_format({}, "opnsense", "x.yaml")
        assert result == []

    def test_direct_call_carries_provider_argument(self, temp_dir: Path) -> None:
        """Provider passed in is reflected in emitted resources."""
        loader = PackageLoader(temp_dir)
        result = loader._parse_nested_provider_format(
            {"firewall": {"log": {"x": 1}}}, "opnsense", "x.yaml"
        )
        assert result[0].provider == "opnsense"

    def test_direct_call_non_string_key_rejected(self, temp_dir: Path) -> None:
        """Non-string interior key raises a clear error."""
        loader = PackageLoader(temp_dir)
        # Build a dict with an int key — Python allows it; YAML normally
        # wouldn't, but the loader must defend against it.
        data: dict[str, Any] = {123: {}}  # type: ignore[dict-item]
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_nested_provider_format(data, "opnsense", "x.yaml")
        assert "must be a string" in str(excinfo.value)


@pytest.mark.unit
class TestSingletonNamesAreDotted:
    """Several singletons coexist because each is named by its dotted type (#1237)."""

    def test_two_singletons_get_distinct_names(self, temp_dir: Path) -> None:
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"system": {"tuning": {"a": 1}, "firmware": {"b": 2}}}}
        resources = loader._parse_resources_from_data(data, "system.yaml", "opnsense")
        assert sorted(r.name for r in resources) == ["system.firmware", "system.tuning"]
        assert all(r.name == r.type for r in resources)

    def test_singleton_resource_types_constant(self) -> None:
        from infrafoundry.core.config.package_loader import SINGLETON_RESOURCE_TYPES

        assert {
            k for k, v in DOTTED_RESOURCE_SHAPES.items() if v == "dict"
        } == SINGLETON_RESOURCE_TYPES
        assert {"system.tuning", "radvd"} <= SINGLETON_RESOURCE_TYPES
        assert "firewall.aliases" not in SINGLETON_RESOURCE_TYPES


@pytest.mark.unit
class TestAcmeclientNested:
    """The acmeclient settings dict and four lists load to dotted types (#790)."""

    def test_settings_and_lists_load_with_name_injected(self, temp_dir: Path) -> None:
        data = {
            "opnsense": {
                "acmeclient": {
                    "settings": {"enabled": True},
                    "accounts": [{"name": "acct", "config": {"email": "admin@example.com"}}],
                    "validations": [{"name": "dns", "config": {"method": "dns01"}}],
                    "actions": [{"name": "gui", "config": {"type": "configd_restart_gui"}}],
                    "certs": [{"name": "web", "config": {"common_name": "a.example.com"}}],
                }
            }
        }
        resources = PackageLoader(temp_dir)._parse_resources_from_data(data, "t.yaml", "opnsense")
        by_type = {r.type: r for r in resources}
        assert set(by_type) == {
            "acmeclient.settings",
            "acmeclient.accounts",
            "acmeclient.validations",
            "acmeclient.actions",
            "acmeclient.certs",
        }
        assert by_type["acmeclient.settings"].config == {"enabled": True}
        assert by_type["acmeclient.accounts"].name == "acct"
        assert by_type["acmeclient.accounts"].config["name"] == "acct"
        assert by_type["acmeclient.certs"].config["common_name"] == "a.example.com"

    def test_list_given_as_dict_is_rejected(self, temp_dir: Path) -> None:
        data = {"opnsense": {"acmeclient": {"accounts": {"name": "x", "config": {}}}}}
        with pytest.raises(InvalidConfigurationError, match=r"acmeclient\.accounts"):
            PackageLoader(temp_dir)._parse_resources_from_data(data, "bad.yaml", "opnsense")
