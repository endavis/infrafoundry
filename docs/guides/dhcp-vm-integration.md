# DHCP Reservations and VM Integration

## Overview

InfraFoundry aligns OPNsense Kea DHCPv4 reservations with Proxmox VMs so VMs use DHCP while still receiving predictable IPs. (The legacy `dhcp_static_maps` resource type was retired in #782 — Kea is OPNsense's modern DHCP daemon and `kea_reservation` direct-API supersedes it for every static-mapping use case.)

## Audience and Prerequisites

- **Audience:** Operators configuring Proxmox + OPNsense environments.
- **Prereqs:** OPNsense API access, Proxmox API access, environment config repo set, matching MAC addresses for DHCP reservations and VM NICs, and a `kea_subnet` resource declared for the subnet the reservation falls into (Kea reservations resolve their parent subnet by CIDR at apply time).

## When to Use This

- You want deterministic VM IPs without manual static addressing.
- You need firewall rules and DHCP reservations ready before VM creation.
- You manage multi-provider stacks where network readiness must precede compute.

## Quick Start

1. Declare the subnet (one entry per VLAN/interface; can be reused across many reservations):
   ```yaml
   # envs/{env}/resources/dhcp-subnets.yaml
   resources:
     - provider: opnsense
       type: kea_subnet
       name: lan-subnet
       config:
         subnet: "192.168.10.0/24"
         interface: opt1
         pools:
           - range: "192.168.10.100-192.168.10.200"
         dns_servers: ["192.168.10.1"]
   ```
2. Add a DHCP reservation for the VM. The reservation must point at a
   `kea_subnet` resource declared in the same environment. Two equivalent
   schemas are accepted:

   ```yaml
   # envs/{env}/resources/dhcp-mappings.yaml — preferred (#802, what
   # the framework's own blueprints emit)
   resources:
     - provider: opnsense
       type: kea_reservation
       name: my-vm-dhcp
       config:
         subnet_ref: lan-subnet           # name of the kea_subnet above
         hw_address: "BC:24:11:10:00:96"
         ip_address: "192.168.10.50"
         hostname: "my-vm-01"
         description: "My VM - Managed by InfraFoundry"
   ```

   ```yaml
   # Legacy literal-CIDR form — still supported, useful when the subnet
   # is not declared as a managed resource in this environment
   resources:
     - provider: opnsense
       type: kea_reservation
       name: my-vm-dhcp
       config:
         subnet: "192.168.10.0/24"        # CIDR of the kea_subnet above
         hw_address: "BC:24:11:10:00:96"
         ip_address: "192.168.10.50"
         hostname: "my-vm-01"
         description: "My VM - Managed by InfraFoundry"
   ```

   `subnet_ref` resolves to the kea_subnet's CIDR at plan/apply time;
   both forms produce identical wire calls. Both fields may be present
   simultaneously, in which case the resolved CIDR must match the
   literal `subnet` value. The same dual-form schema applies to
   `kea_dhcp6_reservation`.
3. Create a VM using the same MAC:
   ```yaml
   # envs/{env}/resources/my-vm.yaml
   resources:
     - provider: proxmox
       type: vm
       name: my-vm-01
       config:
         target_node: pve1
         clone: ubuntu-template
         network:
           bridge: vmbr1
           tag: 10
           macaddr: "BC:24:11:10:00:96"
         ipconfig: ip=dhcp
         oncreate: false
   ```
4. Apply:
   ```bash
   foundry infra apply --env homelab
   ```

## Configuration Details

- **Provider execution order:** OPNsense → Proxmox → Kubernetes. DHCP reservations and firewall rules are ready before VMs request IPs.
- **Required fields:** Matching MAC between DHCP map and VM NIC; correct OPNsense interface and VLAN tag; Proxmox bridge/tag align with network design.
- **Defaults:** VMs can remain powered off on creation (`oncreate: false`) if desired.
- **Naming:** Keep resource names descriptive and consistent across providers for easier troubleshooting.

## Validation and Checks

- Run `foundry infra doctor --env <env>` to confirm OPNsense aliases/interfaces and Proxmox templates/bridges exist.
- Verify MAC format is colon-separated and unique per VM.
- After apply, confirm DHCP leases in OPNsense and VM IP assignment in Proxmox.

## Examples

- **Apply with validation:**
  ```bash
  foundry infra doctor --env homelab
  foundry infra apply --env homelab
  ```
- **Destroy if you need to recreate mappings/VMs:**
  ```bash
  foundry infra destroy --env homelab
  ```

## Related Documentation

- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Configuration](../configuration/overview.md)
- [YAML-Only Config](../configuration/yaml-only-config.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)

## Troubleshooting

- **Symptom:** VM gets unexpected IP. **Fix:** Ensure VM MAC matches the DHCP static mapping and bridge/VLAN align with the DHCP interface.
- **Symptom:** DHCP mapping not created. **Fix:** Check OPNsense API credentials and interface name; rerun with `--check-api --check-refs`.
- **Symptom:** VM creation fails. **Fix:** Validate Proxmox template, storage, and bridge exist; confirm provider order by reviewing apply logs.

---

Last updated: 2025-12-23 14:12 GMT


---
[Back to Table of Contents](../index.md)
