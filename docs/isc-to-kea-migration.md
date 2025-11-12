# ISC DHCP to Kea DHCP Migration

This document describes how to migrate from legacy ISC DHCP to modern Kea DHCP on OPNsense using InfraFoundry.

## Overview

ISC DHCP (Internet Systems Consortium DHCP) was the standard DHCP server for many years but is now in maintenance mode. OPNsense has migrated to Kea DHCP, which is:

- **More modern**: Better architecture and features
- **Better maintained**: Active development and security updates
- **API-driven**: Full API support for automation
- **More flexible**: Advanced DHCP features and customization

InfraFoundry provides an automated migration tool to convert ISC DHCP configurations to Kea DHCP format.

## What Gets Migrated

### DHCPv4 Configuration

**From ISC DHCP:**
- Subnet declarations with CIDR notation
- IP address pools (range from/to)
- Gateway (router option)
- DNS servers
- Domain name
- NTP servers
- Lease times (default and max)
- Static mappings (MAC → IP reservations)

**To Kea DHCP:**
- Kea subnet resources with all options
- Kea reservation resources for static mappings

### DHCPv6 Configuration

**From ISC DHCP:**
- IPv6 subnet declarations
- IPv6 address pools
- Prefix delegation settings
- DNS servers and search lists
- Lease times
- Static mappings (DUID → IP reservations)

**To Kea DHCPv6:**
- Kea DHCPv6 subnet resources
- Kea DHCPv6 reservation resources

## Usage

### Basic Migration

Migrate all ISC DHCP interfaces to Kea format:

```bash
infra migrate --env prod --provider opnsense --component isc-to-kea
```

This will:
1. Read all ISC DHCP configuration from OPNsense
2. Convert to Kea DHCP format
3. Generate InfraFoundry YAML in `envs/prod/resources/migrated-isc-to-kea.yaml`

### Selective Interface Migration

Migrate only specific interfaces:

```bash
infra migrate --env prod --provider opnsense --component isc-to-kea -i lan -i opt1
```

### Dry-Run Mode

Preview the migration without writing files:

```bash
infra migrate --env prod --provider opnsense --component isc-to-kea --dry-run
```

### Custom Output File

Specify a custom output location:

```bash
infra migrate --env prod --provider opnsense --component isc-to-kea \
    -o custom/path/dhcp-config.yaml
```

## Migration Process

### Step 1: Review Current ISC Configuration

Before migrating, document your current ISC DHCP setup:

```bash
# On OPNsense via SSH
cat /var/dhcpd/etc/dhcpd.conf        # DHCPv4 config
cat /var/dhcpd/etc/dhcpdv6.conf      # DHCPv6 config
```

Or view in OPNsense web UI: **Services → DHCPv4** and **Services → DHCPv6**

### Step 2: Run Migration

Execute the migration command:

```bash
infra migrate --env prod --provider opnsense --component isc-to-kea
```

### Step 3: Review Generated YAML

The migration creates an InfraFoundry YAML file like:

```yaml
resources:
  # DHCPv4 Subnets
  - provider: opnsense
    type: kea_subnet
    name: lan-dhcp
    config:
      subnet: 192.168.1.0/24
      interface: lan
      pools:
        - range: 192.168.1.100 - 192.168.1.200
      router: 192.168.1.1
      dns_servers:
        - 192.168.1.1
        - 8.8.8.8
      domain: example.local
      ntp_servers:
        - 192.168.1.1
      valid_lifetime: 7200
      max_lifetime: 86400

  # DHCPv4 Reservations
  - provider: opnsense
    type: kea_reservation
    name: server01
    config:
      subnet: 192.168.1.0/24
      hw_address: "00:11:22:33:44:55"
      ip_address: 192.168.1.50
      hostname: server01
      description: Main Server

  # DHCPv6 Subnets
  - provider: opnsense
    type: kea_dhcp6_subnet
    name: lan-dhcpv6
    config:
      subnet: fd00::/64
      interface: lan
      pools:
        - range: fd00::1000 - fd00::2000
      dns_servers:
        - fd00::1
      dns_search_list:
        - example.local
      valid_lifetime: 7200

  # DHCPv6 Reservations
  - provider: opnsense
    type: kea_dhcp6_reservation
    name: server01
    config:
      subnet: fd00::/64
      duid: "00:01:00:01:12:34:56:78:00:11:22:33:44:55"
      ip_address: fd00::50
      hostname: server01
      description: Main Server IPv6
```

### Step 4: Customize as Needed

Edit the generated YAML to:
- Adjust pool ranges
- Add/modify DHCP options
- Update descriptions
- Add additional reservations

### Step 5: Apply Configuration

**Important:** Before applying:
1. **Disable ISC DHCP** in OPNsense (Services → DHCPv4/DHCPv6 → Uncheck "Enable")
2. **Enable Kea DHCP** plugin (System → Firmware → Plugins → os-kea-ctrl)
3. **Verify no IP conflicts** will occur

Apply the Kea DHCP configuration:

```bash
infra plan --env prod          # Review Terraform plan
infra apply --env prod         # Apply configuration
```

### Step 6: Verify

1. Check Kea DHCP service status in OPNsense
2. Monitor DHCP logs: **Services → Kea DHCPv4/v6 → Log Files**
3. Test DHCP client lease acquisition
4. Verify static reservations are working

## Configuration Mapping

### Subnet Options

