# K3s Server Role

Installs K3s in server mode (control plane) on a target node.

## Features

- Installs latest K3s or specific version
- Configures TLS SANs for remote access (Tailscale hostnames)
- Fetches kubeconfig to local machine with updated server endpoint
- Clean install (removes existing K3s if present)
- Retry logic for unreliable networks

## Requirements

- Ubuntu 22.04+ or Debian 12+
- Root/sudo access
- Network connectivity to download K3s

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `k3s_version` | `""` (latest) | K3s version to install (e.g., `v1.28.5+k3s1`) |
| `kubeconfig_local_path` | `~/.kube/k3s-cluster.yaml` | Where to save kubeconfig locally |
| `k3s_server_args` | `""` | Additional server arguments |
| `k3s_cluster_cidr` | `""` | Pod CIDR (default: 10.42.0.0/16) |
| `k3s_service_cidr` | `""` | Service CIDR (default: 10.43.0.0/16) |

## Example Usage

In your InfraFoundry instance configuration:

```yaml
instance:
  - name: k3s-control
    # ... instance config ...
    ansible_host: "k3s-control.your-tailnet.ts.net"
    ansible_roles:
      - k3s-server
    ansible_vars:
      kubeconfig_local_path: "~/.kube/oci-k3s.yaml"
      k3s_server_args: "--disable traefik"
```

## After Installation

```bash
# Use the fetched kubeconfig
export KUBECONFIG=~/.kube/k3s-cluster.yaml

# Verify cluster
kubectl get nodes
kubectl get pods -A
```

## Customization

### Disable Default Components

```yaml
ansible_vars:
  k3s_server_args: "--disable traefik --disable servicelb"
```

### Custom Network CIDRs

```yaml
ansible_vars:
  k3s_cluster_cidr: "10.100.0.0/16"
  k3s_service_cidr: "10.101.0.0/16"
```

## Notes

- The role adds `ansible_host` to TLS SANs, enabling kubectl via Tailscale
- Existing K3s installations are completely removed before reinstall
- Kubeconfig `server:` is automatically updated to use `ansible_host`
