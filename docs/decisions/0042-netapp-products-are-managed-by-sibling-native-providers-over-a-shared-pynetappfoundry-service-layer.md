---
title: "ADR-0042: NetApp products are managed by sibling native providers over a shared pynetappfoundry service layer"
description: Each NetApp product is its own native provider, all sharing one pynetappfoundry service layer, one optional netapp extra, in-memory credentials and pins, and a read-first direct runner with managed-set deletes
date: 2026-11-27
audience:
  - contributors
tags:
  - adr
---

# ADR-0042: NetApp products are managed by sibling native providers over a shared pynetappfoundry service layer

## Status

Accepted

## Context

InfraFoundry managed an ONTAP cluster only through Ansible (`netapp.ontap`) and blueprint API scripts. Issue #1373 asks for a native `ontap` provider; `aiqum`, `dii` and `console` providers for the other NetApp APIs follow (#1378, #1377, #1379).

pynetappfoundry already speaks all of those APIs: a typed OpenAPI client, `QuerySet` reads, `Mutation` writes with job polling, and TLS fingerprint pinning. It is built around its own configuration directory, though. `Config.__init__` parses every TOML file under that directory and creates `data/<script>/...` under the current directory, credentials come from TOML or `NF_*` variables, and pins are recorded on first use in `<config_dir>/.trust/tls_fingerprints.json`. The OpenAPI spec (about 12 MB) is not part of the wheel; `nf config download-spec` downloads it from the pynetappfoundry repository at the installed tag.

MikroTik ([ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md)) and QNAP ([ADR-0038](0038-qnap-switches-are-managed-over-the-web-uis-json-api-with-firmware-upgraded-by-a-provider-command.md), [ADR-0039](0039-qnap-switch-vlans-and-lacp-groups-are-managed-by-the-direct-runner-with-a-full-list-membership-model-and-fail-closed-lock-out-checks.md)) already solved the same shape: read the device, diff against the YAML, write in order, stop at the first error, and delete only what InfraFoundry applied ([ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)).

## Decision

1. **One provider per NetApp product.** `ontap` is first; `aiqum`, `dii` and `console` are siblings added later. Each has its own resource types, settings key (`provider_settings.<name>`), validator and runner.
2. **One shared service layer.** `providers/_netapp/` holds what the siblings share: the lazy import of pynetappfoundry, the credential and TLS adapter, and per-product service classes (`ontap.py` now). A provider's manager depends on a small service protocol, so tests use an in-memory fake and the library stays behind one seam.
3. **One optional extra, `infrafoundry[netapp]`.** It carries `pynetappfoundry`. The issue text asked for `infrafoundry[ontap]`; the maintainer chose the product-neutral name because every sibling needs the same library. Nothing under `providers/ontap/` or `providers/_netapp/` imports the library at import time; the service factory imports it inside a function and raises an error that names the extra. The providers always register, and a core-only install fails clearly when a run first needs the library.
4. **Credentials are injected in memory.** The adapter subclasses `Config` with an `__init__` that sets only the members the API clients read and never calls the parent constructor. It overrides `get_user`, `get_schema_location` and `get_trust_store`. No secret is written to disk, no TOML is parsed, and no directory is created. A unit test builds the real client, `QuerySet` and `Mutation` through the adapter, so a pynetappfoundry upgrade that breaks it fails CI.
5. **TLS is trusted by pin, CA bundle or an explicit opt-out, and nothing is persisted.** `tls_fingerprint` goes to an in-memory store that never writes (the QNAP convention, not pynetappfoundry's trust-on-first-use file). `ca_bundle` or `verify_ssl: true` turn on chain validation. `verify_ssl: false` with no pin is the unsafe opt-out: it pins whatever certificate the cluster presents for that run only and logs a warning on every run. A pin mismatch becomes an error that says to re-pin `tls_fingerprint`.
6. **The OpenAPI spec is read from `api_spec_dir`.** The default is `~/.infrafoundry/netapp/apis`, with the spec at `<api_spec_dir>/ontap/all.json` and the same layout for every sibling. InfraFoundry never downloads it. A missing spec fails validation and the run, naming the path and the exact download URL, which is built offline from pynetappfoundry's installed version.
7. **A read-first direct runner with managed-set deletes.** `OntapRestRunner` is the ADR-0026 pattern without Terraform: the provider writes an empty `terraform {}` block, and the runner plans, applies, destroys and detects drift. A LIF is matched by (SVM, name); only SVM-scoped LIFs are considered, so cluster and node management LIFs are never touched. Create is read-first because a POST is not idempotent. Writes are sent with job polling. Deletes follow the managed set and `absent: true`; filtered and drift runs are add-only. Updating or deleting the LIF whose live address is the `host` setting is refused.
8. **"Protocols" are a service policy.** ONTAP REST has no protocol field on an IP interface. YAML takes `service_policy`; `protocols: [nfs, cifs]` is a convenience for `default-data-files` and `[iscsi]` or `[nvme_tcp]` for `default-data-blocks`. Mixing file and block protocols, or giving both keys, is a schema error.
9. **Ansible stays for creating the cluster from the console.** Native management starts once the cluster exists. Later increments retire the `ontap-post-cluster` blueprint's Ansible and its API scripts as the matching resource types arrive.

## Rationale

- **One `netapp` provider:** rejected. The products have different authentication, settings, resource types and lifecycles, and one provider would grow a type namespace and a settings block that no single product needs.
- **Keeping Ansible `netapp.ontap`:** rejected for steady-state management. It cannot report a plan against live state in InfraFoundry's model, and it pulls a separate dependency chain. It stays for cluster creation, which has no REST target yet.
- **Writing a temporary pynetappfoundry config directory with the secrets:** rejected. It puts credentials on disk, depends on that library's file formats, and makes the run's side effects harder to test.
- **Runner duplication:** `OntapRestRunner` copies the structure of `MikroTikRestRunner` without its update hook. A shared direct-REST runner base would be a refactor and is left to a follow-up issue.
- **Upgrade risk:** the adapter relies on a few pynetappfoundry internals. The cost is one small subclass and one unit test that exercises the real objects.

## Related Issues

- [#1373](https://github.com/endavis/infrafoundry/issues/1373) native ontap provider backed by pynetappfoundry
- [#1378](https://github.com/endavis/infrafoundry/issues/1378) aiqum provider
- [#1377](https://github.com/endavis/infrafoundry/issues/1377) dii provider
- [#1379](https://github.com/endavis/infrafoundry/issues/1379) console provider

## Related Documentation

- [ONTAP provider](../providers/ontap.md)
- [ADR-0014](0014-opnsense-direct-api-apply-mechanism.md) direct-API apply mechanism
- [ADR-0018](0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md) direct runners delete only what they applied
- [ADR-0022](0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md) a runner that acts on existing machines without creating them
- [ADR-0023](0023-infra-plan-runs-providers-offline-validation-live-checks-stay-in-infra-doctor.md) offline validation in plan, live checks in doctor
- [ADR-0026](0026-mikrotik-routeros-is-managed-natively-over-the-rest-api-by-a-direct-runner.md) MikroTik management
