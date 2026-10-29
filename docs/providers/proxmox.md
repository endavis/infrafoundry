---
title: "Proxmox Provider"
description: "Manage Proxmox VMs, containers, templates, networks and storage with bpg/proxmox"
audience:
  - users
tags:
  - providers
---

# Proxmox Provider

The Proxmox provider manages virtual machines, containers, templates,
networks, and storage on a Proxmox Virtual Environment (PVE) cluster via
the `bpg/proxmox` Terraform provider.

## Supported Resources

| Type | Description |
|------|-------------|
| `vm` | QEMU VM (from template clone, cloud-init image download, OVA import, or raw disk image import) |
| `container` | LXC container with network and mount-point support |
| `template` | VM template from a remote image or clone source |
| `network` | Linux bridge or VLAN-aware bridge on a node |
| `storage` | NFS, CIFS, or directory-backed storage pool |
| `trigger` | Lightweight `terraform_data` marker for script-only packages |
| `sdn_zone` | Cluster-wide SDN zone (VXLAN) |
| `sdn_vnet` | SDN vnet in a zone; VMs and containers attach to it as a bridge |

## Prerequisites

### API token

Create a PVE API token in the Proxmox web UI
(`Datacenter → Permissions → API Tokens`) with the privileges your
configuration needs (typically `PVEVMAdmin`, `PVEDatastoreAdmin`, and
`PVESysAdmin` for a full `apply`).

A token has two forms:

- Split form: `USER@REALM!TOKENID` + separate secret (the form the
  Terraform provider uses).
- Joined form: `USER@REALM!TOKENID=SECRET` (a single string).

Either is supported by the provider settings.

## Configuration

### Provider settings

Add Proxmox credentials to your environment's `settings.yaml`:

```yaml
name: prod

provider_settings:
  proxmox:
    api_url: "https://pve.example.com:8006/api2/json"

    # Option A: split token
    api_token_id: "terraform@pve!tf"
    api_token_secret: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

    # Option B: joined token (alternative to the pair above)
    # api_token: "terraform@pve!tf=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

    verify_ssl: true       # set to false for homelabs with self-signed certs
    timeout: 30            # seconds for the exporter; dumper uses --timeout
    node: "pve1"           # optional default node for exports/migrations
```

!!! warning "Encrypt with SOPS"
    In production, encrypt your settings file so the token never lands
    in git in plaintext:

    ```bash
    sops --encrypt --in-place envs/prod/settings.yaml
    ```

### Resource files

Create resource configs under `envs/{env}/proxmox/`:

```
envs/prod/proxmox/
├── networks.yaml
├── storage.yaml
├── templates.yaml
├── vms.yaml
└── containers.yaml
```

### VMs from an appliance disk image

A VM with `ova_source` or `disk_image_source` is built over SSH on its
`target_node` with `qm` commands rather than by cloning. Use it for appliances
that ship as a disk, not as a cloud image. Such VMs skip cloud-init.

- **`ova_source`** is a path on the Proxmox host to an `.ova`. Its VMDKs are
  extracted and imported in order.
- **`disk_image_source`** is a raw disk image (`.img`, or `.img.bz2`). It is
  either an absolute path on the Proxmox host or an `http(s)` URL.
  - A URL is downloaded into `disk_image_cache_dir` (default
    `/var/lib/vz/template/cache/infrafoundry`).
  - A `.bz2` is decompressed there.
  - Both results are cached, so later runs reuse them.
  - If `disk_image_sha256` is set, the downloaded or given file is checked
    against it before use.
  - The image is imported as the only disk.

The two are mutually exclusive.

```yaml
vms:
  - name: opnsense-test
    target_node: pve3
    vmid: 950
    disk_image_source: "https://pkg.opnsense.org/releases/26.1/OPNsense-26.1.6-nano-amd64.img.bz2"
    disk_image_sha256: "<sha256 of the .img.bz2>"
    disk_bus: ide
    disk_storage: local-lvm
    serial: true
    network:
      - { bridge: vmbr1, model: e1000 }
      - { bridge: vmbr0, model: e1000, tag: 10 }
```

The `opnsense-vm` blueprint (`blueprints/opnsense-vm/`) uses this to build a
disposable OPNsense test firewall.

### Memory ballooning

VMs and templates take an optional `balloon` key, the minimum memory in MiB
that Proxmox may shrink the guest to (the bpg `memory.floating` attribute).

- **Unset**: the balloon device stays on with a minimum equal to `memory`
  (default 2048). The guest reports free pages to the host but is never shrunk.
- **`0`**: no balloon device.
- **A value below `memory`**: Proxmox may shrink the VM to that minimum under
  host memory pressure.

```yaml
vms:
  - name: app-01
    target_node: pve1
    memory: 14336
    balloon: 8192   # may shrink to 8 GiB; omit for no shrinking, 0 for no device
```

