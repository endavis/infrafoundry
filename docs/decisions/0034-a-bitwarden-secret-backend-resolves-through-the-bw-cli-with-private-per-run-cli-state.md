---
title: "ADR-0034: A bitwarden secret:// backend resolves through the bw CLI with private per-run CLI state"
description: A read-only bitwarden secret:// backend resolves vault items through the bw CLI with private per-process CLI state, and secret:// URIs work in the Terraform and Ansible secret bridges.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0034: A bitwarden secret:// backend resolves through the bw CLI with private per-run CLI state

## Status
Accepted

## Context
Secrets could come only from the environment's SOPS `secrets.yaml`, the process environment or files. Operators who keep credentials in a self-hosted Vaultwarden or in Bitwarden had no way to use them: the only code, `VaultwardenProvider`, was unused in `src/`, wrote `BW_SESSION` into the process environment, and put `bw` stderr into exceptions (#1520).

## Decision
A read-only `bitwarden` backend resolves `secret://bitwarden/<item>/<field>` through the `bw` CLI. It is registered under the `infrafoundry.secrets` entry points and configured by the `secret_backends.bitwarden` block of an environment's `settings.yaml`.

- **Addressing:** the key is split on the last `/` into `<item>` and `<field>`. An item is a UUID (`bw get item`) or an exact name (`bw list items --search`, re-filtered for an exact match because `--search` is fuzzy). Zero matches is not-found; several is an error naming the count. `organization` and `collection` scope the lookup and accept a UUID or an exact name. Fields are `username`, `password`, `notes`, `uri` (first), `totp` (the current code) or a custom field name; built-in names win.
- **Bootstrap credentials:** `client_id`, `client_secret` and `master_password` are `secret://env/...` or `secret://env_secrets/...` URIs, defaulting to `BW_CLIENTID`, `BW_CLIENTSECRET` and `BW_PASSWORD`. Any other backend, `bitwarden` included, is rejected so a credential cannot point back into the vault. They reach `bw` only through the subprocess environment, each to the one command that needs it, never argv.
- **Private CLI state:** each process creates a 0700 directory and passes it to every `bw` call as `BITWARDENCLI_APPDATA_DIR`. Inherited `BW_*` and app-data variables are stripped from the subprocess environment. The operator's own `bw` login, server and `BW_SESSION` are never read, repointed or logged out. The cost is a fresh login per process.
- **One session per process:** `config server`, `status`, `login --apikey`, `unlock --passwordenv BW_PASSWORD --raw`, `sync` run once; a second backend in the process reuses the session. `bw lock`, `bw logout` and removal of the directory run at exit (`atexit`) or through `close_bitwarden_sessions()`. A SIGKILLed process leaves its 0700 directory behind.
- **https only:** `server` must be an `https://` URL, and `bw status` must report it back after `bw config server`.
- **Value-free errors:** exceptions carry at most the `bw` subcommand, the item or field reference and a reason. Never stderr, values or credentials; stderr is not logged either.
- **Wiring:** `build_secret_resolver(env_config)` replaces the five hand-built resolvers (MikroTik, OpenWrt and collector settings, OPNsense component configs, provider settings for Terraform). The backend is created on first use, so an environment that never resolves a `secret://bitwarden/...` value never runs `bw`.
- **Terraform and Ansible bridges:** `terraform_secrets` entries (and so the Kubernetes value-secret fields), the host `tailscale.auth` refs and the destroy-time tailnet cleanup also accept `secret://<backend>/<key>`. A value starting with `secret://` is always a URI and is classified before `outputs.` (ADR-0029), `package.` (ADR-0031) and the unprefixed dotted path, which are unchanged. Only the backends `build_secret_resolver` configures are allowed (`env_secrets` always, `bitwarden` when configured); `env` and `file` are not opened to the bridges. The variable is named `secret_<backend>_<slug(key)>`; two URIs with the same slug fail through the existing collision check. Plan-time validation and `infra doctor` stay offline: an `env_secrets` URI is checked against the decrypted secrets, a `bitwarden` URI only for shape and a configured backend (shown as apply time). The vault is queried at apply time. The `KeyError`, `ValueError` and warning contracts are kept and value-free.
- **Removed:** `VaultwardenProvider` and its `vaultwarden` provider module. Use `secret://bitwarden/...`. This is a breaking change to a documented programmatic API.
- **Out of scope:** `package.` naming for Tailscale auth refs, and the `env` and `file` backends in the bridges.

## Rationale
`secret://` is already the way config fields name a secret, so a new backend works everywhere `env_secrets` does with no new grammar for those sites. Private CLI state keeps a run from logging out or repointing the operator's own `bw`, and keeps the operator's `BW_SESSION` out of the run. Resolving credentials through `env` and `env_secrets` keeps the bootstrap in places the operator already controls. Offline plan-time checks keep `infra doctor` and validation from needing the vault or network.

## Amendments

- Provider settings resolve at every reader through `resolved_provider_settings` / `with_resolved_provider_settings`; offline paths check shape and backend only (#1594).

## Related Issues
- Issue #1520: add a bitwarden/vaultwarden secret:// backend
- Issue #1590: pass the vaultwarden master password to bw by environment variable
- Issue #1594: resolve secret:// URIs in every provider's settings

## Related Documentation
- [Bitwarden / Vaultwarden secret backend](../configuration/secrets-vaultwarden.md)
- [Secret backend design](../plugin_system/SECRET_BACKEND_DESIGN.md)
