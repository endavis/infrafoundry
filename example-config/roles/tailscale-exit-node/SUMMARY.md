# Tailscale Exit Node Role - Summary

## Overview

A production-ready Ansible role that configures Linux servers as Tailscale exit nodes, supporting both regular Linux distributions (Ubuntu, Debian, RHEL, Fedora) and immutable systems (Ubuntu Core).

## What This Role Does

1. **Detects System Type**: Automatically identifies if the system is immutable or regular Linux
2. **Installs Tailscale**: Uses appropriate method (snap for immutable, native package manager for regular)
3. **Configures IP Forwarding**: Enables IPv4 and IPv6 forwarding for routing
4. **Sets Up Firewall**: Configures UFW, firewalld, or iptables for exit node traffic
5. **Authenticates & Advertises**: Connects to Tailscale network and advertises as exit node

## Key Features

✅ **Multi-Distribution Support**
   - Ubuntu (20.04, 22.04, 24.04)
   - Debian (11, 12)
   - RHEL/CentOS (8, 9)
   - Fedora (38, 39, 40)

✅ **Immutable OS Support**
   - Ubuntu Core (22, 24)
   - Automatic snap installation and interface connections

✅ **Intelligent Installation**
   - Detects read-only filesystems
   - Chooses appropriate package manager
   - Falls back to snap when needed

✅ **Complete Firewall Configuration**
   - UFW (Ubuntu/Debian)
   - firewalld (RHEL/Fedora)
   - iptables (immutable systems)
   - NAT/masquerading setup

✅ **Flexible Configuration**
   - Exit node advertisement
   - Subnet route advertisement
   - Custom Tailscale settings
   - Variable-driven configuration

## File Structure

```
tailscale-exit-node/
├── README.md                        # Comprehensive documentation (500+ lines)
├── QUICKSTART.md                    # Quick start guide (300+ lines)
├── SUMMARY.md                       # This file
├── test-role.sh                     # Validation script
├── defaults/
│   └── main.yml                     # Default variables (12 vars)
├── tasks/
│   ├── main.yml                     # Entry point with detection logic
│   ├── install_snap.yml             # Snap installation (Ubuntu Core)
│   ├── install_native.yml           # APT/YUM/DNF installation
│   ├── configure_ip_forwarding.yml  # IPv4/IPv6 forwarding
│   ├── configure_firewall.yml       # Firewall configuration
│   └── configure_tailscale.yml      # Tailscale setup
├── handlers/
│   └── main.yml                     # Service reload handlers
└── meta/
    └── main.yml                     # Role metadata
```

## Quick Usage

### Basic Exit Node

```yaml
vms:
  - name: exit-node-01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 2048
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

### Exit Node with Subnet Routes

```yaml
ansible_vars:
  tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
  tailscale_advertise_routes:
    - "192.168.100.0/24"
    - "10.0.0.0/8"
```

### Ubuntu Core Exit Node

```yaml
vms:
  - name: exit-node-core
    clone: ubuntu-core-22-template
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

## Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `tailscale_auth_key` | (required) | Tailscale authentication key |
| `tailscale_exit_node` | `true` | Enable exit node functionality |
| `tailscale_advertise_routes` | `[]` | Additional subnet routes |
| `tailscale_accept_routes` | `true` | Accept routes from other nodes |
| `tailscale_configure_firewall` | `true` | Auto-configure firewall |
| `tailscale_enable_ip_forwarding` | `true` | Enable IP forwarding |
| `tailscale_force_snap` | `false` | Force snap installation |
| `tailscale_snap_channel` | `latest/stable` | Snap channel |
| `tailscale_start_on_boot` | `true` | Enable service at boot |
| `tailscale_hostname` | `ansible_hostname` | Tailscale hostname |
| `tailscale_firewall_zones` | `[public]` | Firewalld zones (RHEL) |

## How It Works

