---
title: "Tailscale Provider"
description: "Manage a tailnet's ACL, auth keys, device routes and tags, and DNS with the official tailscale/tailscale Terraform provider"
audience:
  - users
tags:
  - providers
---

# Tailscale Provider

The Tailscale provider manages the control plane of a tailnet: the ACL policy, auth keys, device subnet routes and tags, and DNS settings. It generates Terraform for the official [tailscale/tailscale](https://registry.terraform.io/providers/tailscale/tailscale/latest) provider and runs it through the standard Terraform runner.

!!! note "Node side versus control plane"
    This provider is the **control plane**. The `opnsense.tailscale.*` types ([OPNsense Resource Coverage](../development/opnsense-resource-coverage.md)) configure the `os-tailscale` plugin on a firewall, which is the **node side**. A subnet router needs both: the node advertises a route, and a `device_subnet_routes` resource here approves it. The two do not collide: the node types belong to provider `opnsense` and the types here to provider `tailscale`.

!!! note "Live-tested"
    Every resource type was applied, re-planned with no changes, and destroyed against a throwaway tailnet with provider v0.29.3, using OAuth. The test covered the `acl` import id, a tagged `tailnet_key`, the three DNS types, and `device_subnet_routes` and `device_tags` looked up by `hostname`. A firewall joined with the minted key through the `opnsense.tailscale.*` types, and its advertised route was approved. The OAuth client in that test held every scope, so the per-resource scope table below was not narrowed by the test.

## Supported Resources

| Type | Terraform resource | Description |
|------|--------------------|-------------|
| `acl` | `tailscale_acl` | The tailnet policy file (one per environment) |
| `tailnet_key` | `tailscale_tailnet_key` | An auth key |
| `device_subnet_routes` | `tailscale_device_subnet_routes` | The approved subnet routes of one device |
| `device_tags` | `tailscale_device_tags` | The tags of one device |
| `dns_nameservers` | `tailscale_dns_nameservers` | Global nameservers (one per environment) |
| `dns_preferences` | `tailscale_dns_preferences` | MagicDNS on or off (one per environment) |
| `dns_search_paths` | `tailscale_dns_search_paths` | DNS search domains (one per environment) |

`tailscale_dns_configuration` and `tailscale_dns_split_nameservers` are deliberately not exposed. They manage the same DNS settings as the three DNS types above, so the two families must not be mixed. DNS settings managed outside InfraFoundry with those resources conflict with the DNS types here too.

Resource names must be unique across all Tailscale types, and must be valid Terraform names (letters, digits, `_` and `-`, not starting with a digit).

## Configuration

### Provider Settings

Add the credentials to the environment's `settings.yaml`, as `secret://` URIs into the environment's encrypted `secrets.yaml`:

```yaml
name: test

providers:
  - tailscale

provider_settings:
  tailscale:
    oauth_client_id: secret://env_secrets/tailscale/oauth_client_id
    oauth_client_secret: secret://env_secrets/tailscale/oauth_client_secret
    tailnet: "-"        # the credential's own tailnet (the default)
    # scopes: [policy_file, auth_keys, devices:core, devices:routes, dns]
    # base_url: https://api.tailscale.com
```

```yaml
# envs/test/secrets.yaml (SOPS-encrypted)
tailscale:
  oauth_client_id: example-client-id
  oauth_client_secret: example-client-secret
```

To use an API key instead of OAuth, set `api_key: secret://env_secrets/tailscale/api_key` and leave the `oauth_*` settings out. Setting `api_key` together with `oauth_client_*` is an error, as is `oauth_client_id` without `oauth_client_secret`, or `scopes` without OAuth.

Credentials are never written to generated files. The URIs are resolved when the runner starts and passed to Terraform only as `TF_VAR_tailscale_*` environment variables. Every variable defaults to null.

### Fallback and Override Variables

- With a setting left out, the official provider falls back to its own variables: `TAILSCALE_API_KEY`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_CLIENT_SECRET` and `TAILSCALE_TAILNET`.
- With `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`, the same names override the matching `provider_settings.tailscale` keys (see [AI Command Blocking](../development/ai/command-blocking.md) for the gate). The override is applied first, then `secret://` resolution.
- The auth mode is OAuth when `oauth_client_id` is set, or failing that `TAILSCALE_OAUTH_CLIENT_ID` is.

`foundry infra doctor --env <name> -P tailscale` checks that the settings are consistent. It makes no network call and does not exchange a token.

### OAuth Scopes

Give the OAuth client the scopes for the resources you use. The names below come from Tailscale's documentation; the live test used a client holding every scope, so it did not check this minimal set:

| Resource | Scope |
|----------|-------|
| `acl` | `policy_file` |
| `tailnet_key` | `auth_keys` |
| `device_tags`, and the `device:` lookup | `devices:core` |
| `device_subnet_routes` | `devices:routes` |
| `dns_*` | `dns` |

### OAuth Requires Tags

An OAuth client can only create auth keys that carry tags, and the tags must be owned in the ACL's `tagOwners`. A `tailnet_key` without `tags` is therefore an error under OAuth. If an `acl` with a structured `policy` is declared, a tag used by a `tailnet_key` or `device_tags` resource that is missing from `policy.tagOwners` is reported as a warning.

## Resource Reference

Place resources in `envs/{env}/tailscale/<type>.yaml`, in a package directory under `envs/{env}/tailscale/` that has an `infrafoundry.yml` manifest, or in a resource-centric file with `provider: tailscale`. The provider-centric file name is the type, for example `acl.yaml` or `device_subnet_routes.yaml`.

### acl

Give exactly one of `policy` (a YAML mapping, serialised to JSON) or `hujson` (a string, kept verbatim so comments survive).

```yaml
acl:
  - name: tailnet-policy
    import_id: acl
    policy:
      tagOwners:
        tag:server: ["autogroup:admin"]
      acls:
        - action: accept
          src: ["tag:server"]
          dst: ["tag:server:*"]
```

```yaml
acl:
  - name: tailnet-policy
    import_id: acl
    hujson: |
      {
        // Servers talk to each other.
        "tagOwners": {"tag:server": ["autogroup:admin"]},
        "acls": [{"action": "accept", "src": ["tag:server"], "dst": ["tag:server:*"]}],
      }
```

Resource files are Jinja-rendered. If a HuJSON block contains `{{`, `{%` or `{#`, wrap it in `{% raw %}` and `{% endraw %}`.

| Field | Required | Description |
|-------|----------|-------------|
| `policy` / `hujson` | One of | The policy |
| `overwrite_existing_content` | No | Skip the import requirement. Omitted unless set |
| `reset_acl_on_destroy` | No | Reset to Tailscale's default policy on destroy. Omitted unless set |
| `import_id` | No | Import the existing policy into state (framework-wide field) |

A new `tailscale_acl` needs one of two things, or the provider refuses to take over the existing policy: import it with `import_id: acl`, or set `overwrite_existing_content: true`, which can overwrite the policy file. The import id `acl` was confirmed by the live test: the first plan reads `1 to import`, and the import is a no-op on later runs.

!!! note "Plan summary with an import"
    When an import is pending, `foundry infra plan` prints `terraform: Unable to parse plan output` instead of a summary. The shared runner's summary does not recognise Terraform's `Plan: N to import, ...` line. The plan itself is correct and `apply` performs the import.

Destroying an `acl` without `reset_acl_on_destroy` only removes it from state; the policy stays in the tailnet as last applied.

!!! warning "Resetting on destroy opens access"
    Tailscale's default policy is allow-all. `reset_acl_on_destroy: true` therefore replaces your policy with one that allows everything. It is off by default.

### tailnet_key

```yaml
tailnet_key:
  - name: node-key
    description: example node key
    tags: ["tag:server"]
    reusable: false
    preauthorized: true
    ephemeral: false
    expiry: 3600
    recreate_if_invalid: never
```

| Field | Required | Description |
|-------|----------|-------------|
| `tags` | Under OAuth | Tags, each `tag:<name>` |
| `description` | No | Key description |
| `reusable`, `preauthorized`, `ephemeral` | No | Booleans |
| `expiry` | No | Seconds, a positive integer |
| `recreate_if_invalid` | No | `always` or `never` |

The key value is exposed as the sensitive output `tailnet_key_<name>`, and `tailnet_keys` lists `id`, `expires_at` and `invalid` for each key:

```bash
terraform -chdir=generated/<env>/terraform/tailscale output -raw tailnet_key_<name>
```

!!! danger "State holds secrets"
    The key value, and the ACL, are stored in plaintext in the Terraform state (`generated/<env>/terraform/tailscale/terraform.tfstate` for a local backend). Use an encrypted remote backend, a short `expiry`, and `ephemeral` or single-use keys. Do not paste the output into shared logs.

When an `acl` is declared, keys, routes and tags depend on it, so the tags exist in `tagOwners` first.

### device_subnet_routes and device_tags

Name the device with `device:` (recommended) or a raw `device_id`. With `device:`, the generated Terraform looks the device up by `hostname` or full `name`, and uses its `node_id`. The live test confirmed that both `device_subnet_routes` and `device_tags` accept `node_id`.

```yaml
device_subnet_routes:
  - name: fw-test-routes
    device:
      hostname: fw-test
      wait_for: 120s      # optional: wait for the device to join
    routes:
      - 192.0.2.0/24
      - 2001:db8::/64
```

```yaml
device_tags:
  - name: fw-test-tags
    device_id: "example-device-id"
    tags: ["tag:server"]
    keep_tags_on_destroy: true  # optional; see below
```

Each resource owns the device's full set of routes or tags, so at most one `device_subnet_routes` and one `device_tags` resource may point at a device. Routes must be CIDRs with no host bits set.

!!! warning "Destroying `device_tags` on a tagged node fails"
    Destroying a `device_tags` resource clears the device's tags. For a node that joined with a tagged auth key, the Tailscale API refuses that with `tagged nodes cannot be untagged without reauth (400)`, and `foundry infra destroy` stops. Set `keep_tags_on_destroy: true` on the resource: `foundry infra destroy` then removes `tailscale_device_tags.<name>` from state instead of clearing the tags, so the device keeps them. The destroy prints `Keeping tailscale_device_tags.<name>: removed from state, not destroyed` and completes; this was verified against a node that joined with a tagged key. The field takes effect on the next destroy and needs no apply first. Without it, destroy clears the tags as before. For a resource applied without the field, the manual fallback is to delete the device from the tailnet first, or to run `terraform state rm tailscale_device_tags.<name>`.

### Joining an OPNsense node with a minted key

The live test fed a `tailnet_key` to a firewall: read the key from the output, store it in SOPS without printing it, and reference it from `opnsense.tailscale.auth.pre_auth_key`. The box does not echo a stored key back reliably, so set `update_pre_auth_key: true` for the apply that should write a new key:

```bash
terraform -chdir=generated/<env>/terraform/tailscale output -json tailnet_key_<name> \
  | sops set --value-stdin envs/<env>/secrets.yaml '["opnsense"]["tailscale"]["auth"]["pre_auth_key"]'
```

```yaml
opnsense:
  tailscale:
    auth:
      update_pre_auth_key: true
      pre_auth_key: secret://env_secrets/opnsense/tailscale/auth/pre_auth_key
```

### dns_nameservers, dns_preferences, dns_search_paths

```yaml
dns_nameservers:
  - name: tailnet-dns
    nameservers: [192.0.2.53, "2001:db8::53"]
```

```yaml
dns_preferences:
  - name: tailnet-magic-dns
    magic_dns: true
```

```yaml
dns_search_paths:
  - name: tailnet-search
    search_paths: [example.com]
```

Each of these, and `acl`, may appear at most once per environment.

## Running It

```bash
foundry infra doctor --env test -P tailscale
foundry infra plan --env test -P tailscale
foundry infra apply --env test -P tailscale
foundry infra destroy --env test -P tailscale
```

The Terraform provider is pinned to `~> 0.29.3` (at least 0.29.3, below 0.30.0). It is pre-1.0, where minor versions may break, and only that version's schema was checked.

## Related

- [ADR-0020](../decisions/0020-wrap-the-official-tailscale-terraform-provider-for-tailnet-control-plane-management.md)
- [OPNsense Resource Coverage: Tailscale](../development/opnsense-resource-coverage.md#tailscale-787)
