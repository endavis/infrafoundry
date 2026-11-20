# K3s Agent Role

Installs K3s in agent mode (worker node), joining an existing K3s cluster.

## Features

- Automatically fetches join token from control plane
- Installs matching K3s version
- Clean install (removes existing K3s agent if present)
- Verifies successful cluster join
- Retry logic for unreliable networks

## Requirements

- Ubuntu 22.04+ or Debian 12+
- Root/sudo access
- K3s server must be installed and running first
- Network connectivity to control plane (port 6443)

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `k3s_version` | `""` (latest) | K3s version (should match server) |
| `k3s_control_host` | `k3s-control` | Inventory hostname of control plane |
| `k3s_agent_args` | `""` | Additional agent arguments |

## Example Usage

In your InfraFoundry instance configuration:

```yaml
instance:
  - name: k3s-worker-0
    # ... instance config ...
    ansible_host: "k3s-worker-0.your-tailnet.ts.net"
    ansible_roles:
      - k3s-agent
    ansible_vars:
      k3s_control_host: "k3s-control"
```

## How It Works

1. Connects to `k3s_control_host` to fetch the node join token
2. Gets the control plane's `ansible_host` for the server URL
3. Installs K3s agent with the token and server URL
4. Verifies the node appears in `kubectl get nodes`

## Important Notes

### Execution Order

Workers must be provisioned **after** the control plane. In InfraFoundry, this is handled automatically when you define the control plane before workers in your configuration.

### Control Host Reference

The `k3s_control_host` must match the inventory hostname of your control plane node:

```yaml
# Control plane
- name: k3s-control        # This is the inventory hostname
  ansible_roles:
    - k3s-server

# Workers reference it
- name: k3s-worker-0
  ansible_roles:
    - k3s-agent
  ansible_vars:
    k3s_control_host: "k3s-control"  # Must match above
```

### Network Requirements

The agent needs to reach the control plane on port 6443. With Tailscale, this works automatically via the overlay network.

## Customization

### Node Labels

```yaml
ansible_vars:
  k3s_agent_args: "--node-label role=worker --node-label zone=private"
```

### Node Taints

```yaml
ansible_vars:
  k3s_agent_args: "--node-taint dedicated=worker:NoSchedule"
```
