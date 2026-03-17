# ONTAP Simulator 2-Node Cluster

Deploys a 2-node NetApp ONTAP Simulator cluster on Proxmox, including DHCP
reservations on OPNsense and fully automated cluster setup via Ansible.

## Quick Start

```bash
# Deploy everything (VMs, DHCP, cluster setup)
infra apply --env prod --package ontap-cluster

# Destroy everything
infra destroy --env prod --package ontap-cluster
```

## What It Does

1. **Creates 2 ONTAP Simulator VMs** from an OVA on Proxmox
2. **Creates DHCP reservations** on OPNsense (node mgmt, cluster mgmt, data LIFs)
3. **Runs automated post-deploy setup** via `on_create` event handler:
   - Serial console setup (first boot wizard, sysid assignment for node 02)
   - Cluster create on node 01
   - Cluster join on node 02
   - Post-cluster config: SVM, data LIFs, DNS, NTP, aggregates

## Configuration

**`infrafoundry.yml` is the only file you need to edit.** All other files
(playbooks, roles, templates) derive their configuration from its `variables`
section.

### Variables Reference

| Variable | Description | Example |
|---|---|---|
| **VM Configuration** | | |
| `node01_name` | Node 1 hostname | `ontapcl-01` |
| `node02_name` | Node 2 hostname | `ontapcl-02` |
| `node01_vmid` | Proxmox VM ID for node 1 | `220` |
| `node02_vmid` | Proxmox VM ID for node 2 | `221` |
| `node01_target` | Proxmox host for node 1 | `pve1` |
| `node02_target` | Proxmox host for node 2 | `pve1` |
| `ova_source` | Path to ONTAP Simulator OVA on Proxmox storage | `/mnt/pve/infra/appliances/ontap/9.18.1/vsim-...ova` |
| `disk_storage` | Proxmox storage for VM disks | `nas01` |
| **Proxmox Hosts** | | |
| `pve1_host` | FQDN/IP of Proxmox host 1 | `192.168.1.10` |
| `pve2_host` | FQDN/IP of Proxmox host 2 | `192.168.1.11` |
| **Network** | | |
| `bridge` | Proxmox network bridge | `vmbr0` |
| `mgmt_vlan` | VLAN tag for management network | `10` |
| **MAC Addresses** | | |
| `node01_mgmt_mac` | Node 1 management NIC (e0c) | `` |
| `node01_data_mac` | Node 1 data NIC (e0d) | `` |
| `node02_mgmt_mac` | Node 2 management NIC (e0c) | `` |
| `node02_data_mac` | Node 2 data NIC (e0d) | `` |
| **Node 02 Identity** | | |
| `node02_serial_number` | Serial number for node 2 (from OVA) | `4082368-50-7` |
| `node02_sysid` | System ID for node 2 (from OVA) | `4082368507` |
| **Cluster Configuration** | | |
| `cluster_name` | ONTAP cluster name | `ontapcl` |
| `cluster_mgmt_ip` | Cluster management LIF IP | `192.168.1.220` |
| `cluster_mgmt_mask` | Cluster management subnet mask | `255.255.255.0` |
| `cluster_mgmt_gateway` | Cluster management gateway | `192.168.1.1` |
| `node01_mgmt_ip` | Node 1 management IP | `192.168.1.221` |
| `node02_mgmt_ip` | Node 2 management IP | `192.168.1.222` |
| `node_mgmt_mask` | Node management subnet mask | `255.255.255.0` |
| `node_mgmt_gateway` | Node management gateway | `192.168.1.1` |
| `ontap_password` | Admin password for ONTAP | `changeme123` |
| `dns_domain` | DNS domain name | `lab.local` |
| **Post-Cluster: SVM & Data LIFs** | | |
| `svm_name` | Storage VM name | `svm_data` |
| `data_lif1_ip` | Data LIF 1 IP (on node 1) | `192.168.1.230` |
| `data_lif2_ip` | Data LIF 2 IP (on node 2) | `192.168.1.231` |
| `data_lif_mask` | Data LIF subnet mask | `255.255.255.0` |
| **DNS & NTP** | | |
| `dns_nameserver` | DNS server IP | `192.168.1.1` |
| `ntp_server` | NTP server IP | `192.168.1.1` |
| **DHCP Reservations** | | |
| `dhcp_subnet` | OPNsense Kea subnet reference | `opt1-infrastructure` |
| `data_lif1_mac` | Data LIF 1 MAC for DHCP reservation | `bc:24:11:00:01:d1` |
| `data_lif2_mac` | Data LIF 2 MAC for DHCP reservation | `bc:24:11:00:02:d2` |
| `cluster_mgmt_mac` | Cluster mgmt MAC for DHCP reservation | `01:01:01:01:01:01` |

