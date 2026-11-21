---
title: "Bitwarden / Vaultwarden secret backend"
description: "Resolve secret://bitwarden/... values from a Bitwarden or Vaultwarden vault through the bw CLI"
audience:
  - users
tags:
  - configuration
---

# Bitwarden / Vaultwarden secret backend

The `bitwarden` backend resolves `secret://bitwarden/<item>/<field>` from a Bitwarden or Vaultwarden vault, read-only. It works wherever `secret://env_secrets/...` works: provider settings, OPNsense component configs, collector devices, and the Terraform and Ansible secret bridges (see [below](#using-vault-values-in-terraform_secrets-and-host-tailscale-auth)). The design is recorded in [ADR-0034](../decisions/0034-a-bitwarden-secret-backend-resolves-through-the-bw-cli-with-private-per-run-cli-state.md).

## Prerequisites

1. **Bitwarden CLI (`bw`)** on the machine running InfraFoundry. It is an npm package or a standalone binary, not a Python dependency. See the [Bitwarden CLI help](https://bitwarden.com/help/cli/).
2. **A dedicated automation account** on the vault, limited to one collection. Create an API key for it (client ID and client secret) and note its master password.

## Configuration

Add a `secret_backends.bitwarden` block to the environment's `settings.yaml`:

```yaml
secret_backends:
  bitwarden:
    server: https://vault.example.com   # required, https only
    organization: Example Org           # optional: name or UUID
    collection: Automation              # optional: name or UUID
    # Where the bootstrap credentials come from (these are the defaults):
    client_id: secret://env/bw_clientid
    client_secret: secret://env/bw_clientsecret
    master_password: secret://env/bw_password
```

Then use it like any other `secret://` value:

```yaml
provider_settings:
  mikrotik:
    api_url: https://192.0.2.1
    username: secret://bitwarden/Router Admin/username
    password: secret://bitwarden/Router Admin/password
```

### Where provider settings resolve

Provider settings resolve for every provider, wherever the provider reads them: the API clients, the Terraform environment variables and the live validators. The values are resolved in memory when they are read, never when the environment config loads, so `bw` starts only when a `secret://bitwarden/...` value is actually used.

- `infra plan` and the offline validation, plus validators that only check a setting is present, check a settings URI offline: its shape and that its backend is configured. No vault is contacted.
- `infra doctor` runs live checks against the provider APIs, so it resolves the settings first. A bitwarden URI queries the vault there.
- The Terraform environment variable builder resolves only the settings keys it maps to a variable.
- For a provider with instances (OPNsense `firewalls:`, Kubernetes `clusters:`), only the shared top-level keys and the checked instance's entry are resolved. A URI that cannot be resolved is reported once per instance, labelled with the instance name, and never fails a sibling instance.

### Credential sources

`client_id`, `client_secret` and `master_password` are `secret://` URIs. Only two backends are accepted, so a credential can never point back into the vault:

- `secret://env/<key>` reads an environment variable. With the empty prefix the defaults map to `BW_CLIENTID`, `BW_CLIENTSECRET` and `BW_PASSWORD`.
- `secret://env_secrets/<path>` reads the environment's decrypted SOPS secrets, for example `secret://env_secrets/bitwarden/master_password`.

The credentials are read only when the first `secret://bitwarden/...` value is resolved. A run that never resolves one never starts `bw` and needs none of them.

## Addressing

`secret://bitwarden/<item>/<field>` is split on the **last** `/`, so an item name may contain `/` but a field name may not.

- `<item>` is an item ID (UUID, fetched with `bw get item`) or an exact item name. A name is looked up with `bw list items --search`, then filtered for an **exact** match, because `--search` is fuzzy. No match is an error. Several items with the same name is an error that names the count; use the item ID instead.
- `organization` and `collection` limit the lookup. An item fetched by ID outside the scope is treated as not found.

| Field | Value |
| :--- | :--- |
| `username` | the login username |
| `password` | the login password |
| `notes` | the notes |
| `uri` | the first login URI |
| `totp` | the current one-time code (`bw get totp`), not the seed |
| anything else | the custom field with that exact name |

Built-in names win over a custom field of the same name. A missing field, a custom field name used twice and an empty value are all errors; none of them includes a value.

## How the session works

- **Private state.** Each InfraFoundry process creates a private `0700` directory and passes it to every `bw` call as `BITWARDENCLI_APPDATA_DIR`. Your own `bw` login, server setting and `BW_SESSION` are never read, changed or logged out, and inherited `BW_*` variables are removed from the `bw` environment. The cost is a fresh login per process.
- **One session per process.** The steps `bw config server`, `bw status`, `bw login --apikey`, `bw unlock`, `bw sync` run once. Later lookups in the same process reuse the session.
- **Teardown.** At exit `bw lock` and `bw logout` run and the directory is removed. A process killed with `SIGKILL` leaves its `0700` directory (`infrafoundry-bw-*` in the temporary directory) behind; delete it by hand.
- **Credentials stay out of argv.** They are passed through the environment of the one command that needs them (`login` gets the client ID and secret, `unlock` gets the master password through `--passwordenv`).
- **Server check.** `server` must be `https://`. After `bw config server`, the backend reads `bw status` and fails if the server did not take.

!!! note "Verified against bw"
    A live test with `bw` 2026.10.1 against a self-hosted Vaultwarden, scoped to one organization collection, resolved `username`, `password` and a custom field by exact item name, and reported a missing field and a missing item as errors. The `uri`, `notes` and `totp` fields and lookup by item ID follow the Bitwarden documentation and are covered by the unit tests only.

## Using vault values in `terraform_secrets` and host Tailscale auth

`terraform_secrets` entries (including the Kubernetes `string_data_secrets`, `data_secrets` and `value_secret` fields), the host `tailscale.auth` refs and the destroy-time tailnet cleanup also accept `secret://<backend>/<key>`.

A reference is classified in this order, and the first match wins:

1. A value starting with `secret://` is always a URI. A malformed one such as `secret://bitwarden` is an error, never a dotted lookup.
2. `outputs.` ([ADR-0029](../decisions/0029-providers-consume-other-providers-terraform-outputs-through-outputs-references.md))
3. `package.` ([ADR-0031](../decisions/0031-secret-references-resolve-from-the-owning-packages-secretsyaml-through-a-package-prefix.md))
4. An unprefixed dotted path into the environment's `secrets.yaml`

Only `env_secrets` and (when configured) `bitwarden` are allowed in these bridges; `env` and `file` are not.

The Terraform variable is named `secret_<backend>_<slug(key)>`, where the slug lowercases the key and turns each run of non-alphanumeric characters into `_`. `secret://bitwarden/Router Admin/password` becomes `secret_bitwarden_router_admin_password`, declared `sensitive` and passed as `TF_VAR_*`. Two URIs that give the same name fail with a message naming only the references.

Plan-time validation and `infra doctor` stay offline. An `env_secrets` URI is checked against the decrypted secrets. A `bitwarden` URI is checked only for shape and a configured backend, and `infra doctor` lists it as apply time. The vault is queried at apply time, and only when such a reference is present. A `data_secrets` value must already be base64, as with SOPS secrets; that is not checked for a URI at plan time.

## Security notes

- The master password is needed to decrypt the vault. Keep it in a masked CI variable or in SOPS, never in `settings.yaml`.
- Exceptions and logs carry at most the `bw` subcommand, the item or field reference and a reason. `bw` stderr is discarded, because a failed request makes it print a stack trace.
- Resolved values reach providers in memory. For Terraform they travel as `TF_VAR_*` and are never written to generated `.tf` files; a value still lands in the Terraform state, as with any secret.
- The backend is read-only. It never creates or edits items.

## Migrating from `VaultwardenProvider`

`VaultwardenProvider` (`infrafoundry.core.secrets.providers.vaultwarden`) and its `SecretManager(provider=...)` use are removed. It was unused by the framework itself and could write to the vault. Replace programmatic `load_secret("item")` calls with `secret://bitwarden/<item>/<field>` references, and `BW_SERVER` with `secret_backends.bitwarden.server`.

## Troubleshooting

- **"Bitwarden CLI (bw) not found on PATH"**: install `bw` and make sure it is on `PATH`.
- **"bitwarden 'master_password' could not be resolved"**: the credential URI points at an unset variable or a missing SOPS key. The message names the setting and the URI, not a value.
- **"bw login failed (exit 1)"** or similar: the message names the failing subcommand only. Run the command by hand against a scratch `BITWARDENCLI_APPDATA_DIR` to see `bw`'s own output.
- **"matched 0 entries" for organization or collection**: the name is not exact, or the account cannot see it. Use the UUID.
- **"is ambiguous"**: two items share the name; use the item ID.
