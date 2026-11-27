---
title: "ONTAP Provider"
description: "Manage the data LIFs of a NetApp ONTAP cluster over its REST API through pynetappfoundry, with a pinned certificate, a plan against the live cluster, managed-set deletes and a lock-out refusal"
audience:
  - users
tags:
  - providers
---

# ONTAP Provider

The ONTAP provider manages the data LIFs (IP interfaces) of one NetApp ONTAP cluster per environment over the cluster's REST API. It reads the cluster, compares it with your YAML and creates, updates or deletes LIFs. It does not generate Terraform: `infra plan` and `infra apply` talk to the cluster directly, and `infra drift detect` reports out-of-band changes. The decisions and the rejected alternatives are in [ADR-0042](../decisions/0042-netapp-products-are-managed-by-sibling-native-providers-over-a-shared-pynetappfoundry-service-layer.md).

`ontap` is the first of a family of NetApp providers (`aiqum`, `dii` and `console` follow) that share one service layer and one extra. Creating the cluster itself from the console stays with Ansible.

## Install

The provider talks to the cluster through [pynetappfoundry](https://github.com/endavis/pynetappfoundry), which is an optional extra:

```bash
pip install 'infrafoundry[netapp]'
```

Without the extra the provider still registers, and a run that needs the cluster fails with a message that names the extra.

## Get the OpenAPI spec

pynetappfoundry validates against the ONTAP OpenAPI spec (about 12 MB), which is not part of the package. InfraFoundry reads it from `<api_spec_dir>/ontap/all.json`, by default `~/.infrafoundry/netapp/apis/ontap/all.json`. The spec is the ONTAP spec file of the pynetappfoundry repository's example config, at the tag of the installed version. When it is missing, `infra doctor` and every run name the path and the exact download URL. The spec is not a secret, and InfraFoundry never downloads it for you.

## Settings

```yaml
provider_settings:
  ontap:
    host: cluster1.example.com            # the cluster management LIF
    username: secret://env_secrets/ontap/username
    password: secret://env_secrets/ontap/password
    tls_fingerprint: "AB:CD:EF:..."       # SHA-256 of the cluster's certificate
    # ca_bundle: certs/ca.pem             # validate the chain against this CA bundle instead
    # verify_ssl: true                    # or against the system CA store
    # timeout: 30
    # api_spec_dir: ~/.infrafoundry/netapp/apis
```

| Key | Meaning |
| :-- | :-- |
| `host` | Host name or address of the cluster management LIF. No scheme, no path. |
| `username`, `password` | Must be `secret://` references; a plaintext value is rejected. |
| `tls_fingerprint` | SHA-256 of the cluster's certificate, with or without `:` separators. Pins the certificate and skips chain validation. |
| `ca_bundle` | A CA bundle file; chain and host name are validated. A relative path starts at the config repository. |
| `verify_ssl` | `true` validates the chain against the system CA store. `false` with no pin is the unsafe opt-out, see below. |
| `timeout` | Seconds per request, 1-600, default 30. |
| `api_spec_dir` | Directory that holds the spec, as `<api_spec_dir>/ontap/all.json`. Default `~/.infrafoundry/netapp/apis`. |

Exactly one way to trust the cluster is required: `tls_fingerprint`, `ca_bundle`, `verify_ssl: true` or the opt-out. A pin cannot be combined with `ca_bundle` or `verify_ssl: true`, and `ca_bundle` cannot be combined with `verify_ssl: false`.

Take the pin from the cluster once, and compare it with the certificate you expect:

```bash
openssl s_client -connect cluster1.example.com:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256
```

**The opt-out.** `verify_ssl: false` with no pin pins whatever certificate the cluster presents for that run only, never writes it anywhere, and logs a warning on every run. It protects nothing against an attacker who is already on the path at the first request; use it only to get started.

**A mismatch.** When the certificate no longer matches the pin, the run fails with a message that says to re-pin `tls_fingerprint`. Nothing is sent before the check, so credentials do not reach the wrong host.

Credentials and the pin are held in memory for the run. pynetappfoundry's own configuration directory is not used, and nothing is written to disk.

## Resources

One resource type: `network.ip.interface`, a data LIF in an SVM.

```yaml
resources:
  - name: nfs-a
    type: network.ip.interface
    provider: ontap
    config:
      svm: svm1
      address: 192.0.2.10
      netmask: 24                  # a prefix length or 255.255.255.0
      home_node: cluster1-01
      home_port: e0d
      protocols: [nfs, cifs]       # or service_policy: default-data-files
      auto_revert: true

  - name: old-lif
    type: network.ip.interface
    provider: ontap
    config:
      svm: svm1
      absent: true                 # delete it
```

| Field | Meaning |
| :-- | :-- |
| `svm` | Required. The SVM that owns the LIF. Part of the identity. |
| `name` | The LIF name. Defaults to the resource name. Part of the identity. |
| `address`, `netmask` | Required. `netmask` is compared as a prefix length, so `24` and `255.255.255.0` are equal. |
| `home_node`, `home_port` | Required. The home port is sent together with its node. |
| `service_policy` | The service policy, for example `default-data-files` or `default-data-blocks`. |
| `protocols` | A convenience for `service_policy`, see below. |
| `auto_revert` | Whether the LIF returns to its home port by itself. |
| `absent` | `true` deletes the LIF. It may carry only `svm` and `name`. |

**Protocols are a service policy.** ONTAP REST has no protocol field on an IP interface; since ONTAP 9.18 a service policy decides what a LIF serves. `protocols: [nfs, cifs]` means `service_policy: default-data-files`, and `[iscsi]` or `[nvme_tcp]` means `default-data-blocks`. Giving both keys, an unknown protocol, or a mix of file and block protocols is a schema error: declare a second LIF.

Only the fields you declare are compared. A field you leave out keeps whatever the cluster has.

## Identity and deletes

A LIF is matched by (`svm`, `name`). Only SVM-scoped LIFs are considered, so the cluster and node management LIFs are never touched, and moving a LIF to another SVM is a delete plus a create.

Undeclared LIFs are kept and listed in the plan as `unmanaged (kept)`, but only for SVMs your YAML mentions. InfraFoundry deletes a LIF it did not find in the YAML only when it applied that LIF before and the YAML no longer declares it (the managed set, [ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)), or when you set `absent: true`. A filtered run (`--resource`) and a drift run only add and update, never delete.

Create is read-first: a LIF is created only when the plan, built from a read of the same run, did not find it. Writes wait for the cluster's job to finish, and a run stops at the first error and lists the steps that had completed.

## Refusals and warnings

- **Management LIF.** Updating or deleting the LIF whose live address is the `host` setting is refused before any write, because the change could cut the connection InfraFoundry runs over. If `host` cannot be resolved, a plan with an update or delete is refused too.
- **Off the home port.** A declared LIF that is not on its home port gets a warning. ONTAP keeps it where it is until it is reverted.

## What is not managed yet

Only data LIFs. Cluster and node management LIFs, routes, broadcast domains, SVMs, volumes and the other ONTAP objects are not managed by this provider yet. Creating the cluster from the console stays with Ansible.

## Checks

`infra doctor` checks the settings, the secrets, the spec file, that the cluster answers (it reports the ONTAP version) and that the SVMs, nodes and ports your YAML names exist.

## Verification status

The request paths and bodies are checked in unit tests against the real pynetappfoundry objects, with a small spec and no cluster. The first run against a live cluster, including the home port and node bodies, is recorded here by the maintainer after it happens.