## Package Structure

```
ontap-cluster/
  infrafoundry.yml          # Main config — edit this
  vm.yaml                   # VM definitions (Jinja2 template)
  dhcp.yaml                 # DHCP reservations (Jinja2 template)
  scripts/
    ontap-post-terraform.sh # on_create event handler
  ontap-lab-playbook.yml    # Master playbook (runs serial + cluster setup)
  ontap-lab-serial-setup.yml  # First-boot serial console setup
  ontap-lab-cluster-setup.yml # Cluster create/join/post-config
  ansible.cfg               # Ansible settings
  requirements.yml          # Ansible Galaxy requirements
  roles/
    ontap-serial-setup/     # First-boot wizard via expect scripts
    ontap-cluster-setup/    # Cluster create + node join via expect
    ontap-post-cluster/     # SVM, LIFs, DNS, NTP, aggregates via ONTAP REST
  logs/                     # Expect script logs (auto-generated)
```

## Files You Typically Edit

| File | When to Edit |
|---|---|
| `infrafoundry.yml` | Always — all configuration lives here |
| `vm.yaml` | Only if changing VM hardware (cores, memory, NICs, disk bus) |
| `dhcp.yaml` | Only if adding/removing DHCP reservations |

## Network Layout

Each ONTAP Simulator VM has 4 NICs:

| NIC | Interface | Purpose |
|---|---|---|
| `net0` (e1000) | e0a | Cluster interconnect |
| `net1` (e1000) | e0b | Cluster interconnect |
| `net2` (e1000) | e0c | Node management (VLAN tagged) |
| `net3` (e1000) | e0d | Data (VLAN tagged) |

## Automation Flow

```
infra apply --package ontap-cluster
  |
  +-- Terraform: Create 2 OVA VMs on Proxmox
  +-- Terraform: Create 5 DHCP reservations on OPNsense
  |
  +-- on_create (requires: ontapcl-01, ontapcl-02):
       |
       +-- ontap-post-terraform.sh
            |
            +-- Generate Ansible inventory from infrafoundry.yml
            +-- ansible-playbook ontap-lab-playbook.yml
                 |
                 +-- ontap-serial-setup (expect: first-boot wizard)
                 +-- ontap-cluster-setup (expect: cluster create + join)
                 +-- ontap-post-cluster (REST API: SVM, LIFs, DNS, NTP)
```

## Prerequisites

- ONTAP Simulator OVA extracted and accessible on Proxmox storage
- Ansible installed with `netapp.ontap` collection (`ansible-galaxy install -r requirements.yml`)
- `expect` available on the Proxmox host (for serial console automation)
- SSH access to Proxmox hosts as root

## Manual Playbook Runs

If you need to re-run the Ansible playbooks without redeploying:

```bash
cd config-repo/envs/dev/proxmox/ontap-cluster/

# Run the full setup
./scripts/ontap-post-terraform.sh

# Or run individual playbooks manually
ansible-playbook -i .generated-inventory.yml ontap-lab-serial-setup.yml -e @.generated-vars.json -v
ansible-playbook -i .generated-inventory.yml ontap-lab-cluster-setup.yml -e @.generated-vars.json -v
```

## Troubleshooting

- **Logs**: Check `logs/` for expect script output from cluster create/join
- **Serial console**: `ssh root@pve1 "qm terminal <vmid>"` to access ONTAP serial console
- **Cluster status**: `ssh admin@<cluster_mgmt_ip>` then `cluster show`
- **Node not joining**: Verify `node02_serial_number` and `node02_sysid` match the OVA