| ISC DHCP | Kea DHCP | Description |
|----------|----------|-------------|
| `subnet` + `subnet_bits` | `subnet` (CIDR) | Network address with prefix length |
| `range from/to` | `pools[].range` | Dynamic IP pool range |
| `option routers` | `router` | Default gateway |
| `option domain-name-servers` | `dns_servers` | DNS servers |
| `option domain-name` | `domain` | Domain name |
| `option ntp-servers` | `ntp_servers` | NTP servers |
| `default-lease-time` | `valid_lifetime` | Default lease duration (seconds) |
| `max-lease-time` | `max_lifetime` | Maximum lease duration (seconds) |

### Reservation Options

| ISC DHCP | Kea DHCP | Description |
|----------|----------|-------------|
| `hardware ethernet` | `hw_address` | MAC address (DHCPv4) |
| `fixed-address` | `ip_address` | Reserved IP address |
| `host-name` | `hostname` | Client hostname |
| - | `description` | Optional description |

### DHCPv6 Specific

| ISC DHCP | Kea DHCP | Description |
|----------|----------|-------------|
| `host-identifier option dhcp6.client-id` | `duid` | DHCPv6 Unique Identifier |
| `fixed-address6` | `ip_address` | Reserved IPv6 address |
| `option dhcp6.name-servers` | `dns_servers` | IPv6 DNS servers |
| `option dhcp6.domain-search` | `dns_search_list` | DNS search domains |

## Limitations

### What Is NOT Migrated

The migration tool currently does **not** handle:

1. **Advanced DHCP options** - Custom DHCP option definitions need manual conversion
2. **Conditional logic** - ISC's class matching and conditionals
3. **Failover configuration** - HA/failover setups require manual setup
4. **Shared networks** - Multiple subnets on same physical network
5. **Dynamic DNS updates** - DDNS configuration needs manual setup
6. **Custom scripts** - on commit/release/expire scripts

These features require manual configuration in Kea.

### ISC DHCP API Limitations

Since ISC DHCP doesn't have a rich API like Kea:

- **Current implementation** returns empty dictionaries (placeholder)
- **To use in production**, you need to implement one of:
  1. Parse OPNsense `config.xml` (via backup/download API)
  2. Read ISC DHCP config files via SSH
  3. Use OPNsense Core API to read system configuration

The migration logic is fully implemented - only the ISC config reading needs a data source.

## Troubleshooting

### Migration produces empty YAML

**Cause:** ISC DHCP service methods return empty data (not yet implemented for your setup)

**Solution:** Implement ISC config reading in `services/isc_dhcp.py`:
- Option 1: Parse OPNsense XML config
- Option 2: Read ISC DHCP config files
- Option 3: Use OPNsense Core API

### Missing DHCP options after migration

**Cause:** Not all ISC options have direct Kea equivalents

**Solution:** Add custom DHCP options manually to the generated YAML

### Reservations not working

**Cause:** MAC address format or DUID mismatch

**Solution:** 
- DHCPv4: Verify MAC address format (colon-separated)
- DHCPv6: Get correct DUID from OPNsense DHCP leases

## Additional Resources

- [Kea DHCP Documentation](https://kea.readthedocs.io/)
- [OPNsense Kea Plugin](https://docs.opnsense.org/manual/kea.html)
- [ISC DHCP to Kea Migration Guide](https://kea.readthedocs.io/en/latest/arm/admin.html#migrating-from-isc-dhcp)
- [InfraFoundry Documentation](../../README.md)

## Architecture

The migration uses InfraFoundry's 3-layer architecture:

```
CLI (infra migrate)
    ↓
OPNsenseProvider.migrate_isc_to_kea()
    ↓
ISCToKeaMigrationManager (orchestration)
    ↓
ISCDHCPService (read ISC config)
    ↓
OPNsenseClient (API calls)
```

This separation allows:
- **Easy testing** - Mock each layer independently
- **Reusability** - Service methods can be used elsewhere
- **Maintainability** - Clear separation of concerns

## Example Scenarios

### Scenario 1: Simple Home Network

**ISC Config:**
- Single LAN with DHCP
- Static IP for NAS
- DNS pointing to router

**Migration:**
```bash
infra migrate --env home --provider opnsense --component isc-to-kea
infra apply --env home
```

### Scenario 2: Multi-VLAN Enterprise

**ISC Config:**
- Multiple VLANs (lan, dmz, guest)
- Many static reservations
- Different lease times per VLAN

**Migration:**
```bash
# Migrate all interfaces
infra migrate --env prod --provider opnsense --component isc-to-kea

# Review and customize per-VLAN settings
vim envs/prod/resources/migrated-isc-to-kea.yaml

# Apply staged (one VLAN at a time)
infra plan --env prod --resource lan-dhcp
infra apply --env prod --resource lan-dhcp

infra plan --env prod --resource dmz-dhcp
infra apply --env prod --resource dmz-dhcp
```

### Scenario 3: IPv6-Only Network

**ISC Config:**
- DHCPv6 with prefix delegation
- IPv6 static assignments

**Migration:**
```bash
infra migrate --env ipv6 --provider opnsense --component isc-to-kea -i lan
# Only DHCPv6 resources will be generated
```

## Best Practices

1. **Test in non-production first** - Migrate dev/staging before production
2. **Document deviations** - Note any manual changes from generated config
3. **Backup ISC config** - Keep original ISC configuration for reference
4. **Monitor after migration** - Watch DHCP logs and client behavior
5. **Plan maintenance window** - Schedule migration during low-usage period
6. **Keep old leases** - Kea can read ISC lease database for smooth transition

## Future Enhancements

Planned improvements to the migration tool:

- [ ] Parse OPNsense config.xml directly
- [ ] Handle shared-network declarations
- [ ] Convert custom DHCP options
- [ ] Migrate DHCPv6 prefix delegation
- [ ] Support ISC DHCP failover to Kea HA migration
- [ ] Validate IP address conflicts before migration
- [ ] Generate migration report with warnings
