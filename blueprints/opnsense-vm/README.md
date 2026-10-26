# opnsense-vm Blueprint

A disposable OPNsense firewall on Proxmox, for testing the OPNsense provider.
It imports the official OPNsense **nano** image, boots it, and bootstraps it
over the serial console so the box comes up with your root password, an API
key, static WAN and LAN addresses, and a WAN rule that lets the controller
reach the API. The OPNsense provider can then manage it with no manual steps.

## How it works

1. **VM (Proxmox provider, `disk_image_source`).** On the Proxmox host, the
   provider downloads the nano image, checks its sha256 (if `image_sha256` is
   set), decompresses it into `image_cache_dir`, and imports it as the boot
   disk. Downloads and decompressed images are cached. The VM has two e1000
   NICs, which FreeBSD names `em0` and `em1`:
   - `em0` is the LAN, on `lan_bridge` (default `vmbr1`, an isolated bridge);
   - `em1` is the WAN, on `wan_bridge` tagged with `wan_vlan` (default
     `vmbr0`, VLAN 10).
2. **Bootstrap (`on_create` event).** `scripts/opnsense-post-terraform.sh` runs
   `opnsense-bootstrap.yml` against the Proxmox host. The role starts the VM
   with an expect script listening on its serial socket. The script logs in as
   root/`opnsense` (the nano defaults) and opens the shell. It then sends a
   PHP script in base64 pieces and runs it. The PHP script edits the config
   through OPNsense's own config class and sets:
   - the hostname and domain;
   - the root password, and an API key and secret for root;
   - the WAN as `wan_ip`/`wan_prefix`, with the RFC1918 and bogon blocks off
     (the WAN is on a private network);
   - the LAN as `lan_ip`/`lan_prefix`;
   - a WAN pass rule for TCP 443 from `api_allow_cidr`.

   The box then reboots. The handler waits until
   `https://<wan_ip>/api/core/firmware/status` turns away an
   unauthenticated request (302 to the login page). The probe sends no
   credentials, since the certificate is self-signed and not verified.
3. **Manage it.** Point the environment's `opnsense` provider settings at
   `https://<wan_ip>` with the same key and secret.

The bootstrap does not set a default gateway or DNS. Manage those with the
provider (`gateways`, `system.dns`) after the box is up.

## Usage

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: opnsense-test
description: "Disposable OPNsense test firewall"
blueprint: opnsense-vm

variables:
  vm_name: opnsense-test
  vmid: 950
  target_node: pve3
  pve_host: "192.168.10.102"
  image_sha256: "<sha256 of the .img.bz2 from the release checksums file>"
```

```yaml
# envs/<env>/proxmox/<package>/secrets.yaml (SOPS-encrypted)
variables:
  opnsense_root_password: "..."
  opnsense_api_key: "..."
  opnsense_api_secret: "..."
```

```bash
foundry infra apply --env <env> --package opnsense-test
```

To remove it, run `foundry infra destroy --env <env> --package opnsense-test`,
which stops and purges the VM. The cached image stays on the Proxmox host.

## Variables

### Required

| Variable | Description |
| -------- | ----------- |
| `vm_name` | Proxmox VM name and the firewall's hostname |
| `vmid` | Proxmox VM ID |

### Package secrets (required)

| Secret | Description |
| ------ | ----------- |
| `opnsense_root_password` | Root password set on the box |
| `opnsense_api_key` | API key created for root (no `:`) |
| `opnsense_api_secret` | Its secret |

### Optional

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `target_node` | `pve3` | Proxmox node for the VM |
| `pve_host` | `192.168.10.102` | Address Ansible uses to SSH to `target_node` as root |
| `disk_storage` | `local-lvm` | Storage for the imported disk |
| `memory` / `cores` | `2048` / `2` | VM size |
| `image_source` | nano 26.1.6 on pkg.opnsense.org | URL or absolute path on the PVE host of a `.img` or `.img.bz2` |
| `image_sha256` | `""` | sha256 of `image_source`; empty skips the check |
| `image_cache_dir` | `/var/lib/vz/template/cache/infrafoundry` | Where downloads and decompressed images are kept |
| `wan_bridge` / `wan_vlan` | `vmbr0` / `10` | WAN bridge and VLAN tag |
| `wan_ip` / `wan_prefix` | `192.168.10.250` / `24` | Static WAN address |
| `lan_bridge` | `vmbr1` | LAN bridge |
| `lan_ip` / `lan_prefix` | `192.168.99.1` / `24` | LAN address |
| `domain` | `lab.local` | Domain |
| `api_allow_cidr` | `192.168.10.0/24` | Source allowed to reach the web GUI/API on the WAN |
| `boot_timeout` | `600` | Seconds to wait for the first login prompt, and for the API afterwards |
| `extra_tags` | `[]` | Extra Proxmox tags |

## Prerequisites

- **Bridges:** `lan_bridge` exists on `target_node`. For an isolated LAN,
  create a bridge with no ports.
- **SSH:** the controller can SSH to `pve_host` as root, and the host key is
  already in `known_hosts` (Ansible checks it).
- **Network:** the Proxmox host can reach `image_source`; the controller can
  reach `wan_ip` on TCP 443 (it must be inside `api_allow_cidr`).
- **Ansible** is on `PATH` on the controller. The playbook installs `expect`
  and `socat` on the Proxmox host.

## Notes

- The bootstrap runs once, on create. On a box that is already bootstrapped,
  the default credentials are rejected and the bootstrap fails; destroy and
  re-apply to start over.
- Nothing secret is written to the Proxmox host. The rendered PHP reaches the
  expect process only through its environment, and the expect log is paused
  while it is sent.
