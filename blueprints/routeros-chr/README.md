# routeros-chr Blueprint

A disposable MikroTik RouterOS Cloud Hosted Router (CHR) on Proxmox, for
testing the MikroTik provider without a real switch. It imports MikroTik's
`.img.zip` image, boots it, and bootstraps it over the serial console so the
box comes up with an admin password, an optional static management address and
the REST service enabled.

## How it works

1. **VM (Proxmox provider, `disk_image_source`).** On the Proxmox host, the
   provider downloads the `.img.zip`, checks its sha256 (if `image_sha256` is
   set), extracts the single `.img` member into `image_cache_dir` with python3
   (no `unzip` needed), and imports it as the boot disk (IDE, serial socket).
   The VM has virtio NICs:
   - `ether1` is the management NIC on `mgmt_bridge` (tagged with `mgmt_vlan`
     when it is not 0);
   - `ether2`.. are `trunk_nics` trunk NICs (default 2) on `trunk_bridge`,
     untagged.
2. **Bootstrap (`on_create` event).** `scripts/routeros-post-terraform.sh`
   runs `routeros-bootstrap.yml` against the Proxmox host. The role starts the
   VM with an expect script listening on its serial socket. The script:
   - logs in as `admin+ct` with an empty password (the `+ct` suffix turns off
     colours and terminal detection);
   - declines the licence prompt if it appears;
   - answers the forced password change with `routeros_admin_password`, passed
     through the expect process's environment, never written to the host, with
     logging off while it is sent;
   - sets `/system identity` to `vm_name`;
   - with `mgmt_ip` set, replaces the DHCP client on `ether1` with
     `mgmt_ip`/`mgmt_prefix`, plus a default route via `mgmt_gateway` and
     `/ip dns set servers=` from `mgmt_dns` (a comma-separated list sets several),
     each only when set;
   - runs `/ip service set www disabled=no` (plain HTTP; `www-ssl` needs a
     certificate on the box).

   No reboot is needed. With `mgmt_ip` set, the handler then waits until
   `http://<mgmt_ip>/rest/system/resource` answers 401 to a request with no
   credentials. With DHCP (`mgmt_ip` empty) the address is not known, so the
   probe is skipped.
3. **Manage it.** Point the environment's `mikrotik` provider settings at
   `http://<mgmt_ip>` with `username: admin` and the same password. `infra
   doctor` warns about plaintext HTTP; that is expected here.
4. **Destroy.** `infra destroy` stops and purges the VM through the Proxmox
   provider's destroy step. No extra code is involved.

CHR's free licence caps throughput (MikroTik's documented behaviour), which is
enough for API testing.

## Secrets

In the package's `secrets.yaml` (`variables:`):

| Key | Purpose |
| :--- | :--- |
| `routeros_admin_password` | password set on the `admin` user |

## Usage

Copy `example-config/envs/dev/proxmox/chr-test/` and edit the values:

```yaml
name: chr-test
blueprint: routeros-chr
variables:
  vm_name: chr-test
  vmid: 951
  target_node: pve-node1
  pve_host: "192.0.2.13"
  mgmt_ip: "192.0.2.241"
  mgmt_gateway: "192.0.2.1"
  mgmt_dns: "192.0.2.53"
```

```bash
foundry infra apply --env dev --package chr-test
```

## Variables

See `blueprint.yaml`. Required: `vm_name`, `vmid`, `target_node`, `pve_host`.
Everything else has a default: `image_source` (CHR 7.25.1 `.img.zip`),
`image_sha256`, `memory` 512, `cores` 1, `mgmt_bridge` `vmbr0`, `mgmt_vlan` 0,
`mgmt_ip` empty, `mgmt_prefix` 24, `mgmt_gateway` empty, `mgmt_dns` empty (needs `mgmt_ip`), `trunk_bridge`
`vmbr1`, `trunk_nics` 2, `boot_timeout` 300.

## Verified on a live CHR

Checked against RouterOS 7.25.1 CHR on Proxmox VE 9 (#1485):

- The image imports from `.img.zip` and boots from the IDE disk.
- The serial console prints `CHR Login:`. `admin+ct` with an empty password logs in.
- RouterOS asks `Do you want to see the software license? [Y/n]`; the script answers `n`.
- The forced password change prompts `new password>` and then
  `repeat new password>`. RouterOS draws the `new password>` line twice before
  it reads input, so the script answers each prompt once only. Answering it
  twice types the password at the shell prompt, where it is echoed.
- After `Password changed`, the prompt shows as ` > ` after a cursor-move
  escape sequence, not as `[admin@identity] > `.
- With `trunk_nics: 2` the box has `ether1`..`ether3`. The static address goes
  on `ether1`, and REST answers 401 without credentials and 200 with them.
- `infra destroy` removes the VM.
- With `mgmt_dns` set (#1666), `/ip dns` lists that server after the bootstrap
  and the RouterOS update check resolves the vendor's server (checked with a
  single server, #1665).

Not checked: whether `ether1` has a DHCP client before the bootstrap removes
it (`remove [find ...]` succeeds either way), and which NIC maps to which
`etherN` beyond the count.

## Secrets in logs

The expect script runs with `log_user 0`, so console output never reaches the
Ansible output, and it scrubs the password from its log file
(`/tmp/routeros-bootstrap-<vmid>-<time>.log` on the Proxmox host) before it exits.
