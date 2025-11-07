# Tailscale Exit Node Quick Start

This guide shows how to quickly deploy a Tailscale exit node using InfraFoundry.

## Prerequisites

1. **Tailscale Account**: Sign up at https://tailscale.com
2. **Choose Authentication Method**:
   - **Auth Key** (Recommended for automation): https://login.tailscale.com/admin/settings/keys
   - **OAuth** (More secure, interactive): https://login.tailscale.com/admin/settings/oauth

## Quick Deploy (Auth Key Method)

### 1. Generate Auth Key

At https://login.tailscale.com/admin/settings/keys:
- Enable "Reusable" for infrastructure deployments
- Enable "Preauthorized" to skip manual approval
- Set expiration based on your security policy

### 2. Store Auth Key Securely

Create `secrets/tailscale.yaml`:

```yaml
vault_tailscale_auth_key: "tskey-auth-xxxxx-xxxxxxxxxxxxxxxx"
```

Encrypt it:

```bash
infra secrets encrypt secrets/tailscale.yaml
```

### 3. Add Exit Node to Configuration

In `envs/dev/proxmox/vms.yaml`:

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

### 4. Deploy

```bash
# Plan (dry run)
infra plan --env dev

# Apply
infra apply --env dev
```

### 5. Approve in Admin Console

1. Go to https://login.tailscale.com/admin/machines
2. Find your exit node
3. Click "..." → "Edit route settings"
4. Check "Use as exit node"
5. Click "Save"

### 6. Use Exit Node

From any device on your Tailscale network:

```bash
# Start using exit node
tailscale up --exit-node=exit-node-01

# Stop using exit node
tailscale up --exit-node=
```

## Quick Deploy (OAuth Method)

### 1. Generate OAuth Credentials

At https://login.tailscale.com/admin/settings/oauth:
- Click "Generate OAuth client"
- Description: "InfraFoundry Deployments"
- Copy Client ID and Client Secret

### 2. Store OAuth Credentials Securely

Create `secrets/tailscale.yaml`:

```yaml
vault_tailscale_oauth_client_id: "xxxxxxxxxxxxx"
vault_tailscale_oauth_client_secret: "tskey-client-xxxxxxxxxxxxx"
```

Encrypt it:

```bash
infra secrets encrypt secrets/tailscale.yaml
```

### 3. Add Exit Node to Configuration

In `envs/dev/proxmox/vms.yaml`:

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

### 4. Deploy (Interactive)

```bash
# Apply - will pause for OAuth approval
infra apply --env dev
```

**During deployment:**
1. Ansible will pause and display an OAuth URL
2. Visit the URL in your browser
3. Approve the device
4. Deployment continues automatically

### 5. Exit node is automatically approved with OAuth

No need for manual admin console approval!

## Authentication Method Comparison

| Feature | Auth Key | OAuth |
|---------|----------|-------|
| Automation | ✅ Fully automated | ⚠️ Requires user interaction |
| Security | ⚠️ Long-lived secret | ✅ Short-lived tokens |
| CI/CD | ✅ Perfect for pipelines | ❌ Not suitable |
| Audit trail | ⚠️ Limited | ✅ Per-user/device |
| Revocation | ⚠️ Key-wide | ✅ Individual |
| Setup complexity | ✅ Simple | ⚠️ Slightly more complex |

**Recommendation:**
- **Auth Key**: For production automation, CI/CD, unattended deployments
- **OAuth**: For personal labs, interactive deployments, enhanced security

## Distribution Support

### Regular Linux (APT-based)

**Ubuntu**: 20.04, 22.04, 24.04
**Debian**: 11, 12

Uses native `.deb` packages from Tailscale repository.

```yaml
vms:
  - name: exit-ubuntu
    clone: ubuntu-22-04-template
    ansible_roles:
      - tailscale-exit-node
```

### Regular Linux (RPM-based)

**RHEL/CentOS**: 8, 9
**Fedora**: 38, 39, 40

Uses native `.rpm` packages from Tailscale repository.

```yaml
vms:
  - name: exit-rhel
    clone: rhel-9-template
    ansible_roles:
      - tailscale-exit-node
```

### Immutable Linux

**Ubuntu Core**: 22, 24

Automatically uses snap installation on immutable systems.

```yaml
vms:
  - name: exit-core
    clone: ubuntu-core-22-template
    ansible_roles:
      - tailscale-exit-node
```

## Common Configurations

### Geographic Distribution

Deploy exit nodes in multiple regions:

```yaml
vms:
  - name: exit-us-east
    # ... config ...
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
      tailscale_hostname: "exit-us-east"

  - name: exit-eu-west
    # ... config ...
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
      tailscale_hostname: "exit-eu-west"

  - name: exit-asia-pacific
    # ... config ...
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
      tailscale_hostname: "exit-asia-pacific"
```

### Subnet Router + Exit Node

Route local subnets AND act as exit node:

```yaml
ansible_vars:
  tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
  tailscale_exit_node: true
  tailscale_advertise_routes:
    - "192.168.100.0/24"  # Local LAN
    - "10.0.0.0/8"        # Private network
```

### High-Performance Exit Node

For high-bandwidth scenarios:

```yaml
vms:
  - name: exit-hp-01
    cores: 4
    memory: 4096
    # Use 10Gbps network if available
    network:
      model: virtio
      bridge: vmbr1  # 10GbE bridge

    ansible_roles:
      - common
      - tailscale-exit-node
      - monitoring-agent  # Monitor bandwidth

    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

## Verification

### Check Exit Node Status

SSH to the exit node:

```bash
# Check Tailscale status
tailscale status