### 1. Detection Phase
- Checks if root filesystem is read-only (immutable detection)
- Checks for snapd availability
- Identifies Linux distribution
- Determines installation method

### 2. Installation Phase
- **Snap** (Ubuntu Core, immutable systems):
  - Installs Tailscale snap from specified channel
  - Connects required snap interfaces (network-control, firewall-control)
  - Sets service and binary paths for snap

- **Native** (Regular Linux):
  - Adds Tailscale repository (APT/YUM/DNF)
  - Installs Tailscale package
  - Sets service and binary paths for native install

### 3. Configuration Phase
- **IP Forwarding**:
  - Enables IPv4 forwarding (`net.ipv4.ip_forward=1`)
  - Enables IPv6 forwarding (`net.ipv6.conf.all.forwarding=1`)
  - Persistent configuration on regular systems
  - Runtime configuration on immutable systems

- **Firewall**:
  - Opens Tailscale UDP port (41641)
  - Configures forwarding rules for Tailscale interface
  - Sets up NAT/masquerading for exit traffic
  - Distribution-specific (UFW/firewalld/iptables)

- **Tailscale Service**:
  - Starts and enables tailscaled service
  - Authenticates with provided auth key
  - Advertises exit node capability
  - Advertises subnet routes (if configured)
  - Sets hostname

## Testing

Run the validation script:

```bash
cd example-config/roles/tailscale-exit-node
./test-role.sh
```

This checks:
- ✅ All required files exist
- ✅ YAML syntax is valid
- ✅ Example configurations present
- ✅ Documentation is complete

## Example Configurations

Two complete examples are provided in `example-config/envs/dev/resources/vms.yaml`:

1. **exit-node-01**: Regular Ubuntu 22.04 exit node
2. **exit-node-core-01**: Ubuntu Core 22 exit node (immutable)

Store Tailscale auth keys in `envs/{env}/settings.yaml` under `ansible_vars` section (encrypted with SOPS).

## Post-Deployment

After running the role:

1. Visit https://login.tailscale.com/admin/machines
2. Find your exit node
3. Edit route settings
4. Enable "Use as exit node"
5. Save changes

Use from clients:
```bash
tailscale up --exit-node=exit-node-01
```

## Security Considerations

### Auth Key Security
- Store in SOPS-encrypted secrets file
- Never commit plaintext keys
- Use ephemeral keys for testing
- Use reusable keys for production
- Set appropriate expiration

### Firewall Best Practices
- Restrict SSH to Tailscale network only
- Use Tailscale ACLs for access control
- Monitor exit node traffic
- Enable audit logging

### ACL Example
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:employees"],
      "dst": ["tag:exit-node:*"]
    }
  ]
}
```

## Performance Considerations

### Minimum Requirements
- CPU: 1-2 cores
- RAM: 1GB (2GB recommended)
- Network: 100Mbps+ (1Gbps+ for production)
- Disk: Minimal (Tailscale is lightweight)

### High Availability
Deploy multiple exit nodes for redundancy:
- Geographic distribution
- Automatic failover
- Load distribution

## Troubleshooting

### Common Issues

**Authentication fails**: Check auth key validity and expiration

**Exit node not advertised**: Verify IP forwarding is enabled

**Firewall blocks traffic**: Check firewall rules allow forwarding

**Snap issues on Ubuntu Core**: Verify snap interfaces are connected

See README.md for detailed troubleshooting steps.

## Documentation

- **README.md**: Full documentation with examples (500+ lines)
- **QUICKSTART.md**: Quick deployment guide (300+ lines)
- **test-role.sh**: Validation script

## References

- [Tailscale Exit Nodes Documentation](https://tailscale.com/kb/1103/exit-nodes/)
- [Tailscale on Ubuntu Core](https://tailscale.com/kb/1112/userspace-networking/)
- [Ansible Role Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_reuse_roles.html)

## License

MIT

## Author

InfraFoundry Project
