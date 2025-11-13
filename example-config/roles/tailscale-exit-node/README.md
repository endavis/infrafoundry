# Tailscale Exit Node Role

This Ansible role configures a Linux server as a Tailscale exit node, allowing other devices on your Tailscale network to route their internet traffic through this server.

## Features

- ✅ Works on regular Linux (Ubuntu, Debian, RHEL/CentOS, Fedora)
- ✅ Works on immutable Linux (Ubuntu Core with snap confinement)
- ✅ **Supports both Auth Key and OAuth authentication**
- ✅ Automatic distribution detection
- ✅ IP forwarding configuration
- ✅ Firewall configuration (UFW/firewalld)
- ✅ Exit node advertisement
- ✅ Idempotent operations

## Documentation

- **[README.md](README.md)** - This file, complete role documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Quick deployment guide
- **[OAUTH_GUIDE.md](OAUTH_GUIDE.md)** - OAuth authentication guide
- **[SUMMARY.md](SUMMARY.md)** - Role summary and overview

## Requirements

- **Authentication**: Choose one:
  - **Auth Key**: For automated deployments ([Generate here](https://login.tailscale.com/admin/settings/keys))
  - **OAuth**: For interactive, more secure deployments ([Generate here](https://login.tailscale.com/admin/settings/oauth))
- Root/sudo access on target server
- Internet connectivity

## Role Variables

### Required Variables

**Authentication Method 1: Auth Key (Recommended for automation)**

```yaml
tailscale_auth_method: "authkey"             # Use auth key authentication (default)
tailscale_auth_key: "tskey-auth-xxxxx-xxxxxxxxxxxxx"  # Your Tailscale auth key
```

**Authentication Method 2: OAuth (Interactive, more secure)**

```yaml
tailscale_auth_method: "oauth"               # Use OAuth authentication
tailscale_oauth_client_id: "xxxxx"           # OAuth client ID
tailscale_oauth_client_secret: "tskey-client-xxxxx"  # OAuth client secret
tailscale_oauth_timeout: 300                 # Seconds to wait for OAuth (default: 300)
```

### Optional Variables

```yaml
# Exit node configuration
tailscale_exit_node: true                    # Enable exit node (default: true)
tailscale_advertise_routes: []               # Additional subnet routes to advertise
tailscale_accept_routes: true                # Accept subnet routes from other nodes

# Firewall configuration
tailscale_configure_firewall: true           # Auto-configure firewall (default: true)
tailscale_firewall_zones:                    # Firewalld zones (RHEL/Fedora)
  - public

# IP forwarding
tailscale_enable_ip_forwarding: true         # Enable IPv4/IPv6 forwarding (default: true)

# Installation method
tailscale_force_snap: false                  # Force snap installation even on regular distros
tailscale_snap_channel: "latest/stable"      # Snap channel to use

# Service management
tailscale_start_on_boot: true                # Enable service at boot (default: true)
```

## Authentication Methods

### Auth Key (Default)

Best for: **Automated deployments, CI/CD, unattended installations**

Create an auth key at https://login.tailscale.com/admin/settings/keys

**Pros:**
- ✅ Fully automated, no user interaction
- ✅ Can be made reusable for multiple nodes
- ✅ Can be set to expire
- ✅ Works well with Infrastructure as Code

**Cons:**
- ⚠️ Key is a long-lived secret that needs secure storage
- ⚠️ If compromised, can be used to add devices to your network

**Usage:**
```yaml
ansible_vars:
  tailscale_auth_method: "authkey"  # This is the default
  tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

### OAuth (Interactive)

Best for: **Personal deployments, interactive setups, enhanced security**

Create OAuth credentials at https://login.tailscale.com/admin/settings/oauth

**Pros:**
- ✅ More secure - short-lived tokens
- ✅ Tied to a specific user/machine
- ✅ Better audit trail
- ✅ Can be revoked individually

**Cons:**
- ⚠️ Requires user interaction (visit URL to authenticate)
- ⚠️ Not suitable for fully automated deployments
- ⚠️ Ansible playbook will pause waiting for authentication

**Usage:**
```yaml
ansible_vars:
  tailscale_auth_method: "oauth"
  tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
  tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
  tailscale_oauth_timeout: 300  # Wait up to 5 minutes for user to authenticate
```

**How it works:**
1. Ansible runs `tailscale up` with OAuth credentials
2. Tailscale generates a login URL
3. You visit the URL and approve the device
4. Tailscale completes authentication
5. Role continues with configuration

## Example Usage

### Basic Exit Node (Auth Key)

```yaml
vms:
  - name: exit-node-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 2048
    ipconfig: ip=192.168.100.20/24,gw=192.168.100.1

    ansible_roles:
      - common
      - tailscale-exit-node

    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

### Exit Node with OAuth Authentication

For interactive deployment with OAuth:

```yaml
vms:
  - name: exit-node-oauth-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 2048
    ipconfig: ip=192.168.100.20/24,gw=192.168.100.1

    ansible_roles:
      - tailscale-exit-node

    ansible_vars:
      tailscale_auth_method: "oauth"
      tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
      tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
```

**Note:** When using OAuth, the Ansible playbook will pause and display a URL. You'll need to visit the URL to approve the device.

### Exit Node with Subnet Routes

Route specific subnets through this exit node:

```yaml
ansible_vars:
  tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
  tailscale_advertise_routes:
    - "192.168.100.0/24"  # Local LAN
    - "10.0.0.0/8"        # Internal network
```

### Ubuntu Core Exit Node

For immutable Ubuntu Core systems:

```yaml
vms:
  - name: exit-node-core-01
    target_node: pve01
    clone: ubuntu-core-22-template
    cores: 2
    memory: 2048

    ansible_roles:
      - tailscale-exit-node

    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
      # Role automatically detects Ubuntu Core and uses snap
```

### Multiple Exit Nodes (Geographic Distribution)

```yaml
vms:
  - name: exit-node-us-east
    # ... VM config ...
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key_us }}"
      tailscale_hostname: "exit-us-east"

  - name: exit-node-eu-west
    # ... VM config ...
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key_eu }}"
      tailscale_hostname: "exit-eu-west"
```

## How It Works

### Detection Logic

1. **Check for immutable filesystem**: Tests if `/` is read-only
2. **Check for snap**: Determines if snapd is available
3. **Detect distribution**: Identifies Ubuntu/Debian/RHEL/Fedora
4. **Choose installation method**:
   - Immutable systems → snap
   - Regular systems → native package manager

### Installation Methods

#### Regular Linux (apt/yum/dnf)

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# RHEL/CentOS/Fedora
dnf config-manager --add-repo https://pkgs.tailscale.com/stable/rhel/8/tailscale.repo
dnf install tailscale
```

#### Immutable Linux (snap)

```bash
snap install tailscale
```

### Configuration Steps

1. Install Tailscale (method depends on distribution)
2. Enable IP forwarding in sysctl
3. Configure firewall (UFW or firewalld)
4. Start Tailscale service
5. Authenticate with auth key
6. Advertise exit node
7. Advertise subnet routes (if configured)

### Firewall Rules

The role configures:
- **Input**: Allow Tailscale interface traffic
- **Forward**: Allow forwarding from Tailscale interface
- **NAT**: Configure masquerading for exit traffic

## Post-Installation

### Enable Exit Node in Admin Console

After running this role:

1. Go to https://login.tailscale.com/admin/machines
2. Find your exit node machine
3. Click the "..." menu → "Edit route settings"
4. Check "Use as exit node"
5. Click "Save"

### Using the Exit Node

On client devices:

```bash
# Use this exit node
tailscale up --exit-node=exit-node-01

# Stop using exit node
tailscale up --exit-node=
```

Or in the Tailscale GUI, select the exit node from the menu.

## Verification

### Check Tailscale Status

```bash
# On the exit node
tailscale status

# Check if exit node is advertised
tailscale status --json | jq '.Self.AllowedIPs'
```

### Check IP Forwarding

```bash
# Should return 1
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding
```

### Check Firewall

```bash
# Ubuntu/Debian (UFW)
sudo ufw status verbose

# RHEL/Fedora (firewalld)
sudo firewall-cmd --list-all
```

### Test Exit Node

From a client device:

```bash
# Connect through exit node
tailscale up --exit-node=exit-node-01

# Check your public IP (should be exit node's IP)
curl ifconfig.me

# Check route
ip route | grep tailscale
```

## Troubleshooting

### Authentication Fails

**Problem**: Tailscale can't authenticate

**Solutions**:
- Verify auth key is correct and not expired
- Check auth key has "Reusable" and "Ephemeral" options if needed
- Ensure server has internet connectivity

```bash
# Test connectivity
ping 8.8.8.8

# Check Tailscale logs
journalctl -u tailscaled -f
```

### Exit Node Not Advertised

**Problem**: Exit node doesn't appear in admin console

**Solutions**:
- Check IP forwarding is enabled
- Verify firewall allows forwarding
- Restart Tailscale service

```bash
# Enable IP forwarding manually
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv6.conf.all.forwarding=1

# Restart Tailscale
sudo systemctl restart tailscaled

# Re-advertise exit node
sudo tailscale up --advertise-exit-node
```

### Snap Installation Issues (Ubuntu Core)

**Problem**: Snap commands fail

**Solutions**:
```bash
# Check snap status
snap list tailscale

# Check snap logs
snap logs tailscale -f

# Reconnect snap interfaces
sudo snap connect tailscale:firewall-control
sudo snap connect tailscale:network-control
```

### Firewall Blocks Traffic

**Problem**: Exit node traffic is blocked

**Solutions**:
```bash
# UFW - Allow forwarding
sudo ufw route allow in on tailscale0

# firewalld - Add to trusted zone
sudo firewall-cmd --zone=trusted --add-interface=tailscale0 --permanent
sudo firewall-cmd --reload
```

## Security Considerations

### Auth Key Security

- **Never commit auth keys to git**: Use SOPS encryption
- **Use ephemeral keys**: For temporary/test nodes
- **Use reusable keys**: For permanent infrastructure
- **Set key expiry**: Short expiry for security

```yaml
# envs/prod/settings.yaml (encrypted with SOPS)
ansible_vars:
  vault_tailscale_auth_key: "tskey-auth-xxxxx-xxxxxxxxxxxxx"
```

### Firewall Best Practices

- Restrict SSH access to Tailscale network only
- Use Tailscale ACLs to control exit node access
- Monitor exit node traffic
- Enable audit logging

### ACL Configuration

In Tailscale admin console, create ACLs:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:employees"],
      "dst": ["tag:exit-node:*"]
    }
  ],
  "autoApprovers": {
    "exitNode": ["tag:exit-node"]
  }
}
```

## Performance Considerations

### System Requirements

- **CPU**: 1-2 cores minimum (more for high bandwidth)
- **RAM**: 1GB minimum (2GB recommended)
- **Network**: 1Gbps+ for best performance
- **Disk**: Minimal (Tailscale is lightweight)

### Bandwidth Planning

- Exit node handles all client traffic
- Plan bandwidth based on concurrent users
- Monitor with:
  ```bash
  # Install vnstat
  sudo apt install vnstat

  # Monitor tailscale interface
  vnstat -i tailscale0
  ```

### High Availability

For production, deploy multiple exit nodes:

```yaml
vms:
  - name: exit-node-primary
    # ... config ...
  - name: exit-node-secondary
    # ... config ...
  - name: exit-node-tertiary
    # ... config ...
```

Clients can switch between them automatically.

## Related Roles

This role works well with:
- `common` - Base system configuration
- `monitoring-agent` - Monitor exit node traffic
- `fail2ban` - Additional security
- `unattended-upgrades` - Automatic security updates

## References

- [Tailscale Exit Nodes Documentation](https://tailscale.com/kb/1103/exit-nodes/)
- [Tailscale on Ubuntu Core](https://tailscale.com/kb/1112/userspace-networking/)
- [Tailscale Subnet Routes](https://tailscale.com/kb/1019/subnets/)
- [Tailscale ACLs](https://tailscale.com/kb/1018/acls/)
