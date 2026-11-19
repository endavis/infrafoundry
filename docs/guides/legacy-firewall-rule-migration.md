---
title: "Legacy Firewall Rule Migration"
description: "Export legacy OPNsense filter rules to InfraFoundry YAML and cut over safely"
audience:
  - users
tags:
  - guides
  - opnsense
---

# Legacy Firewall Rule Migration

## Overview

OPNsense 26.x keeps two rule systems. Legacy rules live in the `<filter><rule>` section of `config.xml` and are shown on the classic rule pages. Automation rules live in the MVC `firewall/filter/*` controller, which InfraFoundry manages (see [ADR-0015](../decisions/0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md)). The MVC API does not list legacy rules, so `foundry config migrate --component firewall.rules` alone never sees them.

`--include-legacy` reads the legacy rules and writes them as `firewall.rules` YAML, in the order they have on the box. It is read-only: one search of the automation rules plus one GET of the configuration backup. Nothing is written to the firewall.

## Two Paths

| Path | What it does |
|------|--------------|
| OPNsense migration page (`/ui/firewall/migration`, GUI only, no REST surface) | Converts legacy rules to automation rules in place on the box. InfraFoundry does not own the result. |
| `foundry config migrate ... --include-legacy` | Writes reviewable YAML. Applying it creates rules InfraFoundry owns (`[infrafoundry:<name>]` description suffix and the `infrafoundry` category marker). |

Do not use both on the same rules: you would get duplicates.

## Export

```bash
foundry config migrate --env fw-test --provider opnsense --component firewall.rules \
  --include-legacy --dry-run
```

Review the output, then write it:

```bash
foundry config migrate --env fw-test --provider opnsense --component firewall.rules \
  --include-legacy
```

The API key needs the backup-download privilege, because `config.xml` is fetched from `core/backup/download/this`. The document holds secrets, so it is parsed in memory with a hardened XML parser and is never logged or written to disk. Without the privilege the command reports it, still emits the automation rules and exits non-zero.

### Partial exports

Anything that cannot be carried over is listed, one line per rule and field. Without `--allow-partial` the command exits 1 and writes nothing. With `--allow-partial` it writes the YAML and lists the same issues in a header comment:

```bash
foundry config migrate --env fw-test --provider opnsense --component firewall.rules \
  --include-legacy --allow-partial
```

Review every listed item before applying. A rule exported without its `sched` or `os` match is broader than the original.

## Mapping

| Legacy element | YAML field |
|----------------|------------|
| `type` | `action` |
| `descr` | `description` (an `[infrafoundry:...]` marker is removed and reported) |
| `disabled` | `enabled: false` |
| `interface` | `interface` (one identifier from the interfaces, interface groups or `openvpn`, `wireguard`, `enc0`) |
| `floating`, `quick`, `direction` | `state_policy: floating`, `quick`, `direction` (a non-floating rule gets `quick: true`, `direction: in`) |
| `ipprotocol`, `protocol` | `ipprotocol` (default `inet`), `protocol` (upper-cased, default `any`) |
| `source`, `destination` | `source_net` / `destination_net` (`any`, address or network keyword, verbatim), `*_not`, `*_port` |
| `statetype` | `statetype` |
| `category` | `categories` (names or UUIDs resolved to category UUIDs) |
| other elements named like an MVC field (`gateway`, `icmptype`, `max-src-nodes`, ...) | the underscored field |

Rules get `sequence` values in document order, after the highest `sequence` already on the box, so their relative order is kept and they sort behind existing automation rules. Names come from the description (lowercase slug, at most 48 characters, `-2`, `-3` on a clash with any resource in the environment); a rule without a description is named `<interface>-rule-<n>` or `floating-rule-<n>`.

The value vocabulary (network keywords passed verbatim, protocol casing) follows the legacy layout and has not been proven against a real export. Check the first dry run against the box.

### Not exported

Reported, and the rest of the rule is still exported, for `sched`, `dnpipe`, `pdnpipe`, `os`, `associated-rule-id` and any other non-empty unknown element. Skipped and reported:

- a floating rule on several interfaces (`interface` is single-valued in the schema);
- a rule naming an interface that does not exist on the box;
- a rule with an unsupported action.

Unmanaged automation rules (those without the identity suffix) are still not exported, as before.

## Cutover Order

pf evaluates, all quick, first match wins:

1. automation floating rules;
2. legacy floating rules;
3. automation interface rules;
4. legacy interface rules.

Safe order:

1. `foundry infra plan --env <env> --add-only` and review the diff.
2. Apply the exported set while the legacy rules still exist. Nothing is lost if the export is wrong.
3. Verify with `plan` and `pfctl -sr` on the box.
4. Disable the legacy rules by hand and watch traffic.
5. Delete the legacy rules.

The reverse order opens a policy gap. A legacy floating quick rule is evaluated before automation interface rules, so a legacy floating block can shadow an exported interface pass until it is disabled; check this before disabling anything. (Measured with low sequence numbers.)
