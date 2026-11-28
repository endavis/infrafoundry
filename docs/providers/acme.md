---
title: "ACME Provider"
description: "Issue per-device Let's Encrypt certificates with DNS-01 on Cloudflare, keep them SOPS-encrypted beside the package that declares them, and install them on a host over SSH"
audience:
  - users
tags:
  - providers
---

# ACME Provider

The `acme` provider declares certificates for your devices. `foundry certs issue` orders each one from Let's Encrypt with the DNS-01 challenge on Cloudflare, keeps the certificate and its key SOPS-encrypted in the package that declares it, installs it on the target and checks that the target serves it. Nothing is exposed to the internet: DNS-01 needs only a DNS record, not an inbound connection. The decisions and the rejected alternatives are in [ADR-0040](../decisions/0040-per-device-lets-encrypt-certificates-are-issued-by-infrafoundry-over-acme-with-cloudflare-dns-01-and-installed-through-an-optional-provider-hook.md).

`infra apply` never issues a certificate. The provider writes an empty `terraform {}` block; only `foundry certs` talks to the CA and rewrites the encrypted files. What is covered today: issue, install and unattended renewal on a [`host`](host.md#install-target-for-certificates), a [Proxmox `vm` or `node`](proxmox.md#install-target-for-certificates), a [MikroTik device](mikrotik.md#install-target-for-certificates), a [NetApp ONTAP `cluster` or `svm`](ontap.md#install-target-for-certificates) and an [OCI `instance`](oci.md#install-target-for-certificates).

A VM target names the VM instead of a host. Its SSH host key must be pinned first with `foundry secrets host-keys`:

```yaml
target:
  provider: proxmox
  resource: app-01
  fullchain_path: /etc/ssl/infrafoundry/app.fullchain.pem
  key_path: /etc/ssl/infrafoundry/app.key
  reload: [systemctl, reload, caddy]
```

## Settings

```yaml
# envs/prod/settings.yaml
providers:
  - acme
  - host
provider_settings:
  acme:
    agree_tos: true                  # required: you accept the CA's terms of service
    email: admin@example.com         # optional: the CA's expiry and problem notices
    directory: staging               # staging (default) | production | https://...
    renew_before_days: 30            # optional, 1-60
    cloudflare:
      api_token: secret://env_secrets/acme/cloudflare_api_token
      zone_id: secret://env_secrets/acme/cloudflare_zone_id
    propagation:                     # optional
      timeout: 180                   # seconds to wait for the TXT records to be visible
      interval: 5
    # doh:                           # optional, off by default: DNS-over-HTTPS JSON resolvers
    #   - https://cloudflare-dns.com/dns-query
    #   - https://dns.google/resolve
```

| Key | Meaning |
| :--- | :--- |
| `agree_tos` | Must be `true`. |
| `directory` | `staging` is the default so a first run cannot spend production rate limits. Set `production` when the staging run works. A URL selects another ACME CA. |
| `cloudflare.api_token`, `cloudflare.zone_id` | Required, and must be `secret://` references. No secret name is hard-coded: point them at any secret path, including one an existing OPNsense validation already uses. |
| `renew_before_days` | A certificate with this many days or fewer left is issued again. Default 30. |
| `propagation` | `foundry certs` queries the zone's authoritative nameservers directly (recursion off, UDP with a TCP retry) until every one of them serves every TXT value, then asks the CA. There is no fixed sleep. |
| `doh` | Optional and off by default. When set, these DNS-over-HTTPS resolvers are polled only after the authoritative nameservers all serve the value, each stage with its own `propagation.timeout`. Public resolvers are not the default because one queried before the record exists can cache the negative answer and keep failing the check. |

Create a dedicated Cloudflare API token with the permission Zone.DNS:Edit on the one zone that holds your names. The token must also be able to read the zone itself, because the zone's nameservers are looked up with it; add Zone:Read if Cloudflare refuses the lookup. The host running `foundry certs` needs outbound DNS (UDP and TCP port 53) to the zone's nameservers. One zone per environment is supported. Validation messages name keys, never values, and the token is scrubbed from every error.

Every TXT record InfraFoundry creates carries the comment `infrafoundry-acme <certificate name>` and is deleted again whatever happens. Records left by a crashed run are removed when the next order starts.

## Declaring a certificate

A certificate is a resource of the `acme` provider and must live in a package, because its key goes into that package's `secrets.yaml`.

```yaml
# envs/prod/acme/proxy/infrafoundry.yml
name: proxy
provider: acme
resources: [certificate.yaml]
```

```yaml
# envs/prod/acme/proxy/certificate.yaml
certificate:
  - name: proxy-cert
    names: ["*.example.com", "example.com"]   # 1-100 names, at most one leading "*." label, no IP addresses
    key_type: ec-p256                         # ec-p256 (default) | rsa-2048
    renew_before_days: 30                     # optional, overrides the provider setting
    target:
      provider: host
      resource: proxy-01                      # a host resource of the environment
      fullchain_path: /etc/ssl/infrafoundry/proxy.fullchain.pem   # cert_path and/or fullchain_path
      key_path: /etc/ssl/infrafoundry/proxy.key
      owner: root
      group: root
      cert_mode: "0644"
      key_mode: "0600"
      sudo: false
      reload: ["systemctl", "reload", "caddy"]   # an argv list, never a shell string
      verify: {port: 443, server_name: proxy.example.com}
```

`cert_path` receives the leaf certificate; `fullchain_path` receives the leaf and the intermediate chain. The directories must already exist on the target: InfraFoundry never creates directories, and a missing one fails the install with the path named (the certificate stays stored, so the next run retries only the install). Paths must be absolute and distinct, and may hold only letters, digits and `._/@+:-`. `verify` is optional: without it the install is not checked. `server_name` is required when every name is a wildcard; otherwise it defaults to the first plain name.

`infra plan`, `infra apply` and `infra doctor` check the declaration and the settings offline, and name the exact problem.

## Commands

```bash
foundry certs status --env prod              # reads the encrypted store only
foundry certs issue --env prod               # every certificate that is missing, due or not installed
foundry certs issue --env prod proxy-cert    # only this one
foundry certs issue --env prod --force       # issue again even when the stored one is current
foundry certs renew --env prod               # unattended: only what is due, never issued or not installed
foundry certs renew --env prod --dry-run     # report what would be done; no lock, no network
```

`issue` holds the environment lock (a long run keeps it alive), processes certificates one at a time and continues past a failure. For each one the order is: issue, write the encrypted entry, install, verify, record `installed_sha256`, record a state row. A certificate that is stored but not installed gets an install-only retry the next time, so a failed install never costs a second order from the CA.

| Exit code | Meaning |
| :--- | :--- |
| `0` | Every certificate is current and installed. |
| `1` | One or more certificates failed. |
| `2` | Usage error: unknown certificate name, missing or invalid settings. |
| `75` | The environment lock is held. |

The encrypted store changes in your config repo: commit it after a run.

### Renewing unattended

`renew` is the command for a timer. It processes the certificates `issue` would without `--force`: those with the renewal window or fewer days left, never issued, declared with other names, key type or directory than the stored one, or stored but not installed (an install-only retry). It differs from `issue` on purpose:

- There is no `--force`: an unattended run never orders a certificate that is current.
- When nothing is due it prints nothing, takes no lock, contacts nothing and exits `0`, so a daily timer is cheap and quiet. Only certificates that were acted on or failed are printed.
- `--dry-run` prints what would be done (`would issue` or `would install`, with the reason), takes no lock and contacts no CA, DNS host or target. It exits `1` only when a declaration is invalid.
- A held lock exits `75` instead of waiting (unless `--lock-timeout` is set), so the next run retries.

Example systemd units. `SuccessExitStatus=75` keeps a held lock from marking the unit failed:

```ini
# /etc/systemd/system/foundry-certs-renew.service
[Unit]
Description=Renew InfraFoundry certificates

[Service]
Type=oneshot
WorkingDirectory=/opt/infrafoundry
Environment=INFRAFOUNDRY_CONFIG_REPO=/opt/infrafoundry-config
ExecStart=/usr/local/bin/foundry certs renew --env prod
SuccessExitStatus=75
```

```ini
# /etc/systemd/system/foundry-certs-renew.timer
[Unit]
Description=Daily InfraFoundry certificate renewal

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Or with cron (no output means nothing was due; cron mails any output):

```cron
17 3 * * * cd /opt/infrafoundry && INFRAFOUNDRY_CONFIG_REPO=/opt/infrafoundry-config foundry certs renew --env prod
```

The unit needs the SOPS age key and SSH access to the targets, as an interactive run does. Renewed certificates change the encrypted store, so commit the config repo from your own routine.

### Plan warning, doctor check and events

- `infra plan` prints a warning for each certificate that is due, expired, never issued, unreadable or not installed. It reads the encrypted store offline and never fails the plan.
- `infra doctor` checks that the Cloudflare token can read the zone's DNS records (one read-only call). A failure names the HTTP status, never the token or the zone id.
- `foundry certs` publishes `CERTIFICATE_ISSUED` and `CERTIFICATE_INSTALLED` per certificate and `CERTIFICATE_FAILED` on a failure, to the event bus handlers configured for the environment. The payload holds the certificate name, its names, expiry and SHA-256 fingerprint (and the error text on failure), never a key or the token.

## Where things are stored

| What | Where |
| :--- | :--- |
| Certificate, chain, key, expiry, fingerprint | The declaring package's `secrets.yaml`, under `variables.acme_certificates.<name>` |
| ACME account key and URI | The environment's `secrets.yaml`, under `acme.accounts.<directory>` |
| State row | `ACTIVE`, with names, expiry, fingerprint and target. No key material. |

Writes are atomic (`sops set` on a copy, then a rename), and no plaintext key ever touches disk or a command line. `acme_certificates` never reaches package variables, script environments or templates.

## Related

- [Host provider](host.md#install-target-for-certificates)
- [Proxmox provider](proxmox.md#install-target-for-certificates)
- [OCI provider](oci.md#install-target-for-certificates)
- [MikroTik provider](mikrotik.md#install-target-for-certificates)
- [ONTAP provider](ontap.md#install-target-for-certificates)
- [Reverse Proxy for Device Web UIs](../guides/reverse-proxy.md): the first consumer, a Caddy VM that serves device UIs with this certificate
- [ADR-0040](../decisions/0040-per-device-lets-encrypt-certificates-are-issued-by-infrafoundry-over-acme-with-cloudflare-dns-01-and-installed-through-an-optional-provider-hook.md)
- [CLI reference: certs](../usage/cli-reference.md#certs-group-foundry-certs)
