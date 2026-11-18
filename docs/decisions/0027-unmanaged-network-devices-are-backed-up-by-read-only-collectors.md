---
title: "ADR-0027: Unmanaged network devices are backed up by read-only collectors"
description: Unmanaged network devices are backed up by read-only collectors that store SOPS-encrypted exports in the config repo, outside the provider and state model
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0027: Unmanaged network devices are backed up by read-only collectors

## Status
Accepted

## Context
Some network devices in an environment are never managed by InfraFoundry: an ISP-supplied ONT or router that the ISP manages remotely, or a travel OpenWrt router. Their configuration still matters (WAN VLANs, LAN subnets, port forwards), and hand-made captures go stale. Issue #1481 asks for a read-only backup of such devices into the config repo. Two designs were considered: a read-only provider, and a separate collector concept.

## Decision
Add **collectors**: read-only readers of unmanaged devices that live outside the provider, runner and state model, in `src/infrafoundry/collectors/`. `foundry infra collect --env <env> [--device/-d NAME]` runs them.

- **Configuration.** A `collectors:` section in `envs/<env>/settings.yaml` lists devices (name, type, address, credentials as `secret://env_secrets/...`) and an optional `output_dir`, default `device-configs/<env>`, which must stay inside the config repo and outside `envs/` (every subdirectory of an environment is otherwise discovered as a provider).
- **Types.** `huawei-ont-web`, `routeros-rest` (reusing the MikroTik REST client) and `openwrt-ssh` (the `ssh` binary, key authentication only, host-key checking left on). A plain in-package registry maps type to factory; entry-point registration is the later extension path.
- **Encrypted at rest.** Secret-bearing artifacts are SOPS-encrypted whole-file (binary input, JSON output) to `<name>.sops.json`. The plaintext exists only in a temp directory removed on every path. OpenWrt UCI exports are both redacted and encrypted.
- **Change detection.** The previous file is decrypted in memory and the plaintext hashes are compared. Unchanged artifacts are not rewritten, so there is no ciphertext churn in git. Volatile output (the RouterOS export timestamp, `ip addr` lease lifetimes) is normalised first.
- **Lock-out safety.** The Huawei collector makes exactly one login attempt per run on one session, never retries, and always logs out. A device failure is isolated; the command exits non-zero after printing the summary.
- **No state.** Collectors write no state database rows and generate no Terraform.

## Rationale
A provider carries plan, apply and state semantics that a read-only backup does not have, and a backup of an unmanaged device has no desired state to diff against. A separate concept keeps the provider contract unchanged. Hash comparison on the plaintext avoids a sidecar fingerprint file that could drift from its ciphertext or publish a guessable hash. An in-package registry avoids plugin scaffolding for three in-tree types.

## Related Issues

- Issue #1481: back up unmanaged network device configs

## Related Documentation

- [Device config collectors](../guides/device-config-collectors.md)
- [ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md)
