# AIQUM (Active IQ Unified Manager) on Rocky 9

Deploys a Rocky Linux 9 VM from a cloud-init template, installs NetApp AIQUM
via RPM with all prerequisites, completes the first-experience setup wizard
via REST API, and adds the ONTAP cluster for monitoring.

## Quick Start

```bash
# Deploy everything (VM, DHCP, AIQUM install, initial setup, cluster add)
infra apply --env prod --package aiqum

# Destroy everything
infra destroy --env prod --package aiqum
```

## What It Does

1. **Creates a Rocky 9 VM** cloned from template, with cloud-init (ansible user, DHCP networking, qemu-guest-agent)
2. **Creates a DHCP reservation** on OPNsense
3. **Runs automated post-deploy setup** via `on_create` event handler:
   - Installs prerequisites (EPEL, MySQL 8.4 repo, 7-Zip, firewalld, wget)
   - Opens firewall ports (443, 9443, 80, 8080, 56072, 56080, 56443)
   - Downloads and installs AIQUM RPM (~1.9GB) from infra-web
   - Completes the First Experience Wizard (FEW) via REST API:
     - Configures email/SMTP notification
     - Enables AutoSupport
     - Changes admin password from default
     - Enables API Gateway
     - Adds ONTAP cluster as datasource
     - Marks initial setup complete

## Configuration

**`infrafoundry.yml` is the only file you need to edit.** All other files
derive their configuration from its `variables` section.

### Variables Reference

| Variable | Description | Example |
|---|---|---|
| **VM Configuration** | | |
| `vm_name` | VM hostname | `aiqum` |
| `vmid` | Proxmox VM ID | `222` |
| `target_node` | Proxmox host | `pve1` |
| `template_vmid` | Rocky 9 template VM ID | `901` |
| `cores` | CPU cores | `4` |
| `memory` | Memory in MB | `12288` |
| `disk_size` | Disk size in GB | `150` |
| `disk_storage` | Proxmox storage | `nas01` |
| **Network** | | |
| `mac_address` | VM MAC address | `` |
| `ip_address` | VM IP (via DHCP reservation) | `192.168.1.50` |
| `gateway` | Default gateway | `192.168.1.1` |
| `dns_server` | DNS server | `192.168.1.1` |
| `dhcp_subnet` | OPNsense Kea subnet reference | `opt1-infrastructure` |
| **AIQUM** | | |
| `aiqum_admin_user` | AIQUM admin username | `umadmin` |
| `aiqum_admin_password` | AIQUM admin password (replaces default `admin`) | `CHANGE_ME` |
| `aiqum_admin_email` | Admin email for notifications | `admin@example.com` |
| **SMTP** | | |
| `smtp_server` | SMTP relay server | `smtp.example.com` |
| `smtp_port` | SMTP port | `2525` |
| `smtp_user` | SMTP auth username | `aiqum` |
| `smtp_password` | SMTP auth password | `CHANGE_ME` |
| **ONTAP Cluster** | | |
| `ontap_cluster_ip` | ONTAP cluster management IP | `192.168.1.220` |
| `ontap_admin_user` | ONTAP admin username | `admin` |
| `ontap_admin_password` | ONTAP admin password | `CHANGE_ME` |

## Package Structure

```
aiqum/
  infrafoundry.yml            # Main config — edit this
  vm.yaml                     # VM definition (Jinja2 template)
  dhcp.yaml                   # DHCP reservation (Jinja2 template)
  scripts/
    aiqum-post-terraform.sh   # on_create event handler (orchestrates everything)
    aiqum-install-remote.sh   # RPM install script (runs on the VM)
    aiqum-initial-setup.py    # First Experience Wizard automation (REST API)
    capture-console.sh        # Utility to capture VM console output
  docs/
    full-deploy-output.txt    # Example output from a full deploy
```

## Files You Typically Edit

| File | When to Edit |
|---|---|
| `infrafoundry.yml` | Always — all configuration lives here |
| `vm.yaml` | Only if changing VM hardware (cores, memory, NICs) |
| `dhcp.yaml` | Only if changing DHCP reservation settings |

## Automation Flow

```
infra apply --package aiqum
  |
  +-- Terraform: Clone Rocky 9 template, resize disk to 150G
  +-- Terraform: Upload cloud-init user-data (ansible user, DHCP, qemu-agent)
  +-- Terraform: Create DHCP reservation on OPNsense
  |
  +-- on_create (resource: aiqum):
       |
       +-- aiqum-post-terraform.sh
            |
            +-- Phase 1: Wait for VM SSH (via ansible jumphost)
            +-- Phase 2: Upload and run aiqum-install-remote.sh on VM
            |    +-- Install wget, unzip
            |    +-- Configure EPEL + MySQL 8.4 repos
            |    +-- Install 7-Zip
            |    +-- Configure firewall (all AIQUM ports)
            |    +-- Download AIQUM RPM from infra-web (~1.9GB)
            |    +-- Run pre_install_check.sh
            |    +-- Install AIQUM RPM + 225 dependencies
            +-- Phase 3: Wait for AIQUM web UI
            +-- Phase 4: Run aiqum-initial-setup.py (FEW wizard)
                 +-- Step 1: Configure email + SMTP
                 +-- Step 2: Enable AutoSupport
                 +-- Step 3: Change admin password
                 +-- Step 4: Enable API Gateway
                 +-- Step 5: Add ONTAP cluster
                 +-- Step 6: Mark setup complete
```

## Prerequisites

- Rocky 9 cloud-init template (VM ID 901) on Proxmox
- AIQUM RPM and install scripts available at `http://your-web-server/applications/aiqum/`
- SSH access to `ansible@ansible.example.com` (jumphost for VM access)
- ONTAP cluster running and reachable (for cluster add step)

## AIQUM RPM Source

The RPM and related files must be available at:
```
http://your-web-server/applications/aiqum/
  netapp-um-9.18-el9.x86_64.rpm    # Main RPM (~1.9GB)
  pre_install_check.sh              # Prerequisite checker
  install7zip.sh                    # 7-Zip installer
```

These are extracted from `ActiveIQUnifiedManager-9.18-el9.zip` downloaded from
the NetApp Support site.

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

## Troubleshooting

- **VM not booting**: Check `cpu_type` — Rocky 9 requires `host` (not `kvm64`)
- **Cloud-init not applied**: Snippet names must not include `.yaml` extension
- **AIQUM install fails**: Check prerequisites — EPEL, MySQL 8.4 repo, and 7-Zip must be installed first
- **Web UI shows setup wizard**: The `aiqum-initial-setup.py` script didn't complete; run it manually
- **Cluster add fails**: Check firewall port 9443 is open; verify ONTAP cluster is reachable from the VM
- **Stale data after redeploy**: NFS stale file handles can preserve old disk data; clean `/mnt/pve/<storage>/images/<vmid>/` on the Proxmox host before redeploying
