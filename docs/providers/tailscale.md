---
title: "Tailscale Provider"
description: "Manage a tailnet's ACL, auth keys, device routes and tags, and DNS (including split DNS) with the official tailscale/tailscale Terraform provider"
audience:
  - users
tags:
  - providers
---

# Tailscale Provider

The Tailscale provider manages the control plane of a tailnet: the ACL policy, auth keys, device subnet routes and tags, and DNS settings including split-DNS routes. It generates Terraform for the official [tailscale/tailscale](https://registry.terraform.io/providers/tailscale/tailscale/latest) provider and runs it through the standard Terraform runner.

!!! note "Node side versus control plane"
    This provider is the **control plane**. The `opnsense.tailscale.*` types ([OPNsense Resource Coverage](../development/opnsense-resource-coverage.md)) configure the `os-tailscale` plugin on a firewall, which is the **node side**. A subnet router needs both: the node advertises a route, and a `device_subnet_routes` resource here approves it. The two do not collide: the node types belong to provider `opnsense` and the types here to provider `tailscale`.

!!! note "Live-tested"
    Every resource type was applied, re-planned with no changes, and destroyed against a throwaway tailnet with provider v0.29.3, using OAuth. The test covered the `acl` import id, a tagged `tailnet_key`, the three DNS types, and `device_subnet_routes` and `device_tags` looked up by `hostname`. A firewall joined with the minted key through the `opnsense.tailscale.*` types, and its advertised route was approved. The OAuth client in that test held every scope, so the per-resource scope table below was not narrowed by the test.

## Supported Resources

| Type | Terraform resource | Description |
|------|--------------------|-------------|
| `acl` | `tailscale_acl` | The tailnet policy file (one per environment) |
| `tailnet_key` | `tailscale_tailnet_key` | An auth key |
| `oauth_client` | `tailscale_oauth_client` | An OAuth client whose credentials other providers can consume |
| `device_subnet_routes` | `tailscale_device_subnet_routes` | The approved subnet routes of one device |
| `device_tags` | `tailscale_device_tags` | The tags of one device |
| `dns_nameservers` | `tailscale_dns_nameservers` | Global nameservers (one per environment) |
| `dns_preferences` | `tailscale_dns_preferences` | MagicDNS on or off (one per environment) |
| `dns_search_paths` | `tailscale_dns_search_paths` | DNS search domains (one per environment) |
| `dns_split_nameservers` | `tailscale_dns_split_nameservers` | Nameservers for one domain (split DNS), one per domain |

`tailscale_dns_configuration` is deliberately not exposed. The provider's documentation for v0.29.3 says it manages the entirety of a tailnet's DNS configuration and conflicts with `tailscale_dns_nameservers`, `tailscale_dns_preferences`, `tailscale_dns_search_paths` and `tailscale_dns_split_nameservers`, and that they must not be used simultaneously. So do not combine the DNS types here with a `tailscale_dns_configuration` managed elsewhere (another Terraform root or tool). The four DNS types here may be combined with each other; the same documentation lists no conflict among them.

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
| `oauth_client` | `oauth_keys` on the managing client, plus every scope the new client is given |
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

### oauth_client

```yaml
oauth_client:
  - name: k8s-operator
    description: example operator client
    scopes: ["devices:core", "auth_keys"]
    tags: ["tag:k8s-operator"]
```

| Field | Required | Description |
|-------|----------|-------------|
| `scopes` | Yes | A non-empty list of scope names |
| `description` | No | Client description |
| `tags` | No | Tags, each `tag:<name>`; a tag missing from `tagOwners` is a warning |

The client id and secret are exposed as the sensitive outputs `oauth_client_<name>_id` and `oauth_client_<name>_secret` (a hyphen in the name becomes `_`), and `oauth_clients` lists `created_at` for each client. The scope needed on the managing client to create OAuth clients (`oauth_keys`) comes from Tailscale's documentation and was not checked in a live test.

!!! danger "State holds secrets"
    The client secret is stored in plaintext in the Terraform state of this provider, and again in the state of any provider that consumes it. Use an encrypted remote backend.

Another provider can take the id or secret straight from these outputs with an `outputs.tailscale.<output>` reference, for example in a Kubernetes secret:

```yaml
secrets:
  - name: operator-oauth
    config:
      namespace: tailscale
      string_data_secrets:
        client_id: outputs.tailscale.oauth_client_k8s_operator_id
        client_secret: outputs.tailscale.oauth_client_k8s_operator_secret
```

See [Kubernetes Secrets](kubernetes.md#secrets) for the rules, and [Dependency Ordering](../configuration/dependency-ordering.md#cross-provider-dependencies) for how tailscale is applied first.

When an `acl` is declared, `oauth_client` depends on it like the other resources.

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

Prefer `opnsense.tailscale.auth.mint`: the firewall mints a single-use, tagged key from an OAuth client at apply time, so no key is kept in secrets and a rebuild needs no manual step. The OAuth client needs the `auth_keys` scope and must own the tags in `tagOwners`. Nothing is minted when the node is already `Running`. See [Minting the key](../development/opnsense-resource-coverage.md#minting-the-key-1510). The path was verified live against a test firewall (#1510), with an OAuth client that held every scope; the `auth_keys` scope alone has not been tested.

```yaml
opnsense:
  tailscale:
    auth:
      mint:
        oauth_client_id: secret://env_secrets/opnsense/tailscale/auth/oauth_client_id
        oauth_client_secret: secret://env_secrets/opnsense/tailscale/auth/oauth_client_secret
        tags: [tag:example]
```

The alternative below uses a `tailnet_key` of this provider and stores the key. The live test fed a `tailnet_key` to a firewall: read the key from the output, store it in SOPS without printing it, and reference it from `opnsense.tailscale.auth.pre_auth_key`. The box does not echo a stored key back reliably, so set `update_pre_auth_key: true` for the apply that should write a new key:

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

Each of these, and `acl`, may appear at most once per environment. `dns_split_nameservers` is the exception: one resource per domain.

### dns_split_nameservers

```yaml
dns_split_nameservers:
  - name: internal-split
    domain: example.com
    nameservers: [192.0.2.53, "2001:db8::53"]
    import_id: example.com
```

| Field | Required | Description |
|-------|----------|-------------|
| `domain` | yes | The DNS name the route covers, without a trailing dot |
| `nameservers` | yes | IPv4 or IPv6 addresses that resolve the domain; unordered, no repeats |
| `import_id` | no | The domain of an existing route to adopt; must equal `domain` |

- One resource per domain; domains must be unique (compared ignoring case).
- Changing `domain` replaces the route, because the provider forces a new resource. `nameservers` is unordered.
- To adopt a route made in the admin console, set `import_id` to its domain and declare the same nameservers. The first plan is expected to report one import and no change; later runs treat the import block as a no-op. This is not live-tested. An `import_id` that differs from `domain` is a validation error, because it would import another route and the next plan would replace it.
- Removing the resource deletes the route from the tailnet.
- Combining it with `dns_nameservers`, `dns_preferences` and `dns_search_paths` is allowed: the v0.29.3 provider documentation lists a conflict only for `tailscale_dns_configuration`. Coexistence was not live-tested.

## Instance `tailscale:` block

AWS, OCI and Proxmox instances can join the tailnet at first boot through a `tailscale:` block, which renders the Tailscale cloud-init module. [Host resources](host.md) take the same block and enroll through Ansible at apply instead.

```yaml
resources:
  - name: node-a
    type: instance
    tailscale:
      auth:
        oauth:
          client_id_secret: tailscale.oauth_client_id
          client_secret_secret: tailscale.oauth_client_secret
      hostname: node-a
      advertise_tags: [tag:example]
      remove_on_destroy: true
```

| Field | Meaning |
| :--- | :--- |
| `auth.auth_key_secret` | Secret path, or a `secret://env_secrets/...` or `secret://bitwarden/...` URI, of a static auth key. Exactly one of this or `auth.oauth` is required. |
| `auth.oauth.client_secret_secret` | Secret path or `secret://` URI of an OAuth client secret, passed to the module as its auth key. Requires `advertise_tags`. |
| `auth.oauth.client_id_secret` | Secret path or `secret://` URI of the OAuth client id. Optional for joining; required for removal on destroy. |
| `hostname` | Tailnet hostname. Defaults to the resource name. |
| `advertise_tags`, `advertise_routes` | Tags and subnet routes the node advertises. |
| `accept_dns`, `accept_routes`, `enable_ssh` | Client settings passed to the module. |
| `advertise_exit_node` | The node offers itself as an exit node. Default `false`. The module enables IP forwarding for it. Its `0.0.0.0/0` and `::/0` routes still need approval, for example with the tailscale provider's `device_subnet_routes`, unless an ACL `autoApprovers` entry covers them. Cloud-init instances only (AWS, OCI, Proxmox). |
| `track`, `additional_parts` | Tailscale release track and extra cloud-init parts. |
| `remove_on_destroy` | Remove the tailnet device when the instance is destroyed. Default `true`. |

### Removing the tailnet device on destroy

After `foundry infra destroy` deletes an instance, InfraFoundry removes its device from the tailnet through the Tailscale API. It applies to `host` resources as well. This also applies to resource (`-r`), package (`-p`) and provider (`-P`) destroys, and only to instances the destroy actually deleted.

- The OAuth client needs the `devices:core` scope, and both `client_id_secret` and `client_secret_secret` set.
- A device is removed when its hostname matches the block's `hostname` and it carries at least one of the block's `advertise_tags` (both case-insensitive). Collision copies such as `node-a-1` keep the hostname `node-a` and are removed too.
- `auth_key_secret` mode cannot call the API, a block without `client_id_secret` has no client id, and `remove_on_destroy: false` opts out. Each is skipped with a log line.
- API failures only print a warning; the destroy still succeeds. Remove the device by hand in the admin console.
- An instance already gone outside InfraFoundry is not cleaned up.
- An apply that replaces an instance does not remove the old device: the old and new devices share a hostname and tags, so cleanup could delete the replacement that just joined.

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
- [Host Provider](host.md)
- [OPNsense Resource Coverage: Tailscale](../development/opnsense-resource-coverage.md#tailscale-787)
