"""End-to-end golden tests: ``Manager.migrate(...)`` emits nested-format YAML.

Per ADR-0016 (#793 Phase 4), every direct-OPNsense component manager's
``migrate()`` method must emit the new nested ``opnsense:`` schema rather
than the legacy flat resource-centric format. The CLI (``foundry config
migrate --provider opnsense --component <type>``) writes whatever each
manager returns verbatim, so the ``migrate()`` output must round-trip
through :class:`PackageLoader` cleanly to land at the documented dotted
``ResourceConfig.type``.

Each test below:

1. Mocks the live OPNsense API (each manager's ``Service.from_environment``
   factory) to return a small set of records.
2. Calls ``Manager.migrate(env_name, provider_name=...)``.
3. Asserts the YAML output has the nested ``opnsense:`` namespace at the
   expected dotted path (e.g. ``opnsense.firewall.aliases``).
4. Loads the YAML back through :func:`_parse_nested_provider_format` and
   verifies the resulting ``ResourceConfig`` list matches the mocked-live
   records by name and dotted type — this is the operator-facing contract:
   ``migrate`` output must be re-readable by the loader.

The 14 nominal direct-OPNsense resource types (per the ADR-0016 mapping
table) are covered across 12 manager classes — :class:`KeaDHCPManager`
emits all four Kea types in one document, so a single test exercises the
full Kea quartet with assertions per type.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.config.package_loader import (
    DOTTED_RESOURCE_SHAPES,
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.provider import ResourceConfig

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _round_trip(yaml_text: str, source_filename: str) -> list[ResourceConfig]:
    """Parse a nested YAML document the way the loader does at runtime.

    Equivalent to a single env-load step for the opnsense provider.
    Returns the list of ``ResourceConfig`` items the loader would emit
    if this were a real ``envs/<env>/<...>.yaml`` file.
    """
    data = yaml.safe_load(yaml_text)
    assert isinstance(data, dict), f"top-level YAML must be a mapping, got {type(data).__name__}"
    nested = data.get(NESTED_PROVIDER_NAMESPACE)
    assert isinstance(nested, dict), (
        f"top-level '{NESTED_PROVIDER_NAMESPACE}:' must be a mapping; got {type(nested).__name__}"
    )
    loader = PackageLoader(base_dir=Path("/tmp/unused"))
    return loader._parse_nested_provider_format(nested, NESTED_PROVIDER_NAMESPACE, source_filename)


def _assert_nested_path_present(yaml_text: str, dotted_type: str, *, expected_shape: str) -> Any:
    """Assert the YAML has the expected dotted path under ``opnsense:``.

    Returns the leaf value at the path so per-type tests can make
    further assertions on its shape and contents.
    """
    data = yaml.safe_load(yaml_text)
    assert NESTED_PROVIDER_NAMESPACE in data, (
        f"expected top-level '{NESTED_PROVIDER_NAMESPACE}:' in YAML; got "
        f"{sorted(data) if isinstance(data, dict) else type(data).__name__}"
    )
    cursor: Any = data[NESTED_PROVIDER_NAMESPACE]
    parts = dotted_type.split(".")
    for key in parts[:-1]:
        assert isinstance(cursor, dict) and key in cursor, (
            f"missing intermediate key '{key}' on path "
            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted_type}': cursor={cursor!r}"
        )
        cursor = cursor[key]
    leaf_key = parts[-1]
    assert isinstance(cursor, dict) and leaf_key in cursor, (
        f"missing leaf key '{leaf_key}' under "
        f"'{NESTED_PROVIDER_NAMESPACE}.{dotted_type}': cursor={cursor!r}"
    )
    leaf = cursor[leaf_key]
    if expected_shape == "list":
        assert isinstance(leaf, list), (
            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted_type}' must be a list "
            f"(got {type(leaf).__name__})"
        )
    elif expected_shape == "dict":
        assert isinstance(leaf, dict), (
            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted_type}' must be a dict "
            f"(got {type(leaf).__name__})"
        )
    return leaf


def _assert_no_flat_resources_key(yaml_text: str) -> None:
    """Sanity check: no flat-format ``resources:`` top-level survivor."""
    data = yaml.safe_load(yaml_text)
    assert isinstance(data, dict)
    assert "resources" not in data, (
        "Nested-format output should not contain the flat 'resources:' key. "
        f"Got top-level keys: {sorted(data)}"
    )


# ---------------------------------------------------------------------------
# 1. interfaces.vlans -- VlanManager
# ---------------------------------------------------------------------------


class TestMigrateVlansEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.vlan.VlanService"

    def test_vlans_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.vlan import VlanManager

        # Build a mock that has a real ``export_to_yaml`` (which is what
        # we're testing) — patch only ``from_environment``.
        from infrafoundry.providers.opnsense.services.vlan import VlanService

        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "if": "igb0", "tag": "10", "descr": "vlan10", "pcp": "0"},
                {"uuid": "u2", "if": "igb1", "tag": "20", "descr": "vlan20", "pcp": "0"},
            ]
        }
        real_service = VlanService(client)

        manager = VlanManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = real_service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "interfaces.vlans", expected_shape="list")
        assert len(leaf) == 2
        assert leaf[0]["name"] == "vlan-igb0-10"
        assert leaf[0]["config"]["device"] == "igb0"
        assert leaf[0]["config"]["tag"] == 10
        assert leaf[1]["name"] == "vlan-igb1-20"
        _assert_no_flat_resources_key(yaml_text)

        # Round-trip through the loader.
        parsed = _round_trip(yaml_text, "vlans.yaml")
        assert [(r.name, r.type) for r in parsed] == [
            ("vlan-igb0-10", "interfaces.vlans"),
            ("vlan-igb1-20", "interfaces.vlans"),
        ]


# ---------------------------------------------------------------------------
# 2. interfaces.assignments -- InterfaceAssignmentManager
# ---------------------------------------------------------------------------


class TestMigrateInterfaceAssignmentsEmitsNested:
    SERVICE_PATH = (
        "infrafoundry.providers.opnsense.components.interface_assignment.InterfaceAssignmentService"
    )

    def test_interface_assignments_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.interface_assignment import (
            InterfaceAssignmentManager,
        )
        from infrafoundry.providers.opnsense.services.interface_assignment import (
            InterfaceAssignmentService,
        )

        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "identifier": "lan",
                    "device": "igb1",
                    "description": "LAN",
                    "ipv4": [{"ipaddr": "10.0.0.1", "subnet": "24"}],
                    "ipv6": [],
                    "is_physical": True,
                },
                {
                    "identifier": "wan",
                    "device": "igb0",
                    "description": "WAN",
                    "ipv4": [{"ipaddr": "dhcp"}],
                    "ipv6": [],
                    "is_physical": True,
                },
            ]
        }
        real_service = InterfaceAssignmentService(client)

        manager = InterfaceAssignmentManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = real_service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(
            yaml_text, "interfaces.assignments", expected_shape="list"
        )
        names = sorted(entry["name"] for entry in leaf)
        assert names == ["lan", "wan"]
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "interface_assignments.yaml")
        assert {(r.name, r.type) for r in parsed} == {
            ("lan", "interfaces.assignments"),
            ("wan", "interfaces.assignments"),
        }


# ---------------------------------------------------------------------------
# 3. firewall.aliases -- AliasManager
# ---------------------------------------------------------------------------


class TestMigrateAliasesEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.alias.AliasService"

    def test_aliases_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.alias import AliasManager
        from infrafoundry.providers.opnsense.services.alias import AliasService

        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "name": "web_servers",
                    "type": {"host": {"value": "Host(s)", "selected": 1}},
                    "description": "Web tier",
                    "content": "10.0.0.1\n10.0.0.2",
                    "enabled": "1",
                },
                {
                    "uuid": "u2",
                    "name": "trusted_nets",
                    "type": {"network": {"value": "Network(s)", "selected": 1}},
                    "description": "Trusted",
                    "content": "10.0.0.0/24",
                    "enabled": "1",
                },
            ]
        }
        real_service = AliasService(client)

        manager = AliasManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = real_service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "firewall.aliases", expected_shape="list")
        assert len(leaf) == 2
        names = [entry["name"] for entry in leaf]
        assert "web_servers" in names
        assert "trusted_nets" in names
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "aliases.yaml")
        assert {(r.name, r.type) for r in parsed} == {
            ("web_servers", "firewall.aliases"),
            ("trusted_nets", "firewall.aliases"),
        }


# ---------------------------------------------------------------------------
# 4. firewall.nat -- NATRuleManager
# ---------------------------------------------------------------------------


class TestMigrateNATRulesEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.nat_rule.NATRuleService"

    def test_nat_rules_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.nat_rule import NATRuleManager

        # NATRuleService.search_all_tolerant() returns ``list[LiveNATRule]``.
        # We mock that directly to keep the test focused on the migrate
        # path's nested wrapping (rather than re-validating the search
        # parser, which has its own dedicated tests).
        from infrafoundry.providers.opnsense.services.nat_rule import (
            LiveNATRule,
            NATRuleService,
        )

        live_rules = [
            LiveNATRule(
                uuid="u1",
                kind="outbound",
                description="WAN nat [infrafoundry:wan-nat]",
                managed_name="wan-nat",
                raw={
                    "uuid": "u1",
                    "description": "WAN nat [infrafoundry:wan-nat]",
                    "interface": "wan",
                    "enabled": "1",
                },
            ),
            LiveNATRule(
                uuid="u2",
                kind="port_forward",
                description="ssh fwd [infrafoundry:ssh-fwd]",
                managed_name="ssh-fwd",
                raw={
                    "uuid": "u2",
                    "description": "ssh fwd [infrafoundry:ssh-fwd]",
                    "interface": "wan",
                    "enabled": "1",
                },
            ),
        ]
        service = NATRuleService(MagicMock())
        with patch.object(service, "search_all_tolerant", return_value=live_rules):
            manager = NATRuleManager(tmp_path)
            with patch(self.SERVICE_PATH) as svc_cls:
                svc_cls.from_environment.return_value = service
                yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "firewall.nat", expected_shape="list")
        names = sorted(entry["name"] for entry in leaf)
        assert names == ["ssh-fwd", "wan-nat"]
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "nat_rules.yaml")
        assert {(r.name, r.type) for r in parsed} == {
            ("wan-nat", "firewall.nat"),
            ("ssh-fwd", "firewall.nat"),
        }


# ---------------------------------------------------------------------------
# 5. firewall.rules -- FirewallRuleManager
# ---------------------------------------------------------------------------


class TestMigrateFirewallRulesEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.firewall_rule.FirewallRuleService"

    def test_firewall_rules_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.firewall_rule import (
            FirewallRuleManager,
        )
        from infrafoundry.providers.opnsense.services.firewall_rule import (
            FirewallRuleService,
        )

        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "description": "lan-allow [infrafoundry:lan-allow]",
                    "interface": "lan",
                    "action": "pass",
                    "enabled": "1",
                },
            ]
        }
        service = FirewallRuleService(client)
        # Prime the marker so unmanaged rules with no infrafoundry tag
        # are filtered correctly.
        service._category_uuid = "marker-uuid"

        manager = FirewallRuleManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "firewall.rules", expected_shape="list")
        names = [entry["name"] for entry in leaf]
        assert "lan-allow" in names
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "firewall_rules.yaml")
        assert {(r.name, r.type) for r in parsed} == {("lan-allow", "firewall.rules")}


# ---------------------------------------------------------------------------
# 6. routing.gateways -- GatewayManager
# ---------------------------------------------------------------------------


class TestMigrateGatewaysEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.gateway.GatewayService"

    def test_gateways_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.gateway import GatewayManager
        from infrafoundry.providers.opnsense.services.gateway import GatewayService

        # The service issues a search + per-gateway get; mock both.
        client = MagicMock()
        # ``search`` response is a {"rows": [...]} dict.
        # ``get`` response is a {"gateway_item": {...}} envelope.
        client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "name": "WAN_GW",
                        "interface": "wan",
                        "ipprotocol": "inet",
                        "gateway": "10.0.0.1",
                        "priority": "200",
                        "is_dynamic": "0",
                        "is_disabled": "0",
                        "default_gw": "1",
                    },
                ]
            },
            # getGateway/u1
            {
                "gateway_item": {
                    "name": "WAN_GW",
                    "interface": {"wan": {"value": "WAN", "selected": 1}},
                    "ipprotocol": {"inet": {"value": "IPv4", "selected": 1}},
                    "gateway": "10.0.0.1",
                    "priority": "200",
                    "disabled": "0",
                    "monitor_disable": "0",
                    "fargw": "0",
                    "force_down": "0",
                    "nonlocalgateway": "0",
                    "monitor": "",
                    "monitor_noroute": "0",
                    "weight": "1",
                    "data_payload": "1",
                    "descr": "",
                }
            },
        ]
        service = GatewayService(client)

        manager = GatewayManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "routing.gateways", expected_shape="list")
        assert leaf
        assert leaf[0]["name"] == "WAN_GW"
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "gateways.yaml")
        assert [(r.name, r.type) for r in parsed] == [("WAN_GW", "routing.gateways")]


# ---------------------------------------------------------------------------
# 7. routing.static -- StaticRouteManager
# ---------------------------------------------------------------------------


class TestMigrateStaticRoutesEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.static_route.StaticRouteService"

    def test_static_routes_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.static_route import (
            StaticRouteManager,
        )
        from infrafoundry.providers.opnsense.services.static_route import StaticRouteService

        client = MagicMock()
        client.request.side_effect = [
            # searchroute
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "network": "10.0.10.0/24",
                        "gateway": "WAN_GW",
                        "descr": "internal",
                        "disabled": "0",
                    },
                ]
            },
            # getroute/u1
            {
                "route": {
                    "network": "10.0.10.0/24",
                    "gateway": {
                        "WAN_GW": {"value": "WAN_GW - 10.0.0.1", "selected": 1},
                    },
                    "descr": "internal",
                    "disabled": "0",
                }
            },
        ]
        service = StaticRouteService(client)

        manager = StaticRouteManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "routing.static", expected_shape="list")
        assert leaf
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "static_routes.yaml")
        assert len(parsed) == 1
        assert parsed[0].type == "routing.static"


# ---------------------------------------------------------------------------
# 8. interfaces.virtual_ips -- VirtualIPManager
# ---------------------------------------------------------------------------


class TestMigrateVirtualIPsEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.virtual_ip.VirtualIPService"

    def test_virtual_ips_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.virtual_ip import VirtualIPManager
        from infrafoundry.providers.opnsense.services.virtual_ip import VirtualIPService

        client = MagicMock()
        client.request.side_effect = [
            # searchItem
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "interface": "lan",
                        "mode": "ipalias",
                        "address": "10.0.0.10",
                        "vhid": "",
                        "subnet_bits": "24",
                        "subnet": "10.0.0.10/24",
                        "descr": "alias",
                    },
                ]
            },
            # getItem/u1
            {
                "vip": {
                    "interface": {"lan": {"value": "LAN", "selected": 1}},
                    "mode": {"ipalias": {"value": "IP Alias", "selected": 1}},
                    "address": "10.0.0.10",
                    "subnet_bits": "24",
                    "vhid": "",
                    "advbase": "1",
                    "advskew": "0",
                    "descr": "alias",
                    "password": "",
                    "nobind": "0",
                    "peer": "",
                    "peer6": "",
                }
            },
        ]
        service = VirtualIPService(client)

        manager = VirtualIPManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(
            yaml_text, "interfaces.virtual_ips", expected_shape="list"
        )
        assert leaf
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "virtual_ips.yaml")
        assert len(parsed) == 1
        assert parsed[0].type == "interfaces.virtual_ips"


# ---------------------------------------------------------------------------
# 9. unbound.host_overrides -- UnboundHostOverrideManager
# ---------------------------------------------------------------------------


class TestMigrateUnboundHostOverridesEmitsNested:
    SERVICE_PATH = (
        "infrafoundry.providers.opnsense.components.unbound_host_override"
        ".UnboundHostOverrideService"
    )

    def test_unbound_host_overrides_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.unbound_host_override import (
            UnboundHostOverrideManager,
        )
        from infrafoundry.providers.opnsense.services.unbound_host_override import (
            UnboundHostOverrideService,
        )

        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {
                    "uuid": "u1",
                    "hostname": "web",
                    "domain": "example.com",
                    "rr": "A",
                    "server": "10.0.0.1",
                    "description": "",
                    "enabled": "1",
                },
                {
                    "uuid": "u2",
                    "hostname": "mail",
                    "domain": "example.com",
                    "rr": "A",
                    "server": "10.0.0.2",
                    "description": "",
                    "enabled": "1",
                },
            ]
        }
        service = UnboundHostOverrideService(client)

        manager = UnboundHostOverrideManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(
            yaml_text, "unbound.host_overrides", expected_shape="list"
        )
        names = sorted(entry["name"] for entry in leaf)
        assert names == ["mail-example-com", "web-example-com"]
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "unbound_host_overrides.yaml")
        assert {(r.name, r.type) for r in parsed} == {
            ("web-example-com", "unbound.host_overrides"),
            ("mail-example-com", "unbound.host_overrides"),
        }


# ---------------------------------------------------------------------------
# 10. unbound.host_aliases -- UnboundHostAliasManager
# ---------------------------------------------------------------------------


class TestMigrateUnboundHostAliasesEmitsNested:
    SERVICE_PATH = (
        "infrafoundry.providers.opnsense.components.unbound_host_alias.UnboundHostAliasService"
    )

    def test_unbound_host_aliases_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.unbound_host_alias import (
            UnboundHostAliasManager,
        )
        from infrafoundry.providers.opnsense.services.unbound_host_alias import (
            UnboundHostAliasService,
        )

        client = MagicMock()
        # Sequence: searchHostAlias, then per-uuid getHostAlias, then
        # searchHostOverride for the parent label map.
        client.request.side_effect = [
            # searchHostAlias
            {
                "rows": [
                    {
                        "uuid": "a1",
                        "host": {"u_parent": {"value": "web", "selected": 1}},
                        "hostname": "www",
                        "domain": "example.com",
                        "description": "",
                    },
                ]
            },
            # searchHostOverride
            {
                "rows": [
                    {
                        "uuid": "u_parent",
                        "hostname": "web",
                        "domain": "example.com",
                    },
                ]
            },
            # getHostAlias/a1
            {
                "alias": {
                    "host": {"u_parent": {"value": "web", "selected": 1}},
                    "hostname": "www",
                    "domain": "example.com",
                    "description": "",
                    "enabled": "1",
                }
            },
        ]
        service = UnboundHostAliasService(client)

        manager = UnboundHostAliasManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "unbound.host_aliases", expected_shape="list")
        assert leaf
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "unbound_host_aliases.yaml")
        assert len(parsed) == 1
        assert parsed[0].type == "unbound.host_aliases"


# ---------------------------------------------------------------------------
# 11. unbound.forwards -- UnboundForwardManager
# ---------------------------------------------------------------------------


class TestMigrateUnboundForwardsEmitsNested:
    SERVICE_PATH = (
        "infrafoundry.providers.opnsense.components.unbound_forward.UnboundForwardService"
    )

    def test_unbound_forwards_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.unbound_forward import (
            UnboundForwardManager,
        )
        from infrafoundry.providers.opnsense.services.unbound_forward import (
            UnboundForwardService,
        )

        client = MagicMock()
        client.request.side_effect = [
            # searchForward
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "type": "forward",
                        "domain": "example.com",
                        "server": "1.1.1.1",
                        "port": "53",
                        "verify": "",
                        "description": "",
                        "enabled": "1",
                    },
                ]
            },
            # getForward/u1
            {
                "dot": {
                    "type": {"forward": {"value": "Forward", "selected": 1}},
                    "domain": "example.com",
                    "server": "1.1.1.1",
                    "port": "53",
                    "verify": "",
                    "description": "",
                    "enabled": "1",
                }
            },
        ]
        service = UnboundForwardService(client)

        manager = UnboundForwardManager(tmp_path)
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "unbound.forwards", expected_shape="list")
        assert leaf
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "unbound_forwards.yaml")
        assert len(parsed) == 1
        assert parsed[0].type == "unbound.forwards"


# ---------------------------------------------------------------------------
# 12-15. KeaDHCPManager emits all four kea types in one call:
#   kea.dhcp4.subnets, kea.dhcp4.reservations,
#   kea.dhcp6.subnets, kea.dhcp6.reservations.
# ---------------------------------------------------------------------------


class TestMigrateKeaDHCPEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp.KeaDHCPService"

    @pytest.fixture
    def manager_with_service(self, tmp_path: Path) -> tuple[Any, Any]:
        from infrafoundry.providers.opnsense.components.kea_dhcp import KeaDHCPManager
        from infrafoundry.providers.opnsense.services.kea_dhcp import KeaDHCPService

        # Build a *real* KeaDHCPService so ``export_to_yaml`` runs the
        # nested-emit code path. Replace only the four search methods.
        # Using ``MagicMock()`` for the whole service auto-mocks
        # ``export_to_yaml`` to return a MagicMock, which downstream
        # ``yaml.safe_load`` then reads from indefinitely (allocates
        # tens of GB and hangs).
        service = KeaDHCPService(MagicMock())
        service.search_dhcpv4_subnets = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {"description": "lan", "subnet": "10.0.0.0/24", "pools": "10.0.0.10-10.0.0.99"},
            ]
        )
        service.search_dhcpv4_reservations = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "subnet": "10.0.0.0/24",
                    "hw_address": "aa:bb:cc:dd:ee:ff",
                    "ip_address": "10.0.0.50",
                    "hostname": "fileserver",
                    "description": "FS",
                },
            ]
        )
        service.search_dhcpv6_subnets = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {"description": "lan", "subnet": "2001:db8::/64"},
            ]
        )
        service.search_dhcpv6_reservations = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "subnet": "2001:db8::/64",
                    "duid": "00:01:00:01:aa:bb",
                    "ip_address": "2001:db8::50",
                    "hostname": "fileserver",
                    "description": "FS6",
                },
            ]
        )

        manager = KeaDHCPManager(tmp_path)
        return manager, service

    def test_kea_emits_all_four_types_under_nested_namespace(
        self, manager_with_service: tuple[Any, MagicMock]
    ) -> None:
        manager, service = manager_with_service
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        # All four leaves must be present even if some are empty.
        for dotted in (
            "kea.dhcp4.subnets",
            "kea.dhcp4.reservations",
            "kea.dhcp6.subnets",
            "kea.dhcp6.reservations",
        ):
            leaf = _assert_nested_path_present(yaml_text, dotted, expected_shape="list")
            assert isinstance(leaf, list)
        _assert_no_flat_resources_key(yaml_text)

    def test_kea_dhcp4_subnets_round_trip(
        self, manager_with_service: tuple[Any, MagicMock]
    ) -> None:
        manager, service = manager_with_service
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        parsed = _round_trip(yaml_text, "kea_dhcp.yaml")
        v4_subnets = [r for r in parsed if r.type == "kea.dhcp4.subnets"]
        assert len(v4_subnets) == 1
        assert v4_subnets[0].name == "lan"
        assert v4_subnets[0].config["subnet"] == "10.0.0.0/24"

    def test_kea_dhcp4_reservations_round_trip(
        self, manager_with_service: tuple[Any, MagicMock]
    ) -> None:
        manager, service = manager_with_service
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        parsed = _round_trip(yaml_text, "kea_dhcp.yaml")
        v4_res = [r for r in parsed if r.type == "kea.dhcp4.reservations"]
        assert len(v4_res) == 1
        assert v4_res[0].name == "fileserver"

    def test_kea_dhcp6_subnets_round_trip(
        self, manager_with_service: tuple[Any, MagicMock]
    ) -> None:
        manager, service = manager_with_service
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        parsed = _round_trip(yaml_text, "kea_dhcp.yaml")
        v6_subnets = [r for r in parsed if r.type == "kea.dhcp6.subnets"]
        assert len(v6_subnets) == 1
        assert v6_subnets[0].name == "lan_v6"

    def test_kea_dhcp6_reservations_round_trip(
        self, manager_with_service: tuple[Any, MagicMock]
    ) -> None:
        manager, service = manager_with_service
        with patch(self.SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            yaml_text = manager.migrate("test-env")

        parsed = _round_trip(yaml_text, "kea_dhcp.yaml")
        v6_res = [r for r in parsed if r.type == "kea.dhcp6.reservations"]
        assert len(v6_res) == 1
        assert v6_res[0].name == "fileserver_v6"


# ---------------------------------------------------------------------------
# Cross-cutting: all 14 dotted paths declared by the loader's shape table
# match what the `migrate` paths currently emit. If a manager forgot to
# wire its new dotted type into either ``DOTTED_RESOURCE_SHAPES`` or its
# own ``export_to_yaml``, the round-trip tests above would fail per-type;
# this guard catches a stale registration in one place.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 16. cron.jobs -- CronJobsManager (#789)
# ---------------------------------------------------------------------------


class TestMigrateCronJobsEmitsNested:
    SERVICE_PATH = "infrafoundry.providers.opnsense.components.cron_jobs.CronJobsService"

    def test_cron_jobs_emit_nested(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.components.cron_jobs import CronJobsManager
        from infrafoundry.providers.opnsense.services.cron_jobs import (
            CronJobsService,
            LiveCronJob,
        )

        live_job = LiveCronJob(
            uuid="uuid-1",
            managed_name="acme-renew",
            description="[infrafoundry:acme-renew]",
            origin="AcmeClient",
            raw={
                "uuid": "uuid-1",
                "description": "[infrafoundry:acme-renew]",
                "enabled": "1",
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "acmeclient cron-auto-renew",
                "parameters": "",
                "origin": "AcmeClient",
            },
        )
        # Use a real service so export_to_yaml exercises the real emit path.
        service = CronJobsService(MagicMock())
        with patch.object(service, "search", return_value=[live_job]):
            manager = CronJobsManager(tmp_path)
            with patch(self.SERVICE_PATH) as svc_cls:
                svc_cls.from_environment.return_value = service
                yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "cron.jobs", expected_shape="list")
        assert len(leaf) == 1
        assert leaf[0]["name"] == "acme-renew"
        _assert_no_flat_resources_key(yaml_text)

        parsed = _round_trip(yaml_text, "cron_jobs.yaml")
        assert [(r.name, r.type) for r in parsed] == [("acme-renew", "cron.jobs")]

    def test_cron_jobs_unmanaged_excluded(self, tmp_path: Path) -> None:
        """Unmanaged live jobs (no identity suffix) are NOT exported."""
        from infrafoundry.providers.opnsense.components.cron_jobs import CronJobsManager
        from infrafoundry.providers.opnsense.services.cron_jobs import (
            CronJobsService,
            LiveCronJob,
        )

        unmanaged = LiveCronJob(
            uuid="uuid-unmanaged",
            managed_name=None,
            description="unmanaged box cron",
            origin="OPNsense",
            raw={
                "uuid": "uuid-unmanaged",
                "description": "unmanaged box cron",
                "enabled": "1",
                "minutes": "5",
                "hours": "*",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "/usr/local/sbin/whatever",
                "parameters": "",
                "origin": "OPNsense",
            },
        )
        service = CronJobsService(MagicMock())
        with patch.object(service, "search", return_value=[unmanaged]):
            manager = CronJobsManager(tmp_path)
            with patch(self.SERVICE_PATH) as svc_cls:
                svc_cls.from_environment.return_value = service
                yaml_text = manager.migrate("test-env")

        leaf = _assert_nested_path_present(yaml_text, "cron.jobs", expected_shape="list")
        assert leaf == []


class TestDottedTypeRegistrySanity:
    """The 15 list-shape resource types (phase-1 + cron.jobs) are all accounted for."""

    EXPECTED_LIST_TYPES: tuple[str, ...] = (
        "interfaces.vlans",
        "interfaces.assignments",
        "firewall.aliases",
        "firewall.nat",
        "firewall.rules",
        "routing.gateways",
        "routing.static",
        "interfaces.virtual_ips",
        "unbound.host_overrides",
        "unbound.host_aliases",
        "unbound.forwards",
        "kea.dhcp4.subnets",
        "kea.dhcp4.reservations",
        "kea.dhcp6.subnets",
        "kea.dhcp6.reservations",
        "cron.jobs",
    )

    def test_each_phase_1_dotted_type_registered_as_list(self) -> None:
        for dotted in self.EXPECTED_LIST_TYPES:
            assert dotted in DOTTED_RESOURCE_SHAPES, (
                f"{dotted!r} is not in DOTTED_RESOURCE_SHAPES — the loader "
                "won't accept its nested-format YAML."
            )
            assert DOTTED_RESOURCE_SHAPES[dotted] == "list", (
                f"{dotted!r} declared as {DOTTED_RESOURCE_SHAPES[dotted]!r}, expected 'list'."
            )
