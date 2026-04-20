# Proxmox Provider

The Proxmox provider manages virtual machines, containers, templates,
networks, and storage on a Proxmox Virtual Environment (PVE) cluster via
the `bpg/proxmox` Terraform provider.

## Supported Resources

| Type | Description |
|------|-------------|
| `vm` | QEMU VM (from template clone, cloud-init image download, or OVA import) |
| `container` | LXC container with network and mount-point support |
| `template` | VM template from a remote image or clone source |
| `network` | Linux bridge or VLAN-aware bridge on a node |
| `storage` | NFS, CIFS, or directory-backed storage pool |
| `trigger` | Lightweight `terraform_data` marker for script-only packages |

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
