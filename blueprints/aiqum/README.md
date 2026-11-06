# AIQUM (Active IQ Unified Manager) Blueprint

Reusable blueprint that deploys NetApp Active IQ Unified Manager on a Rocky 9
Proxmox VM, configures an OPNsense DHCP reservation, and runs a multi-phase
post-deploy event handler that installs the AIQUM RPM, completes the First
Experience Wizard via REST API, and adds an ONTAP cluster as a monitored
datasource.

This blueprint clones from the `rocky9-template` blueprint. See
`blueprints/rocky9-template/README.md` for the upstream template, and
`blueprints/ontap-cluster/blueprint.yaml` for the canonical multi-file blueprint
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
  target_node: node1
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
| `target_node` | Proxmox host | `node1` |
| `disk_storage` | Proxmox storage pool for the disk | `local-lvm` |
| `ip_address` | VM IP (assigned via DHCP reservation) | `192.168.1.50` |
| `dhcp_subnet` | OPNsense Kea subnet reference | `opt1-servers` |
| `aiqum_admin_password` | AIQUM admin password (replaces default `admin`) | (secret) |
| `aiqum_admin_email` | Admin email for notifications | `admin@example.com` |
| `aiqum_url_base` | Base URL hosting the AIQUM RPM | `http://web/aiqum` |
| `jumphost` | SSH jumphost for VM access during install | `ansible@host` |
| `smtp_server` | SMTP relay server | `smtp.example.com` |
| `smtp_user` | SMTP auth username | `aiqum` |
| `smtp_password` | SMTP auth password | (secret) |
| `ontap_cluster_ip` | ONTAP cluster management IP | `192.0.2.220` |
| `ontap_admin_password` | ONTAP admin password | (secret) |
| `aiqum_alert_email` | Email address for alert notifications (empty = skip) | `alerts@example.com` |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `template_vmid` | `901` | Rocky 9 cloud-init template VM ID |
| `cores` | `4` | vCPU count |
| `memory` | `12288` | Memory in MiB (AIQUM minimum) |
| `balloon` | `0` | Minimum memory in MiB the host may shrink the VM to; `0` never shrinks it (see Notes) |
| `disk_size` | `150` | Disk size in GiB (AIQUM minimum) |
| `bridge` | `vmbr0` | Network bridge |
| `vlan_tag` | `10` | VLAN tag for the VM NIC. Empty: untagged, e.g. on an SDN vnet |
| `mac_address` | `""` | VM MAC (empty = Proxmox auto-assigns) |
| `aiqum_admin_user` | `umadmin` | AIQUM admin username |
| `smtp_port` | `587` | SMTP port |
| `ontap_admin_user` | `admin` | ONTAP admin username |
| `publish_dns` | `false` | Create an OPNsense Unbound host override for the VM (see Publishing DNS) |
| `dns_domain` | `""` | Domain for the override; required when `publish_dns` is true |
| `extra_tags` | `[]` | Additional Proxmox tags to append |

## Publishing DNS

With `publish_dns: true` (and `dns_domain` set) the blueprint also emits an
`unbound.host_overrides` resource named `<vm_name>-dns` on OPNsense, mapping
`<vm_name>.<dns_domain>` to `ip_address`. The default is off and emits nothing;
`publish_dns: true` without `dns_domain` fails the load with an error naming
the input.

