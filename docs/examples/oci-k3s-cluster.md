# OCI K3s Cluster with Tailscale

A complete example of deploying a K3s Kubernetes cluster on Oracle Cloud Infrastructure (OCI) using Always Free Tier ARM instances with Tailscale for secure management access.

## Overview

This example demonstrates:

- **OCI Free Tier**: Maximizes the Always Free ARM instances (4 OCPUs, 24GB RAM)
- **Network Isolation**: Workers in private subnet with NAT gateway for image pulls
- **Secure Access**: Tailscale overlay network for SSH and kubectl access
- **Full Automation**: Terraform for infrastructure, Ansible for K3s installation
- **OCI Firewall Fix**: Automated iptables configuration for K3s networking

## Architecture

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    OCI VCN                          │
                    │                  10.0.0.0/16                        │
                    │                                                     │
    Internet        │  ┌─────────────────┐    ┌─────────────────────┐    │
        │           │  │  Public Subnet  │    │   Private Subnet    │    │
        │           │  │   10.0.0.0/24   │    │    10.0.1.0/24      │    │
        ▼           │  │                 │    │                     │    │
   ┌────────┐       │  │ ┌─────────────┐ │    │ ┌─────────────────┐ │    │
   │Internet│◄──────┼──┤ │k3s-control  │ │    │ │  k3s-worker-0   │ │    │
   │Gateway │       │  │ │ 2 OCPU/8GB  │ │    │ │  1 OCPU/8GB     │ │    │
   └────────┘       │  │ │ Public IP   │ │    │ │  No Public IP   │ │    │
        │           │  │ └─────────────┘ │    │ └─────────────────┘ │    │
        │           │  │                 │    │                     │    │
        │           │  │                 │    │ ┌─────────────────┐ │    │
   ┌────────┐       │  │                 │    │ │  k3s-worker-1   │ │    │
   │  NAT   │◄──────┼──┼─────────────────┼────┤ │  1 OCPU/8GB     │ │    │
   │Gateway │       │  │                 │    │ │  No Public IP   │ │    │
   └────────┘       │  │                 │    │ └─────────────────┘ │    │
                    │  └─────────────────┘    └─────────────────────┘    │
                    └─────────────────────────────────────────────────────┘
                                           │
                                           │ Tailscale Overlay
                                           ▼
                                   ┌───────────────┐
                                   │  Your Device  │
                                   │  (Tailscale)  │
                                   └───────────────┘
```

## Prerequisites

1. **OCI Account** with Always Free Tier resources
2. **OCI CLI** configured (`~/.oci/config`)
3. **Tailscale Account** with an auth key
4. **InfraFoundry** installed

## Configuration Files

The example is located in `example-config/envs/oci-k3s/`:

```
example-config/
├── envs/oci-k3s/
│   ├── settings.yaml                    # OCI credentials, Tailscale auth key
│   ├── README.md                        # Quick start guide
│   ├── DECISIONS.md                     # Design decisions and reasoning
│   ├── oci/
│   │   ├── network.yaml                 # VCN, subnets, gateways
│   │   └── instances.yaml               # Control plane + workers
│   ├── files/cloud-init-snippets/
│   │   └── tailscale.yaml               # Bootstrap: DNS, Tailscale
│   └── scripts/
│       └── cleanup-tailscale.sh         # Pre-destroy Tailscale cleanup
└── roles/
    ├── k3s-server/                      # Control plane + iptables
    │   ├── tasks/main.yml
    │   ├── defaults/main.yml
    │   └── README.md
    └── k3s-agent/                       # Worker nodes + iptables
        ├── tasks/main.yml
        ├── defaults/main.yml
        └── README.md
```

## Key Design Decisions

For detailed explanations of all design decisions, see [DECISIONS.md](../../example-config/envs/oci-k3s/DECISIONS.md).

### OCI Firewall Fix (Critical)

OCI Ubuntu instances have restrictive default iptables rules that block K3s networking. The fix is applied via Ansible AFTER K3s installation.

**Why Ansible instead of cloud-init?**
- Cloud-init runs BEFORE K3s installation
- K3s/flannel removes UDP 8472 rules during initialization
- Rules applied via cloud-init disappear from live iptables
- Ansible applies rules AFTER K3s, ensuring they persist

**Required iptables rules:**

| Port | Protocol | Purpose |
|------|----------|---------|
| 8472 | UDP | Flannel VXLAN (pod networking) |
| 10250 | TCP | Kubelet API (kubectl logs/exec) |
| 6443 | TCP | Kubernetes API server |

### Tailscale for Management

All management access goes through Tailscale:
- No SSH or Kubernetes API exposed to internet
- Works across NAT and firewalls
- Built-in SSH via `--ssh` flag
- MagicDNS for easy node addressing

## Deployment Steps

### 1. Find Your Ubuntu ARM Image OCID

```bash
oci compute image list \
  --compartment-id <your-compartment-ocid> \
  --operating-system "Canonical Ubuntu" \
  --operating-system-version "24.04" \
  --shape "VM.Standard.A1.Flex" \
  --sort-by TIMECREATED --sort-order DESC \
  --query 'data[0].id' --raw-output
```

### 2. Update Configuration

Edit `envs/oci-k3s/settings.yaml`:
```yaml
provider_settings:
  oci:
    tenancy_ocid: "ocid1.tenancy.oc1..your-tenancy"
    user_ocid: "ocid1.user.oc1..your-user"
    compartment_ocid: "ocid1.compartment.oc1..your-compartment"
    # ...

