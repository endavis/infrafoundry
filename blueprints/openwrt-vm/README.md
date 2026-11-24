# openwrt-vm Blueprint

A disposable stock OpenWrt VM on Proxmox, for testing the OpenWrt provider
without a real router. It imports OpenWrt's x86-64 `generic-ext4-combined`
`.img.gz` image, boots it, and bootstraps it over the serial console so the box
comes up with key-only root SSH at a static management address.

## How it works

1. **VM (Proxmox provider, `disk_image_source`).** On the Proxmox host, the
   provider downloads the `.img.gz`, checks its sha256 (if `image_sha256` is
   set), decompresses it with `gunzip` into `image_cache_dir`, and imports it as
   the boot disk (IDE, serial socket). The VM has virtio NICs:
   - `eth0` (net0) is the LAN / management NIC on `mgmt_bridge` (tagged with
     `mgmt_vlan` when it is not 0);
   - `eth1` (net1) is the WAN NIC on `wan_bridge`; an empty `wan_bridge` means
     no WAN NIC.
2. **Bootstrap (`on_create` event).** `scripts/openwrt-post-terraform.sh` runs
   `openwrt-bootstrap.yml` against the Proxmox host. The role starts the VM with
   an expect script listening on its serial socket. The script:
   - reconnects while the serial socket refuses connections early in VM start;
   - presses Enter once when the console asks for it. Stock OpenWrt offers this
     shell early in boot, while the kernel still writes to the console, so the
     script waits until the console has been quiet for 5 seconds, presses Enter
     again for a fresh prompt (every 10 seconds until it shows, since an early
     keypress can be dropped), and waits (up to 120 seconds) until procd's
     `- init complete -` shows in `logread` before it changes anything. procd
     logs that line to syslog only, not to the console;
   - writes `ssh_public_key` (type and base64 only, the comment is dropped) to
     `/etc/dropbear/authorized_keys`. The serial console has no flow control
     and drops characters from a long line, so the key is sent in 64-character
     chunks and installed only when the file has the expected length;
   - installs the pinned ed25519 host key in dropbear's format (see
     [SSH host keys](#ssh-host-keys)), 16 bytes per console line with the log
     file closed, and checks it on the VM (`dropbearkey -y` must print the
     pinned public key) before it replaces the generated key;
   - sets dropbear's `keyfile` list to the pinned key only, so dropbear (`-r`)
     serves it alone; the RSA and ECDSA keys stay on disk, because the init
     script regenerates any missing key type on every start;
   - turns `PasswordAuth` and `RootPasswordAuth` off, so SSH is key-only (the
     root password stays unset);
   - sets the hostname to `vm_name` and the LAN address to
     `mgmt_ip`/`mgmt_netmask`, with `mgmt_gateway` and `mgmt_dns` when set;
   - unless `lan_dhcp` is true, turns off the LAN DHCP server, router
     advertisements, DHCPv6 and NDP proxying;
   - commits, restarts the services and reloads the network.

   Every console command is sent with an exit-code marker, and a non-zero code
   fails the run. The handler then waits until `mgmt_ip` port 22 sends an SSH
   banner, and connects with strict host key checking against the pinned
   public key only (no credential is used). A mismatch stops it at once and
   names the VM; it also fails if the VM still serves an RSA or ECDSA key.
3. **Manage it.** Point the OpenWrt provider at `mgmt_ip` with key-based root
   SSH. The provider needs `/usr/bin/ucode`, which stock 25.12 ships.
4. **Destroy.** `infra destroy` stops and purges the VM through the Proxmox
   provider's destroy step.

## First-boot window

Before the bootstrap runs, stock OpenWrt serves DHCP on its vendor default LAN
address 192.168.1.1/24 and sends IPv6 router advertisements on the management
bridge. Nothing can stop that without changing the image. Attach `mgmt_bridge`
to an isolated bridge or VLAN while the VM is created.

On an OpenWrt 23.05-based vendor build, the dnsmasq init script probes the
interface for another DHCP server and skips serving when one answers, unless the
DHCP section sets `force`. This was not checked on stock 25.12, so do not rely
on it.

## Secrets

The SSH public key is a normal input, and the root password stays unset. The
pinned host key lives in the package's SOPS `secrets.yaml` under
`variables.ssh_host_keys.<vm_name>`. Run `foundry secrets host-keys --env <env>`
before the first apply: `infra plan` fails until it has run, like the other VM
blueprints (a breaking change for existing `openwrt-vm` packages). A deployed VM
is pinned: the key it presents is recorded and the VM is not changed. To rebuild
it, destroy it, run `foundry secrets host-keys --env <env> --regenerate
<vm_name>`, then apply.

## SSH host keys

The VM opts in with `ssh_host_key: {address: <mgmt_ip>, format: dropbear}`
([ADR-0032](../../docs/decisions/0032-blueprint-vms-get-pre-generated-ssh-host-keys-that-scripts-pin.md)).
There is no cloud-init, so the bootstrap installs the key over the serial
console. The framework converts it to dropbear's format and passes it to the
bootstrap as the package variable `ssh_host_keys_dropbear`; the public key
reaches the script as `ssh_known_hosts`.

- The bootstrap limits dropbear to the pinned key through its `keyfile` list,
  and the post-apply script fails if the VM still serves an RSA or ECDSA key.
  The pin covers ed25519 only, so a client that took another key on first use
  would bypass it. Deleting the other keys does not work: OpenWrt's dropbear
  init script regenerates every missing key type when it starts.
- Record the pinned key (`ssh_known_hosts`) in the `known_hosts` of the machine
  that runs the OpenWrt provider, which checks host keys strictly (ADR-0033). A
  rebuilt VM presents the same pinned key.

## Usage

Copy `example-config/envs/dev/proxmox/openwrt-test/` and edit the values:

```yaml
name: openwrt-test
blueprint: openwrt-vm
variables:
  vm_name: openwrt-test
  vmid: 952
  target_node: pve-node1
  pve_host: "192.0.2.13"
  ssh_public_key: "ssh-ed25519 AAAA... example-key"
  mgmt_ip: "192.0.2.242"
  mgmt_gateway: "192.0.2.1"
```

```bash
foundry infra apply --env dev --package openwrt-test
```

## Variables

See `blueprint.yaml`. Required: `vm_name`, `vmid`, `target_node`, `pve_host`,
`ssh_public_key`, `mgmt_ip`. `mgmt_ip` is required because an empty value would
keep the vendor default address and its DHCP server. Everything else has a
default: `image_source` (OpenWrt 25.12.6 `.img.gz`), `image_sha256`, `memory`
256, `cores` 1, `mgmt_bridge` `vmbr0`, `mgmt_vlan` 0, `mgmt_netmask`
`255.255.255.0`, `mgmt_gateway` and `mgmt_dns` empty, `lan_dhcp` false,
`wan_bridge` `vmbr1`, `boot_timeout` 300.

## Live verification

Verified with OpenWrt 25.12.6 (x86-64 ext4 combined image) on Proxmox VE:

- the `.img.gz` imports and the IDE disk boots;
- net0 is `eth0` (LAN, `br-lan`) and net1 is `eth1` (WAN);
- the bootstrap reaches the shell, waits for `- init complete -`, installs a
  4096-bit RSA key and finishes; `infra apply` then sees the SSH banner;
- root SSH works with the key, and password login is refused
  (`Permission denied (publickey)`);
- the LAN address is set, and the LAN DHCP server, RA, DHCPv6 and NDP proxy are
  off.

Not live-verified yet: the full bootstrap with the host key install over the
console. Checked by hand on a 25.12 VM: the 83-byte dropbear key built by the
framework loads with `dropbearkey -y`, and a dropbear started with `-r` and only
the ed25519 key serves no RSA or ECDSA key. The bootstrap and the post-apply
script fail if either does not hold on a real run.

Three faults surfaced on the way and are handled by the script:

- the serial socket refused the first connection;
- the early-boot shell;
- characters dropped from a long console line.

## Secrets in logs

The expect script runs with `log_user 0`, so console output never reaches the
Ansible output either; its log file is
`/tmp/openwrt-bootstrap-<vmid>-<time>.log` on the Proxmox host. The host key
lines are not logged: the log file is closed while they are sent, and no error
message names them. The rendered expect script holds the key, so the role
removes it, the wrapper and the output file in an `always:` step; the tasks that
hold the key use `no_log`. The key is also in `INFRAFOUNDRY_VAR_ssh_host_keys_dropbear`
of this package's script environment (and in the JSON on stdin to a jumphost),
and never in Terraform state.
