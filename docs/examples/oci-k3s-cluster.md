# OCI K3s Cluster with Tailscale

A complete example of deploying a K3s Kubernetes cluster on Oracle Cloud Infrastructure (OCI) using Always Free Tier ARM instances with Tailscale for secure management access.

## Overview

This example demonstrates:

- **OCI Free Tier**: Maximizes the Always Free ARM instances (4 OCPUs, 24GB RAM)
- **Network Isolation**: Workers in private subnet with NAT gateway for image pulls
- **Secure Access**: Tailscale overlay network for SSH and kubectl access
- **Full Automation**: Terraform for infrastructure, Ansible for K3s installation

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
│   ├── README.md                        # Detailed setup instructions
│   ├── oci/
│   │   ├── network.yaml                 # VCN, subnets, gateways
│   │   └── instances.yaml               # Control plane + workers
│   └── files/cloud-init-snippets/
│       └── tailscale.yaml               # Tailscale installation script
└── roles/
    ├── k3s-server/                      # Control plane installation
    │   ├── tasks/main.yml
    │   ├── defaults/main.yml
    │   └── README.md
    └── k3s-agent/                       # Worker node installation
        ├── tasks/main.yml
        ├── defaults/main.yml
        └── README.md
```

## Key Configuration

### Network (`oci/network.yaml`)

```yaml
vcn:
  - name: k3s-vcn
    cidr_block: "10.0.0.0/16"
    internet_gateway: true
    nat_gateway: true        # Enables outbound for private subnet
    security_list:
      ingress_rules:
        - source: "0.0.0.0/0"
          protocol: "6"
          tcp_options:
            min: 22
            max: 22

subnet:
  - name: k3s-control-subnet
    cidr_block: "10.0.0.0/24"
    public: true             # Control plane gets public IP

  - name: k3s-worker-subnet
    cidr_block: "10.0.1.0/24"
    public: false            # Workers are private
```

### Instances (`oci/instances.yaml`)

```yaml
instance:
  - name: k3s-control
    shape: VM.Standard.A1.Flex
    shape_config:
      ocpus: 2
      memory_in_gbs: 8
    subnet: k3s-control-subnet
    assign_public_ip: true
    cloud_init_snippets:
      - tailscale
    ansible_host: "k3s-control.${variables.tailnet}"
    ansible_roles:
      - k3s-server

  - name: k3s-worker-0
    subnet: k3s-worker-subnet
    assign_public_ip: false
    ansible_roles:
      - k3s-agent
    ansible_vars:
      k3s_control_host: "k3s-control"
```

### Cloud-Init Tailscale (`files/cloud-init-snippets/tailscale.yaml`)

The cloud-init snippet installs Tailscale on first boot with retry logic for unreliable networks:

```yaml
#cloud-config
runcmd:
  - |
    # Download and install Tailscale with retries
    for i in $(seq 1 30); do
      curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/pool/tailscale_*.deb -o /tmp/tailscale.deb && break
      sleep 10
    done
    dpkg -i /tmp/tailscale.deb
  - tailscale up --auth-key=${TS_AUTH_KEY} --hostname=${HOSTNAME} --ssh
```

## Deployment Steps

### 1. Find Your Ubuntu ARM Image OCID

```bash
oci compute image list \
  --compartment-id <your-compartment-ocid> \
  --operating-system "Canonical Ubuntu" \
  --operating-system-version "22.04" \
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
infra secrets init --env oci-k3s
sops --encrypt --in-place envs/oci-k3s/settings.yaml
```

### 4. Deploy Infrastructure

```bash
# Generate and review Terraform
infra plan --env oci-k3s

# Create infrastructure
infra apply --env oci-k3s
```

### 5. Install K3s

After Terraform completes and nodes join Tailscale:

```bash
# Run Ansible to install K3s
infra apply --env oci-k3s --ansible-only
```

### 6. Access Your Cluster

```bash
# Use the fetched kubeconfig
export KUBECONFIG=~/.kube/oci-k3s.yaml

# Verify cluster
kubectl get nodes
kubectl get pods -A
```

## Ansible Roles

### k3s-server

Installs K3s control plane:
- Configures TLS SANs for Tailscale hostname
- Fetches kubeconfig to local machine
- Updates server endpoint for remote access

Variables:
- `kubeconfig_local_path`: Where to save kubeconfig (default: `~/.kube/k3s-cluster.yaml`)
- `k3s_version`: Specific version (default: latest)
- `k3s_server_args`: Additional server arguments

### k3s-agent

Installs K3s worker nodes:
- Fetches join token from control plane
- Joins existing cluster
- Verifies successful registration

Variables:
- `k3s_control_host`: Inventory name of control plane (required)
- `k3s_version`: Should match server version
- `k3s_agent_args`: Additional agent arguments

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

## Troubleshooting

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

## See Also

- [OCI Provider Documentation](../providers/oci.md)
- [Ansible Runner Documentation](../runners/ansible.md)
- [Separate Config Repository Guide](../configuration/separate-config-repo.md)
- [Example Config Repository](../../example-config/)

---

**Last Updated:** 2025-01-25
