# DHCP Static Mapping and VM Integration

## Overview

InfraFoundry can align OPNsense DHCP static mappings with Proxmox VMs so VMs use DHCP while still receiving predictable IPs.

## Audience and Prerequisites

- **Audience:** Operators configuring Proxmox + OPNsense environments.
- **Prereqs:** OPNsense API access, Proxmox API access, environment config repo set, and matching MAC addresses for DHCP reservations and VM NICs.

## When to Use This

- You want deterministic VM IPs without manual static addressing.
- You need firewall rules and DHCP reservations ready before VM creation.
- You manage multi-provider stacks where network readiness must precede compute.

## Quick Start

1. Add a DHCP static map:
   ```yaml
   # envs/{env}/resources/dhcp-mappings.yaml
   resources:
     - provider: opnsense
       type: dhcp_static_maps
       name: my-vm-dhcp
       config:
         interface: opt1
         mac: "BC:24:11:10:00:96"
         ip: "192.168.10.50"
         hostname: "my-vm-01"
         description: "My VM - Managed by InfraFoundry"
   ```
2. Create a VM using the same MAC:
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
3. Apply:
   ```bash
   infra apply --env homelab
   ```

## Configuration Details

- **Provider execution order:** OPNsense → Proxmox → Kubernetes. DHCP reservations and firewall rules are ready before VMs request IPs.
- **Required fields:** Matching MAC between DHCP map and VM NIC; correct OPNsense interface and VLAN tag; Proxmox bridge/tag align with network design.
- **Defaults:** VMs can remain powered off on creation (`oncreate: false`) if desired.
- **Naming:** Keep resource names descriptive and consistent across providers for easier troubleshooting.

## Validation and Checks

- Run `infra validate --env <env> --check-api --check-refs` to confirm OPNsense aliases/interfaces and Proxmox templates/bridges exist.
- Verify MAC format is colon-separated and unique per VM.
- After apply, confirm DHCP leases in OPNsense and VM IP assignment in Proxmox.

## Examples

- **Apply with validation:**
  ```bash
  infra validate --env homelab --check-api --check-refs
  infra apply --env homelab
  ```
- **Destroy if you need to recreate mappings/VMs:**
  ```bash
  infra destroy --env homelab
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

Last updated: 2025-11-29 14:12 GMT
