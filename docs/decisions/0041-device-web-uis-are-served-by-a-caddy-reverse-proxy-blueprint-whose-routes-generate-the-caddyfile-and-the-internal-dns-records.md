---
title: "ADR-0041: Device web UIs are served by a Caddy reverse-proxy blueprint whose routes generate the Caddyfile and the internal DNS records"
description: A Caddy reverse-proxy blueprint serves device web UIs under the operator's domain, generating the Caddyfile and the internal DNS records from one route list
date: 2026-11-27
audience:
  - contributors
tags:
  - adr
---

# ADR-0041: Device web UIs are served by a Caddy reverse-proxy blueprint whose routes generate the Caddyfile and the internal DNS records

## Status

Accepted

## Context

Device web UIs (a NAS, a switch) often serve self-signed certificates and sit on addresses without names. Operators want them reachable by name under their own domain with a trusted certificate, from the LAN and over a tailnet. [ADR-0040](0040-per-device-lets-encrypt-certificates-are-issued-by-infrafoundry-over-acme-with-cloudflare-dns-01-and-installed-through-an-optional-provider-hook.md) issues and installs certificates, with a Proxmox VM as a target. A reverse proxy VM is its first consumer.

## Decision

1. **A `reverse-proxy` blueprint runs Caddy on one Proxmox VM.** Automatic HTTPS is off; the certificate comes from the acme provider and is installed on the VM.
2. **Routes are a blueprint input, not a resource type.** A new resource type would need a new provider. One `routes` list feeds the DNS records, the Caddyfile and the handler env, so they cannot drift.
3. **DNS is generated from the routes.** One `opnsense` `unbound.host_overrides` per route, all pointing at the proxy, from a proxmox package (the same cross-provider generation as the `aiqum` and `service-vm` blueprints).
4. **`infra plan` shows route changes through the DNS records.** The override description carries a summary of the route (backend, options, allowed networks), so a changed route is an in-place update. A plan that SSHes to the VM to diff the Caddyfile would break the offline plan of [ADR-0023](0023-infra-plan-runs-providers-offline-validation-live-checks-stay-in-infra-doctor.md), so there is none.
5. **The Caddyfile is written by an `after_apply` script handler, not an Ansible role.** `on_create` and `on_update` fire only when the VM changes, so a route change would never reach it. The handler renders the file with a standard-library Python script, then pipes a node script over the pinned SSH channel of the other proxmox blueprint scripts (strict host keys, the key pinned by `foundry secrets host-keys`, the staged known_hosts file on the jumphost). No blueprint runs Ansible through a jumphost with pinned keys, and ssh does not pass command-line `-o` options to a jump hop, so Ansible would need a new, unproven pinning path.
6. **Validate, then reload only on change.** The node script runs `caddy validate` on the candidate, installs it atomically and reloads Caddy only when the file differs from the live one. A failed validation leaves the running configuration alone.
7. **The certificate is declared in the same package.** `cert.yaml` emits an acme `certificate` when `certificate_names` is set, targeting the VM. Renewals reload Caddy through the certificate's own `reload`. First deployment order: host keys, apply, `foundry certs issue`, apply again.

Tailnet split DNS is not managed here ([#1695](https://github.com/endavis/infrafoundry/issues/1695)).

## Rationale

- **Per-service Tailscale proxy nodes ([#1688](https://github.com/endavis/infrafoundry/issues/1688)):** rejected. One node per UI and tailnet-only reach.
- **A certificate on each device ([#1683](https://github.com/endavis/infrafoundry/issues/1683) to [#1687](https://github.com/endavis/infrafoundry/issues/1687)) as the only path:** rejected. Not every device can take a certificate, and each has its own install method.
- **A resource type for routes:** rejected, see decision 2.
- **A single proxy is a single point of failure.** Direct access to each device by IP keeps working.

## Consequences

- Plan visibility is limited to the DNS descriptions; the Caddyfile itself is checked at apply time.
- Caddy comes from the distribution package; the version depends on the template's release.

Implemented by [#1689](https://github.com/endavis/infrafoundry/issues/1689). Operator documentation: [Reverse Proxy guide](../guides/reverse-proxy.md) and the [blueprint README](https://github.com/endavis/infrafoundry/blob/main/blueprints/reverse-proxy/README.md).
