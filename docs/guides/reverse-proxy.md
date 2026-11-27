---
title: "Reverse Proxy for Device Web UIs"
description: "Serve device web UIs under your own domain with a trusted certificate through the reverse-proxy blueprint"
audience:
  - users
tags:
  - guides
  - blueprints
---

# Reverse Proxy for Device Web UIs

## Overview

The `reverse-proxy` blueprint runs [Caddy](https://caddyserver.com/) on one Proxmox VM and serves each device web UI at `<name>.<dns_domain>` with a Let's Encrypt certificate issued by InfraFoundry ([ACME provider](../providers/acme.md)). One `routes` list generates everything:

- an OPNsense Unbound host override per route, pointing at the proxy;
- the Caddyfile on the VM, with automatic HTTPS off;
- the certificate declaration, installed on the VM for Caddy.

The decision is recorded in [ADR-0041](../decisions/0041-device-web-uis-are-served-by-a-caddy-reverse-proxy-blueprint-whose-routes-generate-the-caddyfile-and-the-internal-dns-records.md).

## Routes

```yaml
variables:
  dns_domain: example.com
  routes:
    - name: nas
      backend: "https://192.0.2.20:443"
      insecure: true
    - name: switch
      backend: "https://192.0.2.21"
      host_header: upstream
      allow_from: ["192.0.2.0/24", "100.64.0.0/10"]
  allowed_networks: []
  certificate_names: ["*.example.com"]
```

| Key | Meaning |
| --- | --- |
| `name` | A DNS label; the route is served at `<name>.<dns_domain>`. Unique per package. |
| `backend` | `http(s)://host[:port]`, without a path. |
| `insecure` | `true` skips verification of the backend's certificate (self-signed UIs). Only for `https` backends. Default `false`. |
| `host_header` | Empty passes the client's `Host` through. `upstream` sends the backend's own host and port. Any other value is sent literally. |
| `allow_from` | CIDRs allowed to reach the route. Empty falls back to `allowed_networks`; when both are empty there is no restriction. |

Every value is validated before it reaches the Caddyfile; an invalid route fails the step with the route named. The VM has at least 2 vCPUs: the blueprint refuses `cores` below 2.

Some UIs check the `Host` header or redirect to their own address. Set `host_header: upstream` (or a literal) for those, and `insecure: true` when the backend serves a self-signed certificate.

## Deploying

The order matters on the first deployment:

1. `foundry secrets host-keys --env <env>` pins the VM's SSH host key.
2. `foundry infra apply --env <env>` creates the VM and the DNS records, installs Caddy and the certificate directory. The Caddyfile step warns that the certificate files are missing; it is retried on the next apply.
3. `foundry certs issue --env <env>` issues the certificate and installs it on the VM.
4. `foundry infra apply --env <env>` again writes the Caddyfile and reloads Caddy.

After that, every apply renders the Caddyfile again, validates it with `caddy validate`, and reloads Caddy only when it changed. A file that fails validation leaves the running configuration alone. Renewals (`foundry certs renew`) reload Caddy through the certificate's own `reload`.

## Certificates

`certificate_names` declares an acme `certificate` for the proxy VM (see [Install Target for Certificates](../providers/proxmox.md#install-target-for-certificates)). The acme provider and its settings must be configured for the environment ([ACME provider](../providers/acme.md)). Leave `certificate_names` empty to deploy without a certificate resource.

## DNS

Each route adds an Unbound host override in the environment's OPNsense, resolving `<name>.<dns_domain>` to the proxy. No public record is created. Clients on a tailnet need a split-DNS route for the domain to the internal resolver. That route is set outside InfraFoundry; managing it is tracked in [#1695](https://github.com/endavis/infrafoundry/issues/1695).

## Firewall

The proxy must be reachable on TCP 443 from the networks that use it. Add a rule to the firewall package, for example:

```yaml
firewall:
  rules:
    - action: pass
      interface: <tailscale-interface-key>   # the interface key of your tailnet network
      protocol: TCP
      source_net: "100.64.0.0/10"
      destination_net: "192.0.2.70/32"       # the proxy VM
      destination_port: "443"
      description: "tailnet to reverse proxy"
```

## What `infra plan` shows

`infra plan` runs offline (ADR-0023), so it never connects to the VM. A route change still shows in the plan: adding or removing a route adds or removes a host override, and the override's description carries a summary of the route (backend, `insecure`, `host_header`, allowed networks), so a changed backend or option is an in-place update of that override. The Caddyfile itself is validated at apply time.

## Trade-offs

One proxy is a single point of failure for the names it serves. Direct access to each device by its address keeps working.

## Related

- [Blueprints](../configuration/blueprints.md)
- [ACME provider](../providers/acme.md)
- [Proxmox provider](../providers/proxmox.md#install-target-for-certificates)
- [SSH Host Key Checking](ssh-host-key-checking.md)