- Clients must reach this OPNsense box's Unbound directly, or through an
  `unbound.forwards` entry for `dns_domain` on the resolver they do use (see
  #1168).
- Turning `publish_dns` off later may leave the last override on the box
  (#1252); remove it by hand if it matters.

## ONTAP must resolve the AIQUM hostname

When AIQUM adds a cluster it tells ONTAP to open a cluster-agent connection back to
`wss://<hostname>:56443`, where `<hostname>` is the bare VM hostname (`vm_name`). ONTAP
resolves that name with its own DNS servers. If it cannot, the add fails with an HTTP 500
whose message talks about clock skew or the EMS destination limit. That message is
misleading: the cause is name resolution (#1168).

Before adding the cluster, Step 5 of `aiqum-initial-setup.py` reads ONTAP's DNS servers and
search domains (`GET /api/name-services/dns`) and asks each server for `<vm_name>` and
`<vm_name>.<domain>` for every ONTAP search domain. The outcomes:

| Outcome | Meaning | What Step 5 does |
|---------|---------|------------------|
| OK | A server returned `ip_address` for one of the names | Adds the cluster |
| ERROR | The servers answered but never with `ip_address` | Prints the fix and skips the cluster add; setup continues with Step 6 and still exits 0 |
| WARNING (inconclusive) | No `vm_name` input, ONTAP REST unreadable, no DNS servers configured, or no DNS server answered | Prints the reason and adds the cluster anyway |

To fix an ERROR, publish a DNS record for the hostname on a DNS server ONTAP uses: set
`publish_dns: true` and `dns_domain` on the aiqum package (see
[Publishing DNS](#publishing-dns)), and make sure ONTAP's DNS search domain covers
`dns_domain` so the bare hostname resolves. The `ontap-cluster` package's
`dns_domain` (ONTAP's search domain) and `dns_publish_domain` (the domain it publishes its
own names under, defaulting to `dns_domain`) are the ONTAP-side inputs to keep consistent
with it. Then re-run the package or add the cluster to AIQUM by hand.

## Prerequisites

- The `rocky9-template` blueprint applied (provides VM ID `901` to clone from)
- AIQUM RPM and install scripts hosted at `${aiqum_url_base}/`:
  - `netapp-um-9.18-el9.x86_64.rpm` (~1.9 GB)
  - `pre_install_check.sh`
  - `install7zip.sh`
- SSH jumphost reachable from the InfraFoundry host
- ONTAP cluster running and reachable (for the cluster-add step)
- ONTAP's DNS servers resolve the AIQUM hostname to `ip_address` (see
  [ONTAP must resolve the AIQUM hostname](#ontap-must-resolve-the-aiqum-hostname))

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
                 +-- Step 5: Check ONTAP resolves the AIQUM hostname, then add the
                 |           ONTAP cluster (skipped if the check fails; waits up to
                 |           180 s; a failure or timeout is reported and setup continues)
                 +-- Step 6: Mark setup complete
                 +-- Step 7: Create default alert policy (if aiqum_alert_email set)
                 +-- Step 8: Send test alert email (if alert created)
```

## Keeping AIQUM in step with ontap-cluster

Step 5 adds only the cluster present when AIQUM is installed. To keep AIQUM in step with
cluster rebuilds and destroys, set the optional `aiqum_*` inputs on the `ontap-cluster`
package: `aiqum_address` and `aiqum_admin_password` (put the password in the package's
`secrets.yaml`), plus `aiqum_admin_user` (default `umadmin`) and `aiqum_cluster_user`
(default `admin`; its password is `ontap_password`). Create then registers the cluster
(skipped when a data source already matches by address or name), and destroy removes it.

The requests carry the AIQUM admin and ONTAP passwords, so AIQUM's certificate is verified.
For AIQUM's self-signed certificate, set `aiqum_ca_cert` to a PEM file that trusts it, for
example the certificate exported from the AIQUM web UI. `aiqum_tls_insecure: "true"` skips
the check, which is not recommended.

Entries left behind by a destroy done before this existed must be removed once by hand:

```bash
# AIQUM: list the data sources, then delete the stale one by its key
curl -sk -u umadmin:<password> https://<aiqum>/api/admin/datasources/clusters
curl -sk -u umadmin:<password> -X DELETE https://<aiqum>/api/admin/datasources/clusters/<key>

# NetApp Console: delete the stale on-prem working environment (bearer token and agent ID)
curl -s -X DELETE -H "Authorization: Bearer <token>" -H "x-agent-id: <agent-id>" \
  https://api.bluexp.netapp.com/occm/api/onprem/working-environments/<publicId>
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
- `balloon` lets an overcommitted Proxmox node reclaim the guest's page cache by
  shrinking the VM toward that minimum under memory pressure. AIQUM's
  recommended minimum is 12 GiB, so a lower `balloon` trades AIQUM performance
  for host stability; the install scripts do not check memory. With `0` the VM
  keeps its balloon device (it returns freed pages to the host) but is never
  shrunk. See [Memory ballooning](../../docs/providers/proxmox.md#memory-ballooning).
- The default tags (`ontap`, `aiqum`) and `cloud_init_snippets` are recipe-level
  metadata baked into the blueprint. Additional tags can be appended via `extra_tags`.
- Events live at the top of `blueprint.yaml` (not embedded in `vm.yaml`)
  because the shorthand `vms:` format does not extract per-resource events.
- See `blueprints/ontap-cluster/` for the canonical structure reference for
  multi-file blueprints with cross-provider resources, top-level events,
  and scripts.
