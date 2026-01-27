# OCI K3s Cluster - Design Decisions

This document records all significant design decisions made during the development of the OCI K3s cluster example, along with the reasoning behind each decision.

## Table of Contents

1. [Network Architecture](#network-architecture)
2. [Firewall/iptables Configuration](#firewalliptables-configuration)
3. [Cloud-Init vs Ansible](#cloud-init-vs-ansible)
4. [Tailscale Integration](#tailscale-integration)
5. [Destroy Workflow](#destroy-workflow)

---

## Network Architecture

### Decision: Public Subnet for Control Plane, Private Subnet for Workers

**Choice:** Control plane in public subnet (10.0.0.0/24), workers in private subnet (10.0.1.0/24)

**Reasoning:**
- Control plane needs a public IP for initial Tailscale registration via cloud-init
- Workers can use NAT gateway for outbound traffic (image pulls) without public exposure
- Reduces attack surface by keeping worker nodes off the public internet
- All management access goes through Tailscale overlay network

**Alternatives Considered:**
- All nodes in public subnet: Simpler but exposes workers unnecessarily
- All nodes in private subnet: Would require a bastion host or VPN for initial setup

### Decision: Use Tailscale for Management Access

**Choice:** Tailscale overlay network for SSH and kubectl access

**Reasoning:**
- No need to expose SSH (port 22) or Kubernetes API (port 6443) to the internet
- Works seamlessly across NAT and firewalls
- Built-in SSH via `--ssh` flag eliminates need for SSH key management
- Enables access to workers in private subnet without bastion host
- ACL policies provide fine-grained access control

**Alternatives Considered:**
- Public IPs with security groups: Exposes services to internet
- VPN (WireGuard/OpenVPN): More complex setup and management
- Bastion host: Additional cost and management overhead

---

## Firewall/iptables Configuration

### Decision: Apply iptables Rules via Ansible (NOT Cloud-Init)

**Choice:** iptables rules are applied in Ansible roles AFTER K3s installation

**Reasoning:**
We discovered through extensive testing that applying iptables rules in cloud-init does NOT work reliably:

1. **The Problem:**
   - Cloud-init `bootcmd` runs before K3s installation
   - Rules were added correctly and persisted to `/etc/iptables/rules.v4`
   - After K3s installation, UDP 8472 (VXLAN) rule disappeared from live iptables
   - TCP rules (6443, 10250) remained; only UDP 8472 was removed
   - This was 100% reproducible across multiple destroy/create cycles

2. **Root Cause:**
   - K3s/flannel specifically manages UDP 8472 for VXLAN traffic
   - During K3s initialization, it removes external UDP 8472 rules
   - The persisted file remained correct, but live iptables was modified

3. **The Solution:**
   - Apply iptables rules in Ansible AFTER K3s installation completes
   - K3s has finished all its iptables modifications
   - Our rules are applied last and persist correctly

**Files Changed:**
- `roles/k3s-server/tasks/main.yml` - iptables tasks at end
- `roles/k3s-agent/tasks/main.yml` - iptables tasks at end
- `files/cloud-init-snippets/tailscale.yaml` - removed iptables, added note

**Alternatives Considered:**
- Cloud-init with delays: Tried `sleep 2` before save, didn't help
- Cloud-init with reload: Would require reboot, complex
- Disable OCI firewall entirely: Removes defense-in-depth

### Decision: Specific iptables Rules (Not Disable Firewall)

**Choice:** Add specific ACCEPT rules for K3s traffic rather than disabling the firewall

**Required Rules:**
| Port | Protocol | Purpose |
|------|----------|---------|
| 8472 | UDP | Flannel VXLAN overlay network |
| 10250 | TCP | Kubelet API (kubectl logs/exec) |
| 6443 | TCP | Kubernetes API server |

**Reasoning:**
- OCI security lists provide network-level protection
- Host-level firewall provides defense-in-depth
- Only allow traffic from VCN CIDR (10.0.0.0/16)
- Minimal attack surface while enabling K3s functionality

**Alternatives Considered:**
- Flush all iptables rules: Loses all protection
- Use firewalld: OCI images use iptables, would add complexity
- Modify OCI image: Not reproducible, maintenance burden

### Decision: Remove REJECT from FORWARD Chain

**Choice:** Remove the `REJECT --reject-with icmp-host-prohibited` rule from FORWARD chain

**Reasoning:**
- OCI Ubuntu images have a REJECT rule at the end of FORWARD chain
- K3s flannel creates a FLANNEL-FWD chain for pod-to-pod traffic
- The REJECT rule was positioned BEFORE FLANNEL-FWD, blocking all pod traffic
- Removing REJECT allows FLANNEL-FWD rules to process traffic
- OCI security lists still provide network-level protection

---

## Cloud-Init vs Ansible

### Decision: Use Cloud-Init for Bootstrap, Ansible for Configuration

**Choice:**
- Cloud-init: DNS fallback, SSH keys, Tailscale installation
- Ansible: K3s installation, iptables rules, cluster configuration

**Reasoning:**
- Cloud-init runs during first boot, before SSH access is available
- Perfect for bootstrapping network access (Tailscale)
- Ansible runs after nodes are accessible, can handle complex configuration
- Ansible can coordinate between nodes (e.g., fetch join token)
- Ansible can retry and handle failures gracefully

**What Cloud-Init Handles:**
```yaml
bootcmd:
  - ssh-keygen -A                    # Generate SSH host keys
  - DNS fallback configuration       # Fix OCI DNS issues
  - Force IPv4 for apt               # Avoid IPv6 timeouts

runcmd:
  - Install Tailscale                # Enable network access
  - tailscale up                     # Join tailnet
```

**What Ansible Handles:**
- K3s server installation
- K3s agent installation (with token from server)
- iptables rules (AFTER K3s installation)
- Kubeconfig fetch and configuration

### Decision: Direct .deb Download for Tailscale

**Choice:** Download Tailscale .deb directly instead of using apt repository

**Reasoning:**
- OCI network can be unreliable during first boot
- apt repository setup requires multiple network calls
- Direct .deb download with retries is more robust
- Reduces dependencies on external infrastructure

**Implementation:**
```bash
# Fetch package index to get latest version
VER=$(curl -fsSL ".../Packages" | grep "^Version:" | ...)

# Download specific .deb file
curl -fsSL ".../pool/tailscale_${VER}_${ARCH}.deb" -o /tmp/tailscale.deb

# Install directly
dpkg -i /tmp/tailscale.deb
```

---

## Tailscale Integration

### Decision: Use Reusable Auth Keys

**Choice:** Use reusable Tailscale auth keys for all nodes

**Reasoning:**
- Single auth key can provision multiple nodes
- Simplifies configuration (one key in settings.yaml)
- Key can be rotated without changing per-node config

**Recommended Auth Key Settings:**
- Reusable: Yes (for multiple nodes)
- Ephemeral: Yes (auto-removes stale nodes when destroyed)
- Tags: `tag:k8s-cluster` (for ACL policies)

### Decision: Enable Tailscale SSH

**Choice:** Use `--ssh` flag when joining Tailscale

**Reasoning:**
- Eliminates need for SSH key distribution
- Uses Tailscale identity for authentication
- Works with MagicDNS hostnames
- Simplifies Ansible connection configuration

### Decision: Tailscale Operator for Kubernetes Services

**Choice:** Deploy Tailscale Kubernetes Operator for service exposure

**Reasoning:**
- Exposes Kubernetes services directly to tailnet
- No need for LoadBalancer or Ingress configuration
- Services get Tailscale DNS names automatically
- Integrates with Tailscale ACLs for access control

**OAuth Client Requirements:**
- Scopes: `devices:read`, `devices:write`, `routes:read`, `routes:write`, `auth_keys`
- Tags: `tag:k8s-operator` (auto-applied to operator devices)

---

## Destroy Workflow

### Decision: Manual Tailscale Cleanup Script

**Choice:** Provide a cleanup script to remove Tailscale devices before infrastructure destroy

**Reasoning:**
- When instances are destroyed, Tailscale devices become orphaned
- Orphaned devices clutter the Tailscale admin console
- Manual deletion is tedious with multiple nodes
- Script automates cleanup using Tailscale API

**Script:** `scripts/cleanup-tailscale.sh`
```bash
# Usage
TAILSCALE_API_KEY=tskey-api-xxx ./scripts/cleanup-tailscale.sh

# Dry run
TAILSCALE_API_KEY=tskey-api-xxx DRY_RUN=true ./scripts/cleanup-tailscale.sh
```

**Workflow:**
1. Run cleanup script (delete Tailscale devices)
2. Run `infra destroy` (destroy OCI instances)
3. Run `infra apply` (create fresh instances)

**Future Enhancement:**
- GitHub Issue #177: Add environment lifecycle hooks
- Will allow automatic cleanup in `before_destroy` hook

---

## Summary of Key Files

| File | Purpose |
|------|---------|
| `settings.yaml` | OCI credentials, Tailscale auth key |
| `oci/network.yaml` | VCN, subnets, gateways |
| `oci/instances.yaml` | Control plane + worker instances |
| `files/cloud-init-snippets/tailscale.yaml` | Bootstrap: DNS, Tailscale |
| `roles/k3s-server/tasks/main.yml` | Control plane + iptables |
| `roles/k3s-agent/tasks/main.yml` | Workers + iptables |
| `scripts/cleanup-tailscale.sh` | Pre-destroy Tailscale cleanup |

---

## Troubleshooting Reference

### DNS Resolution Failures from Worker Pods

**Symptom:** `nslookup kubernetes.default.svc` times out

**Cause:** UDP 8472 (VXLAN) blocked by iptables

**Fix:** Verify iptables rules applied by Ansible:
```bash
sudo iptables -L INPUT -n | grep 8472
# Should show: ACCEPT udp -- 10.0.0.0/16 0.0.0.0/0 udp dpt:8472
```

### kubectl logs/exec Returns 502 Bad Gateway

**Symptom:** `kubectl logs` or `kubectl exec` fails

**Cause:** TCP 10250 (kubelet API) blocked by iptables

**Fix:** Verify iptables rules:
```bash
sudo iptables -L INPUT -n | grep 10250
# Should show: ACCEPT tcp -- 10.0.0.0/16 0.0.0.0/0 tcp dpt:10250
```

### Tailscale Devices Remain After Destroy

**Symptom:** Old devices in Tailscale admin console after destroy

**Fix:** Run cleanup script before destroy:
```bash
TAILSCALE_API_KEY=tskey-api-xxx ./scripts/cleanup-tailscale.sh
```
