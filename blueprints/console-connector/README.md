# NetApp Console agent (console-connector) Blueprint

Reusable blueprint that deploys the NetApp Console agent (formerly the BlueXP
Connector) on an Ubuntu 24.04 Proxmox VM, with an OPNsense DHCP reservation and
an `on_create` handler that installs Docker Engine and the agent.

**Scope is install only.** Registering the agent with the NetApp Console,
adding the ONTAP cluster and deregistering the agent are manual steps
documented below. NetApp documents no non-interactive registration, so this
blueprint calls no Console API.

Requirements come from
<https://docs.netapp.com/us-en/console-setup-admin/task-install-agent-on-prem.html>.

This blueprint clones from the `ubuntu-template` blueprint (default
`template_vmid: 900`). Its structure follows `blueprints/aiqum/`.

## Usage

```yaml
# envs/<env>/proxmox/<package>/infrafoundry.yml
name: console-connector
blueprint: console-connector

variables:
  vm_name: console-connector
  vmid: 223
  target_node: pve1
  disk_storage: local-lvm
  ip_address: "192.168.1.51"
  dhcp_subnet: my-subnet
  console_agent_url_base: "http://web/applications/console-connector"
  console_agent_installer: "NetApp_Console_Agent_Cloud_<version>"
  console_agent_sha256: "<sha256sum of the installer>"
```

```bash
infra apply --env <env> --package console-connector
```

## Variables

### Required

| Variable | Description |
|---|---|
| `vm_name` | VM hostname (also DHCP hostname) |
| `vmid` | Proxmox VM ID |
| `target_node` | Proxmox host |
| `disk_storage` | Proxmox storage pool for the disk |
| `ip_address` | VM IP (assigned via DHCP reservation) |
| `dhcp_subnet` | OPNsense Kea subnet reference |
| `console_agent_url_base` | Base URL of your internal mirror of the installer |
| `console_agent_installer` | Installer file name, `NetApp_Console_Agent_Cloud_<version>` |
| `console_agent_sha256` | SHA-256 of the installer (`sha256sum <file>`). The VM refuses to run a download that does not match. |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `template_vmid` | `900` | Ubuntu 24.04 template VM ID |
| `template_node` | `pve1` | Node hosting the template |
| `cores` | `8` | vCPU count (unverified sizing, see below) |
| `memory` | `32768` | Memory in MiB (unverified sizing, see below) |
| `disk_size` | `180` | Disk GiB: 120 for `/opt` plus 40 for `/var`, plus the OS and headroom (the install script checks the free space) |
| `bridge` | `vmbr0` | Network bridge |
| `vlan_tag` | `10` | VLAN tag. Empty: untagged, e.g. on an SDN vnet |
| `mac_address` | `""` | VM MAC (empty = Proxmox auto-assigns) |
| `jumphost` | `""` | SSH jumphost (`user@host`); empty = direct SSH |
| `ssh_user` | `ansible` | SSH user on the VM |
| `docker_version` | `27.5.1` | Docker Engine version, supported range 23.0.6 to 28.0.0 |
| `console_agent_install_args` | `""` | Extra installer flags, e.g. `--proxy <url> --cacert <file>` |
| `extra_tags` | `[]` | Additional Proxmox tags |

`docker_version` is the upstream version only (`27.5.1`). The install script
looks up the matching `5:<version>-...` string in `apt-cache madison docker-ce`
and fails with a clear error if the version is not in Docker's apt repository.

## Verified and unconfirmed facts

Verified against the NetApp page above:

- The component is the **Console agent**; Ubuntu 24.04 LTS with Docker Engine
  23.0.6 to 28.0.0 is supported (RHEL 8/9 with Podman also, not used here).
- `/opt` needs 120 GiB (`/opt/application/netapp`); `/var` needs 40 GiB
  (`/var/lib/docker`).
- The installer comes from the NetApp Console UI or the NetApp Support Site. Use
  the "online" installer, `NetApp_Console_Agent_Cloud_<version>`, run as root
  after `chmod +x`, with optional `--proxy <url> --cacert <file>`.
- The install fails when `http_proxy`/`https_proxy` are set. The install script
  unsets them.

**Not confirmed, verify on a live install:**

- CPU and RAM. 8 cores and 32 GB are the defaults but are not verified; override
  `cores` and `memory` as needed.
- The idempotency markers (`/opt/application/netapp` present plus a running
  container). They live in one function, `console_agent_installed`, in
  `scripts/console-connector-install-remote.sh`.

## Prerequisites

- The `ubuntu-template` blueprint applied (template `ubuntu-2404-template`, VM ID `900`).
- The installer mirrored at `${console_agent_url_base}/${console_agent_installer}`.
  Download it from the NetApp Console or the NetApp Support Site and put it on an
  internal web server.
- SSH jumphost reachable from the InfraFoundry host, if `jumphost` is set.
- Outbound access from the VM, at least to `mysupport.netapp.com` and
  `signin.b2c.netapp.com`. The NetApp page lists the full set of endpoints;
  open them in the firewall or NAT in front of the VM. This README does not
  repeat the list.

## Automation Flow

```
infra apply --package console-connector
  +-- Terraform: clone the Ubuntu 24.04 template, resize disk
  +-- Terraform: cloud-init (ansible user, DHCP, qemu-agent, hostname)
  +-- Terraform: DHCP reservation on OPNsense
  +-- on_create: console-connector-post-terraform.sh
       +-- Phase 0: preflight (ssh-agent, SSH probe)
       +-- Phase 1: wait for SSH, then cloud-init
       +-- Phase 2: upload console-connector-install-remote.sh
       +-- Phase 3: run it on the VM
       |    +-- skip when the agent is already installed
       |    +-- unset proxy variables, check free space on /opt and /var
       |    +-- install Docker Engine at docker_version (Docker apt repo, noble)
       |    +-- download and run the installer
       +-- Phase 4: wait for https://<ip>, print the registration steps
```

The remote script runs on the VM (Ubuntu 24.04, `apt`), not on the jumphost; see
[blueprint script portability](../../docs/development/blueprint-script-portability.md).

## Manual steps

### Register the agent

1. Open `https://<ip_address>` in a browser.
2. Log in and choose your NetApp Console organization.
3. Name the system. Keep restricted mode disabled (unsupported on-premises).
4. Select *Let's start*.

### Add the ONTAP cluster

In the NetApp Console, add the on-premises ONTAP cluster through the registered
agent. This is manual; API-based discovery is a possible follow-up.

### Deregister before destroy

`infra destroy` removes the VM and the DHCP reservation only. Remove the agent
from the NetApp Console first, or its entry stays behind.

## Notes

- Default tags are `ontap` and `console-connector`; add more with `extra_tags`.
- Events live in `blueprint.yaml`, because the shorthand `vms:` format does not
  extract per-resource events.
