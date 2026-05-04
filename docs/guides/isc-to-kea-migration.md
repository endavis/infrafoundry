# ISC DHCP to Kea DHCP Migration

## Overview

InfraFoundry provides an automated migration from legacy ISC DHCP configs to Kea DHCP on OPNsense, converting IPv4/IPv6 subnets, pools, and reservations into InfraFoundry YAML.

## Audience and Prerequisites

- **Audience:** Operators migrating OPNsense DHCP from ISC to Kea.
- **Prereqs:** OPNsense access, `foundry config migrate` available, and target config repo to receive generated YAML. The component name is `isc_to_kea` (Python-identifier form). Before issue #726 it was spelled `isc-to-kea`; the hyphenated form is no longer accepted.

## When to Use This

- Moving from ISC DHCP (maintenance mode) to Kea for API-driven management.
- Migrating selected interfaces or full DHCP configurations.
- Generating InfraFoundry resources from existing ISC settings.

## Quick Start

```bash
# Migrate all interfaces
foundry config migrate --env prod --provider opnsense --component isc_to_kea

# Migrate selected interfaces
foundry config migrate --env prod --provider opnsense --component isc_to_kea -i lan -i opt1

# Dry-run preview
foundry config migrate --env prod --provider opnsense --component isc_to_kea --dry-run
```

## Configuration Details

- **Outputs:** InfraFoundry YAML at `envs/{env}/resources/migrated-isc_to_kea.yaml` by default (use `-o` to override).
- **Coverage:**
  - DHCPv4: subnets, pools, gateway, DNS, domain, NTP, lease times, static mappings.
  - DHCPv6: subnets, pools, prefix delegation, DNS/search lists, lease times, static mappings.
- **Behavior:** Reads ISC config from OPNsense, converts to Kea resources (`kea_subnet`, reservations, etc.), and writes YAML.
- **Interfaces:** Use `-i` to limit migration to specific interfaces.

## Validation and Checks

- Review generated YAML before apply; ensure networks, gateways, and reservations align with desired state.
- Run `foundry infra doctor --env <env>` after adding migrated resources.
- Keep backups of original ISC configs (`/var/dhcpd/etc/dhcpd.conf`, `/var/dhcpd/etc/dhcpdv6.conf`).

## Examples

- **Custom output path:**
  ```bash
  foundry config migrate --env prod --provider opnsense --component isc_to_kea -o custom/path/dhcp-config.yaml
  ```
- **Generated resource snippet:**
  ```yaml
  resources:
    - provider: opnsense
      type: kea_subnet
      name: lan-dhcp
      config:
        cidr: 10.0.0.0/24
        gateway: 10.0.0.1
        pools:
          - start: 10.0.0.10
            end: 10.0.0.200
        reservations:
          - mac: "AA:BB:CC:DD:EE:FF"
            ip: 10.0.0.50
            hostname: host-01
  ```

## Related Documentation

- [Configuration Guide](../configuration/overview.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)
- [DHCP Static Mapping and VM Integration](dhcp-vm-integration.md)
- [Notifications Guide](../configuration/notifications.md)

## Troubleshooting

- **Symptom:** Missing interface migration. **Fix:** Specify interfaces with `-i`; confirm interface names match OPNsense.
- **Symptom:** Incorrect reservations. **Fix:** Verify MAC/IP in generated YAML against source config; adjust before apply.
- **Symptom:** Apply errors post-migration. **Fix:** Validate references/networks and rerun `foundry infra doctor --env <env>`; ensure Kea services are reachable.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
