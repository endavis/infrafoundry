# DHCP Static Mapping and VM Integration

## Overview

InfraFoundry supports automatic integration between OPNsense DHCP static mappings and Proxmox VMs. This allows VMs to use DHCP while still receiving predictable, consistent IP addresses.

## How It Works

### Provider Execution Order

InfraFoundry applies providers in a specific order to ensure dependencies are met:

1. **OPNsense** - Network configuration, firewall rules, DHCP mappings
2. **Proxmox** - Virtual machines
3. **Kubernetes** - Container orchestration

This ordering ensures that:
- DHCP reservations exist before VMs request IPs
- Firewall rules are in place before VMs start
- Network configuration is ready before infrastructure

### Configuration Pattern

**Step 1: Create DHCP Static Mapping**

File: `envs/{env}/resources/dhcp-mappings.yaml`

```yaml
resources:
  - provider: opnsense
    type: dhcp_static_maps
    name: my-vm-dhcp
    config:
      interface: opt1           # VLAN interface in OPNsense
      mac: "BC:24:11:10:00:96"  # Must match VM MAC
      ip: "192.168.10.50"       # Reserved IP
      hostname: "my-vm-01"
      description: "My VM - Managed by InfraFoundry"
```

**Step 2: Create VM with Matching MAC**

File: `envs/{env}/resources/my-vm.yaml`

```yaml
resources:
  - provider: proxmox
    type: vm
    name: my-vm-01
    config:
      target_node: pve1
      clone: ubuntu-template

      # Network with SAME MAC as DHCP mapping
      network:
        bridge: vmbr1
        tag: 10
        macaddr: "BC:24:11:10:00:96"  # Must match DHCP mapping

      # Use DHCP - will get reserved IP
      ipconfig: ip=dhcp

      # Don't start on creation (optional)
      oncreate: false
```

**Step 3: Deploy**

```bash
infra apply --env homelab
```

InfraFoundry will:
1. Create the DHCP static mapping in OPNsense
2. Create the VM in Proxmox
3. VM requests DHCP and receives its reserved IP (192.168.10.50)

## MAC Address Format

Proxmox uses a specific MAC address scheme:

```
BC:24:11:VV:HH:HH
│  │  │  │  └─────── Host/VM identifier (hex)
│  │  │  └────────── VLAN ID (hex)
│  │  └───────────── Proxmox prefix
│  └──────────────── Proxmox prefix
└─────────────────── Proxmox prefix (locally administered)
```

Example:
- VLAN 10 (0x0A), VM ID 150 (0x96): `BC:24:11:0A:00:96`
- VLAN 20 (0x14), VM ID 200 (0xC8): `BC:24:11:14:00:C8`

## Benefits

1. **Predictable IPs**: VMs always get the same IP address
2. **DHCP Flexibility**: Easy to change IPs without reconfiguring VMs
3. **Centralized Management**: All IP assignments in one place (OPNsense)
4. **DNS Integration**: OPNsense can automatically register hostnames in DNS
5. **Audit Trail**: Clear record of which MAC gets which IP

## Troubleshooting

### VM Gets Wrong IP

- Check that MAC addresses match exactly between DHCP mapping and VM
- Verify DHCP mapping was created (check OPNsense UI)
- Check VM is on the correct VLAN

### DHCP Mapping Not Created

- Check OPNsense credentials in `envs/credentials.yaml`
- Verify interface name (e.g., `opt1`) matches OPNsense configuration
- Check Terraform apply output for errors

### VM Created Before DHCP Mapping

This should not happen with InfraFoundry's provider ordering, but if it does:
- Run `infra apply` again - Terraform will update the DHCP mapping
- Restart the VM to request a new DHCP lease

## See Also

- [Separate Configuration Repository Pattern](separate-config-repo.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [State Management](state-management.md)
