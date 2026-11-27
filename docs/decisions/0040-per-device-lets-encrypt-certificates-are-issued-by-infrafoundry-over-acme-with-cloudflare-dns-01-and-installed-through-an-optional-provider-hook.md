---
title: "ADR-0040: Per-device Let's Encrypt certificates are issued by InfraFoundry over ACME with Cloudflare DNS-01 and installed through an optional provider hook"
description: InfraFoundry issues Let's Encrypt certificates itself with DNS-01 on Cloudflare, stores them SOPS-encrypted beside the package that declares them, and installs them through an optional provider hook, starting with the host provider
date: 2026-11-27
audience:
  - contributors
tags:
  - adr
---

# ADR-0040: Per-device Let's Encrypt certificates are issued by InfraFoundry over ACME with Cloudflare DNS-01 and installed through an optional provider hook

## Status

Accepted

## Context

Devices that serve HTTPS (a reverse proxy, a management UI) need certificates that browsers and clients trust, and they have no public path for the HTTP-01 challenge. Let's Encrypt can validate with DNS-01 on the domain's DNS host, which needs no inbound access to the device. Running one issuer per device by hand, or a shell client in a cron job, keeps the keys and tokens outside InfraFoundry's secret handling, and gives no view of what expires when.

InfraFoundry already stores per-package secrets in SOPS files ([ADR-0032](0032-blueprint-vms-get-pre-generated-ssh-host-keys-that-scripts-pin.md) keeps SSH host keys the same way), runs Linux hosts over SSH through the `host` provider ([ADR-0022](0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md)), and has an environment lock for commands that must exclude apply and destroy.

## Decision

1. **Own issuer, built on the `acme` library.** `core/certs/` orders certificates from an ACME directory with DNS-01 on Cloudflare. `acme` and `cryptography` are runtime dependencies; only `core/certs/acme_client.py` imports `acme` and `josepy`, behind an `AcmeClient` protocol, so tests use a fake CA.
2. **A thin `acme` provider declares the certificates.** The resource type is `certificate`. The provider gives offline schema checks (`ValidatesOffline`), `--provider acme` filtering and a place in the state database. It writes an empty `terraform {}`: `infra apply` never issues a certificate, because issuing talks to a CA and rewrites encrypted files in the config repo. Only `foundry certs` does.
3. **Settings come from `secret://` references.** `provider_settings.acme.cloudflare.api_token` and `zone_id` must be `secret://` references; no secret name is hard-coded, and a user may point them at secret paths that exist already. The default directory is `staging`; production is chosen by name, never by default. One Cloudflare zone per environment.
4. **Storage follows the host-key model.** Each certificate and its key are stored in the declaring package's SOPS `secrets.yaml` under `variables.acme_certificates.<name>`. `package_loader` keeps that key out of the merged manifest variables, as it does `ssh_host_keys`. The ACME account key is stored in the environment's `secrets.yaml` under `acme.accounts.<directory-id>`. Writes are atomic: `sops set --value-stdin` on a copy, then `os.replace`; no plaintext touches disk.
5. **Install is an optional provider hook.** `InstallsCertificate` in `core/protocols.py` adds `install_certificate(target, cert_pem, chain_pem, key_pem)`. A provider that does not implement it cannot be a target; existing contracts are unchanged. The `host` provider implements it over SSH with strict host-key checking and no prompts. Files go on stdin, are written under `umask 077`, backed up, moved into place and reloaded in one remote call, and restored if a move or the reload fails. After an install, core checks the served leaf's SHA-256 over TLS without a chain check, so staging certificates verify too.
6. **Safe order and failure isolation.** `foundry certs issue` holds the environment lock, processes certificates one at a time, and continues past a failure. The order is issue, write the encrypted entry, install, verify, write `installed_sha256`, record an `ACTIVE` state row (names, expiry, fingerprint, target; no key material). A certificate that is stored but not installed gets an install-only retry. Exit codes: 0 ok, 1 a certificate failed, 2 usage error, 75 the lock is held.
7. **DNS-01 hygiene.** Propagation is checked by querying every authoritative nameserver of the zone directly (recursion off) until each serves every TXT value, with no fixed sleep; DNS-over-HTTPS resolvers are an opt-in later stage ([#1692](https://github.com/endavis/infrafoundry/issues/1692)). Every record carries the comment `infrafoundry-acme <name>` and is deleted in a `finally`; stale InfraFoundry records are purged when an order starts. The token is scrubbed from every error.
8. **Delivery in three PRs.** The first covers issue and install on a `host` (this ADR's implementation). The second adds unattended renewal: `foundry certs renew` (the `issue` selection without `--force`, quiet and lock-free when nothing is due, `--dry-run` without lock or network), plan warnings from `AcmeProvider.get_plan_notes`, a Cloudflare token check in `infra doctor`, the additive `CERTIFICATE_ISSUED`, `CERTIFICATE_INSTALLED` and `CERTIFICATE_FAILED` events (payloads without key material or token) and timer examples. VM targets follow and amend this ADR.

## Rationale

- **A shell ACME client on each device:** rejected. The token would live on every device and there would be no central expiry view or lock.
- **Terraform ACME provider:** rejected. It would put keys in Terraform state and tie issuance to `apply`, which has no business renewing certificates on a schedule.
- **Issuing during `apply`:** rejected. A plan that contacts a CA and rewrites the config repo is not a plan.
- **Core logic in the provider package:** rejected. The issuer, store and installer serve every provider that opts into the hook.

## Related Issues

- [#1692](https://github.com/endavis/infrafoundry/issues/1692) acme propagation check can be defeated by cached negative dns answers
- [#1682](https://github.com/endavis/infrafoundry/issues/1682) issue and renew per-device Let's Encrypt certificates with Cloudflare DNS-01

## Related Documentation

- [ACME provider](../providers/acme.md)
- [Host provider](../providers/host.md)
- [CLI reference](../usage/cli-reference.md)
