---
title: "ADR-0021: AWS provider generates hashicorp/aws Terraform with credentials from the standard AWS chain"
description: The aws provider wraps the official hashicorp/aws Terraform provider for security groups, EC2 instances and EBS volumes, takes only region and profile from settings, and protects data volumes from destroy
date: 2026-11-16
audience:
  - contributors
tags:
  - adr
---

# ADR-0021: AWS provider generates hashicorp/aws Terraform with credentials from the standard AWS chain

## Status
Accepted

## Context
InfraFoundry has no provider for AWS. Issue #1397 asks for one that manages EC2 instances, the security groups they use and EBS data volumes, including adopting resources that already exist. The official `hashicorp/aws` Terraform provider covers all of it, and boto3 is not a project dependency.

## Decision
Add an `aws` provider that generates Terraform for `hashicorp/aws` instead of writing an API client.

- **Resources:** `security_group`, `instance` and `ebs_volume`. VPCs and subnets are referenced by ID only; the provider does not create them.
- **Credentials:** `provider_settings.aws` takes `region` and `profile` and nothing else. They reach Terraform as `TF_VAR_aws_region` and `TF_VAR_aws_profile`, both defaulting to null, so the AWS provider falls back to its own chain (environment variables, shared config, SSO, instance role). `access_key`, `secret_key`, `token` and `session_token` in the settings are a validation error, which keeps secrets out of YAML. Under `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE`, `AWS_REGION` and `AWS_PROFILE` override the two settings.
- **Validation:** config-only checks with no network call, because there is no AWS SDK. The same validators run in `doctor` and in `generate_terraform`, which raises `SchemaValidationError` on an ERROR-level finding.
- **Rules as resources:** ingress and egress rules are `aws_vpc_security_group_ingress_rule` and `aws_vpc_security_group_egress_rule` resources, never inline blocks. A security group Terraform creates has no default egress rule, so an omitted `egress:` renders allow-all IPv4 and IPv6 rules, and `egress: []` renders none.
- **Importing:** `import_id` adopts the primary resource (`aws_security_group`, `aws_instance`, `aws_ebs_volume`), which alone keeps the bare resource name. Companions take suffixed names so the generic import-block scan cannot match them. A rule takes its own `import_id`, and a volume takes `attachment_import_id`, so a group with existing rules or an attached volume can be adopted.
- **Data volumes:** `ebs_volume.prevent_destroy` defaults to true and renders `lifecycle { prevent_destroy = true }`, and the attachment sets `stop_instance_before_detaching`. For a protected volume the provider returns the volume's address from `get_state_addresses_kept_on_destroy` (#1349), so `infra destroy` forgets the volume and leaves it in AWS. The volume's availability zone is its own required key, never read from the instance, so replacing an instance replaces only the attachment.
- **AMIs:** `ami_ssm_parameter` renders a data source and `lifecycle { ignore_changes = [ami] }`, so a new published image does not replace a running instance. `replace_on_ami_change: true` opts out.
- **Defaults:** IMDSv2 required, an encrypted gp3 root volume, and a `Name` tag.
- **Cloud-init:** the shared `cloud_init_snippets` and `tailscale:` handling used by the OCI provider.
- **Version pin:** `hashicorp/aws ~> 6.0`.

## Rationale
The official provider already models these resources and tracks the AWS API, so wrapping it follows the OCI and Tailscale providers and adds no dependency. Leaving credentials to the AWS chain keeps secrets out of YAML and generated files and works with SSO and instance roles. Separate rule resources can each be imported, and the volume protection makes the replace-the-instance flow safe for data.

Alternatives rejected:

- **boto3 or a direct-API provider.** It needs a new dependency and duplicates the official provider.
- **Inline `ingress` and `egress` blocks.** They conflict with rule resources and cannot be imported one rule at a time.
- **Taking the volume's availability zone from the instance.** An instance replacement would then force a volume replacement.

## Related Issues

- Issue #1397: AWS provider for EC2 instances, security groups and EBS volumes
- Issue #1349: keep resources in AWS on destroy (state-removal hook)

## Related Documentation

- [AWS provider](../providers/aws.md)
