# AIQUM (Active IQ Unified Manager) Blueprint

Reusable blueprint that deploys NetApp Active IQ Unified Manager on a Rocky 9
Proxmox VM, configures an OPNsense DHCP reservation, and runs a multi-phase
post-deploy event handler that installs the AIQUM RPM, completes the First
Experience Wizard via REST API, and adds an ONTAP cluster as a monitored
datasource.

This blueprint clones from the `rocky9-template` blueprint. See
`blueprints/rocky9-template/README.md` for the upstream template, and
`blueprints/ontap-cluster/README.md` for the canonical multi-file blueprint
structure.

## Usage

A package consumes this blueprint with a thin manifest that supplies only the
per-instance values:

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: aiqum
description: "NetApp Active IQ Unified Manager"
blueprint: aiqum

variables:
  vm_name: aiqum
  vmid: 222
  target_node: pve1
  disk_storage: local-lvm
  ip_address: "192.168.1.50"
  dhcp_subnet: my-subnet
  # ... secrets and per-environment URLs (see below)
```

Then:

```bash
infra apply --env <env> --package aiqum
```

## Variables

### Required (must be set in the consuming package)

| Variable | Description | Example |
|---|---|---|
| `vm_name` | VM hostname (also DHCP hostname) | `aiqum` |
| `vmid` | Proxmox VM ID | `222` |
| `target_node` | Proxmox host | `pve1` |
| `disk_storage` | Proxmox storage pool for the disk | `local-lvm` |
| `ip_address` | VM IP (assigned via DHCP reservation) | `192.168.1.50` |
| `dhcp_subnet` | OPNsense Kea subnet reference | `opt1-infrastructure` |
| `aiqum_admin_password` | AIQUM admin password (replaces default `admin`) | (secret) |
| `aiqum_admin_email` | Admin email for notifications | `admin@example.com` |
| `aiqum_url_base` | Base URL hosting the AIQUM RPM | `http://web/aiqum` |
| `jumphost` | SSH jumphost for VM access during install | `ansible@host` |
| `smtp_server` | SMTP relay server | `smtp.example.com` |
| `smtp_user` | SMTP auth username | `aiqum` |
| `smtp_password` | SMTP auth password | (secret) |
| `ontap_cluster_ip` | ONTAP cluster management IP | `192.168.1.220` |
| `ontap_admin_password` | ONTAP admin password | (secret) |
| `aiqum_alert_email` | Email address for alert notifications (empty = skip) | `alerts@example.com` |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `template_vmid` | `901` | Rocky 9 cloud-init template VM ID |
| `cores` | `4` | vCPU count |
| `memory` | `12288` | Memory in MiB (AIQUM minimum) |
| `disk_size` | `150` | Disk size in GiB (AIQUM minimum) |
| `bridge` | `vmbr0` | Network bridge |
| `vlan_tag` | `10` | VLAN tag for the VM NIC |
| `mac_address` | `""` | VM MAC (empty = Proxmox auto-assigns) |
| `aiqum_admin_user` | `umadmin` | AIQUM admin username |
| `smtp_port` | `587` | SMTP port |
| `ontap_admin_user` | `admin` | ONTAP admin username |
| `extra_tags` | `[]` | Additional Proxmox tags to append |

## Prerequisites

- The `rocky9-template` blueprint applied (provides VM ID `901` to clone from)
- AIQUM RPM and install scripts hosted at `${aiqum_url_base}/`:
  - `netapp-um-9.18-el9.x86_64.rpm` (~1.9 GB)
  - `pre_install_check.sh`
  - `install7zip.sh`
- SSH jumphost reachable from the InfraFoundry host
- ONTAP cluster running and reachable (for the cluster-add step)

## Automation Flow

```
infra apply --package aiqum
  |
  +-- Terraform: Clone Rocky 9 template, resize disk to 150G
  +-- Terraform: Upload cloud-init user-data (ansible user, DHCP, qemu-agent)
  +-- Terraform: Create DHCP reservation on OPNsense
  |
  +-- on_create (resource: <vm_name>):
       |
       +-- aiqum-post-terraform.sh
            |
            +-- Phase 1: Wait for VM SSH (via ansible jumphost)
            +-- Phase 2: Upload and run aiqum-install-remote.sh on VM
            |    +-- Install wget, unzip
            |    +-- Configure EPEL + MySQL 8.4 repos
            |    +-- Install 7-Zip
            |    +-- Configure firewall (all AIQUM ports)
            |    +-- Download AIQUM RPM from aiqum_url_base (~1.9GB)
            |    +-- Run pre_install_check.sh
            |    +-- Install AIQUM RPM + 225 dependencies
            +-- Phase 3: Wait for AIQUM web UI
            +-- Phase 4: Regenerate certificates (FQDN-based)
            +-- Phase 5: Run aiqum-initial-setup.py (FEW wizard)
                 +-- Step 1: Configure email + SMTP
                 +-- Step 2: Enable AutoSupport
                 +-- Step 3: Change admin password
                 +-- Step 4: Enable API Gateway
                 +-- Step 5: Add ONTAP cluster
                 +-- Step 6: Mark setup complete
                 +-- Step 7: Create default alert policy (if aiqum_alert_email set)
                 +-- Step 8: Send test alert email (if alert created)
```

## Firewall Ports

AIQUM requires these ports open (configured automatically by the install script):

| Port | Purpose |
|---|---|
| 443 | Web UI and REST API |
| 9443 | Cluster agent communication (AMQP/websocket) |
| 80 | HTTP redirect |
| 8080 | Internal services |
| 56072, 56080, 56443 | Acquisition unit communication |

## Post-Deploy Access

After a successful deploy:
- **Web UI**: `https://<ip_address>/`
- **Username**: value of `aiqum_admin_user` (default: `umadmin`)
- **Password**: value of `aiqum_admin_password`

## Notes

- VM hardware (`cores`, `memory`, `disk_size`) is set to AIQUM minimum
  recommendations and is rarely overridden.
- The default tags (`ontap`, `aiqum`) and `cloud_init_snippets` are recipe-level
  metadata baked into the blueprint. Additional tags can be appended via `extra_tags`.
- Events live at the top of `blueprint.yaml` (not embedded in `vm.yaml`)
  because the shorthand `vms:` format does not extract per-resource events.
- See `blueprints/ontap-cluster/` for the canonical structure reference for
  multi-file blueprints with cross-provider resources, top-level events,
  and scripts.
