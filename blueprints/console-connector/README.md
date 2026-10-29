# NetApp Console agent (console-connector) Blueprint

Reusable blueprint that deploys the NetApp Console agent (formerly the BlueXP
Connector) on an Ubuntu 24.04 Proxmox VM, with an OPNsense DHCP reservation and
an `on_create` handler that installs Docker Engine and the agent.

**Scope is install plus optional registration.** Registering the agent can be
scripted (see [Scripted registration](#scripted-registration)); without the
service account inputs it is a manual browser step. Adding the ONTAP cluster and
deregistering the agent are manual steps documented below.

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
  console_agent_installer: "netapp-console-agent-<version>"
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
| `console_agent_installer` | Installer file name, `netapp-console-agent-<version>` |
| `console_agent_sha256` | SHA-256 of the installer (`sha256sum <file>`). The VM refuses to run a download that does not match. |

### Optional (blueprint defaults)

| Variable | Default | Description |
|---|---|---|
| `template_vmid` | `900` | Ubuntu 24.04 template VM ID |
| `template_node` | `pve1` | Node hosting the template |
| `cores` | `8` | vCPU count (unverified sizing, see below) |
| `memory` | `32768` | Memory in MiB (unverified sizing, see below) |
| `balloon` | `0` | Minimum memory in MiB with ballooning on; `0` turns it off (see below) |
| `disk_size` | `180` | Disk GiB: 120 for `/opt` plus 40 for `/var`, plus the OS and headroom (the install script checks the free space) |
| `bridge` | `vmbr0` | Network bridge |
| `vlan_tag` | `10` | VLAN tag. Empty: untagged, e.g. on an SDN vnet |
| `mac_address` | `""` | VM MAC (empty = Proxmox auto-assigns) |
| `jumphost` | `""` | SSH jumphost (`user@host`); empty = direct SSH |
| `ssh_user` | `ansible` | SSH user on the VM |
| `docker_version` | `27.5.1` | Docker Engine version, supported range 23.0.6 to 28.0.0 |
| `console_agent_install_args` | `""` | Extra installer flags, e.g. `--proxy <url> --cacert <file>` |
| `console_client_id` | `""` | Service account client ID; enables scripted registration |
| `console_client_secret` | `""` | Service account secret; put it in `secrets.yaml` (SOPS) |
| `console_admin_email` | `""` | Email of the Console user that administers the agent |
| `console_account_id` | `""` | Console organization ID; empty: the only account the service account sees |
| `console_company` | `""` | Company name sent at registration; empty: `vm_name` |
| `console_site` | `default` | Site name sent at registration |
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
  the "online" installer, `netapp-console-agent-<version>`, run as root
  after `chmod +x`, with optional `--proxy <url> --cacert <file>`.
- The install fails when `http_proxy`/`https_proxy` are set. The install script
  unsets them.

**Not confirmed, verify on a live install:**

- CPU and RAM. 8 cores and 32 GB are the defaults but are not verified; override
  `cores` and `memory` as needed. The installer refuses to run below 13,312 MiB
  of guest MemTotal, so `memory` must be at least 14336.
- Ballooning. Without it the guest fills its memory with page cache that the
  host cannot reclaim; a 14 GiB agent using about 2.5 GB was killed by the
  host's out-of-memory killer on a full node. Set `balloon` (for example 8192)
  to let the host take memory back under pressure. The guest still sees the full
  `memory` at install, so the installer's check is unaffected.
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
       +-- Phase 4: wait for https://<ip>
       +-- Phase 5: register the agent (console-connector-register.py), or
                    print the manual registration steps
```

The remote script runs on the VM (Ubuntu 24.04, `apt`), not on the jumphost; see
[blueprint script portability](../../docs/development/blueprint-script-portability.md).

## Scripted registration

Set `console_client_id`, `console_client_secret` and `console_admin_email` to
register the agent during `infra apply`. Set none of them to keep the manual
flow; setting only some fails with the missing names.

1. In the NetApp Console, create a service account with an admin role (for
   example Organization admin) and copy its client ID and secret.
2. Put `console_client_secret` (and `console_client_id`) under `variables:` in
   the package `secrets.yaml`, encrypted with SOPS.
3. Set `console_admin_email` in `infrafoundry.yml`. Set `console_account_id` when
   the service account sees more than one organization; otherwise registration
   fails and lists the choices.

The helper `scripts/console-connector-register.py` (stdlib only) runs on the
InfraFoundry host, as the Phase 4 check does, even when a jumphost is set. That
host must reach `netapp-cloud-account.auth0.com`,
`api.bluexp.netapp.com` and the agent over HTTPS. It is idempotent: an agent
that already reports `isSetup` is left alone and no token is requested. Every
request to the agent, including the status checks, is certificate-pinned: Phase 5
reads the agent's certificate over SSH (`openssl` on the VM) and the helper trusts
exactly that certificate. The NetApp endpoints use normal verification. The
secret is read from the environment, never passed on a command line or printed. A `User is not associated as admin` error
means the service account lacks an admin role.

## Manual steps

### Register the agent (without a service account)

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
