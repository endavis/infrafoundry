---
title: "AWS Provider"
description: "Manage EC2 instances, security groups and EBS volumes through the official hashicorp/aws Terraform provider"
audience:
  - users
tags:
  - providers
---

# AWS Provider

The AWS provider generates Terraform for the official `hashicorp/aws` provider. It manages EC2 instances, the security groups they use and EBS data volumes, and can adopt resources that already exist.

## Supported Resources

| Type | Terraform resources | Description |
|------|---------------------|-------------|
| `security_group` | `aws_security_group`, `aws_vpc_security_group_ingress_rule`, `aws_vpc_security_group_egress_rule` | Security group with one resource per rule |
| `instance` | `aws_instance`, `aws_ssm_parameter` (data) | EC2 instance with IMDSv2, an encrypted root volume, cloud-init and Tailscale |
| `ebs_volume` | `aws_ebs_volume`, `aws_volume_attachment` | Data volume and its attachment to an instance |

VPCs and subnets are referenced by ID; the provider does not create them.

## Prerequisites

Credentials are resolved by Terraform's AWS provider, not by InfraFoundry. Use any of the standard sources: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, a shared config profile, SSO, or an instance role. Install Terraform or OpenTofu (`foundry doctor` checks).

## Configuration

### Provider Settings

```yaml
name: prod

provider_settings:
  aws:
    region: "us-east-1"     # optional, falls back to AWS_REGION or the shared config
    profile: "default"      # optional, falls back to AWS_PROFILE
```

Only `region` and `profile` are accepted. `access_key`, `secret_key`, `token` and `session_token` are a validation error: keep credentials out of YAML.

With `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`, the `AWS_REGION` and `AWS_PROFILE` environment variables override the two settings.

### Resource Files

Create resource configs under `envs/{env}/aws/`:

```
envs/prod/aws/
├── security_groups.yaml
├── instances.yaml
└── volumes.yaml
```

## Resource Reference

### Security Group