# Check IP address
tailscale ip -4

# Check advertised routes
tailscale status --json | jq '.Self.AllowedIPs'

# Check IP forwarding
sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding
```

### Test from Client

```bash
# Connect through exit node
tailscale up --exit-node=exit-node-01

# Verify you're using the exit node
curl ifconfig.me
# Should show exit node's public IP

# Check route table
ip route | grep tailscale

# Test connectivity
ping 8.8.8.8
```

## Troubleshooting

### Exit Node Not Appearing

**Check service is running:**
```bash
systemctl status tailscaled
```

**Check logs:**
```bash
journalctl -u tailscaled -f
```

**Manually re-advertise:**
```bash
sudo tailscale up --advertise-exit-node
```

### Authentication Fails

**Verify auth key:**
- Check key hasn't expired
- Verify it's copied correctly (no extra spaces)
- Generate a new key if needed

**Re-authenticate:**
```bash
sudo tailscale up --authkey=tskey-auth-xxxxx
```

### Firewall Blocks Traffic

**Check firewall status:**
```bash
# Ubuntu/Debian
sudo ufw status verbose

# RHEL/Fedora
sudo firewall-cmd --list-all
```

**Manually configure:**
```bash
# UFW
sudo ufw allow 41641/udp
sudo ufw route allow in on tailscale0

# firewalld
sudo firewall-cmd --zone=trusted --add-interface=tailscale0 --permanent
sudo firewall-cmd --reload
```

### IP Forwarding Not Working

**Check current settings:**
```bash
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding
```

**Enable manually:**
```bash
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv6.conf.all.forwarding=1
```

**Make persistent:**
```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

## Security Best Practices

### Auth Key Management

1. **Use separate keys** for dev/staging/prod
2. **Set expiration dates** on auth keys
3. **Rotate keys** regularly
4. **Encrypt in SOPS** - never commit plaintext keys

```yaml
# secrets/tailscale.yaml (encrypted)
vault_tailscale_auth_key_dev: "tskey-auth-dev-xxxxx"
vault_tailscale_auth_key_prod: "tskey-auth-prod-xxxxx"
```

### Access Control Lists (ACLs)

Restrict who can use exit nodes:

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

### Monitoring

Deploy monitoring to track exit node usage:

```yaml
ansible_roles:
  - common
  - tailscale-exit-node
  - prometheus-node-exporter
  - monitoring-agent
```

Monitor:
- Bandwidth usage
- Active connections
- CPU/memory usage
- Disk space

### Firewall Rules

Restrict SSH access to Tailscale network only:

```yaml
ansible_tasks:
  - name: Restrict SSH to Tailscale network
    ufw:
      rule: limit
      port: "22"
      proto: tcp
      from_ip: 100.64.0.0/10  # Tailscale CGNAT range
```

## Advanced Usage

### Using with GitHub Actions

Deploy exit nodes in CI/CD:

```yaml
# .github/workflows/deploy-exit-node.yml
- name: Deploy exit node
  env:
    SOPS_AGE_KEY: ${{ secrets.SOPS_AGE_KEY }}
    INFRAFOUNDRY_CONFIG_REPO: ./infra-config
  run: |
    infra apply --env prod --auto-approve
```

### Dynamic DNS

Update DNS records with exit node IPs:

```yaml
ansible_tasks:
  - name: Update DNS record
    community.general.cloudflare_dns:
      zone: example.com
      record: exit-us-east
      type: A
      value: "{{ ansible_default_ipv4.address }}"
      api_token: "{{ vault_cloudflare_api_token }}"
```

### Load Balancing

Use multiple exit nodes with automatic failover:

1. Deploy multiple exit nodes in same region
2. Clients automatically switch on failure
3. Use Tailscale's built-in health checks

### Monitoring Dashboard

Create Grafana dashboard for exit nodes:

```yaml
ansible_roles:
  - tailscale-exit-node
  - prometheus-node-exporter
  - grafana-agent

ansible_vars:
  grafana_metrics:
    - node_network_receive_bytes_total{device="tailscale0"}
    - node_network_transmit_bytes_total{device="tailscale0"}
```

## Performance Tuning

### Increase Connection Limits

```yaml
ansible_tasks:
  - name: Increase connection tracking
    sysctl:
      name: net.netfilter.nf_conntrack_max
      value: "262144"
      state: present
```

### Optimize Network Stack

```yaml
ansible_tasks:
  - name: Optimize TCP settings
    sysctl:
      name: "{{ item.key }}"
      value: "{{ item.value }}"
      state: present
    loop:
      - { key: "net.core.rmem_max", value: "134217728" }
      - { key: "net.core.wmem_max", value: "134217728" }
      - { key: "net.ipv4.tcp_rmem", value: "4096 87380 67108864" }
      - { key: "net.ipv4.tcp_wmem", value: "4096 65536 67108864" }
```

## References

- [Tailscale Exit Nodes](https://tailscale.com/kb/1103/exit-nodes/)
- [Tailscale ACLs](https://tailscale.com/kb/1018/acls/)
- [Ubuntu Core with Tailscale](https://tailscale.com/kb/1112/userspace-networking/)
- [InfraFoundry Ansible Integration](../../docs/ansible-integration.md)
