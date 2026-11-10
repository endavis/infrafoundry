---
title: "ADR-0020: Wrap the official Tailscale Terraform provider for tailnet control-plane management"
description: The tailscale provider wraps the official tailscale/tailscale Terraform provider, with OAuth credentials resolved from secret:// URIs into TF_VAR_ variables
date: 2026-11-10
audience:
  - contributors
tags:
  - adr
---

# ADR-0020: Wrap the official Tailscale Terraform provider for tailnet control-plane management

## Status
Accepted

## Context
A tailnet has a control plane (the ACL policy, auth keys, device routes and tags, DNS) that the node-side `opnsense.tailscale.*` types (#787) cannot reach. Issue #870 asks for a provider that manages it. Tailscale publishes an official Terraform provider, `tailscale/tailscale`, that covers these resources.

## Decision
Add a `tailscale` provider that generates Terraform for the official provider instead of writing an API client.

- **Resources:** `acl`, `tailnet_key`, `device_subnet_routes`, `device_tags`, `dns_nameservers`, `dns_preferences` and `dns_search_paths`. `tailscale_dns_configuration` and `tailscale_dns_split_nameservers` are reported through `get_unsupported_resource_types()`, because they manage the same DNS settings as the three exposed resources and the two families must not be mixed.
- **Credentials:** OAuth first, with `api_key` as the alternative. Values in `provider_settings.tailscale` may be `secret://env_secrets/...` URIs. `TerraformGeneratorMixin.build_terraform_env_vars` gains an opt-in, keyword-only `resolve_secret_uris` parameter (default False, so no other provider changes) that resolves them against the environment's decrypted secrets. The values reach Terraform only as `TF_VAR_*` environment variables. Every variable defaults to null, so the provider falls back to its own `TAILSCALE_*` variables.
- **Tailnet key output:** `tailnet_key.key` is sensitive and is exposed as one sensitive output per key. It is already in the Terraform state, so the output adds no exposure, and `terraform output -raw` is the way to read it without opening the state. The docs state that local state holds the key and ACL in plaintext and recommend an encrypted remote backend.
- **ACL:** exactly one of `policy` (a mapping, serialised to JSON) or `hujson` (a string kept verbatim). A fresh `tailscale_acl` needs an import (`import_id`) or `overwrite_existing_content: true`; the provider refuses otherwise. `reset_acl_on_destroy` is opt-in because resetting restores Tailscale's allow-all default policy.
- **Devices:** `device_subnet_routes` and `device_tags` take a `device:` lookup (hostname or name, rendered as a `tailscale_device` data source) or a raw `device_id`. At most one of each per device. `device_tags` accepts an opt-in `keep_tags_on_destroy: true`, which removes the resource from Terraform state before destroy so a tagged node keeps its tags (the API refuses to untag it). It uses the additive `ProviderBase.get_state_addresses_kept_on_destroy` hook.
- **Validation:** config-only checks. Doctor makes no network call. Under OAuth, a `tailnet_key` without `tags` is an error, because OAuth clients can only create tagged keys.
- **Version pin:** `~> 0.29.3`. The provider is pre-1.0, where minor versions may break, and only that schema was measured.

## Rationale
The official provider already models these resources and tracks the Tailscale API, so wrapping it follows the ESXi and OCI providers and avoids new HTTP client code and a second place to track API changes. Resolving `secret://` URIs into `TF_VAR_*` keeps credentials out of generated files, matching the existing secrets bridge, and the opt-in flag leaves every other provider's behaviour unchanged.

Alternatives rejected:

- **A direct-API provider.** It would duplicate the official provider and need new client, auth and drift logic.
- **Exposing `dns_configuration`.** It overlaps the three DNS resources; offering both invites conflicting writes to the same settings.
- **Not exposing the key.** The end-to-end flow (joining a firewall to a tailnet) needs the key, and withholding the output would not remove it from the state.

## Related Issues

- Issue #870: Tailscale control-plane provider
- Issue #787: OPNsense os-tailscale plugin (the node side)
- Issue #1349: keep tags on destroy for tagged nodes

## Related Documentation

- [Tailscale provider](../providers/tailscale.md)