secrets:
  tailscale:
    auth_key: "tskey-auth-XXXX-XXXXXXXXXXXX"
```

Edit `envs/oci-k3s/oci/instances.yaml`:
- Replace image OCIDs
- Add your SSH public key

### 3. Encrypt Settings

```bash
foundry secrets init --env oci-k3s
sops --encrypt --in-place envs/oci-k3s/settings.yaml
```

### 4. Deploy Infrastructure

```bash
# Generate and review Terraform
foundry infra plan --env oci-k3s

# Create infrastructure and install K3s
foundry infra apply --env oci-k3s
```

### 5. Access Your Cluster

```bash
# Use the fetched kubeconfig
export KUBECONFIG=~/.kube/oci-k3s.yaml

# Verify cluster
kubectl get nodes
kubectl get pods -A
```

## Destroy Workflow

**Important:** Clean up Tailscale devices before destroying infrastructure to avoid orphaned entries.

```bash
# 1. Clean up Tailscale devices
TAILSCALE_API_KEY=tskey-api-xxx ./scripts/cleanup-tailscale.sh

# 2. Destroy infrastructure
foundry infra destroy --env oci-k3s

# 3. (Optional) Recreate
foundry infra apply --env oci-k3s
```

Get your API key from: https://login.tailscale.com/admin/settings/keys
Required scopes: `devices:read`, `devices:write`

## Ansible Roles

### k3s-server

Installs K3s control plane:
- Configures TLS SANs for Tailscale hostname
- Fetches kubeconfig to local machine
- Updates server endpoint for remote access
- **Applies OCI iptables fix after K3s installation**

Variables:
- `kubeconfig_local_path`: Where to save kubeconfig (default: `~/.kube/k3s-cluster.yaml`)
- `k3s_version`: Specific version (default: latest)
- `k3s_server_args`: Additional server arguments
- `k3s_vcn_cidr`: VCN CIDR for iptables rules (default: `10.0.0.0/16`)
- `k3s_oci_firewall_fix`: Enable OCI firewall fix (default: `true`)

### k3s-agent

Installs K3s worker nodes:
- Fetches join token from control plane
- Joins existing cluster
- Verifies successful registration
- **Applies OCI iptables fix after K3s installation**

Variables:
- `k3s_control_host`: Inventory name of control plane (required)
- `k3s_version`: Should match server version
- `k3s_agent_args`: Additional agent arguments
- `k3s_vcn_cidr`: VCN CIDR for iptables rules (default: `10.0.0.0/16`)
- `k3s_oci_firewall_fix`: Enable OCI firewall fix (default: `true`)

## Resource Usage

| Resource | Free Tier Limit | This Config |
|----------|-----------------|-------------|
| ARM OCPUs | 4 | 4 (2+1+1) |
| RAM | 24 GB | 24 GB (8+8+8) |
| Boot Volume | 200 GB | 150 GB (50×3) |

## Customization

### Different Region

Update `settings.yaml` region and find new image OCID:
```yaml
provider_settings:
  oci:
    region: "eu-frankfurt-1"
```

### Disable Traefik

```yaml
ansible_vars:
  k3s_server_args: "--disable traefik"
```

### Add Node Labels

```yaml
ansible_vars:
  k3s_agent_args: "--node-label zone=private"
```

### Disable OCI Firewall Fix

If running on a non-OCI cloud or with different firewall configuration:
```yaml
ansible_vars:
  k3s_oci_firewall_fix: false
```

## Troubleshooting

### DNS Resolution Failures from Worker Pods

**Symptom:** `nslookup kubernetes.default.svc` times out from worker pods

**Cause:** UDP 8472 (VXLAN) blocked by iptables

**Diagnosis:**
```bash
# Check if VXLAN rule exists
ssh ubuntu@<node> 'sudo iptables -L INPUT -n | grep 8472'
# Should show: ACCEPT udp -- 10.0.0.0/16 0.0.0.0/0 udp dpt:8472
```

**Fix:** Re-run Ansible to apply iptables rules:
```bash
foundry infra apply --env oci-k3s --ansible-only
```

### kubectl logs/exec Returns 502 Bad Gateway

**Symptom:** `kubectl logs <pod>` or `kubectl exec` fails with 502

**Cause:** TCP 10250 (kubelet API) blocked by iptables

**Diagnosis:**
```bash
ssh ubuntu@<node> 'sudo iptables -L INPUT -n | grep 10250'
```

### Tailscale Not Connecting

```bash
# Check cloud-init logs
ssh ubuntu@<public-ip> 'sudo cat /var/log/cloud-init-output.log'

# Check Tailscale status
ssh ubuntu@<public-ip> 'sudo tailscale status'
```

### Workers Can't Pull Images

Verify NAT gateway is configured and private subnet routes through it.

### Instance Creation Fails

OCI free tier ARM instances are popular. Try different availability domains or off-peak hours.

### Orphaned Tailscale Devices

After destroy, devices may remain in Tailscale admin console. Run cleanup script:
```bash
TAILSCALE_API_KEY=tskey-api-xxx ./scripts/cleanup-tailscale.sh
```

## See Also

- [Design Decisions Document](../../example-config/envs/oci-k3s/DECISIONS.md)
- [OCI Provider Documentation](../providers/oci.md)
- [Ansible Runner Documentation](../runners/ansible.md)
- [Separate Config Repository Guide](../configuration/separate-config-repo.md)
- [Example Config Repository](../../example-config/)

---

**Last Updated:** 2026-01-26