```yaml
security_group:
  - name: web
    description: "Web tier"
    vpc_id: "vpc-0123456789abcdef0"
    ingress:
      - name: ssh
        description: "SSH from the admin network"
        ip_protocol: tcp
        from_port: 22
        to_port: 22
        cidr_ipv4: "192.0.2.0/24"
      - name: https-v6
        ip_protocol: tcp
        from_port: 443
        to_port: 443
        cidr_ipv6: "2001:db8::/32"
    tags:
      Role: web
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Group name; also the Terraform resource name |
| `vpc_id` | Yes | VPC the group belongs to |
| `description` | No | Default `Managed by InfraFoundry`; changing it replaces the group |
| `ingress` | No | List of rules |
| `egress` | No | List of rules. Omitted renders allow-all IPv4 and IPv6 rules; `[]` renders none |
| `tags` | No | Extra tags; `Name` is always set |

Each rule takes:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique within the group; letters, digits, `_` and `-` |
| `ip_protocol` | Yes | `tcp`, `udp`, `icmp`, `icmpv6`, `-1` (all) or a protocol number |
| `from_port`, `to_port` | tcp and udp | 0-65535 with `from_port <= to_port`; `-1` is allowed for ICMP |
| `cidr_ipv4` or `cidr_ipv6` | Exactly one | A CIDR with no host bits set, of the matching family |
| `description` | No | Rule description |
| `import_id` | No | Security group rule ID to adopt, for example `sgr-0123456789abcdef0` |

A group Terraform creates has no default egress rule, which is why an omitted `egress:` adds allow-all rules. Without them, cloud-init and Tailscale could not reach the network.

### Instance

```yaml
instance:
  - name: app
    ami_ssm_parameter: "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
    instance_type: t3.micro
    subnet_id: "subnet-0123456789abcdef0"
    security_groups:
      - web                          # a declared security_group
      - "sg-0123456789abcdef0"       # or a raw ID
    key_name: deploy
    root_volume_size: 30
    tags:
      Role: app
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Instance name; becomes the `Name` tag |
| `ami` or `ami_ssm_parameter` | Exactly one | A literal AMI ID, or an SSM parameter that holds one |
| `instance_type` | Yes | For example `t3.micro` |
| `subnet_id` | Yes | Subnet ID |
| `security_groups` | No | Declared group names or `sg-` IDs |
| `availability_zone` | No | Must match the zone of any volume attached by name |
| `key_name` | No | EC2 key pair name |
| `associate_public_ip_address` | No | Rendered when set |
| `ipv6_only`, `ipv6_address_count` | No | See [IPv6-only instances](#ipv6-only-instances) |
| `imdsv2_required` | No | Default `true`; `false` allows IMDSv1 |
| `root_volume_size`, `root_volume_type`, `root_volume_encrypted`, `kms_key_id` | No | Root volume; defaults to an encrypted `gp3` volume |
| `replace_on_ami_change` | No | With `ami_ssm_parameter` only. Default `false` |
| `user_data`, `user_data_replace_on_change` | No | See [Cloud-init and Tailscale](#cloud-init-and-tailscale) |
| `tags` | No | Extra tags |
| `import_id` | No | Instance ID to adopt |

With `ami_ssm_parameter`, the instance renders `lifecycle { ignore_changes = [ami] }`. Otherwise each new published image would replace the running instance on the next plan. Set `replace_on_ami_change: true` to opt out.

### EBS Volume

```yaml
ebs_volume:
  - name: data
    availability_zone: us-east-1a
    size: 20
    instance: app                    # or instance_id: "i-0123456789abcdef0"
    device_name: /dev/sdf
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Volume name |
| `availability_zone` | Yes | Never read from the instance, so replacing an instance does not replace the volume |
| `size` | Yes | Size in GiB |
| `instance` or `instance_id` | Exactly one | A declared instance, or a raw ID |
| `type` | No | `gp3` (default), `gp2`, `io1`, `io2`, `st1`, `sc1` or `standard` |
| `encrypted` | No | Default `true` |
| `iops`, `throughput`, `kms_key_id` | No | Rendered when set |
| `device_name` | No | Default `/dev/sdf`; `/dev/sd[f-p]` or `/dev/xvd[f-p]` |
| `prevent_destroy` | No | Default `true`; see [Data volume protection](#data-volume-protection) |
| `tags` | No | Extra tags |
| `import_id` | No | Volume ID to adopt |
| `attachment_import_id` | No | Attachment to adopt, `<device>:<volume-id>:<instance-id>`, for example `/dev/sdf:vol-0123456789abcdef0:i-0123456789abcdef0` |

## IPv6-only instances

`ipv6_only: true` renders:

- `ipv6_address_count` (default 1) and `associate_public_ip_address = false`
- `metadata_options { http_protocol_ipv6 = "enabled" }`, so the instance metadata service is reachable over IPv6
- `private_dns_name_options { hostname_type = "resource-name" }`, because IP-based hostnames need IPv4
- `enable_resource_name_dns_aaaa_record = true` in the same block, so the resource name resolves to the instance's IPv6 address

It conflicts with `associate_public_ip_address: true`. `ipv6_address_count` alone also works on a dual-stack subnet. The subnet must have an IPv6 CIDR.

## Cloud-init and Tailscale

An instance takes one of:

- `cloud_init_snippets`: snippet names merged into a `#cloud-config` document, rendered as `user_data`.
- `tailscale:` block: renders the Tailscale cloud-init module and passes its output as `user_data_base64`. The auth secret becomes a sensitive Terraform variable filled from the environment's secrets.
- `user_data`: a raw string.

`user_data_replace_on_change: true` replaces the instance when its user data changes; by default it does not.

## Adopting existing resources

Set `import_id` on a security group, instance or volume and `foundry infra plan` renders a Terraform `import {}` block for it. Rules and attachments are separate resources, so adopt them with a rule's `import_id` and a volume's `attachment_import_id`. Without them, adopting a group that already has rules would try to create duplicates.

- An adopted instance needs an `ami:` that matches its current image, or Terraform replaces it. An `ami_ssm_parameter` is safe because of `ignore_changes`.
- A volume still attached to an unmanaged instance must be detached before it can be attached to a new instance. This is the replace-the-instance flow: adopt the volume, remove the old instance, then apply.

## Data volume protection

`prevent_destroy` defaults to `true`. The volume renders `lifecycle { prevent_destroy = true }` and its attachment sets `stop_instance_before_detaching = true`. On `foundry infra destroy`, a protected volume is removed from Terraform state and left in AWS, and the attachment is destroyed so the volume is detached. Set `prevent_destroy: false` to have destroy delete the volume.

## Validation

`foundry infra doctor` and `foundry infra plan` check configuration only; no AWS API call is made. They reject credentials in settings, malformed or wrong-family CIDRs, a rule with both or neither CIDR, bad ports or protocols, duplicate rule names, unknown security group or instance references, a missing or doubled AMI source, mismatched availability zones, and bad device names. A missing region is a warning.

## Generated Files

```
generated/{env}/terraform/aws/
├── provider.tf
├── variables.tf
├── security_groups.tf
├── instances.tf
├── ebs_volumes.tf
└── outputs.tf
```

Outputs: `security_group_ids`, `instance_ids`, `instance_private_ips`, `instance_public_ips`, `instance_ipv6_addresses` and `ebs_volume_ids`, each keyed by resource name.

## Out of scope

VPCs, subnets and route tables, load balancers, IAM, Elastic IPs, Auto Scaling groups, and Ansible post-configuration. Credentials are never accepted in YAML.

See [ADR-0021](../decisions/0021-aws-provider-generates-hashicorpaws-terraform-with-credentials-from-the-standard-aws-chain.md).
