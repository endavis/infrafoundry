---
title: "OCI Provider"
description: "Manage Oracle Cloud Infrastructure networking and compute"
audience:
  - users
tags:
  - providers
---

# OCI Provider

The OCI (Oracle Cloud Infrastructure) provider manages networking and compute resources in Oracle Cloud.

## Supported Resources

| Type | Description |
|------|-------------|
| `compartment` | Compartment (`oci_identity_compartment`), optionally nested under another |
| `vcn` | Virtual Cloud Network with optional internet gateway and security list |
| `subnet` | Public or private subnet within a VCN |
| `instance` | Compute instance with flex shapes and cloud-init support |

## Prerequisites

### OCI API Key

Generate an API signing key and upload the public key to OCI Console:

```bash
mkdir -p ~/.oci
openssl genrsa -out ~/.oci/oci_api_key.pem 2048
chmod 600 ~/.oci/oci_api_key.pem
openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem
```

Upload `~/.oci/oci_api_key_public.pem` in **OCI Console > Identity > Users > API Keys**.

### Required OCIDs

Collect these from the OCI Console:

- **Tenancy OCID**: Identity > Compartments (root compartment)
- **User OCID**: Identity > Users > your user
- **Compartment OCID** (optional when every resource sets `compartment`): Identity > Compartments > target compartment
- **Fingerprint**: Shown after uploading the API key

## Configuration

### Provider Settings

Add OCI credentials to your environment's `settings.yaml`:

```yaml
name: prod

provider_settings:
  oci:
    tenancy_ocid: "ocid1.tenancy.oc1..aaaaaa..."
    user_ocid: "ocid1.user.oc1..aaaaaa..."
    fingerprint: "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
    private_key_path: "~/.oci/oci_api_key.pem"
    region: "us-phoenix-1"
    compartment_ocid: "ocid1.compartment.oc1..aaaaaa..."
```

!!! warning "Encrypt with SOPS"
    In production, encrypt your settings file:
    ```bash
    sops --encrypt --in-place envs/prod/settings.yaml
    ```

### Resource Files

Create resource configs under `envs/{env}/oci/`:

```
envs/prod/oci/
├── network.yaml      # VCNs and subnets
└── instances.yaml    # Compute instances
```

## Resource Reference

### Compartment

```yaml
compartment:
  - name: workload-comp
    description: "Compartment for the workload"
    parent: ocid1.compartment.oc1..aaaaaaaexample   # optional: OCID or compartment name
    enable_delete: false                            # optional
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Compartment name |
| `description` | Yes | Compartment description |
| `parent` | No | A compartment resource name or an OCID (default: the tenancy, `oci_tenancy_ocid`) |
| `enable_delete` | No | Let `terraform destroy` delete the compartment (default: `false`) |

VCNs, subnets and instances take an optional `compartment` field: a compartment resource
name or an OCID. Without it, a resource uses `compartment_ocid` from the provider settings.
A subnet does not inherit its VCN's compartment, so set the field on each resource.

!!! warning "Home region"
    OCI creates compartments only in the tenancy home region. Set `region` in the provider
    settings to the home region when the environment has `compartment` resources.
    `foundry infra doctor` reports an error otherwise.

### VCN

```yaml
vcn:
  - name: my-vcn
    cidr_block: "192.0.2.0/24"
    dns_label: "myvcn"              # optional, max 15 chars
    internet_gateway: true           # creates IGW + public route table
    security_list:                   # optional
      egress_rules:
        - destination: "0.0.0.0/0"
          protocol: "all"
      ingress_rules:
        - source: "0.0.0.0/0"
          protocol: "6"             # TCP
          tcp_options:
            min: 22
            max: 22
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | VCN display name (used as Terraform resource ID) |
| `cidr_block` | Yes | VCN CIDR block |
| `compartment` | No | Compartment name or OCID (default: `compartment_ocid`) |
| `dns_label` | No | DNS label for the VCN (max 15 alphanumeric chars) |
| `internet_gateway` | No | Create an internet gateway and public route table |
| `security_list` | No | Security list with ingress/egress rules |

A subnet that sets no `security_list_id` is attached to its VCN's `security_list` when the VCN
declares one; otherwise it uses the OCI default security list. An explicit `security_list_id` on
the subnet takes precedence.

### Subnet

