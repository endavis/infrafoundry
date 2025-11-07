#!/usr/bin/env python3
"""
OPNsense Configuration Parser

Parses OPNsense config.xml backup and generates InfraFoundry YAML configurations.
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml


class OPNsenseParser:
    """Parse OPNsense XML configuration and generate InfraFoundry YAML files."""

    def __init__(self, config_path: Path):
        """Initialize parser with config file path."""
        self.config_path = config_path
        self.tree = ET.parse(config_path)
        self.root = self.tree.getroot()

    def parse_interfaces(self) -> dict[str, Any]:
        """Parse interface configurations."""
        interfaces = {}
        interfaces_elem = self.root.find("interfaces")

        if interfaces_elem is None:
            return interfaces

        for iface in interfaces_elem:
            if iface.tag == "lo0":  # Skip loopback
                continue

            name = iface.tag
            config = {
                "name": name,
                "physical_interface": self._get_text(iface, "if"),
                "description": self._get_text(iface, "descr") or name.upper(),
                "enabled": self._get_text(iface, "enable") == "1",
            }

            # IPv4 configuration
            ipaddr = self._get_text(iface, "ipaddr")
            if ipaddr and ipaddr not in ("dhcp", "dhcp6"):
                config["ipv4_address"] = ipaddr
                subnet = self._get_text(iface, "subnet")
                if subnet:
                    config["ipv4_subnet"] = int(subnet)
            elif ipaddr == "dhcp":
                config["ipv4_type"] = "dhcp"

            # IPv6 configuration
            ipaddrv6 = self._get_text(iface, "ipaddrv6")
            if ipaddrv6 and ipaddrv6 not in ("dhcp6", "::1"):
                config["ipv6_address"] = ipaddrv6
                subnetv6 = self._get_text(iface, "subnetv6")
                if subnetv6:
                    config["ipv6_subnet"] = int(subnetv6)
            elif ipaddrv6 == "dhcp6":
                config["ipv6_type"] = "dhcp6"

            # Security settings
            if self._get_text(iface, "blockpriv") == "1":
                config["block_private_networks"] = True
            if self._get_text(iface, "blockbogons") == "1":
                config["block_bogon_networks"] = True

            interfaces[name] = config

        return interfaces

    def parse_aliases(self) -> dict[str, Any]:
        """Parse firewall aliases."""
        aliases = {}

        # Find aliases in the Firewall section
        firewall = self.root.find(".//Firewall")
        if firewall is None:
            return aliases

        alias_section = firewall.find(".//Alias")
        if alias_section is None:
            return aliases

        aliases_elem = alias_section.find("aliases")
        if aliases_elem is None:
            return aliases

        for alias in aliases_elem.findall("alias"):
            name = self._get_text(alias, "name")
            alias_type = self._get_text(alias, "type")
            enabled = self._get_text(alias, "enabled") == "1"
            content = self._get_text(alias, "content", "")
            description = self._get_text(alias, "description", "")

            if not name or not enabled:
                continue

            # Parse content based on type
            items = [line.strip() for line in content.split("\n") if line.strip()]

            alias_config = {
                "name": name,
                "type": alias_type,
                "description": description,
            }

            if alias_type == "host":
                alias_config["addresses"] = items
            elif alias_type == "network":
                alias_config["networks"] = items
            elif alias_type == "port":
                alias_config["ports"] = items
            else:
                alias_config["content"] = items

            aliases[name] = alias_config

        return aliases

    def parse_dhcp(self) -> dict[str, Any]:
        """Parse DHCP server configurations."""
        dhcp_configs = {}
        dhcpd = self.root.find("dhcpd")

        if dhcpd is None:
            return dhcp_configs

        for interface in dhcpd:
            iface_name = interface.tag
            enabled = self._get_text(interface, "enable") == "1"

            if not enabled:
                continue

            config = {
                "interface": iface_name,
                "enabled": True,
            }

            # Range
            range_elem = interface.find("range")
            if range_elem is not None:
                from_ip = self._get_text(range_elem, "from")
                to_ip = self._get_text(range_elem, "to")
                if from_ip and to_ip:
                    config["range"] = {
                        "from": from_ip,
                        "to": to_ip,
                    }

            # Static mappings
            static_maps = []
            for static in interface.findall("staticmap"):
                mac = self._get_text(static, "mac")
                ipaddr = self._get_text(static, "ipaddr")
                hostname = self._get_text(static, "hostname", "")
                descr = self._get_text(static, "descr", "")

                if mac and ipaddr:
                    mapping = {
                        "mac_address": mac,
                        "ip_address": ipaddr,
                    }
                    if hostname:
                        mapping["hostname"] = hostname
                    if descr:
                        mapping["description"] = descr

                    static_maps.append(mapping)

            if static_maps:
                config["static_mappings"] = static_maps

            # Default lease time
            lease_time = self._get_text(interface, "defaultleasetime")
            if lease_time:
                config["default_lease_time"] = int(lease_time)

            dhcp_configs[iface_name] = config

        return dhcp_configs

    def parse_firewall_rules(self) -> list[dict[str, Any]]:
        """Parse firewall rules."""
        rules = []
        filter_elem = self.root.find("filter")

        if filter_elem is None:
            return rules

        for rule in filter_elem.findall("rule"):
            uuid = rule.get("uuid", "")

            # Basic rule properties
            rule_config = {
                "uuid": uuid,
                "type": self._get_text(rule, "type", "pass"),
                "interface": self._get_text(rule, "interface", ""),
                "protocol": self._get_text(rule, "ipprotocol", "inet"),
                "description": self._get_text(rule, "descr", ""),
            }

            # Direction
            direction = self._get_text(rule, "direction")
            if direction:
                rule_config["direction"] = direction

            # Floating rule
            if self._get_text(rule, "floating") == "yes":
                rule_config["floating"] = True

            # Quick
            if self._get_text(rule, "quick") == "1":
                rule_config["quick"] = True

            # Protocol (TCP/UDP/etc)
            protocol = self._get_text(rule, "protocol")
            if protocol:
                rule_config["transport_protocol"] = protocol

            # Source
            source = rule.find("source")
            if source is not None:
                src_config = {}
                src_net = self._get_text(source, "network")
                src_addr = self._get_text(source, "address")
                src_port = self._get_text(source, "port")

                if src_net:
                    src_config["network"] = src_net
                elif src_addr:
                    src_config["address"] = src_addr

                if src_port:
                    src_config["port"] = src_port

                if self._get_text(source, "not") == "1":
                    src_config["invert"] = True

                if src_config:
                    rule_config["source"] = src_config

            # Destination
            destination = rule.find("destination")
            if destination is not None:
                dst_config = {}
                dst_net = self._get_text(destination, "network")
                dst_addr = self._get_text(destination, "address")
                dst_port = self._get_text(destination, "port")

                if dst_net:
                    dst_config["network"] = dst_net
                elif dst_addr:
                    dst_config["address"] = dst_addr

                if dst_port:
                    dst_config["port"] = dst_port

                if self._get_text(destination, "not") == "1":
                    dst_config["invert"] = True

                if dst_config:
                    rule_config["destination"] = dst_config

            # Gateway
            gateway = self._get_text(rule, "gateway")
            if gateway:
                rule_config["gateway"] = gateway

            # Disabled
            if self._get_text(rule, "disabled") == "1":
                rule_config["enabled"] = False
            else:
                rule_config["enabled"] = True

            rules.append(rule_config)

        return rules

    def parse_vlans(self) -> list[dict[str, Any]]:
        """Parse VLAN configurations."""
        vlans = []
        vlans_elem = self.root.find("vlans")

        if vlans_elem is None:
            return vlans

        for vlan in vlans_elem.findall("vlan"):
            vlan_id = self._get_text(vlan, "tag")
            parent = self._get_text(vlan, "if")
            descr = self._get_text(vlan, "descr", "")

            if vlan_id and parent:
                vlans.append({
                    "vlan_id": int(vlan_id),
                    "parent_interface": parent,
                    "description": descr,
                })

        return vlans

    def _get_text(self, elem: ET.Element, tag: str, default: str = "") -> str:
        """Safely get text content from an XML element."""
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return default

    def parse_system(self) -> dict[str, Any]:
        """Parse system configuration."""
        system = self.root.find("system")
        if system is None:
            return {}

        config = {
            "hostname": self._get_text(system, "hostname"),
            "domain": self._get_text(system, "domain"),
            "timezone": self._get_text(system, "timezone"),
            "language": self._get_text(system, "language", "en_US"),
        }

        # DNS servers
        dns_servers = []
        for dns in system.findall("dnsserver"):
            if dns.text:
                dns_servers.append(dns.text.strip())
        if dns_servers:
            config["dns_servers"] = dns_servers

        # SSH configuration
        ssh = system.find("ssh")
        if ssh is not None:
            ssh_config = {
                "enabled": self._get_text(ssh, "enabled") == "enabled",
                "interfaces": self._get_text(ssh, "interfaces", ""),
            }
            config["ssh"] = ssh_config

        # WebGUI configuration
        webgui = system.find("webgui")
        if webgui is not None:
            config["webgui"] = {
                "protocol": self._get_text(webgui, "protocol", "https"),
                "port": self._get_text(webgui, "port", ""),
            }

        return config

    def parse_gateways(self) -> list[dict[str, Any]]:
        """Parse gateway configurations."""
        gateways = []
        gateways_section = self.root.find(".//Gateways")

        if gateways_section is None:
            return gateways

        for gateway in gateways_section.findall("gateway_item"):
            gw_config = {
                "uuid": gateway.get("uuid", ""),
                "name": self._get_text(gateway, "name"),
                "description": self._get_text(gateway, "descr", ""),
                "interface": self._get_text(gateway, "interface"),
                "protocol": self._get_text(gateway, "ipprotocol"),
                "gateway_ip": self._get_text(gateway, "gateway", "dynamic"),
                "default_gateway": self._get_text(gateway, "defaultgw") == "1",
                "disabled": self._get_text(gateway, "disabled") == "1",
                "monitor_disable": self._get_text(gateway, "monitor_disable") == "1",
                "priority": self._get_text(gateway, "priority", "255"),
            }

            gateways.append(gw_config)

        return gateways

    def parse_nat_outbound(self) -> list[dict[str, Any]]:
        """Parse NAT outbound rules."""
        nat_rules = []
        nat = self.root.find("nat")

        if nat is None:
            return nat_rules

        outbound = nat.find("outbound")
        if outbound is None:
            return nat_rules

        mode = self._get_text(outbound, "mode", "automatic")

        for rule in outbound.findall("rule"):
            source = rule.find("source")
            destination = rule.find("destination")

            rule_config = {
                "description": self._get_text(rule, "descr", ""),
                "interface": self._get_text(rule, "interface"),
                "protocol": self._get_text(rule, "ipprotocol", "inet"),
            }

            if source is not None:
                src_network = self._get_text(source, "network")
                if src_network:
                    rule_config["source_network"] = src_network

            if destination is not None:
                if self._get_text(destination, "any") == "1":
                    rule_config["destination"] = "any"

            nat_rules.append(rule_config)

        return {"mode": mode, "rules": nat_rules}

    def parse_openvpn(self) -> list[dict[str, Any]]:
        """Parse OpenVPN client configurations."""
        vpn_clients = []
        openvpn = self.root.find("openvpn")

        if openvpn is None:
            return vpn_clients

        for client in openvpn.findall("openvpn-client"):
            client_config = {
                "description": self._get_text(client, "description"),
                "server_address": self._get_text(client, "server_addr"),
                "server_port": self._get_text(client, "server_port"),
                "protocol": self._get_text(client, "protocol", "UDP4"),
                "device_mode": self._get_text(client, "dev_mode", "tun"),
                "crypto": self._get_text(client, "crypto", "AES-256-GCM"),
                "digest": self._get_text(client, "digest", "SHA512"),
                "vpn_id": self._get_text(client, "vpnid"),
                "auth_user": self._get_text(client, "auth_user", "REDACTED"),
                "auth_pass": "REDACTED",  # Never export passwords
            }

            # Custom options
            custom_opts = self._get_text(client, "custom_options", "")
            if custom_opts:
                client_config["custom_options"] = custom_opts.split(";")

            vpn_clients.append(client_config)

        return vpn_clients

    def generate_infrafoundry_configs(self, output_dir: Path) -> None:
        """Generate InfraFoundry YAML configuration files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Parse all sections
        system_config = self.parse_system()
        interfaces = self.parse_interfaces()
        aliases = self.parse_aliases()
        dhcp = self.parse_dhcp()
        rules = self.parse_firewall_rules()
        vlans = self.parse_vlans()
        gateways = self.parse_gateways()
        nat_outbound = self.parse_nat_outbound()
        openvpn_clients = self.parse_openvpn()

        # Create opnsense directory
        opnsense_dir = output_dir / "opnsense"
        opnsense_dir.mkdir(exist_ok=True)

        # Write system configuration
        if system_config:
            system_file = opnsense_dir / "system.yaml"
            with open(system_file, "w") as f:
                yaml.dump(
                    {"system": system_config},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {system_file}")

        # Write interfaces
        if interfaces:
            interfaces_file = opnsense_dir / "interfaces.yaml"
            with open(interfaces_file, "w") as f:
                yaml.dump(
                    {"interfaces": list(interfaces.values())},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {interfaces_file} ({len(interfaces)} interfaces)")

        # Write VLANs
        if vlans:
            vlans_file = opnsense_dir / "vlans.yaml"
            with open(vlans_file, "w") as f:
                yaml.dump(
                    {"vlans": vlans},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {vlans_file} ({len(vlans)} VLANs)")

        # Write aliases
        if aliases:
            aliases_file = opnsense_dir / "aliases.yaml"
            with open(aliases_file, "w") as f:
                yaml.dump(
                    {"aliases": list(aliases.values())},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {aliases_file} ({len(aliases)} aliases)")

        # Write DHCP
        if dhcp:
            dhcp_file = opnsense_dir / "dhcp.yaml"
            with open(dhcp_file, "w") as f:
                yaml.dump(
                    {"dhcp_servers": list(dhcp.values())},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {dhcp_file} ({len(dhcp)} DHCP servers)")

        # Write firewall rules
        if rules:
            # Separate by interface/floating
            rules_by_interface = {}
            floating_rules = []

            for rule in rules:
                if rule.get("floating"):
                    floating_rules.append(rule)
                else:
                    iface = rule.get("interface", "unassigned")
                    if iface not in rules_by_interface:
                        rules_by_interface[iface] = []
                    rules_by_interface[iface].append(rule)

            # Write floating rules
            if floating_rules:
                floating_file = opnsense_dir / "firewall_rules_floating.yaml"
                with open(floating_file, "w") as f:
                    yaml.dump(
                        {"firewall_rules": floating_rules},
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        width=120,
                    )
                print(f"✓ Generated {floating_file} ({len(floating_rules)} floating rules)")

            # Write per-interface rules
            for iface, iface_rules in rules_by_interface.items():
                rules_file = opnsense_dir / f"firewall_rules_{iface}.yaml"
                with open(rules_file, "w") as f:
                    yaml.dump(
                        {"firewall_rules": iface_rules},
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        width=120,
                    )
                print(f"✓ Generated {rules_file} ({len(iface_rules)} rules)")

        # Write gateways
        if gateways:
            gateways_file = opnsense_dir / "gateways.yaml"
            with open(gateways_file, "w") as f:
                yaml.dump(
                    {"gateways": gateways},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {gateways_file} ({len(gateways)} gateways)")

        # Write NAT outbound rules
        if nat_outbound and nat_outbound.get("rules"):
            nat_file = opnsense_dir / "nat_outbound.yaml"
            with open(nat_file, "w") as f:
                yaml.dump(
                    {"nat_outbound": nat_outbound},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(
                f"✓ Generated {nat_file} (mode: {nat_outbound['mode']}, "
                f"{len(nat_outbound['rules'])} rules)"
            )

        # Write OpenVPN clients
        if openvpn_clients:
            vpn_file = opnsense_dir / "openvpn_clients.yaml"
            with open(vpn_file, "w") as f:
                yaml.dump(
                    {"openvpn_clients": openvpn_clients},
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            print(f"✓ Generated {vpn_file} ({len(openvpn_clients)} VPN clients)")

        # Generate summary README
        readme_file = output_dir / "README.md"
        with open(readme_file, "w") as f:
            f.write("# OPNsense Configuration\n\n")
            f.write("Generated from OPNsense config.xml backup.\n\n")
            f.write(f"**Source**: {self.config_path.name}\n")
            f.write(f"**Hostname**: {system_config.get('hostname', 'N/A')}\n")
            f.write(f"**Domain**: {system_config.get('domain', 'N/A')}\n\n")
            f.write("## Summary\n\n")
            f.write(f"- **Interfaces**: {len(interfaces)}\n")
            f.write(f"- **VLANs**: {len(vlans)}\n")
            f.write(f"- **Gateways**: {len(gateways)}\n")
            f.write(f"- **Aliases**: {len(aliases)}\n")
            f.write(f"- **DHCP Servers**: {len(dhcp)}\n")
            f.write(f"- **Firewall Rules**: {len(rules)}\n")
            if nat_outbound and nat_outbound.get("rules"):
                f.write(f"- **NAT Outbound Rules**: {len(nat_outbound['rules'])}\n")
            if openvpn_clients:
                f.write(f"- **OpenVPN Clients**: {len(openvpn_clients)}\n")
            f.write("\n## Files\n\n")
            f.write("- `opnsense/system.yaml` - System settings (hostname, DNS, timezone)\n")
            f.write("- `opnsense/interfaces.yaml` - Network interface configurations\n")
            if vlans:
                f.write("- `opnsense/vlans.yaml` - VLAN definitions\n")
            f.write("- `opnsense/gateways.yaml` - Gateway configurations\n")
            f.write("- `opnsense/aliases.yaml` - Firewall aliases (hosts, networks, ports)\n")
            f.write("- `opnsense/dhcp.yaml` - DHCP server configurations\n")
            f.write("- `opnsense/firewall_rules_*.yaml` - Firewall rules by interface\n")
            if nat_outbound and nat_outbound.get("rules"):
                f.write("- `opnsense/nat_outbound.yaml` - NAT outbound rules\n")
            if openvpn_clients:
                f.write("- `opnsense/openvpn_clients.yaml` - OpenVPN client configurations\n")
            f.write("\n## Configuration Coverage\n\n")
            f.write("This export includes all essential configuration to rebuild OPNsense:\n\n")
            f.write("✅ **System settings** - Hostname, domain, DNS, timezone, SSH, WebGUI\n")
            f.write("✅ **Network configuration** - Interfaces, VLANs, gateways\n")
            f.write("✅ **Firewall** - Rules, aliases, NAT outbound\n")
            f.write("✅ **Services** - DHCP server, OpenVPN clients\n\n")
            f.write("⚠️ **Not included** (requires manual configuration):\n")
            f.write("- User accounts and passwords (security sensitive)\n")
            f.write("- Certificates and private keys (security sensitive)\n")
            f.write("- OpenVPN authentication credentials (marked as REDACTED)\n")
            f.write("- WireGuard configurations (if any)\n")
            f.write("- Port forwarding rules (NAT port forward)\n")
            f.write("- Custom plugins/packages\n\n")
            f.write("## Next Steps\n\n")
            f.write("1. **Review the generated files** - Check all configurations\n")
            f.write("2. **Copy to InfraFoundry** - `cp -r opnsense/ $INFRAFOUNDRY_CONFIG_REPO/envs/prod/`\n")
            f.write("3. **Add sensitive data** - Create `secrets/opnsense.yaml` for VPN credentials\n")
            f.write("4. **Encrypt secrets** - `infra secrets encrypt secrets/opnsense.yaml`\n")
            f.write("5. **Update environment** - Add OPNsense provider to `envs/prod/environment.yaml`\n")
            f.write("6. **Generate Terraform** - `infra plan --env prod`\n")
            f.write("7. **Apply changes** - `infra apply --env prod`\n\n")
            f.write("## Rebuilding from Scratch\n\n")
            f.write("To recreate this OPNsense configuration:\n\n")
            f.write("1. Install fresh OPNsense on hardware/VM\n")
            f.write("2. Complete initial setup wizard (set WAN/LAN interfaces)\n")
            f.write("3. Use InfraFoundry (when OPNsense provider is available) OR\n")
            f.write("4. Manually restore via: System → Configuration → Backups → Restore\n")
            f.write("5. Reconfigure sensitive items: users, certificates, VPN credentials\n")

        print(f"\n✓ Generated {readme_file}")
        print(f"\nAll configuration files written to: {output_dir}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parse OPNsense config.xml and generate InfraFoundry YAML configurations"
    )
    parser.add_argument(
        "config_xml",
        type=Path,
        help="Path to OPNsense config.xml backup file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("opnsense-config"),
        help="Output directory for generated YAML files (default: opnsense-config)",
    )

    args = parser.parse_args()

    if not args.config_xml.exists():
        print(f"Error: Config file not found: {args.config_xml}")
        return 1

    print(f"Parsing OPNsense configuration from: {args.config_xml}")
    print(f"Output directory: {args.output}\n")

    parser = OPNsenseParser(args.config_xml)
    parser.generate_infrafoundry_configs(args.output)

    return 0


if __name__ == "__main__":
    exit(main())
