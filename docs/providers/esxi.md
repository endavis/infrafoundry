# ESXi Provider

The ESXi provider manages resources inside one or more VMware ESXi hosts using the [josenk/esxi](https://registry.terraform.io/providers/josenk/esxi/latest) Terraform provider.

## Supported Resources

| Type | Description |
|------|-------------|
| `vswitch` | Virtual switch with optional uplinks and MTU configuration |
| `portgroup` | Port group on a vswitch with VLAN and security settings |
| `vm` | Guest VM with OVF deployment, disk, and multi-NIC support |

## Prerequisites

### SSH Access

The ESXi provider validates connectivity via SSH (port 22) to each configured host. Ensure:

- SSH is enabled on the ESXi host(s)
- The configured user has sufficient privileges (typically `root`)
- Network connectivity exists between the InfraFoundry host and the ESXi hosts

### Terraform Provider

The provider uses `josenk/esxi ~> 1.10`. It is installed automatically by `terraform init`.

## Configuration

### Provider Settings

Add ESXi host settings to your environment's `settings.yaml`:

```yaml
name: prod

provider_settings:
  esxi:
    timeout: 30  # SSH timeout in seconds (optional, default: 30)
    hosts:
      esxi-01:
        hostname: "192.168.1.10"
        username: "root"
      esxi-02:
        hostname: "192.168.1.11"
        username: "root"
```

Each key under `hosts` is a logical host name used in resource configs. The `hostname` field is the actual SSH hostname or IP address.

### Providing Passwords

Passwords are **never written to disk**. Provide them via Terraform environment variables:

```bash
export TF_VAR_esxi_password_esxi_01="secret"
export TF_VAR_esxi_password_esxi_02="secret"
```

The variable name follows the pattern `TF_VAR_esxi_password_<alias>`, where `<alias>` is the host name with hyphens and dots replaced by underscores (e.g., `esxi-01` becomes `esxi_01`).

### Resource Files

Create resource configs under `envs/{env}/esxi/`:

```
envs/prod/esxi/
├── vswitches.yaml
├── portgroups.yaml
└── vms.yaml
```

## Resource Reference

### vswitch

```yaml
vswitch:
  - name: vSwitch1
    host: esxi-01
    uplink:
      - vmnic1
      - vmnic2
    mtu: 9000
    ports: 128
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Virtual switch name |
| `host` | Yes | Logical host name from `provider_settings.esxi.hosts` |
| `uplink` | No | List of physical NIC names to attach |
| `mtu` | No | Maximum transmission unit (default: 1500) |
| `ports` | No | Number of ports on the vswitch |

### portgroup

```yaml
portgroup:
  - name: prod-network
    host: esxi-01
    vswitch: vSwitch1
    vlan: 100
    promiscuous_mode: false
    mac_changes: false
    forged_transmits: false
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Port group name |
| `host` | Yes | Logical host name |
| `vswitch` | Yes | Name of the vswitch this port group belongs to (must exist on the same host) |
| `vlan` | No | VLAN ID (0 = no VLAN tagging) |
| `promiscuous_mode` | No | Allow promiscuous mode |
| `mac_changes` | No | Allow MAC address changes |
| `forged_transmits` | No | Allow forged transmits |

### vm

```yaml
vm:
  - name: web-server
    host: esxi-01
    ovf_source: "/vmfs/volumes/datastore1/templates/ubuntu.ova"
    disk_store: datastore1
    numvcpus: 4
    memsize: 8192
    power: "on"
    notes: "Production web server"
    guest_startup_timeout: 120
    guest_shutdown_timeout: 30
    network:
      - portgroup: prod-network
        nic_type: vmxnet3
      - portgroup: mgmt-network
        nic_type: vmxnet3
        mac_address: "00:50:56:XX:YY:ZZ"
    virtual_disks:
      - virtual_disk_id: "/vmfs/volumes/datastore1/web-server/data.vmdk"
        slot: "0:1"
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | VM display name |
| `host` | Yes | Logical host name |
| `ovf_source` | No | Path to OVF/OVA template for deployment |
| `disk_store` | No | Datastore for the VM |
| `numvcpus` | No | Number of virtual CPUs |
| `memsize` | No | Memory in MB |
| `power` | No | Power state: `on` or `off` |
| `notes` | No | Annotations/notes for the VM |
| `guest_startup_timeout` | No | Seconds to wait for guest startup |
| `guest_shutdown_timeout` | No | Seconds to wait for guest shutdown |
| `network` | No | List of network interfaces (see below) |
| `virtual_disks` | No | List of additional virtual disks (see below) |

**Network interface fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `portgroup` | No | Port group name (alias for `virtual_network`) |
| `virtual_network` | No | Virtual network name (default: `VM Network`) |
| `nic_type` | No | NIC type (e.g., `vmxnet3`, `e1000`) |
| `mac_address` | No | Static MAC address |

The `network` field accepts either a single dict or a list of dicts. A single dict is automatically normalized to a list.

**Virtual disk fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `virtual_disk_id` | Yes | Path to the VMDK file |
| `slot` | No | SCSI slot (default: `0:1`) |

## Multi-Host Support

The ESXi provider supports managing resources across multiple ESXi hosts simultaneously. Each host gets its own Terraform provider alias, and resources are routed to the correct host based on the `host` field.

```yaml
# Resources can target different hosts
vswitch:
  - name: vSwitch1
    host: esxi-01
  - name: vSwitch1
    host: esxi-02

portgroup:
  - name: prod-net
    host: esxi-01
    vswitch: vSwitch1
  - name: prod-net
    host: esxi-02
    vswitch: vSwitch1
```

## Validation

The ESXi provider validates:

- **Connectivity**: SSH access to each configured host on port 22
- **Vswitch references**: Portgroups reference vswitches that exist on the same host
- **Portgroup references**: VMs reference portgroups that exist on the same host

```bash
infra validate --env prod
```

## Config Export

The ESXi provider includes an exporter that discovers existing resources via SSH:

```python
from infrafoundry.providers.esxi.exporter import EsxiConfigExporter

exporter = EsxiConfigExporter(env_config)
exports = exporter.export(host_filter="esxi-01", resource_filter="vm")
```

The exporter connects to ESXi hosts and runs `esxcli` and `vim-cmd` commands to discover vswitches, portgroups, and VMs, outputting InfraFoundry-compatible YAML.

## Usage

```bash
# Generate Terraform files
infra plan --env prod

# Validate configuration and host connectivity
infra validate --env prod

# Apply infrastructure
infra apply --env prod

# Destroy infrastructure
infra destroy --env prod
```

## Generated Files

After `infra plan`, the generated directory contains:

```
generated/prod/terraform/esxi/
├── provider.tf          # ESXi provider with per-host aliases
├── variables.tf         # Per-host credential variables
├── terraform.tfvars     # Credential values from settings.yaml
├── vswitch.tf           # Virtual switch resources
├── portgroup.tf         # Port group resources
├── vm.tf                # Guest VM resources
└── outputs.tf           # VM IPs, vswitch names, portgroup names
```

## Dependencies

Resources are created in dependency order:

```
vswitch → portgroup → vm
```

Portgroups depend on vswitches, and VMs depend on both vswitches and portgroups.