```yaml
subnet:
  - name: public-subnet
    vcn: my-vcn                     # references a VCN by name
    cidr_block: "192.0.2.0/25"
    dns_label: "public"
    public: true                    # allow public IPs
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Subnet display name |
| `vcn` | Yes | Name of the VCN this subnet belongs to |
| `cidr_block` | Yes | Subnet CIDR block (must be within VCN CIDR) |
| `dns_label` | No | DNS label for the subnet |
| `public` | No | If `true`, allows public IP assignment (default: `false`) |
| `compartment` | No | Compartment name or OCID (default: `compartment_ocid`) |

### Instance

```yaml
instance:
  - name: my-server
    shape: "VM.Standard.A1.Flex"
    shape_config:
      ocpus: 2
      memory_in_gbs: 12
    subnet: public-subnet           # references a subnet by name
    image: "ocid1.image.oc1.iad..."
    ssh_authorized_keys:
      - "ssh-rsa AAAA..."
    boot_volume_size_in_gbs: 50
    public_ip: true
    availability_domain: "Uocm:US-ASHBURN-AD-1"  # optional, defaults to first AD
    freeform_tags:
      env: prod
      role: web
    cloud_init_snippets:
      - base-packages
      - tailscale
    cloud_init_vars:
      tailscale_key: "tskey-auth-..."
    ansible_roles:
      - common
      - docker
    ssh_user: ubuntu                # for Ansible inventory
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Instance display name |
| `compartment` | No | Compartment name or OCID (default: `compartment_ocid`) |
| `shape` | Yes | Compute shape (e.g., `VM.Standard.A1.Flex`, `VM.Standard.E4.Flex`) |
| `shape_config` | No | Required for Flex shapes: `ocpus` and `memory_in_gbs` |
| `subnet` | Yes | Name of the subnet to attach to |
| `image` | Yes | Image OCID for the boot volume |
| `ssh_authorized_keys` | No | List of SSH public keys |
| `boot_volume_size_in_gbs` | No | Boot volume size (default: image default, usually 50 GB) |
| `public_ip` | No | Assign public IP (default: `true`) |
| `availability_domain` | No | AD name (defaults to first AD in region) |
| `freeform_tags` | No | Key-value tags for the instance |
| `cloud_init_snippets` | No | List of cloud-init snippet names to merge |
| `cloud_init_vars` | No | Variables to substitute in cloud-init snippets |
| `ansible_roles` | No | Ansible roles for post-provisioning |
| `ansible_vars` | No | Extra variables for Ansible inventory |
| `ssh_user` | No | SSH user for Ansible (default: `ubuntu`) |

## Cloud-Init Snippets

Place snippet files in your config repo at:

```
envs/{env}/files/cloud-init-snippets/{name}.yaml
```

Example snippet (`base-packages.yaml`):

```yaml
packages:
  - curl
  - wget
  - jq
  - unzip

runcmd:
  - apt-get update
  - apt-get upgrade -y
```

Snippets are deep-merged in order. Variables use `${var_name}` syntax and are substituted from `cloud_init_vars`.

## Validation

The OCI provider validates:

- **Connectivity**: API access using signed requests (requires `cryptography` package)
- **References**: Subnet-to-VCN and instance-to-subnet cross-references
- **Subnet CIDRs**: each subnet `cidr_block` lies inside the `cidr_block` of the VCN it
  references, and no two subnets of one VCN overlap (offline ERROR; a missing or unparsable CIDR
  is skipped)
- **Compartments**: each compartment has a description, a known parent and no parent cycle;
  every `compartment` reference is an OCID or a defined compartment; a resource with no
  `compartment` needs `compartment_ocid` in the provider settings; the region is the
  tenancy home region when compartments are managed

```bash
foundry infra doctor --env prod
```

## Usage

```bash
# Generate Terraform files
foundry infra plan --env prod

# Validate configuration and API connectivity
foundry infra doctor --env prod

# Apply infrastructure
foundry infra apply --env prod

# Destroy infrastructure
foundry infra destroy --env prod
```

## Generated Files

After `foundry infra plan`, the generated directory contains:

```
generated/prod/terraform/oci/
├── provider.tf          # OCI provider configuration
├── variables.tf         # Input variables (values passed via TF_VAR_* env vars)
├── compartments.tf     # Compartments (only when compartment resources exist)
├── vcn.tf              # VCN, subnet, IGW, route table, security list
├── instances.tf        # Compute instances with metadata
└── outputs.tf          # VCN IDs, subnet IDs, instance IPs

generated/prod/ansible/oci/
├── playbook.yml        # Post-provisioning playbook
└── inventory.yml       # Dynamic inventory from Terraform outputs
```

## Common Shapes

| Shape | Architecture | Free Tier |
|-------|-------------|-----------|
| `VM.Standard.A1.Flex` | ARM (Ampere) | 4 OCPUs / 24 GB total |
| `VM.Standard.E4.Flex` | AMD | No |
| `VM.Standard.E5.Flex` | AMD | No |
| `VM.Standard3.Flex` | Intel | No |

## Dependencies

Resources are created in dependency order:

```
compartment → vcn → subnet → instance
```

Terraform orders these by the references in the generated files: a resource that names a
compartment is created after it. `infra analyze` does not yet show the compartment edge.

Subnets depend on VCNs, and instances depend on subnets.
