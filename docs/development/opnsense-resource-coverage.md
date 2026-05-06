# OPNsense Provider Resource Coverage

This document tracks which OPNsense resource types are managed by the InfraFoundry provider today, which are known gaps, and how to plan a box-to-box migration when the provider doesn't yet cover every section of `config.xml`.

It exists to support the decision in [ADR-0013](../decisions/0013-opnsense-full-iac-migration.md): **drop-in OPNsense replacement should be achievable by re-applying YAML against a new endpoint.** Closing the gaps below is a prerequisite for that to work end-to-end.

## Coverage matrix

Source of truth for "supported": `OPNsenseProvider.get_resource_types()` in `src/infrafoundry/providers/opnsense/__init__.py`.

| Section in `config.xml` | InfraFoundry resource type | Status |
| --- | --- | --- |
| `<vlans>` | `vlans` | Supported (direct-API via `OPNsenseDirectRunner`; ADR-0014, #709) |
| `<OPNsense>/Firewall/Alias` | `aliases` | Supported (terraform write path; config-migrate extractor added in #747). YAML schema covers the base fields (`name`, `type`, `description`, `content`, `enabled`) plus type-specific `proto` (geoip), `updatefreq` (urltable / urltable_ports), `categories`, `counters`, and `interface` (dynipv6host); these optional fields are emitted only when the live record carries a non-default value, so existing operator YAML round-trips unchanged. System-internal aliases (`type: internal` per-interface auto-generated entries like `__lan_network`, and `type: external` system-managed tables like `bogons` / `sshlockout`) are silently filtered from extractor output — OPNsense regenerates them server-side and they're not operator-writable via the alias controller; including them would produce a YAML block the terraform write path would attempt to (re)create on apply. |
| `<filter>/rule` (MVC `firewall/filter/*`) | `firewall_rules` | Supported (direct-API; #742). Identity is encoded as a **suffix** in the rule description — `<operator description> [infrafoundry:<name>]` — and every managed rule also carries the OPNsense `infrafoundry` category UUID in its multi-valued `categories` list as a fleet-wide marker (the MVC multi-value field empirically coexists with operator-set categories without collision; the marker is **appended** to the operator list, not overwriting it). Live rules without the suffix tag are unmanaged and ignored by the diff (do not edit a managed rule's description in the GUI — that breaks identity parsing). Targets the **MVC stateful filter controller**, not the legacy `<filter>` block; OPNsense 26.x ships both systems and they do not auto-cross-populate. Migrating an existing legacy ruleset to MVC is a one-time GUI operator step (no REST surface for migration). The terraform path (`firewall_rules.tf.j2` + `browningluke/opnsense_firewall_rule`) was retired in the same PR — no `kind: legacy` shim. Field coverage spans the full MVC `getRule` template (~50 fields) per [ADR-0015 §"Field coverage"](../decisions/0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md#field-coverage); `sched`, `shaper1`, `shaper2` punted to follow-up issues. |
| `<OPNsense>/Kea` (DHCPv4 subnets) | `kea_subnet` | Supported |
| `<OPNsense>/Kea` (DHCPv4 reservations) | `kea_reservation` | Supported |
| `<OPNsense>/Kea` (DHCPv6 subnets) | `kea_dhcp6_subnet` | Supported |
| `<OPNsense>/Kea` (DHCPv6 reservations) | `kea_dhcp6_reservation` | Supported |
| `<OPNsense>/unboundplus/hosts/host` | `unbound_host_override` | Supported (terraform write path; config-migrate extractor added in #748). YAML schema covers the base fields (`hostname`, `domain`, `enabled`, `server`, `description`) plus record-type-specific `rr` (`A` / `AAAA` / `MX`), `mxprio` (MX priority, preserved as a string to match `updatefreq`), and `mx` (MX target). The extended fields are emitted only when the live record carries a non-default value, so existing 5-field operator YAML round-trips unchanged. The extractor synthesizes the operator-facing `name` as `<hostname>-<dot-replaced-domain>` (lowercased; e.g., `web.example.com` → `web-example-com`) so the result is a valid terraform identifier — the template's `replace('-', '_')` filter accepts hyphens but not dots. When `rr` is non-default, the record type is appended as a suffix (e.g., `web-example-com-aaaa`, `mail-example-com-mx`) so an A and an AAAA record on the same hostname don't collide on the same key. No system-internal filter is needed — host overrides are entirely operator-defined (unlike aliases, which carry OPNsense-internal `internal`/`external` types). |
| `<dhcpd>` (legacy ISC) | `dhcp_static_maps` | Supported (legacy; new deployments should use Kea) |
| `<interfaces>` | `interface_assignments` | Supported (direct-API; #711 read-only ship, #716 forked PHP controller, #717 ADR-0014 amendment, #720 production conversion). Write-path mechanism per [ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions): server-side-validated REST via the in-tree `AssignSettingsController.php` fork. Production conversion of `OPNsenseDirectRunner.apply()` completed in #720 (2026-05-03); logical-to-physical interface mapping is now applied automatically by `foundry infra apply`. |
| `<nat>/outbound/rule`, `<nat>/onetoone/rule`, and `<nat>/rule` | `nat_rules` (`kind: outbound` / `kind: one_to_one` / `kind: port_forward`) | Supported (all three kinds, direct-API; #713 outbound + 1:1; #725 port_forward). Identity is encoded as a **suffix** in the rule description — `<operator description> [infrafoundry:<name>]` — and every managed rule also carries the OPNsense `infrafoundry` category as a fleet-wide marker. Live rules without the suffix tag are unmanaged and ignored by the diff (do not edit a managed rule's description in the GUI — that breaks identity parsing). Note: port_forward uses the OPNsense stock `DNatController` at `firewall/d_nat` (snake-case routing); the original 2026-05-03 probe used `firewall/dnat` (concatenated) and incorrectly concluded the controller was absent. |
| `<OPNsense>/Gateways` | `gateways` | Supported (direct-API; #721). Identity is the natural-key `name` (OPNsense enforces uniqueness server-side). Dynamic/virtual gateways synthesized from interface DHCP state (e.g., `WAN_DHCP`, `WAN_DHCP6`) are silently excluded from the diff — they're recreated from interface state on reconfigure and must not appear in YAML. |
| `<staticroutes>/route` | `static_routes` | Supported (direct-API; #722). Identity is the natural-key tuple `(network, gateway)` (OPNsense exposes no server-unique `name` field on routes — operator-facing YAML `name` is metadata only and never travels on the wire). The `gateway` field cross-references either a managed `gateways` resource declared in YAML or a live system gateway (e.g., `WAN_DHCP`, `WAN_DHCP6`); the validator enforces protocol-family match (IPv4 CIDR → IPv4 gateway, IPv6 CIDR → IPv6 gateway). |
| `<virtualip>/vip` | `virtual_ips` | Supported (direct-API; #723). Identity is the natural-key tuple `(interface, mode, address, vhid)` — including `mode` and `vhid` lets multiple CARP VIPs coexist on the same interface+address (different `vhid`s) and distinguishes ipalias from CARP at the same IP. Modes are `ipalias` / `carp` / `proxyarp` only (the issue body's draft also listed `alias` / `other`; the live probe is authoritative — those values are not accepted). The `interface` field cross-references either a managed `interface_assignments` resource declared in YAML or a live overview interface. **CARP `password` is the first direct-API secret-bearing field** — operators provide a `secret://env_secrets/<dotted/path>` URI in YAML and the password is resolved at apply time by the new `EnvSecretsBackend` (see [ADR-0014 §"Secrets handling"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#secrets-handling)); plaintext values in YAML are accepted but produce a soft warning. |
| `<OPNsense>/unboundplus/hosts/host/alias` | `unbound_host_alias` | Supported (direct-API; #724). Identity is the natural-key tuple `(host_uuid, hostname)` — OPNsense keys aliases by parent host_override UUID; the operator-facing YAML uses `(host_name, hostname)` and the component manager resolves `host_name` → parent UUID at apply time by reading `searchHostOverride` rows. The `host` field cross-references either a managed `unbound_host_override` resource declared in YAML or a live host override (`hostname` or `hostname.domain` form). |
| `<OPNsense>/unboundplus/domains/domain` | — | **Merged into `unbound_forward`** (per OPNsense API; see [ADR-0013 §"Implementation order" #5 amendment](../decisions/0013-opnsense-full-iac-migration.md#implementation-order), #724). A `Forward` entry with `type=forward, domain="example.com"` is what the GUI calls a "domain override"; with `domain=""` it is a global forwarder. There is no separate REST surface for domain overrides. |
| `<OPNsense>/unboundplus/forwarding/host` | `unbound_forward` | Supported (direct-API; #724). Identity is the natural-key tuple `(type, domain, server, port)` — including `type` (forward / dot) lets DoT and plain forwarders coexist for the same domain/server/port. **Envelope key on the wire is `dot` regardless of `type` value** (counter-intuitive but empirically confirmed). Field names match the wire format verbatim — `verify` not `verify_cn`; `forward_tcp_upstream` not `forward_tls_upstream`. Empty `domain` = global forwarder; non-empty = per-domain forwarder (a.k.a. domain override). |

Sections intentionally **out of IaC scope** (per ADR-0013): `<hasync>`, `<openvpn>`/`<OPNsense>/OpenVPN`, `<ca>`/`<cert>`, `<OPNsense>/AcmeClient`, `<gres>`, `<gifs>`, `<laggs>`, `<bridges>`, `<ppps>`, `<wireless>`. These are set-once items and are migrated via selective `config.xml` import on the target box.

## Box-to-box migration runbook (template)

This template assumes you are cutting over a current box (`OLD`) to a new box (`NEW`) and want the result to be a drop-in replacement, with subsequent migrations between same-spec boxes being trivial.

### Prerequisites

1. The OPNsense provider supports every resource type your `OLD` config uses (see matrix above; close any gaps first).
2. Both boxes are reachable on the network and admin credentials work.
3. You have downloaded `OLD`'s `config.xml` (System → Configuration → Backups → Download).
4. You have the `NEW` box installed with a base interface accessible from your management network.

### Steps

1. **Extract**: run `foundry config migrate --env <env> --provider opnsense --component <type>` for every supported resource type on `OLD` to dump live state into YAML under `envs/<env>/opnsense/`.
2. **Edit interface map**: in the YAML, remap physical NIC names (`igc0` → `ixl0`, etc.) and any VLAN parent interface references. This is the only manual edit if the new box has different NICs.
3. **Out-of-IaC import**: on `NEW`, System → Configuration → Backups → Restore, choose "Restore area" and import only the sections from "out of IaC scope" above. **Do not** restore VLANs, filter, NAT, or DHCP — those come from IaC.
4. **Verify interface assignments YAML**: confirm the `interface_assignments` YAML in `envs/<env>/opnsense/` correctly maps each logical interface (LAN, WAN, OPT1, etc.) to its physical NIC or VLAN on `NEW`. The mapping is applied automatically during step 7 (`foundry infra apply`) via the in-tree `AssignSettingsController.php` fork ([ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions); production conversion landed in #720). No manual GUI step is required.
5. **Switch endpoint**: update `provider_settings.opnsense.api_url` in `envs/<env>/settings.yaml` to point at `NEW`. Or, for a one-shot operator-driven cutover that doesn't touch the SOPS-encrypted `settings.yaml`, export `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1` together with `OPNSENSE_API_URL=<NEW>` (and optionally `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET`, `OPNSENSE_VERIFY_SSL`) and run plan/apply directly — see [ADR-0014 §"Runtime credential resolution"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#runtime-credential-resolution-741-2026-05-05). Plan/apply emits a one-time WARNING naming the resolved URL so the redirect is loud. Without `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`, env vars are ignored — this protects against forgotten direnv shells.
6. **Plan**: `foundry infra plan --env <env>` and review the diff. Expect a clean apply against the (mostly empty) `NEW` box.
7. **Apply**: `foundry infra apply --env <env>`.
8. **Verify**: confirm interfaces, VLAN trunks, and firewall connectivity. Roll DNS / Tailscale / WAN cutover as appropriate to your environment.
9. **Decommission `OLD`**: power off after a soak period.

### Same-spec follow-on migration

If `NEW2` has identical NICs to `NEW`, step 2 (interface remap) is skipped. The full migration is: change endpoint → plan → apply.

### One-time migration step for existing VLAN-managed environments

Environments that previously used the terraform-based VLAN path (pre-#709) carry stale `opnsense_vlan.<name>` entries in their terraform state. The first apply after upgrading to the direct-API runner will see those entries as deletes. Run the following per-VLAN before the next apply:

```bash
cd generated/<env>/terraform/opnsense
terraform state rm 'opnsense_vlan.<vlan_name_with_underscores>'
```

After the cleanup, terraform plan should show zero VLAN-related changes; the direct-API runner takes over cleanly.

## Closing the gaps

Each gap row in the matrix above corresponds to a planned feature issue. The implementation order in [ADR-0013](../decisions/0013-opnsense-full-iac-migration.md) is:

1. `interface_assignments` (read-only / migrate shipped in #711; write-path mechanism decided in ADR-0014 amendment #717 via a forked PHP REST controller; production conversion of `OPNsenseDirectRunner.apply()` completed in #720 (2026-05-03))
2. `nat_rules` — outbound + 1:1 shipped in #713 (direct-API). Port forwards shipped in #725 as a third `kind` on `nat_rules` via direct-API at `firewall/d_nat` — the 2026-05-04 re-probe of `26.1.6_2` found that the stock `DNatController` ships with the standard CRUD verbs at the snake-case URL (`firewall/d_nat/<action>`); the original 2026-05-03 probe used `firewall/dnat` (concatenated) and incorrectly concluded the controller was absent.
3. `gateways` (#721, completed) and `static_routes` (#722, completed)
4. `virtual_ips` (#723, completed) — direct-API, natural-key tuple `(interface, mode, address, vhid)`; modes `ipalias` / `carp` / `proxyarp`; CARP `password` flows via `secret://env_secrets/<path>` URIs resolved at apply time by the new `EnvSecretsBackend`.
5. Unbound extensions — scope reduced to two resources (`unbound_host_alias`, `unbound_forward`); `domain_override` merged into `unbound_forward` per the live API (#724, completed)
6. `config migrate` extractors for every supported and newly-added resource type
7. `firewall_rules` — migrated to direct-API targeting the OPNsense MVC stateful filter controller `firewall/filter/*` (#742, [ADR-0015](../decisions/0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md), completed). Field coverage is ~50 scalar/enum fields (full MVC `getRule` template); legacy `<filter>/rule` and the browningluke terraform path were retired in the same PR. Operators with existing legacy rulesets must perform a one-time GUI migration at `/ui/firewall/migration` on the source box — there is no REST surface for legacy → MVC migration.

The follow-up issues will be filed against the InfraFoundry repo and linked from ADR-0013 as they're created.
