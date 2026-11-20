# k3s-dns role

Gives k3s its own resolver file and points the kubelet at it, so pods stop
inheriting the node's Tailscale DNS (`100.100.100.100` plus tailnet search
domains), which musl-based pods cannot use for external names.

The role is idempotent and standalone. It never installs or uninstalls k3s and
never touches `/var/lib/rancher`; it fails when the k3s binary is missing.

## What it writes

- `<k3s_dns_config_dir>/resolv.conf` with the nameservers and, when set, a
  `search` line.
- `<k3s_dns_config_dir>/config.yaml.d/50-infrafoundry-dns.yaml` with
  `resolv-conf: <dir>/resolv.conf`.

The `k3s` or `k3s-agent` service restarts only when one of the files changed.

## Variables

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `k3s_dns_nameservers` | `[]` | 1 to 3 resolvers; empty skips the role |
| `k3s_dns_search` | `[]` | Cluster-wide search domains |
| `k3s_dns_config_dir` | `/etc/rancher/k3s` | k3s config directory |
| `k3s_dns_install_marker` | `/usr/local/bin/k3s` | Must exist |
| `k3s_dns_service` | `k3s` | Unit to restart (`k3s-agent` on workers) |
| `k3s_control_host` | unset | Set on workers; the readiness wait runs there |

It sets the fact `k3s_dns_changed`, which `blueprints/k3s-cluster/playbooks/k3s-dns.yml` uses to decide
whether to restart CoreDNS.
