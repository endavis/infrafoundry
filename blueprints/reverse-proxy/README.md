# reverse-proxy Blueprint

Runs Caddy on one Proxmox VM (Ubuntu template) and serves device web UIs at
`<name>.<dns_domain>` with a Let's Encrypt certificate issued by InfraFoundry. One `routes`
list generates the OPNsense DNS host overrides, the Caddyfile and the handler input.
Automatic HTTPS is off; the certificate is installed on the VM by the acme provider.

User guide: [docs/guides/reverse-proxy.md](../../docs/guides/reverse-proxy.md).

## Usage

```yaml
# envs/<env>/proxmox/reverse-proxy/infrafoundry.yml
name: reverse-proxy
blueprint: reverse-proxy

variables:
  vm_name: reverse-proxy
  vmid: 225
  target_node: node1
  disk_storage: local-lvm
  ip_address: "192.0.2.70"
  dhcp_subnet: my-subnet
  dns_domain: example.com
  routes:
    - name: nas
      backend: "https://192.0.2.20:443"
      insecure: true
  certificate_names: ["*.example.com"]
  jumphost: "ansible@jump.example.com"
```

## Variables

| Variable | Default | Description |
| --- | --- | --- |
| `vm_name`, `vmid`, `target_node`, `disk_storage`, `ip_address`, `dhcp_subnet` | required | VM placement and the DHCP reservation |
| `dns_domain` | required | Domain the routes are served under |
| `routes` | `[]` | The route list, see below |
| `allowed_networks` | `[]` | CIDRs allowed on every route without its own `allow_from` |
| `certificate_names` | `[]` | Names of the certificate; empty creates no certificate resource |
| `certificate_key_type` | `ec-p256` | `ec-p256` or `rsa-2048` |
| `cert_dir` | `/etc/ssl/infrafoundry` | Where `proxy.fullchain.pem` and `proxy.key` go on the VM |
| `template_vmid`, `template_node` | `900`, `node1` | Ubuntu template to clone |
| `cores`, `memory`, `disk_size` | `2`, `1024`, `32` | VM size; `cores` must be at least 2; `disk_size` must be at least the template's disk (Proxmox cannot shrink a disk) |
| `bridge`, `vlan_tag`, `mac_address` | `vmbr0`, `10`, empty | Network |
| `jumphost`, `ssh_user` | empty, `ansible` | SSH access |
| `extra_tags`, `cloud_init_snippets_storage`, `balloon` | | Optional VM settings |

### Route schema

| Key | Description |
| --- | --- |
| `name` | DNS label; the FQDN is `<name>.<dns_domain>` |
| `backend` | `http(s)://host[:port]` |
| `insecure` | `true` skips backend certificate verification (https only), default `false` |
| `host_header` | empty: client `Host` passes through; `upstream`: the backend's own; other: literal |
| `allow_from` | CIDR list; empty falls back to `allowed_networks`; both empty: unrestricted |

UIs that check the `Host` header or redirect to their own address need `host_header: upstream`
or a literal value; set `insecure` for backends with a self-signed certificate.

## What gets created

- a Proxmox VM (tag `reverse-proxy`, plus its reserved `ip_address` as a tag) and an OPNsense Kea DHCP reservation;
- one Unbound host override per route (`<vm_name>-<route>`), whose description summarizes the route;
- an acme `certificate` (`<vm_name>-cert`) targeting the VM, when `certificate_names` is set;
- an `after_apply` handler (`reverse-proxy-config`) that renders the Caddyfile, validates it on
  the VM and reloads Caddy only when it changed.

## First deployment

The first deployment needs two applies and two `certs issue` runs, in this order:

1. `foundry secrets host-keys --env <env>`
2. `foundry infra apply --env <env>` (VM, DNS, Caddy; the handler warns that the certificate files are missing)
3. `foundry certs issue --env <env>` (the certificate is issued and installed; its verify step on port 443 fails on this first run, which is expected)
4. `foundry infra apply --env <env>` (writes the Caddyfile, reloads Caddy)
5. `foundry certs issue --env <env>` again (the install-only retry verifies the certificate and records it as installed)

The first verify fails because Caddy has no site configuration until the certificate files
exist: the handler skips the Caddyfile while they are missing, so nothing listens on port 443
with the certificate. Step 4 writes the Caddyfile, and step 5 then verifies successfully.

**Decision (#1700):** the blueprint does not avoid the extra round. The handler validates the
Caddyfile with `caddy validate` before reloading, and a configuration that references missing
certificate files fails validation, so the Caddyfile is only written once the files exist.
Writing a placeholder or self-signed configuration first would change the blueprint's
behaviour and is left to a separate issue.

### SSH agent

The proxy VM is reached through the host in the `jumphost` setting, using the SSH agent. When
that key has a passphrase, load it into the agent (`ssh-add`) before every apply and before
unattended `foundry certs renew` runs. Renewals fail when the agent holds no key.

## Caddy version

Caddy comes from the distribution package on the VM. The directives used (`auto_https off`,
`tls`, `reverse_proxy` with `transport http`, `header_up`, a `remote_ip` matcher, `abort`)
are checked by `caddy validate` on the VM before each reload; the installed version is not
pinned by the blueprint.