!!! warning "Behavior change for existing VMs"
    Before, a VM without `balloon` rendered no `floating` value. Now it renders
    `floating = <memory>`. An existing VM created without `balloon` shows an
    in-place update `floating 0 -> <memory>` at its next apply, and the bpg
    provider reboots the VM to apply it (`reboot_after_update`). Set
    `balloon: 0` on such a VM to keep the old behavior and avoid the reboot.

### SDN zones and vnets

An SDN vnet is a network shared by every node in its zone, so VMs on different
nodes can share an isolated layer-2 segment. A VXLAN zone tunnels it over the
nodes' existing network; no switch configuration is needed. The SDN packages
(`libpve-network-perl`, `ifupdown2`) must be installed on the nodes.

```yaml
sdn_zones:
  - name: nettest
    config:
      kind: vxlan            # the only kind supported so far
      peers: ["192.168.10.100", "192.168.10.101", "192.168.10.102"]
      mtu: 8950              # optional; VXLAN adds ~50 bytes, keep it below the underlay MTU
      # nodes: [pve1, pve3]  # optional; default is every node
sdn_vnets:
  - name: ntlan
    config:
      zone: nettest          # an sdn_zone, by name or id
      tag: 9900              # the VXLAN network identifier (VNI), unique per vnet
      alias: "NetApp test LAN"
```

A VM or container attaches by using the vnet as its bridge
(`network: [{ bridge: ntlan }]`), with no VLAN tag.

- **IDs.** The Proxmox ID is `config.id`, else the resource name. It must be 1–8
  lowercase letters or digits, starting with a letter.
- **Applying.** Proxmox stages SDN changes until they are applied cluster-wide.
  InfraFoundry renders two `proxmox_sdn_applier` resources: one applies after any
  zone or vnet is created or changed, the other applies the deletions after a
  destroy.
- **Ordering.** VMs and containers attached to a managed vnet depend on it, so the
  vnet is live before they are created and is removed only after they are
  destroyed.
- **Doctor.** `infra doctor` accepts a vnet as a VM's bridge once it is in the
  cluster's running SDN config. A vnet declared in the validated resources but
  not applied yet is a warning, since the apply creates it first.

## Provider CLI

The Proxmox provider ships two CLI subcommands under the top-level
`foundry provider` group.

### `foundry provider proxmox dump`

Capture a raw JSON snapshot of the cluster's API state. Intended for
cluster audit, drift debugging, and post-incident forensics — **not**
for generating InfraFoundry YAML (use `export` for that).

```bash
foundry provider proxmox dump --env prod --output pve-state.json
foundry provider proxmox dump --env prod --output pve-state.json --timeout 60
```

**Options:**

| Option | Description |
|--------|-------------|
| `-e`/`--env TEXT` | Environment name (required). |
| `-o`/`--output PATH` | Output JSON file (required). |
| `--timeout INT` | Per-request timeout in seconds (default: 20). |

**Behaviour:**

- Walks a curated endpoint list: cluster status/options/HA/firewall,
  access users/groups/roles, pools, storage (including per-storage
  detail), every node (`status`, `network`, `storage`, `disks/*`,
  `firewall/*`, `qemu`, `lxc`, `apt/versions`, `services`,
  `subscription`, ...), and the `config` + `pending` endpoints for each
  QEMU VM, plus `config` for each LXC container.
- Unwraps the PVE `{"data": ...}` envelope — stored payloads are the
  inner `data` values.
- Saves incrementally and atomically after each section. An
  interrupted dump leaves the JSON on disk valid, containing whatever
  completed before the interrupt.
- Per-call failures are captured inline instead of aborting the dump:
  `{"__timeout__": true, "path": "..."}` for timeouts,
  `{"__error__": "...", "path": "..."}` for other API errors.

### `foundry provider proxmox export`

Extract existing cluster resources (VMs, bridge networks, storage
backends) into InfraFoundry YAML. Useful when adopting an existing
cluster.

```bash
foundry provider proxmox export --env prod --output ./exported
foundry provider proxmox export --env prod --output ./exported --node pve01
foundry provider proxmox export --env prod --output ./exported --resource-type vm
```

**Options:**

| Option | Description |
|--------|-------------|
| `-e`/`--env TEXT` | Environment name (required). |
| `-o`/`--output DIR` | Output directory (created if missing, required). |
| `--node TEXT` | Export only from this node. |
| `--resource-type {vm,network,storage}` | Export only this resource type. |

**Output:** one YAML file per node per resource type
(`<node>-vms.yaml`, `<node>-networks.yaml`) plus a single
`storage.yaml` for cluster-wide storage.

!!! note "Dump vs Export"
    - **Dump** is lossless and captures everything the PVE API exposes
      (even settings InfraFoundry doesn't model). Use it for audit.
    - **Export** is opinionated: it produces InfraFoundry YAML you can
      place under `envs/{env}/proxmox/` and drive through `infra plan`
      / `infra apply`. Use it for migration.

## Related

- ADR: [0005-provider-cli-extensibility](../decisions/0005-provider-cli-extensibility.md)
- CLI reference: [foundry provider proxmox ...](../usage/cli-reference.md)
