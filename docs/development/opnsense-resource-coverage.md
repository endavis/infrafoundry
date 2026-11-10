---
title: "OPNsense Provider Resource Coverage"
description: "Which OPNsense resource types the provider manages, the known gaps, and box-to-box migration planning"
audience:
  - contributors
tags:
  - development
---

# OPNsense Provider Resource Coverage

This document tracks which OPNsense resource types are managed by the InfraFoundry provider today, which are known gaps, and how to plan a box-to-box migration when the provider doesn't yet cover every section of `config.xml`.

It exists to support the decision in [ADR-0013](../decisions/0013-opnsense-full-iac-migration.md): **drop-in OPNsense replacement should be achievable by re-applying YAML against a new endpoint.** Closing the gaps below is a prerequisite for that to work end-to-end.

## Coverage matrix

Every dict-shaped (singleton) resource is named by its dotted type, so `-r system.tuning` selects it and several singletons can coexist in one environment (#1237). State rows recorded under the old name `settings` are renamed automatically on the next run.

Source of truth for "supported": `OPNsenseProvider.get_resource_types()` in `src/infrafoundry/providers/opnsense/__init__.py`.

| Section in `config.xml` | InfraFoundry resource type | Status |
| --- | --- | --- |
| `<vlans>` | `vlans` | Supported (direct-API via `OPNsenseDirectRunner`; ADR-0014, #709) |
| `<OPNsense>/Firewall/Alias` | `aliases` | Supported (direct-API; #775; config-migrate extractor added in #747). Identity is the natural-key alias `name` (OPNsense-enforced unique server-side); the operator-facing top-level YAML `name` and `config.name` agree on extraction (the migrate output writes both identically) and operators may rename the top-level name freely after import — the diff engine uses `config.name` as the wire identity. YAML schema covers the base fields (`name`, `type`, `description`, `content`, `enabled`) plus type-specific `proto` (geoip), `updatefreq` (urltable / urltable_ports — preserved as a string to retain decimal precision), `categories`, `counters`, and `interface` (dynipv6host); these optional fields are emitted only when the live record carries a non-default value, so existing operator YAML round-trips unchanged. The legacy terraform write path (`browningluke/opnsense_firewall_alias` + `aliases.tf.j2`) was retired in #775 — no `kind: legacy` shim. System-internal aliases (`type: internal` per-interface auto-generated entries like `__lan_network`, and `type: external` system-managed tables like `bogons` / `sshlockout`) are silently filtered from extractor output and from the diff engine's view of live state — OPNsense regenerates them server-side and they're not operator-writable via the alias controller; including them in either place would produce spurious deletes and break idempotency. |
| `<filter>/rule` (MVC `firewall/filter/*`) | `firewall_rules` | Supported (direct-API; #742). Identity is encoded as a **suffix** in the rule description — `<operator description> [infrafoundry:<name>]` — and every managed rule also carries the OPNsense `infrafoundry` category UUID in its multi-valued `categories` list as a fleet-wide marker (the MVC multi-value field empirically coexists with operator-set categories without collision; the marker is **appended** to the operator list, not overwriting it). Live rules without the suffix tag are unmanaged and ignored by the diff (do not edit a managed rule's description in the GUI — that breaks identity parsing). Targets the **MVC stateful filter controller**, not the legacy `<filter>` block; OPNsense 26.x ships both systems and they do not auto-cross-populate. Migrating an existing legacy ruleset to MVC is a one-time GUI operator step (no REST surface for migration). The terraform path (`firewall_rules.tf.j2` + `browningluke/opnsense_firewall_rule`) was retired in the same PR — no `kind: legacy` shim. Field coverage spans the full MVC `getRule` template (~50 fields) per [ADR-0015 §"Field coverage"](../decisions/0015-opnsense-firewall-rules-direct-api-via-mvc-controller.md#field-coverage); `sched`, `shaper1`, `shaper2` punted to follow-up issues. |
| `<OPNsense>/Kea` (DHCPv4 subnets) | `kea_subnet` | Supported (direct-API; #777). Identity is the natural-key `subnet` CIDR (operator YAML `subnet:` field; e.g., `10.0.10.0/24`). Wire envelope key is `subnet4` (parallel to DHCPv6's `subnet6`). DHCP options are nested under `option_data` (`routers`, `domain_name_servers`, `ntp_servers`, `domain_search`, `domain_name`); only `option_data_autocollect` is flat. An option not set in YAML is left to OPNsense and not diffed (#1165). `interface` is sent on write, but OPNsense 26.1 does not return it from `getSubnet`, so it is not drift-compared when the box returns none (#1253); Kea's listening interfaces are the global setting. DHCPv6 subnets (`kea_dhcp6_subnet`) get the same comparison rule, but the DHCPv6 behavior on 26.1 is unconfirmed. Honors `--add-only` (a behavioral gain over the legacy terraform path). The legacy terraform write path (`browningluke/opnsense_kea_subnet` + `kea_subnet.tf.j2`) was retired in #777 — no `kind: legacy` shim. |
| `<OPNsense>/Kea` (DHCPv4 reservations) | `kea_reservation` | Supported (direct-API; #778, #802). Identity is the `(hw_address, subnet_uuid)` tuple — DHCPv4 uses MAC address as the client identity (distinct from DHCPv6's `duid`). Operator-facing schema accepts `subnet_ref: <managed kea.dhcp4.subnets name>` (preferred — what the framework's blueprints emit, added in #802) and the legacy `subnet: <CIDR>` literal form (still supported); both fields may be present and must agree. Resolution is a two-step lookup: `subnet_ref` → CIDR via the matching sibling `kea.dhcp4.subnets` resource list, then CIDR → live subnet UUID via `service.search_dhcpv4_subnets()` at plan/apply time. `KeaReservationValidator` flags missing / unknown-ref / wrong-version / disagree cases at plan time via the shared `_xref` resolver before any API call. Missing live subnet raises `ReferenceValidationError` at plan time (a behavioral upgrade over the legacy terraform path which would silently break the terraform graph dependency on a box-to-box cutover). Honors `--add-only`. The legacy terraform write path (`browningluke/opnsense_kea_reservation` + `kea_reservation.tf.j2`) was retired in #778 — no `kind: legacy` shim. The shared `kea_reconfigure` finalization hook coalesces across all four Kea managers (subnet/reservation × v4/v6) so a multi-component apply produces exactly one `kea/service/reconfigure` call. |
| `<OPNsense>/Kea` (DHCPv6 subnets) | `kea_dhcp6_subnet` | Supported (direct-API; #758) |
| `<OPNsense>/Kea` (DHCPv6 reservations) | `kea_dhcp6_reservation` | Supported (direct-API; #758, #802). Identity is the `(duid, subnet_uuid)` tuple. Operator-facing schema accepts `subnet_ref: <managed kea.dhcp6.subnets name>` (preferred, added in #802 for symmetry with DHCPv4) and the legacy `subnet: <CIDR>` literal form (still supported — DHCPv6 fixtures predating #802 use this form unchanged); both fields may be present and must agree. Resolution mirrors DHCPv4: `subnet_ref` → CIDR via sibling `kea.dhcp6.subnets`, then CIDR → live subnet UUID via `service.search_dhcpv6_subnets()`. Same `KeaReservationValidator` covers v4 and v6 in a single pass for wrong-version cross detection. |
| `<OPNsense>/unboundplus/hosts/host` | `unbound_host_override` | Supported (direct-API; #776; config-migrate extractor added in #748). Identity is the natural-key tuple `(hostname, domain, rr)` — including `rr` lets an A and an AAAA record on the same `(hostname, domain)` coexist as distinct identities (a common dual-stack setup). Wire field names are OPNsense's own (`rr` / `mxprio` / `mx`); the operator-facing YAML field names are the same. YAML schema covers the base fields (`hostname`, `domain`, `enabled`, `server`, `description`) plus record-type-specific `rr` (`A` / `AAAA` / `MX`), `mxprio` (MX priority, preserved as a string to match `updatefreq`), and `mx` (MX target). The extended fields are emitted only when the live record carries a non-default value, so existing 5-field operator YAML round-trips unchanged. The extractor synthesizes the operator-facing `name` as `<hostname>-<dot-replaced-domain>` (lowercased; e.g., `web.example.com` → `web-example-com`); when `rr` is non-default, the record type is appended as a suffix (e.g., `web-example-com-aaaa`, `mail-example-com-mx`) so an A and an AAAA record on the same hostname don't collide on the same key. A synthesized name already used by another opnsense resource in the environment, or by an earlier host override in the same run, gets a `-2`, `-3` ... suffix (#1337). No system-internal filter is needed — host overrides are entirely operator-defined. The `unbound_reconfigure` finalization hook is shared across all three Unbound managers (#776), so a multi-unbound apply produces exactly one `unbound/service/reconfigure` call. The legacy terraform write path (`browningluke/opnsense` + `unbound_host_override.tf.j2`) was retired in #776 — no `kind: legacy` shim. |
| `<dhcpd>` (legacy ISC) | — | **Retired (#782).** The `dhcp_static_maps` resource type was deleted in #782; the legacy terraform path referenced `opnsense_dhcpv4_static_map`, which never existed in `browningluke/opnsense`. New deployments use `kea_reservation` (DHCPv4) instead — Kea is OPNsense's modern DHCP daemon and `kea_reservation` direct-API supersedes `dhcp_static_maps` for every operational use case (MAC-bound static IP, hostname, description). |
| `<interfaces>` | `interface_assignments` | Supported (direct-API; #711 read-only ship, #716 forked PHP controller, #717 ADR-0014 amendment, #720 production conversion). Write-path mechanism per [ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions): server-side-validated REST via the in-tree `AssignSettingsController.php` fork. Production conversion of `OPNsenseDirectRunner.apply()` completed in #720 (2026-05-03); logical-to-physical interface mapping is now applied automatically by `foundry infra apply`. |
| `<nat>/outbound/rule`, `<nat>/onetoone/rule`, and `<nat>/rule` | `nat_rules` (`kind: outbound` / `kind: one_to_one` / `kind: port_forward`) | Supported (all three kinds, direct-API; #713 outbound + 1:1; #725 port_forward). Identity is encoded as a **suffix** in the rule description — `<operator description> [infrafoundry:<name>]` — and every managed rule also carries the OPNsense `infrafoundry` category as a fleet-wide marker. Live rules without the suffix tag are unmanaged and ignored by the diff (do not edit a managed rule's description in the GUI — that breaks identity parsing). Note: port_forward uses the OPNsense stock `DNatController` at `firewall/d_nat` (snake-case routing); the original 2026-05-03 probe used `firewall/dnat` (concatenated) and incorrectly concluded the controller was absent. Outbound rules are read from the model (`firewall/source_nat/get`) when the outbound NAT mode is `automatic` or `disabled`, because `searchRule` lists no manual rule in those modes (#1333). `infra plan` warns when declared outbound rules would be inert in the effective mode; see [Outbound NAT mode](#outbound-nat-mode-1333). |
| `<nat>/outbound/mode` | `firewall.source_nat` | Supported (direct-API; #1333). A singleton with one key, `snat_mode` (`automatic`, `hybrid`, `advanced` or `disabled`), written through `firewall/source_nat/set`; the `source_nat_apply` hook calls `firewall/source_nat/apply` once per apply. Needs OPNsense 26.1 or later. See [Outbound NAT mode](#outbound-nat-mode-1333). |
| `<OPNsense>/Gateways` | `gateways` | Supported (direct-API; #721). Identity is the natural-key `name` (OPNsense enforces uniqueness server-side). Dynamic/virtual gateways synthesized from interface DHCP state (e.g., `WAN_DHCP`, `WAN_DHCP6`) are silently excluded from the diff — they're recreated from interface state on reconfigure and must not appear in YAML. |
| `<staticroutes>/route` | `static_routes` | Supported (direct-API; #722). Identity is the natural-key tuple `(network, gateway)` (OPNsense exposes no server-unique `name` field on routes — operator-facing YAML `name` is metadata only and never travels on the wire). The `gateway` field cross-references either a managed `gateways` resource declared in YAML or a live system gateway (e.g., `WAN_DHCP`, `WAN_DHCP6`); the validator enforces protocol-family match (IPv4 CIDR → IPv4 gateway, IPv6 CIDR → IPv6 gateway). |
| `<virtualip>/vip` | `virtual_ips` | Supported (direct-API; #723). Identity is the natural-key tuple `(interface, mode, address, vhid)` — including `mode` and `vhid` lets multiple CARP VIPs coexist on the same interface+address (different `vhid`s) and distinguishes ipalias from CARP at the same IP. Modes are `ipalias` / `carp` / `proxyarp` only (the issue body's draft also listed `alias` / `other`; the live probe is authoritative — those values are not accepted). The `interface` field cross-references either a managed `interface_assignments` resource declared in YAML or a live overview interface. **CARP `password` is the first direct-API secret-bearing field** — operators provide a `secret://env_secrets/<dotted/path>` URI in YAML and the password is resolved at apply time by the new `EnvSecretsBackend` (see [ADR-0014 §"Secrets handling"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#secrets-handling)); plaintext values in YAML are accepted but produce a soft warning. |
| `<OPNsense>/unboundplus/hosts/host/alias` | `unbound_host_alias` | Supported (direct-API; #724). Identity is the natural-key tuple `(host_uuid, hostname)` — OPNsense keys aliases by parent host_override UUID; the operator-facing YAML uses `(host_name, hostname)` and the component manager resolves `host_name` → parent UUID at apply time by reading `searchHostOverride` rows. The `host` field cross-references either a managed `unbound_host_override` resource declared in YAML or a live host override (`hostname` or `hostname.domain` form). |
| `<OPNsense>/unboundplus/domains/domain` | — | **Merged into `unbound_forward`** (per OPNsense API; see [ADR-0013 §"Implementation order" #5 amendment](../decisions/0013-opnsense-full-iac-migration.md#implementation-order), #724). A `Forward` entry with `type=forward, domain="example.com"` is what the GUI calls a "domain override"; with `domain=""` it is a global forwarder. There is no separate REST surface for domain overrides. |
| `<OPNsense>/unboundplus/forwarding/host` | `unbound_forward` | Supported (direct-API; #724). Identity is the natural-key tuple `(type, domain, server, port)` — including `type` (forward / dot) lets DoT and plain forwarders coexist for the same domain/server/port. **Envelope key on the wire is `dot` regardless of `type` value** (counter-intuitive but empirically confirmed). Field names match the wire format verbatim — `verify` not `verify_cn`; `forward_tcp_upstream` not `forward_tls_upstream`. Empty `domain` = global forwarder; non-empty = per-domain forwarder (a.k.a. domain override). |
| `<system>/hostname` + `<system>/domain` + `<system>/timezone` + `<system>/language` | `system.hostname` | **Unsupported on 26.1 (#1149); implementation removed (#1244).** No API on OPNsense 26.1 (its endpoints 404); configured on the legacy System > Settings > General page. `infra plan`/`apply` and `infra doctor` reject the type with this reason; the [endpoint check](#endpoint-registry-and-version-check-1239) would reject it too. |
| `<system>/dnsserver` + `<system>/dnsallowoverride` + `<system>/dnsXgw` | `system.dns` | **Unsupported on 26.1 (#1149); implementation removed (#1244).** No API on OPNsense 26.1 (its endpoints 404); configured on the legacy System > Settings > General page. `infra plan`/`apply` and `infra doctor` reject the type with this reason; the [endpoint check](#endpoint-registry-and-version-check-1239) would reject it too. |
| `<system>/ssh` | `system.ssh` | **Unsupported on 26.1 (#1149); implementation removed (#1244).** No API on OPNsense 26.1 (its endpoints 404); configured on the legacy System > Settings > Administration page. `infra plan`/`apply` and `infra doctor` reject the type with this reason; the [endpoint check](#endpoint-registry-and-version-check-1239) would reject it too. |
| `<system>/webgui` | `system.webgui` | **Unsupported on 26.1 (#1149); implementation removed (#1244).** No API on OPNsense 26.1 (its endpoints 404); configured on the legacy System > Settings > Administration page. `infra plan`/`apply` and `infra doctor` reject the type with this reason; the [endpoint check](#endpoint-registry-and-version-check-1239) would reject it too. |
| `<system>/firmware` | `system.firmware` | Supported (direct-API; #806, reworked #1149). Reads `core/firmware/info` (plugins) and `core/firmware/get` (settings) — verified live on 26.1.6_2. Install-missing-only for plugins (extras warned, never removed); settings drift for the keys present in YAML is written via `core/firmware/set`. **Live results on 26.1.6_2 (#1238):** `POST core/firmware/set` verified (`reboot` 0 → 1 → 0). `install/<pkg>` only queues a background job; the request reached OPNsense but was refused because the box was out of date (the mirror required 26.1.11_10), so a full install check needs a box at the mirror's current release. Apply now waits on `core/firmware/upgradestatus` and re-reads `core/firmware/info`, and fails with the firmware log tail if the plugin is not installed afterwards. Plan counts each missing plugin as an add, matching apply. `remove/<pkg>` and `lock/<pkg>` not tested (apply never calls them). |
| `<system>/remotebackup` (GDrive) | `system.remotebackup` | **Unsupported on 26.1 (#1149); implementation removed (#1244).** No API on OPNsense 26.1 (its endpoints 404); configured on the legacy System > Configuration > Backups page (Google Drive; the page name is an inference, not measured). `infra plan`/`apply` and `infra doctor` reject the type with this reason; the [endpoint check](#endpoint-registry-and-version-check-1239) would reject it too. |
| `<sysctl>` | `system.tuning` | Supported (direct-API; #806, reworked #1149). Per-tunable add/update by name via `core/tunables/*`; tunables not in YAML are never touched. `core/tunables/get` verified live on 26.1.6_2. **Live results on 26.1.6_2 (#1238):** `setItem/<uuid>` verified (changed, then reverted); `addItem` verified (58 → 59 entries); `reconfigure` verified (ran after each tuning apply; re-plan stable); `delItem/<uuid>` verified by hand (apply never calls it). |
| `<dhcpdv6>/<optN>/<ra*>` (legacy ISC RA) → `radvd/settings/*Entry` (modern controller) | `radvd` | Supported (direct-API; #788). **Hybrid YAML-singleton/wire-list** — operator authors a single dict-shape `radvd` resource whose `interfaces` mapping carries one inner mapping per interface; the wire stores those as per-UUID records (verb suffix `*Entry`, NOT `*Item` — confirmed via live probe 2026-05-10). Identity is the wire `interface` field per record. Full-reconcile semantics: interfaces in live state but absent from YAML get DELETED (safe — deleting a record stops RA emission, no data loss). Per-interface `enabled` field replaces a global enable toggle. New shared finalization hook `radvd_reconfigure` coalesces a single `radvd/service/reconfigure` call per apply. **Source-XML location is the legacy `<dhcpdv6>/<optN>/<ra*>` path** — this resource type targets the modern MVC controller only; the legacy path is read-only reference for migration values (Kea owns DHCPv6 leases via `kea.dhcp6.*`, the modern radvd controller owns RA emission). Wire field names use OPNsense's CamelCase (`MinRtrAdvInterval`, `MaxRtrAdvInterval`, `AdvDefaultPreference`, `RDNSS`, `DNSSL`); operator-facing YAML uses snake_case (`min_interval`, `max_interval`, `priority`, `dns_servers`, `domain_search`, `routes`) with translation at the apply boundary. See [ADR-0014 §`radvd`](../decisions/0014-opnsense-direct-api-apply-mechanism.md#radvd-788-2026-05-12). |
| `<cron>/jobs/job` (MVC `cron/settings/*`) | `cron_jobs` (`cron.jobs` dotted type) | Supported (direct-API; #789). **List-shape full-reconcile** — each YAML entry is a distinct scheduled task; managed jobs absent from YAML are deleted. Identity is encoded as a **suffix** in the `description` field — `<user description> [infrafoundry:<name>]` (or bare `[infrafoundry:<name>]` when the operator supplies no description). Unmanaged jobs (no suffix tag) are never touched. **Wire field mapping (confirmed live probe 2026-06-18):** schedule fields pass through 1:1 — OPNsense MVC uses `days`/`months`/`weekdays` (same as YAML keys; no translation). `enabled` serializes as `"1"`/`"0"` strings. `origin` is REQUIRED and always written as `"cron"` so that `delJob` can delete the record (non-`"cron"` origins are delete-protected in OPNsense); `origin` is excluded from drift comparison and always emitted as `"cron"` in export. A validator WARNING is emitted when the operator sets a non-`"cron"` origin in YAML. Schedule fields accept the standard cron grammar: `*`, `*/N`, a plain integer, `L-H`, `L-H/N`, or comma-separated lists; range boundaries are validated at plan time by `CronJobsValidator`. **Reconfigure deferred to finalization hook** — apply does NOT call `cron/service/reconfigure` directly; the runner fires `cron_reconfigure` (the fourth finalization hook, after `kea_reconfigure`, `unbound_reconfigure`, and `radvd_reconfigure`). Destroy calls `reconfigure` directly. `plugin_conflicts()` detects unmanaged live jobs sharing a `command` with a managed YAML job and emits a WARNING (not an error — both will run the same binary). `lock: true` per-resource skips diff and destroy paths (idempotent protection for host-native tasks). `add_only: true` suppresses deletes only; adds and updates still apply. See [ADR-0014 §`cron_jobs`](../decisions/0014-opnsense-direct-api-apply-mechanism.md#cron_jobs-789-2026-06-18). |
| `<system>/user` | `system.users` | Supported (direct-API; #805). List-shape, identity is the wire `name`; deletes are limited to the managed set and a uid-0 account (by live uid) is never deleted. Only the fields set in YAML are written and compared (`set` keeps omitted fields). `uid` is assigned by the box and is not configurable. `password` is a `secret://` reference holding the plaintext (the box hashes it); it is write-only, so it is sent on add only, and on update only with `update_password: true`. `authorizedkeys`, `otp_seed` and `apikeys` must be `secret://` references. See [ADR-0014 system.users and system.groups](../decisions/0014-opnsense-direct-api-apply-mechanism.md#systemusers-and-systemgroups-805). A GUI login with the set password, and with a rotated one, was verified live on a test firewall (#1322). |
| `<system>/group` | `system.groups` | Supported (direct-API; #805). `gid` is assigned by the box and is not configurable. Groups own membership: `member_refs` name `system.users` resources and are written as uids. Applied after `system.users`; group deletes run before user deletes. See [ADR-0014 system.users and system.groups](../decisions/0014-opnsense-direct-api-apply-mechanism.md#systemusers-and-systemgroups-805). |
| `<ca>`, `<cert>`, `<OPNsense>/trust` (MVC `trust/ca/*`, `trust/cert/*`) | `trust.cas`, `trust.certs` | Supported (direct-API; #807). Identity is the live `descr` against the YAML `description` (default: the resource name). `prv` should be a `secret://` URI. Deletes use the managed set; objects the box reports in use, and CAs that look AcmeClient-issued, are never deleted. No `config migrate` extractor. Several behaviours are not verified yet, see [Trust CAs and certificates (#807)](#trust-cas-and-certificates-807). |
| `<OPNsense>/OpenVPN` (MVC `openvpn/instances/*`) | `openvpn.instances` | Supported (direct-API; #808). Client instances only; server instances are not managed and are never touched. Identity is the live `description` (default: the resource name). `username` and `password` are `secret://` URIs. `ca_ref` names a `trust.cas` resource and the optional `cert_ref` a `trust.certs` resource. Deletes use the managed set. No `config migrate` extractor. Add, update, delete and `cert_ref` are verified live, see [OpenVPN client instances (#808)](#openvpn-client-instances-808). |
| `<OPNsense>/OpenVPN` static keys (MVC `openvpn/instances/*StaticKey`) | `openvpn.static_keys` | Supported (direct-API; #1319). A tls-auth, tls-crypt or tls-crypt-v2 key an instance references with `tls_key_ref`. Identity is the live `description` (default: the resource name). `key` is a `secret://` URI; `mode` is required. Deletes use the managed set, and a key a live instance still references is kept. No `config migrate` extractor. See [OpenVPN static keys (#1319)](#openvpn-static-keys-1319). |
| `<openvpn>` (legacy `os-openvpn-legacy` plugin) | none | Unmanaged. A cutover recreates the client as a modern `openvpn.instances` entry; import any legacy server or other legacy configuration by hand. |
| `<OPNsense>/AcmeClient` (`os-acme-client` plugin, `acmeclient/*`) | `acmeclient.settings`, `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions`, `acmeclient.certs` | Supported (direct-API; #790). The wire `name` is the identity (the CN for certs), and certs reference accounts, validations and actions by handle. Secret fields take `secret://` URIs. The four list types delete only managed rows; `config migrate` extractors exist for all five. The plugin comes from `system.firmware`; its renewal cron job is plugin-managed. Add, update, delete, re-plan and `config migrate` are verified live; `fetchCronIntegration` is not. See [ACME client (#790)](#acme-client-790). |
| `<OPNsense>/tailscale` (`os-tailscale` plugin, `tailscale/*`) | `tailscale.settings`, `tailscale.auth`, `tailscale.subnets` | Supported (direct-API; #787). `settings` and `auth` are singletons, `subnets` is a managed-set list keyed by the normalized CIDR. The pre-auth key must be a `secret://` URI. One `tailscale/service/reconfigure` fires per apply; the plugin is never started and no tailnet is joined. A `config migrate` extractor exists for each. See [Tailscale (#787)](#tailscale-787). |
| `<OPNsense>/Syslog` | `syslog.settings` | Supported (direct-API; #804). A singleton over the `general` section of the syslog model (local logging switch and log rotation); only declared fields are compared, the whole live `general` object is echoed back on write; destroy is a no-op; the `syslog_reconfigure` hook fires one reconfigure per apply. Remote `destinations` are not managed. The `set` and `reconfigure` calls are verified live. See [Syslog settings](#syslog-settings-804). |
| `<OPNsense>/monit` | `monit_*` (proposed) | **Gap.** Not managed yet; import it by hand from the old box's `config.xml` until [#791](https://github.com/endavis/infrafoundry/issues/791) ships. |
| `<OPNsense>/Hostwatch` | `hostdiscovery` | Supported (direct-API; #792). The YAML key is `hostdiscovery`, not `hostwatch`, to match the wire API. A singleton; only declared fields are compared (lists as sets), the whole live `general` section is echoed back on write; destroy is a no-op; the `hostdiscovery_reconfigure` hook fires one reconfigure per apply. The `set` and `reconfigure` calls are verified live. See [Host discovery](#host-discovery-792). |
| `<OPNsense>/unboundplus/advanced` (`privatedomain`, `insecuredomain`, `privateaddress`) | `unbound.advanced` | Supported (direct-API; #1254). Only declared fields are compared; the whole `advanced` section is echoed back on write; destroy is a no-op; shares the `unbound_reconfigure` hook. The `set` envelope key `unbound` is verified live through `unbound.settings` (#1091). |
| `<OPNsense>/unboundplus/general`, the rest of `<OPNsense>/unboundplus/advanced` | `unbound.settings` | Supported (direct-API; #1091). Singleton with optional `general:` and `advanced:` mappings keyed by wire field name; only declared fields are compared, each declared live section is echoed back whole on write; destroy is a no-op; shares the `unbound_reconfigure` hook. See [Unbound general and advanced settings](#unbound-general-and-advanced-settings-1091). |
| `<OPNsense>/Interfaces/settings` | `interfaces.settings` | Supported (direct-API; #1092). A singleton over the whole settings model; only declared fields are compared, the whole live object is echoed back on write; destroy is a no-op; the `interfaces_settings_reconfigure` hook fires one reconfigure per apply. **The `set` and `reconfigure` calls are not yet verified against a live box.** See [Interface settings](#interface-settings-1092). |
| `<system>/lb_use_sticky`, `<system>/pf_share_forward`, `<system>/disablenatreflection`, `<system>/pfdebug` (firewall advanced) | none | **Out of scope.** Exist only on a legacy PHP page (`system_advanced_firewall.php`) with no MVC API, and the usual setup leaves them at the defaults. |
| `<system>/timeservers` (NTP) | none | **Out of scope.** Same reason: legacy PHP page only (`services_ntpd.php`), usually left at the defaults. |
| `<OPNsense>/Firewall/Category` (MVC `firewall/category/*Item`) | `firewall.categories` | Supported (direct-API; #1286). Identity is the wire `name` (`config.name`, default the resource name). `auto` and `color` are optional. Deletes use the managed set; the provider's `infrafoundry` marker category is never part of the diff; a category the box reports in use is kept with a warning. A `config migrate` extractor exists. See [Firewall categories (#1286)](#firewall-categories-1286). |

Sections intentionally **out of IaC scope** (per ADR-0013): `<hasync>`, `<gres>`, `<gifs>`, `<laggs>`, `<bridges>`, `<ppps>`, `<wireless>`. These are set-once items and are migrated via selective `config.xml` import on the target box.

## Trust CAs and certificates (#807)

`trust.cas` and `trust.certs` import existing certificate authorities and certificates into the OPNsense trust store through `trust/ca/*` and `trust/cert/*`. They are list-shape, managed-set types ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)); `trust.certs` is the child of `trust.cas`.

```yaml
opnsense:
  trust:
    cas:
      - name: vpn-ca
        config:
          description: vpn.example.com CA
          crt: secret://env_secrets/trust/vpn_ca/crt
          prv: secret://env_secrets/trust/vpn_ca/prv
    certs:
      - name: vpn-server
        config:
          description: vpn.example.com
          type: server
          ca_ref: vpn-ca
          crt: secret://env_secrets/trust/vpn_server/crt
          prv: secret://env_secrets/trust/vpn_server/prv
```

| Field | Types | Meaning |
| --- | --- | --- |
| `description` | both | Wire `descr` and the identity. Defaults to the resource `name`. |
| `crt` | both | PEM certificate. Required. |
| `prv` | both | PEM private key. Use a `secret://env_secrets/<path>` URI; a literal key is a validation error. |
| `csr` | certs | PEM signing request. Optional. |
| `ca_ref` | certs | Name of the `trust.cas` resource that signed it. Resolved to the live CA `refid`; see `ca_refids_by_name` in `services/trust.py`, which the OpenVPN work (#808) reuses; `cert_refids_by_name` is its counterpart for an instance's `cert_ref` (#1320). |
| `type` | certs | `server`, `client` or `combined`. Sent as `cert_type` on add and update; not compared. On import the box keeps the type it derives from the certificate (see below). |
| `lock` | both | Never add, update or delete. |

`refid` and `serial` are assigned by the box and are not YAML fields. A literal `crt` or `csr` is a validation warning (public material, but keep it with its key). Messages and logs name the resource and field and never include a value derived from `crt`, `prv` or `csr`.

**Identity and drift.** A live object matches its YAML entry by `descr`. Two live objects with the same `descr` stop the plan with an error. `crt` is compared as normalized PEM against the row's raw `crt_payload`. `prv` and `csr` are compared only when both sides are non-empty, since the box may not return them. A certificate's `caref` is compared with the resolved CA `refid`.

**Delete guards.** A managed object the box reports as in use (`in_use`) is kept, and so is a managed CA whose description matches `^(?:R|E)\d+$`. The plugin naming is an inference: `refid` is a box-generated uniqid, so the match is on `descr`. `infra plan` shows them as `N blocked (kept)` with a warning, and they stay managed so the next run retries. Certificates are deleted before CAs (reverse-order delete phase).

**Order and pending CAs.** CAs are applied before certificates. A plan for a certificate whose `ca_ref` CA is not on the box yet shows an add plus a warning; at apply, after the CA is created, an unresolved `ca_ref` raises an error before any write.

**Not migrated.** There is no `config migrate` extractor: it would write key material into plaintext YAML. A secret-aware extractor is a follow-up.

**Verified on a test box.** A live plan and apply with a throwaway CA and certificate (removed afterwards) confirmed:

- there is no `import` endpoint; an import is an `add` whose body carries `action` (`existing` for a CA, `import` for a certificate) and the `*_payload` fields. Both imports stored the supplied certificate and key;
- the certificate's `caref` points at the CA resolved from `ca_ref`;
- a second plan is idempotent;
- `set` with a changed `crt` re-imports it in place: same `uuid` and `refid`, the key is kept;
- changing `description` is a delete plus an add, since `descr` is the identity;
- deletes run certificates first, then CAs.

**`type` is not honoured on import.** The box stored `cert_type` as `usr_cert` for a certificate sent with `type: server` (`server_cert`); the stored type appears to follow the imported certificate, not the request. `type` is not compared, so it causes no drift.

**Not verified.** Whether the box refuses to delete an in-use object (the guard above does not rely on it), and the CA row shape beyond the fields read here.

## ACME client (#790)

The `os-acme-client` plugin is managed through five direct-API types: `acmeclient.settings` (a singleton dict) and `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions` and `acmeclient.certs` (lists). The four lists are managed-set types ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). The plugin itself is installed by `system.firmware` (declare `os-acme-client` under its plugins); the five types are applied after it.

```yaml
opnsense:
  acmeclient:
    settings:
      enabled: true
      auto_renewal: true
      environment: stg
      log_level: normal
    accounts:
      - name: example-account
        config:
          email: admin@example.com
          ca: letsencrypt_test
    validations:
      - name: example-dns
        config:
          method: dns01
          dns_service: dns_cf
          dns_cf_token: secret://env_secrets/opnsense/acmeclient/validations/example-dns/dns_cf_token
    actions:
      - name: restart-gui
        config:
          type: configd_restart_gui
    certs:
      - name: example-cert
        config:
          common_name: fw-test.example.com
          alt_names:
            - www.example.com
          account: example-account
          validation: example-dns
          restart_actions:
            - restart-gui
          key_length: key_ec256
          auto_renewal: true
          enabled: false
```

### Identity and `display_name`

The YAML `name` is the cross-reference handle. The identity on the box is the wire `name`:

- **accounts, validations, actions:** `display_name` when set, else the handle. `description` is a separate optional field.
- **certs:** `common_name`, which is the certificate's CN. A CN change is a delete plus an add, which is correct: it is a different certificate.

A handle must not contain a `.`. Two live rows of one type with the same name stop the plan with a drift error. Accounts are not keyed by `(ca, email)`: OPNsense does not enforce that pair, and a key on it would turn an email change into a delete plus an add. A repeated `(ca, email)` is a validator warning, and an update that changes `ca` or `email` warns that the stored account key belongs to the old registration.

### `config migrate` handles

Migrate takes each handle from a slug of the wire name (the CN for certs). One assignment covers all four types, in the order accounts, validations, actions, certs, and skips every opnsense name already in the environment, so a collision gets `-2`, `-3` ... (#1337). An environment row of the same type with the same identity keeps its handle, so re-running migrate and hand-renamed handles are stable, and cert references follow them. A duplicate already in the environment stops migrate with IF-CONFIG-002, naming the types and files.

### Settings (`acmeclient.settings`)

| YAML | wire field | type |
|---|---|---|
| `enabled` | `enabled` | bool |
| `auto_renewal` | `autoRenewal` | bool |
| `environment` | `environment` | `""`, `prod` or `stg` |
| `challenge_port` | `challengePort` | 1-65535 |
| `tls_challenge_port` | `TLSchallengePort` | 1-65535 |
| `restart_timeout` | `restartTimeout` | integer >= 0 |
| `haproxy_integration` | `haproxyIntegration` | bool |
| `haproxy_acl_ref`, `haproxy_action_ref`, `haproxy_server_ref`, `haproxy_backend_ref` | `haproxyAclRef` and the like | passive strings |
| `log_level` | `logLevel` | `normal`, `extended`, `debug`, `debug2`, `debug3` |
| `show_intro` | `showIntro` | bool |

An omitted key is not managed. The write posts the whole live settings object with the declared keys overwritten.

**Renewal cron is plugin-managed.** `UpdateCron` is not a YAML key and is never diffed; its live value is echoed back unchanged on write. After a settings write where `enabled` and `auto_renewal` are both on, InfraFoundry calls `acmeclient/settings/fetchCronIntegration` so the plugin creates or repairs its own job. The job carries no InfraFoundry marker, so `cron.jobs` treats it as unmanaged and keeps it. There is no cross-reference to `cron.jobs`.

### Lists

| type | YAML key | wire field | type |
|---|---|---|---|
| accounts | `enabled`, `description` | same | bool, string |
| | `email` | `email` | string |
| | `ca` | `ca` | `buypass`, `buypass_test`, `google`, `google_test`, `letsencrypt`, `letsencrypt_test`, `sslcom`, `zerossl`, `custom` |
| | `custom_ca`, `eab_kid` | same | string |
| | `eab_hmac` | `eab_hmac` | `secret://` URI |
| validations | `enabled`, `description` | same | bool, string |
| | `method` | `method` | `http01`, `dns01`, `tlsalpn01` |
| | `http_service` | `http_service` | `opnsense`, `haproxy` |
| | `http_opn_autodiscovery`, `http_opn_interface`, `http_opn_ipaddresses` | same | bool, string, list |
| | `http_haproxy_inject`, `http_haproxy_frontends` | `http_haproxyInject`, `http_haproxyFrontends` | bool, list |
| | `tlsalpn_service`, `tlsalpn_acme_autodiscovery`, `tlsalpn_acme_interface`, `tlsalpn_acme_ipaddresses` | same | string, bool, string, list |
| | `dns_service`, `dns_sleep`, `dns_lexicon_provider` | same | string, integer, string |
| | `dns_<provider>_<field>` | same | passed through verbatim, `secret://` URI |
| actions | `enabled`, `description` | same | bool, string |
| | `type` | `type` | one of 18 (`configd_restart_gui`, `configd_restart_haproxy`, `configd_restart_nginx`, `configd_reload_caddy`, `configd_upload_sftp`, `configd_remote_ssh`, `configd_generic`, and the `acme_*` deploy hooks) |
| | `sftp_*`, `remote_ssh_*`, `configd*`, `acme_<type>_*` | same | passed through verbatim; credential-like names take `secret://` URIs |
| certs | `common_name` | `name` | string, required |
| | `enabled`, `description` | same | bool, string |
| | `alt_names` | `altNames` | list |
| | `account` | `account` | reference |
| | `validation` | `validationMethod` | reference |
| | `restart_actions` | `restartActions` | list of references |
| | `key_length` | `keyLength` | `key_2048`, `key_3072`, `key_4096`, `key_ec256`, `key_ec384` |
| | `ocsp`, `auto_renewal` | `ocsp`, `autoRenewal` | bool |
| | `renew_interval` | `renewInterval` | integer >= 1 |
| | `alias_mode` | `aliasmode` | `none`, `automatic`, `domain`, `challenge` |
| | `domain_alias`, `challenge_alias` | `domainalias`, `challengealias` | string |

`id`, `key`, `statusCode`, `statusLastUpdate`, `lastUpdate` and `certRefId` are server-managed and rejected as YAML keys. Comparison is sparse: only declared fields are compared and written. Lists such as `alt_names` compare as sets. At plan, a pass-through key that the plugin's item template (`GET acmeclient/<sub>/get` without a UUID) does not know raises an error.

### References

`account`, `validation` and each `restart_actions` entry take a handle in one of three forms: `name`, `accounts.name` (in-plugin) or `acmeclient.accounts.name`. The manager maps the handle to the sibling resource's wire name, then to the live UUID. A reference whose target is not on the box yet is planned with a warning; at apply an unresolved reference raises `ReferenceValidationError` before any write.

Apply order is settings, accounts, validations, actions, certs. Certs are deleted first, before the types they use. **Limitation:** moving a cert from account A to account B and removing A in the same apply deletes A before the cert is updated. Do it in two applies.

### DNS credential check

For `method: dns01`, `dns_service` is required. A `dns_<provider>_*` field that belongs to a provider other than `dns_service` is an error. Required fields are enforced only for a small curated map, today `dns_cf` (needs `dns_cf_token`); for any other provider the validator warns that its required fields are not checked. A non-`dns01` method that sets `dns_<provider>_*` fields gets a warning. **Looseness:** a provider whose name is a prefix of another (for example `dns_he` and `dns_he_ddns`) lets the longer provider's fields through when the shorter one is selected. At plan, a warning names credential fields of another provider still stored on the box (names only).

### Secrets

`eab_hmac`, every `dns_<provider>_*` field and action fields named like a credential (`*_password`, `*_pass`, `*_tokenkey`, `*_apikey`, `*_token`, `*_key`) take `secret://` URIs, resolved before the diff. A literal value is a validator warning. Values are compared, but never logged, never put in a warning or error, and never in the changed-field list. `config migrate` emits `secret://env_secrets/opnsense/acmeclient/<type>/<handle>/<field>` for every non-empty secret and never the value.

### Plugin not installed

A 404 on the first read at plan means `os-acme-client` is not installed. Every desired row becomes an add (the settings map becomes the update), with the warning "os-acme-client is not installed; declare it under system.firmware plugins", so a fresh box plans cleanly when `system.firmware` installs the plugin in the same apply. At apply a 404 still raises.

### Reconfigure and never-called endpoints

One `acmeclient/service/reconfigure` fires per apply, through the shared `acmeclient_reconfigure` finalization hook. InfraFoundry never calls `register`, `sign`, `revoke`, `removekey`, `automation`, `import`, `signallcerts` or `toggle`: they contact a CA or a remote host. Issuance stays with the plugin's own cron job or the GUI; an account is registered from the GUI.

### Verified and not verified

Verified read-only on a 26.1 test firewall: the endpoints and wire fields above (item keys, `update/{uuid}`, enums).

**Verified live** on a 26.1 test firewall, with a throwaway disabled certificate, a `letsencrypt_test` account, a dns01 validation holding a dummy token, and a restart-GUI action:

- adds of all four list types and a settings update in one apply, with the certificate's references resolved in the same apply and one `service/reconfigure` (one finalization hook) per apply;
- the list `search` endpoints answer `GET`, and `get` without a UUID returns the item template with the plugin's defaults;
- updates of one field per type, where `update/{uuid}` kept the omitted fields (a certificate's `renewInterval`);
- the dns01 token read back in plain text, so the re-plan after each apply showed no change;
- deletes, certificates first;
- `config migrate` output for all five types, planned as the config, showed no change.

Every validation and action carries the fields of every DNS provider and action type, and the plugin gives some of them non-empty defaults (a port, a host, an `insecure` flag). The stale-field warning and `config migrate` ignore them: the warning skips fields still at the template default, and migrate emits only the fields of the row's own provider or action type.

**Not verified:** `settings/fetchCronIntegration` (the test left the plugin disabled, so it was never called). Nothing contacts a CA or a DNS provider and a certificate is never signed, so a valid account and an issued certificate are not live-verified.

## OpenVPN client instances (#808)

`openvpn.instances` manages OpenVPN **client** instances on the modern MVC API (`openvpn/instances/*`, stock OPNsense, no plugin). It is a list-shape, managed-set type ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)) and the child of `trust.cas`. Every write sends `role: client`; a live server instance is never matched, updated or deleted. The legacy `os-openvpn-legacy` plugin is not managed: a cutover recreates the client as a modern instance.

```yaml
opnsense:
  openvpn:
    instances:
      - name: office-vpn
        config:
          description: Office VPN
          enabled: true
          proto: udp
          port: 1194
          remote:
            - vpn.example.com
          ca_ref: vpn-ca
          cert_ref: vpn-client-cert
          username: secret://env_secrets/openvpn/office/username
          password: secret://env_secrets/openvpn/office/password
          data_ciphers:
            - AES-256-GCM
          remote_cert_tls: true
          route:
            - 192.0.2.0/24
```

| Field | Meaning |
| --- | --- |
| `description` | Wire `description` and the identity. Defaults to the resource `name`. |
| `enabled` | Boolean. |
| `dev_type` | `tun`, `tap` or `ovpn`. |
| `proto` | `udp`, `udp4`, `udp6`, `tcp`, `tcp4` or `tcp6`. |
| `remote` | Required list of remote hosts, sent comma-joined; compared in order. |
| `port` | Integer 1-65535. |
| `topology` | `net30`, `p2p` or `subnet`. |
| `ca_ref` | Required. Name of the `trust.cas` resource; resolved to the live CA `refid` (sent as wire `ca`). |
| `cert_ref` | Optional. Name of the `trust.certs` resource; resolved to the live certificate `refid` (sent as wire `cert`). Omitted: `cert` is neither sent nor compared, so a certificate set by hand is never cleared. Certificate-only, username/password-only and combined authentication all work. |
| `tls_key_ref` | Optional. Name of the `openvpn.static_keys` resource ([#1319](#openvpn-static-keys-1319)); resolved to the live static key `uuid` (sent as wire `tls_key`). Omitted: `tls_key` is neither sent nor compared, so a key set by hand is never cleared. |
| `username`, `password` | `secret://env_secrets/<path>` URIs; a literal is a validation error. `password` is write-only: never compared, sent on add and on update only with `update_password: true`. |
| `update_password` | Boolean; send `password` on update too. |
| `auth` | Auth digest name. |
| `data_ciphers` | List; wire `data-ciphers`; compared as a set. |
| `data_ciphers_fallback` | String; wire `data-ciphers-fallback`. |
| `remote_cert_tls` | Boolean. |
| `verify_x509_name` | String; wire `verify-x509-name`. |
| `various_flags`, `route`, `redirect_gateway` | Lists, compared as sets. |
| `keepalive_interval`, `keepalive_timeout`, `reneg_sec`, `tun_mtu`, `fragment`, `mssfix` | Non-negative integers (`reneg_sec` is wire `reneg-sec`). |
| `vpnid` | Optional positive integer; unique across instances. The API requires it on add (verified on a test firewall). It names the tunnel device (`ovpncN` for clients), so pin it when an interface assignment or firewall rule references the device. Omitted: an add allocates the next free id (max of every live instance of any role, every explicit `vpnid` in the apply and ids already allocated, plus one; starting at 1), and the live value is never compared, so it never causes drift. |
| `verb` | Log verbosity, integer 0-11. |
| `lock` | Never add, update or delete. |

Fields are sparse: only the ones you set are written and compared. `uuid` is assigned by the box and rejected, as are `role`, `ca`, `cert` (use `cert_ref`), `tls_key` (use `tls_key_ref`) and the hyphenated wire spellings.

**Not managed (follow-ups).** Server instances. Messages and logs name the resource and field and never include `username` or `password`.

**Order and pending references.** CAs, certificates and static keys are applied before instances, and instances are deleted before them. A plan for an instance whose `ca_ref` CA, `cert_ref` certificate or `tls_key_ref` static key is not on the box yet shows an add plus a warning; at apply an unresolved `ca_ref`, `cert_ref` or `tls_key_ref` raises an error before any write. The `trust.certs` search runs only when an instance sets `cert_ref`, and the static-key search only when one sets `tls_key_ref`. Changes are applied with one `openvpn/service/reconfigure` call after the instance writes.

**What is verified.** A live plan and apply on a test firewall, with a throwaway disabled client and CA that were removed afterwards:

- `add` requires `vpnid`; the template leaves it empty, so an omitted `vpnid` is allocated (the first client got `1`);
- the stored client has role `client` and the `remote`, `port`, CA reference and username from YAML;
- a re-plan is idempotent;
- `set` with a changed `port` changes only that field and keeps the omitted ones, `vpnid` and credentials included;
- removing the config deletes the instance, then certificates, then CAs.

**`cert_ref` verified (#1320).** A second live run on a test firewall, with a throwaway CA, two client certificates signed by it and a disabled client instance, all removed afterwards:

- the first plan shows adds for all four, with pending-reference warnings for the CA and the certificate;
- after the apply, a read-only `GET openvpn/instances/get/{uuid}` shows `cert` selecting the certificate named by `cert_ref`, and `ca` the CA;
- a re-plan is idempotent;
- pointing `cert_ref` at the second certificate is one update, and `cert` then selects that certificate;
- removing the config deletes the instance, then both certificates, then the CA, and none of them is left on the box.

## OpenVPN static keys (#1319)

`openvpn.static_keys` manages the static keys (tls-auth, tls-crypt, tls-crypt-v2) that an OpenVPN instance references through `tls_key`. They live in a sub-API of the instances controller: `openvpn/instances/{search,get,add,set,del}StaticKey`. It is a list-shape, managed-set type ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). An instance names a key with `tls_key_ref`.

```yaml
opnsense:
  openvpn:
    static_keys:
      - name: office-tls-key
        config:
          description: Office tls-crypt key
          mode: crypt
          key: secret://env_secrets/openvpn/office/tls_key
    instances:
      - name: office-vpn
        config:
          ca_ref: vpn-ca
          tls_key_ref: office-tls-key
          remote:
            - vpn.example.com
```

| Field | Meaning |
| --- | --- |
| `description` | Wire `description` and the identity. Defaults to the resource `name`. A changed description is a delete plus an add; two live keys with the same description raise a drift error. |
| `mode` | Required. `auth`, `crypt` or `crypt-v2`. Always sent and compared: the model's empty template silently selects `crypt`, and a wrong mode breaks the tunnel. |
| `key` | Required. A `secret://env_secrets/<path>` URI; a literal is a validation error. After resolution it must be a PEM-style block with BEGIN and END markers. |
| `update_key` | Boolean. Send `key` on update too, whatever the comparison found. |
| `lock` | Never add, update or delete. |

`uuid` is assigned by the box and rejected, as are unknown keys. The `genKey` endpoint is not used: the key comes from the secret.

**Key comparison.** `key` is compared only when the live row returns a non-empty value. Only the `-----BEGIN`..`-----END` block counts, whitespace-normalized, so the `#` comment header that `genKey` and `openvpn --genkey` write does not read as drift. The box echoes the key (verified), so a changed key is detected and sent automatically; `update_key: true` only matters on a box that does not return it, where the key is otherwise sent on add only. Key material is never logged, put in an error message or shown in a `repr`; messages name the resource and the field only.

**In-use guard.** A managed static key that a live instance of any role (client or server) still points at through `tls_key` is not deleted. It is kept with a warning and reported as unresolved, so it stays managed and the next apply retries. The guard reads the instances only when the diff has deletes (and on destroy). When one apply switches an instance to a new key and drops the old key from YAML, the old key is kept and removed on the next apply.

**Order.** Static keys are applied before instances and, because instances split their deletes, deleted after them. Static keys depend on no other table type, so they do not split their own deletes. Changes are applied with one shared `openvpn/service/reconfigure` call.

**What is verified.** A live plan and apply on a test firewall, with a throwaway CA, two generated static keys (kept as `secret://` URIs) and a disabled client instance, all removed afterwards:

- the first plan shows adds for the CA, the key and the instance, with pending-reference warnings on the instance; the apply adds all three and runs one `openvpn/service/reconfigure`;
- `getStaticKey/{uuid}` echoes `key`, and `searchStaticKey` rows carry `uuid`, `description`, `mode`, `%mode` and `key`;
- the instance's `tls_key` is a reference option keyed by static key `uuid`, and it selects the key named by `tls_key_ref`;
- a re-plan is idempotent, including for a key stored with its `#` comment header;
- a `mode` change is one update; pointing `key` at the second secret is one in-place update (same `uuid`, the instance still references it), detected without `update_key`;
- dropping the key from YAML while the live instance still references it keeps the key with a warning on every run;
- removing everything deletes the instance first, then the key and the CA, and nothing is left on the box;
- no key text appears in plan or apply output.

**Not verified:** `crypt-v2` is accepted but has not been tried on a box, and tunnel behaviour, since the test client stayed disabled.

The password reads back from the API, but it is not compared; use `update_password` to rotate it. **Not verified:** whether `mssfix` takes an integer, and tunnel behaviour, since the test client stayed disabled.

## Firewall categories (#1286)

`firewall.categories` manages the categories a firewall rule, NAT rule or alias can carry, through `firewall/category/{search,get,add,set,del}Item`. It is a list-shape, managed-set type ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). Categories are model data: the controller has no reconfigure action, so there is no finalization hook.

```yaml
opnsense:
  firewall:
    categories:
      - name: lab-servers
        config:
          color: "#336699"
      - name: lab-clients
        config:
          name: Lab Clients
          auto: true
```

| Field | Meaning |
| --- | --- |
| `name` | Wire `name` and the identity. Defaults to the resource name. A changed name is a delete plus an add; two live categories with the same desired or managed name raise a drift error. `infrafoundry` is reserved for the provider's marker. |
| `auto` | Boolean, default `false`. Sent as `"0"`/`"1"` and always compared. |
| `color` | String, default empty. Empty, or `#rrggbb` / `rrggbb`. Both sides are compared lowercase and without a leading `#`, so either form causes no drift. It is sent without the `#`. |
| `lock` | Never add, update or delete. |

`uuid` is assigned by the box and rejected, as are unknown keys.

**The `infrafoundry` marker.** The provider tags its managed rules with its own `infrafoundry` category. That row is dropped from every diff, so it is never deleted, never updated and never counted in `N unmanaged (kept)`. `config migrate` and the resource-id lookup skip it too, and a resource whose effective name is `infrafoundry` is a validation error.

**Order.** Nothing in YAML references a category by name: `firewall.rules` and `firewall.aliases` take category UUIDs, and NAT carries only the marker. Add order therefore does not matter. Categories are registered after rules, NAT and aliases, so the runner deletes them after those types without a split delete phase, and they declare no dependencies. If rules ever gain a name-based category reference, this ordering must be revisited.

**A category in use.** The controller deletes safely and refuses a category that something still references, including models this provider does not manage. `infra plan` therefore shows the delete, and `infra apply` keeps the category with a warning (`firewall category '<name>' kept: the box reports it in use`) instead of failing. It is not counted as deleted, stays managed and is retried on the next apply. `infra destroy` skips it the same way.

**`config migrate`.** `foundry config migrate --provider opnsense --component firewall.categories` writes one entry per live category except the marker. The handle is a slug of the name (lowercase, runs of other characters become `-`, `-2`, `-3` ... when a resource of the environment or an earlier row already uses it), and `config.name` carries the exact live name. `auto` appears only when set and `color` only when non-empty.

**What is verified.** The envelope is `category` with `name`, `auto` (a `"0"`/`"1"` string) and `color` (a string), and `searchItem` rows carry every field, so a plan makes one call and no per-row `getItem`. A live plan and apply on a test firewall, with throwaway categories and a disabled throwaway rule, all removed afterwards, confirmed:

- adds store `auto` as `"1"`/`"0"` and `color` without the `#`, lowercase (`#336699` is stored as `336699`); a re-plan is idempotent and the marker is not counted as unmanaged;
- a `color` change is one in-place update (same uuid);
- with a rule still carrying a category's uuid, `delItem` is refused with HTTP 500 and a JSON body whose `errorTitle` reads `Item categories.category {<name>} in use by:`; `infra apply` keeps the category with the warning above, and the next plan shows the delete again;
- removing the rule and the category together deletes the rule in the delete phase and the category later in the same apply;
- `config migrate` writes the live category with its exact name and skips the marker;
- after clean-up only the marker is left, and a final plan is clean.

## Tailscale (#787)

The `os-tailscale` plugin is managed through three direct-API types: `tailscale.settings` and `tailscale.auth` (singleton dicts) and `tailscale.subnets` (a list). The plugin is installed by `system.firmware`, so the three types run after it, in the order settings, auth, subnets. The endpoints are plugin-kind: the bundled specs cover core only, so the version check skips them (see [Endpoint registry and version check](#endpoint-registry-and-version-check-1239)). The provider never starts the service and never joins a tailnet: only the settings, authentication and subnet endpoints and `service/reconfigure` are registered.

Route approval and ACLs are on the control-plane side and are handled by the separate `tailscale` provider; see [Tailscale provider](../providers/tailscale.md).

```yaml
opnsense:
  tailscale:
    settings:
      enabled: false
      listen_port: 41641
      accept_dns: false
      enable_snat: true
    auth:
      login_server: https://controlplane.example.com
      pre_auth_key: secret://env_secrets/opnsense/tailscale/auth/pre_auth_key
    subnets:
      - name: lab-v4
        config:
          subnet: 192.0.2.0/24
          description: Lab IPv4
      - name: lab-v6
        config:
          subnet: 2001:db8::/64
          description: Lab IPv6
```

### Settings (`tailscale.settings`)

Every key is optional; only declared keys are compared and written. Keys are snake_case and map to the plugin's camelCase fields.

| Field | Wire | Type |
| --- | --- | --- |
| `enabled` | `enabled` | bool |
| `login_timeout` | `loginTimeout` | integer, 0 or more |
| `listen_port` | `listenPort` | integer, 0-65535 (0 is accepted so a live 0 round-trips through `config migrate`) |
| `accept_dns` | `acceptDNS` | bool |
| `advertise_exit_node` | `advertiseExitNode` | bool |
| `use_exit_node` | `useExitNode` | string, `""` for none |
| `accept_subnet_routes` | `acceptSubnetRoutes` | bool |
| `enable_ssh` | `enableSSH` | bool |
| `enable_snat` | `disableSNAT` | bool, **inverted** |

**`enable_snat` is inverted.** The plugin stores `disableSNAT`, so `enable_snat: true` is sent as `"0"` and `enable_snat: false` as `"1"`; `config migrate` inverts back. `disable_snat` is refused with a hint.

**`use_exit_node`.** On the box this is an option dict of the offers, which depend on peers. The live value is the selected key. A declared value the box does not offer is a plan warning and an apply error raised before any write. `""` always means none.

**The write omits `subnets`.** The settings `get` nests the subnet list inside the settings model as `subnets: {subnet4: [...]}`. The write body echoes the other live fields with the declared ones overwritten, but never carries `subnets`: OPNsense MVC `set` updates only the nodes posted, so leaving it out keeps the list for the subnet CRUD. A `subnets` key in the settings YAML is refused with a hint to use `tailscale.subnets`. `hostname` and `exit_node` are refused too: they are not plugin settings.

### Authentication (`tailscale.auth`)

| Field | Meaning |
| --- | --- |
| `login_server` | An `http(s)://` URL (`loginServer`). |
| `pre_auth_key` | A `secret://` URI (`preAuthKey`). A literal is a validation ERROR. |
| `update_pre_auth_key` | Bool. Forces the key to be written; see below. |

**Key policy.** The key is resolved through the environment secrets and is never logged, put in an exception, shown in a plan or echoed back from the box.

- When the box returns a non-empty `preAuthKey`, it is compared with the declared one (both stripped) and written on a difference.
- When the box returns an empty or masked value, the key is write-only: it is sent only with `update_pre_auth_key: true`. Declared without the flag, the plan carries a warning telling you to set it.
- With `update_pre_auth_key: true` the key is always sent and counts as a change, like `update_password` on `system.users`. Remove the flag after the apply.
- The write body echoes the live `loginServer` overwritten by the declared one, but never the live `preAuthKey`: echoing an empty or masked value would clear the stored key. A change to `login_server` alone therefore leaves the key untouched.
- The plan shows the key as `[REDACTED]`.

### Subnets (`tailscale.subnets`)

Entries are `name` plus `config` with `subnet` (required), `description` and `lock`. The identity is the normalized CIDR, so `2001:DB8::/64` and `2001:db8::/64` are the same subnet; a CIDR with host bits set is a validation error, and so are two entries with the same normalized CIDR. `description` defaults to the empty string and is always compared and sent. IPv4 and IPv6 share the wire envelope `subnet4`. The box assigns `uuid`; it is rejected as a key.

Deletes use the managed set ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)): a subnet added by hand is kept and shown as unmanaged. Two live subnets with one desired or managed CIDR raise a drift error. Subnets do not split the delete phase.

### Migrate

`foundry config migrate --provider opnsense --component tailscale.settings` writes every mapped field present on the box. `tailscale.auth` writes `login_server`, and `pre_auth_key` only as the placeholder `secret://env_secrets/opnsense/tailscale/auth/pre_auth_key` when the box holds a key; the key itself is never written. `tailscale.subnets` writes one entry per live subnet. The handle is a slug of the description, else of the CIDR, with `-2`, `-3` ... when a resource of the environment or an earlier row already uses it.

### Plugin not installed

A 404 on the first read at plan means `os-tailscale` is not installed. The plan carries the warning `os-tailscale is not installed; declare it under system.firmware plugins`: the singletons plan the declared map as an update and every subnet is an add. A 404 at apply raises.

### Node stays logged out after the key is set

A box can stay out of the tailnet after `tailscale.auth` has written a valid, unused pre-auth key. The cause is in the plugin, not the provider. Its generated `/etc/rc.conf.d/tailscaled` passes `--auth-key` to `tailscale up` only when `/var/db/tailscale/tailscaled.state` exists and holds no `"_current-profile"`. That check came from opnsense/plugins#5047, the fix for a key being reused at boot (opnsense/plugins#4661). It was seen with os-tailscale 1.4 and tailscale 1.98.5_1 on OPNsense 26.1.11, and is reported upstream as [opnsense/plugins#5903](https://github.com/opnsense/plugins/issues/5903). Once a plugin release fixes it, the recovery below is no longer needed.

There are two cases:

- **No state file yet.** The rc script reads its config before `tailscaled` creates the state file, so the first start runs `tailscale up` without the key. The start times out waiting for the `Running` state. A second start passes the key and joins. Seen once, after the state file had been moved aside; not checked on a newly installed box.
- **Stale profile.** Removing the plugin leaves `/var/db/tailscale` behind. After the node was deleted from the tailnet, or after a reinstall, the old profile is still in the state file and the key is never passed. `tailscale status` shows `Logged out.`, and the plugin's `service/start` and `service/restart` return `Error (1)`. A reconfigure or another apply does not help.

To recover:

1. After an apply that writes `tailscale.auth`, read `tailscale/status/status` and check `BackendState`. `Running` means the node joined.
2. If it is `NeedsLogin`, apply again, or call `tailscale/service/reconfigure`. That covers the first case.
3. If it still is `NeedsLogin`, the profile is stale. The API cannot reset it; over SSH on the box, run:

    ```sh
    service tailscaled stop
    mv /var/db/tailscale/tailscaled.state /var/db/tailscale/tailscaled.state.bak
    mv /var/db/tailscale/profile-data /var/db/tailscale/profile-data.bak
    service tailscaled start   # creates a fresh state file; times out without the key
    service tailscaled restart # now passes the key and joins
    ```

    Delete the `.bak` copies once the node shows `Running`.

### Reconfigure

One `tailscale/service/reconfigure` fires per apply, through the shared `tailscale_reconfigure` finalization hook, when any of the three types changed state. `tailscale.subnets` `destroy` reconfigures directly when it deleted a row, because the hook does not fire on destroy.

### Verified and not verified

**Verified by a read-only probe** of a test firewall with the plugin installed and Tailscale disabled: `settings/get` (envelope `settings`, with `useExitNode` as an option dict and `subnets` nested), `authentication/get` (envelope `authentication` with `loginServer` and `preAuthKey`), `settings/searchSubnet` (the usual grid) and `settings/getSubnet` (the item template, envelope `subnet4` with `subnet` and `description`).

**Verified live** on a test firewall: the plugin was installed for the test, Tailscale stayed disabled throughout with a throwaway, non-functional pre-auth key, and the plugin was removed afterwards with its settings restored to the defaults:

- `addSubnet`, `setSubnet/{uuid}` (same uuid) and `delSubnet/{uuid}` (reply `{"result": "deleted"}`) work; `searchSubnet` rows carry `uuid`, `subnet` and `description`; an IPv6 CIDR declared in upper case re-plans clean;
- a subnet added outside the YAML is kept as unmanaged; dropping a managed one deletes it;
- `settings/set` writes `enable_snat: false` as `disableSNAT` `"1"` and leaves the subnet list untouched;
- `authentication/set` stores the key, and `authentication/get` **echoes it**, so a changed key is detected without `update_pre_auth_key`; `loginServer` is not touched when it is not declared;
- `tailscale/service/reconfigure` answers `{"status": "ok"}`; one fires per apply, and the service stays stopped;
- every re-plan is idempotent; `config migrate` re-creates all three types and writes only the `secret://` placeholder for the key;
- the key never appears in plan, apply or migrate output.

**Not verified:** a running tunnel (Tailscale stayed disabled), `use_exit_node` with real peers, and the "plugin not installed" plan warning against a box (covered by unit tests).

## Unbound advanced settings (#1254)

`opnsense.unbound.advanced` is a singleton dict with three list fields:

| YAML | wire field |
|---|---|
| `private_domains` | `privatedomain` |
| `insecure_domains` | `insecuredomain` |
| `private_addresses` | `privateaddress` |

An omitted key is not managed. An empty list (`[]`) is managed and clears the list. Lists are compared as sets. `insecure_domains` is for internal zones under a DNSSEC-signed parent. The `set` envelope key `unbound` was verified live through `unbound.settings` (#1091), which writes the same section through the same call.

```yaml
opnsense:
  unbound:
    advanced:
      private_domains:
        - test.example.net
      insecure_domains:
        - test.example.net
```

## Unbound general and advanced settings (#1091)

`opnsense.unbound.settings` is a singleton dict with optional `general:` and `advanced:` mappings. Keys are the OPNsense wire field names, as in `unbound.forwards`. An omitted key, or an omitted section, is not managed. Comparison is sparse: only declared fields are compared and written; the whole live section is echoed back on write, so undeclared settings stay unchanged.

| Kind | Fields | YAML value |
|---|---|---|
| general booleans | `enabled`, `stats`, `dnssec`, `dns64`, `noarecords`, `regdhcp`, `regdhcpstatic`, `noreglladdr6`, `noregrecords`, `txtsupport`, `cacheflush`, `safesearch`, `enable_wpad` | `true` / `false` |
| `port` | `port` | integer 1-65535 |
| `local_zone_type` | `local_zone_type` | one of `transparent`, `always_nxdomain`, `always_refuse`, `always_transparent`, `deny`, `inform`, `inform_deny`, `nodefault`, `refuse`, `static`, `typetransparent` |
| interface lists | `active_interface`, `outgoing_interface` | list of interface keys, compared as sets |
| text | `dns64prefix` (empty or a network prefix), `regdhcpdomain` (no whitespace) | string |
| advanced booleans | `hideidentity`, `hideversion`, `prefetch`, `prefetchkey`, `dnssecstripped`, `belownxdomain`, `aggressivensec`, `serveexpired`, `serveexpiredttlreset`, `qnameminstrict`, `extendedstatistics`, `logqueries`, `logreplies`, `logtagqueryreply`, `logservfail`, `loglocalactions`, `infrakeepprobing` | `true` / `false` |
| levels | `logverbosity` (0-5), `valloglevel` (0-2) | integer |
| tuning | `serveexpiredreplyttl`, `serveexpiredttl`, `serveexpiredclienttimeout`, `msgcachesize`, `rrsetcachesize`, `outgoingnumtcp`, `incomingnumtcp`, `numqueriesperthread`, `outgoingrange`, `jostletimeout`, `discardtimeout`, `cachemaxttl`, `cachemaxnegativettl`, `cacheminttl`, `infrahostttl`, `infracachenumhosts`, `unwantedreplythreshold` | non-negative integer, or a string without whitespace or commas |

Unknown keys are validation errors. `privatedomain`, `insecuredomain` and `privateaddress` stay owned by `unbound.advanced`: declaring one here (by wire name or by its `unbound.advanced` key) is an error that names the `unbound.advanced` key to use. Both resources can be declared together, in either order. A declared field that the live section does not carry fails at plan time.

**Verified live** on a test firewall: an `advanced` field changed through `unbound/settings/set`, `unbound/service/reconfigure` ran with the service still running, a re-plan after apply showed no update, and restoring the value worked the same way.

`config migrate` exports every supported field present on the box, skipping empty text and empty lists; digit-only text is exported as an integer. The owned fields are never exported. `unbound.advanced` has no migrate extractor yet; that is a known follow-up gap.

```yaml
opnsense:
  unbound:
    settings:
      general:
        enabled: true
        regdhcp: true
        regdhcpstatic: true
        local_zone_type: transparent
      advanced:
        hideidentity: true
        prefetch: true
```

## Interface settings (#1092)

`opnsense.interfaces.settings` is a singleton dict over the `OPNsense\Interfaces\Settings` model. Every key is optional.

| YAML | wire field | type | model default |
|---|---|---|---|
| `disable_checksum_offloading` | `disablechecksumoffloading` | bool | `true` |
| `disable_segmentation_offloading` | `disablesegmentationoffloading` | bool | `true` |
| `disable_large_receive_offloading` | `disablelargereceiveoffloading` | bool | `true` |
| `vlan_hardware_filtering` | `disablevlanhwfilter` | `enable` / `disable` / `default` (wire `0` / `1` / `2`) | `default` |
| `disable_ipv6` | `disableipv6` | bool | `false` |
| `dhcp6_no_release` | `dhcp6_norelease` | bool | `false` |
| `dhcp6_debug` | `dhcp6_debug` | bool | `false` |
| `dhcp6_duid` | `dhcp6_duid` | string | empty |
| `dhcp6_ra_timeout` | `dhcp6_ratimeout` | integer >= 0 | `10` |

An omitted key is not managed. `config migrate` exports only the fields that differ from the defaults above (the defaults were read from OPNsense 26.1.6). A live `disablevlanhwfilter` value outside `0`/`1`/`2` is logged and omitted.

```yaml
opnsense:
  interfaces:
    settings:
      vlan_hardware_filtering: disable
```

**Not yet verified live.** The `get` shape and the defaults were probed on a test firewall, but the `set` call and the `interfaces/settings/reconfigure` call have not been run against a box. The need for `reconfigure` is inferred from the GUI's Apply button. After the first apply, re-run `infra plan` and expect no update.

**Link reset.** Reconfigure re-applies the hardware flags to every interface, which on some NICs can briefly reset the link. Apply during a maintenance window.

## Syslog settings (#804)

`opnsense.syslog.settings` is a singleton dict over the `general` section of the `OPNsense\Syslog` model. Every key is optional. The model's `destinations` list is not managed.

| YAML | wire field | type |
|---|---|---|
| `enabled` | `enabled` | bool |
| `log_local` | `loglocal` | bool |
| `max_preserve` | `maxpreserve` | integer >= 0 |
| `max_file_size` | `maxfilesize` | integer >= 0 |

An omitted key is not managed. `config migrate` exports every `general` field present on the box. The write sends `{"syslog": {"general": {...}}}`: the whole flattened live `general` object with the declared fields overwritten.

```yaml
opnsense:
  syslog:
    settings:
      enabled: true
      log_local: true
      max_preserve: 31
      max_file_size: 10
```

**Verified live** on a test firewall: `syslog/settings/set` with the `syslog` envelope changed `max_preserve` and left the other `general` fields and the `destinations` list unchanged; `syslog/service/reconfigure` ran and the service stayed running; a re-plan after apply showed no update.

## Host discovery (#792)

`opnsense.hostdiscovery` is a singleton dict over the `OPNsense\Hostdiscovery` model, the passive host-discovery service. Every key is optional.

**Rename.** The issue proposed the key `hostwatch`. It is `hostdiscovery` because the wire API is `/api/hostdiscovery/`; `/api/hostwatch/` is not in the 26.1 spec and answers 404.

| YAML | wire field (under `hostdiscovery.general`) | type |
|---|---|---|
| `enabled` | `enabled` | bool |
| `promisc` | `promisc` | bool |
| `verbose` | `verbose` | bool |
| `skip_nets` | `skip_nets` | list of CIDRs |
| `interface` | `interface` | list of interface keys |
| `expire4_interval` | `expire4_interval` | integer >= 0 |
| `expire6_interval` | `expire6_interval` | integer >= 0 |

An omitted key is not managed. List fields compare as sets; `[]` clears the list. Each `interface` entry must be a managed `interfaces.assignments` name or a live interface. `config migrate` exports every live field present.

```yaml
opnsense:
  hostdiscovery:
    enabled: true
    promisc: false
    verbose: false
    skip_nets:
      - 192.0.2.0/24
    interface:
      - lan
    expire4_interval: 3600
    expire6_interval: 3600
```

**Verified live** on a test firewall: `config migrate` output planned with no update; changing `verbose` went through `hostdiscovery/settings/set` (confirming the wire field name), `hostdiscovery/service/reconfigure` ran with the service still running, a re-plan showed no update, and restoring the value worked the same way. An empty `skip_nets` reads back as a single selected empty entry, which compares equal to `[]`.

## Outbound NAT mode (#1333)

`opnsense.firewall.source_nat` is a singleton dict over the `snat_mode` field of the `filter.general` node of the firewall filter model. The name follows the wire controller (`firewall/source_nat`), because `firewall.nat` is a list.

| YAML | wire field (under `filter.general`) | values |
| :--- | :--- | :--- |
| `snat_mode` | `snat_mode` | `automatic`, `hybrid`, `advanced`, `disabled` |

Manual outbound rules (`firewall.nat`, `kind: outbound`) take effect, and `searchRule` lists them, only in `hybrid` or `advanced` mode. A fresh box is in `automatic`, so declared outbound rules did nothing, and each apply added another copy because `searchRule` returned no rows.

```yaml
opnsense:
  firewall:
    source_nat:
      snat_mode: hybrid
```

- **Write.** `POST firewall/source_nat/set` with `{"filter": {"general": {"snat_mode": "hybrid"}}}`, then the `source_nat_apply` hook posts `firewall/source_nat/apply` once. `disabled` is sent as `disabled`. The type is dispatched just before `firewall.nat`; destroy is a no-op.
- **Read path of `firewall.nat`.** Outbound rules come from `searchRule` in `hybrid`, `advanced` and when the mode cannot be read. In `automatic` and `disabled` they are read from `filter.snatrules.rule` of `firewall/source_nat/get`, with option dicts flattened to the selected keys.
- **OPNsense before 26.1.** The mode lives outside the MVC model there, so `get` has no `filter.general.snat_mode`; `firewall.source_nat` fails at plan time with a "needs OPNsense 26.1 or later" error. `firewall.nat` keeps using `searchRule`.
- **Plan warning.** When at least one enabled outbound rule is declared and the effective mode is `automatic` or `disabled`, the plan warns that the rules have no effect and names `firewall.source_nat`. The effective mode is the declared `snat_mode`, otherwise the live one. No warning is issued when the live mode cannot be read.

**Verified live** on a test firewall: `firewall/source_nat/set` with the `filter.general` envelope returned `saved`, `firewall/source_nat/apply` returned `OK`, and afterwards `searchRule` listed the rule and the plan showed no changes. The new code was then run live on the same box. With the mode set back to `automatic` and one managed outbound rule stored, `searchRule` returned no rows, yet the plan showed `firewall.nat` with nothing to add and printed the inert-mode warning. Declaring `snat_mode: hybrid` planned one `firewall.source_nat` update and no warning; the apply ran the `source_nat_apply` hook once, the mode read back `hybrid`, `searchRule` listed the rule again, and the re-plan showed no changes. `config migrate` emitted the declared mode. Copies a box already holds are not removed: live outbound rules are matched by name, so duplicates collapse to one match.

## How deletes work: the managed set (#1256)

`opnsense_direct` deletes only objects InfraFoundry manages ([ADR-0018](../decisions/0018-opnsense-direct-api-deletes-are-limited-to-the-managed-set.md)). A live object InfraFoundry never applied is kept, whether or not its type has YAML entries. `infra plan` shows those as `N unmanaged (kept)` on the type's summary line.

**What counts as managed.** The state database keeps an append-only row per applied resource. For each type and name, the newest row that is `active` or `deleted` decides; the entry is managed when that row is `active`. A successful full `infra apply` records a `deleted` row for every managed name that is no longer in YAML, so it stops being managed. A managed entry InfraFoundry cannot resolve to a key (a row that no longer parses, or a host alias or kea reservation with no resolvable parent and no orphan match) is not released: it stays managed, the plan warns, and the next run retries it. A run that applies only part of the environment (`--add-only`, `-r`, `-p`) deletes nothing and records nothing.

**Removing the last entry of a list type.** The type is still dispatched when it has managed objects, so removing the only alias, forward or reservation deletes that object on the next apply. A type with no YAML entries and nothing managed is skipped.

**Two kinds of type.**

- **Managed-set types** delete a live object only if it matches a managed entry: `interfaces.vlans`, `interfaces.assignments`, `firewall.aliases`, `routing.gateways`, `routing.static`, `interfaces.virtual_ips`, `unbound.host_overrides`, `unbound.host_aliases`, `unbound.forwards`, `kea.dhcp4.subnets`, `kea.dhcp4.reservations`, `kea.dhcp6.subnets`, `kea.dhcp6.reservations`, `trust.cas`, `trust.certs`, `openvpn.static_keys`, `openvpn.instances`, `firewall.categories`, `acmeclient.accounts`, `acmeclient.validations`, `acmeclient.actions`, `acmeclient.certs` and `tailscale.subnets`.
- **Marker types** (`firewall.rules`, `firewall.nat`, `cron.jobs`) already delete only objects carrying InfraFoundry's marker. They use the same dispatch and release rules but need no managed set.
- **Singletons** (`system.*`, `unbound.advanced`, `unbound.settings`, `interfaces.settings`, `syslog.settings`, `hostdiscovery`, `firewall.source_nat`, `acmeclient.settings`, `tailscale.settings`, `tailscale.auth`, `radvd`) are unaffected.

**Upgrading.** There is no migration. The first `infra plan` after upgrading can show deletes you have not seen before: any object InfraFoundry applied for a type whose YAML entries were all removed was previously left on the box and is now deleted. Hand-added objects next to managed ones, which the old full reconcile deleted, are now kept and shown as unmanaged. Review the first plan before applying.

**Parent and child types.** Unbound host overrides are applied before host aliases, and kea subnets before kea reservations. Kea deletes run in reverse order first (reservations, then subnets), so a managed reservation is deleted while its subnet is still live (#1264). OPNsense does not cascade a kea subnet delete to its reservations and does not refuse it, so without this order they would be left pointing at a subnet that no longer exists. Gateways and static routes are applied before firewall rules, so a rule's `gateway:` names a gateway that already exists (#1269). The same reverse-order delete phase covers firewall rules, NAT, static routes, gateways and virtual IPs, so a child is deleted while its parent is still live. Interface assignments use it too: OPNsense refuses to delete an assigned VLAN (HTTP 500), so the assignment is deleted first (#1271). An assignment's apply installs the controller (an SSH step) only when it has something to write, so the delete phase and the forward pass do not repeat it. Radvd uses it too, so a radvd record is deleted before its interface assignment (#1272). Firewall categories are applied after rules, NAT and aliases, so they are deleted after them, and a category the box reports in use is kept with a warning (#1286). Trust CAs are applied before trust certificates, and certificates are deleted first (#807). OpenVPN client instances are applied after the CAs and certificates they reference and deleted before them (#808, #1320). ACME certificates are applied after the accounts, validations and actions they reference and deleted before them (#790). Deleting an Unbound host override does remove its aliases. If a managed child still cannot be matched to its parent, it is matched through live orphans (same MAC/DUID, or for an alias the same hostname and domain; an alias only when exactly one live orphan fits), and with no match it is skipped with a warning and retried on the next run.

**A subnet with reservations you did not create.** InfraFoundry does not delete a kea subnet while a reservation it does not manage, such as one made by hand, still uses it. `infra plan` shows `N blocked (kept)` and a warning naming the subnet and each reservation's MAC or DUID and IP. `infra apply` leaves the subnet in place with the same warning, does not fail, and retries on the next run. To finish the removal, delete or move the reservation on the box, then re-run apply. `infra destroy` skips such a subnet the same way.

**`lan` and `wan` are protected.** A managed `lan` or `wan` assignment is never deleted; it is reported as unmanaged and a warning is logged, because removing the interface the API is reached through would lock you out. Other assignments are deletable, including one that carries the management address. Keep the management interface in YAML with `lock: true`.

**Removing the last opnsense resource.** When an environment has no `provider: opnsense` resources but InfraFoundry still manages opnsense objects, a full `infra plan` or `infra apply` dispatches opnsense and deletes them. Runs with `--add-only`, `-r`, `-p` or `--dry-run` do not. `-P opnsense` works, and `-P <other>` leaves opnsense out (#1260).

## Box-to-box migration runbook (template)

This template assumes you are cutting over a current box (`OLD`) to a new box (`NEW`) and want the result to be a drop-in replacement, with subsequent migrations between same-spec boxes being trivial.

### Prerequisites

1. The OPNsense provider supports every resource type your `OLD` config uses (see matrix above; close any gaps first).
2. Both boxes are reachable on the network and admin credentials work.
3. You have downloaded `OLD`'s `config.xml` (System → Configuration → Backups → Download).
4. You have the `NEW` box installed with a base interface accessible from your management network.

### Steps

1. **Extract**: run `foundry config migrate --env <env> --provider opnsense --component <type>` for every supported resource type on `OLD` to dump live state into YAML under `envs/<env>/opnsense/`.
2. **Edit interface map**: in the YAML, remap physical NIC names (`em0` → `vtnet0`, etc.) and any VLAN parent interface references. This is the only manual edit if the new box has different NICs.
3. **Out-of-IaC import**: on `NEW`, System → Configuration → Backups → Restore, choose "Restore area" and import only the sections from "out of IaC scope" above. **Do not** restore VLANs, filter, NAT, or DHCP — those come from IaC.
4. **Verify interface assignments YAML**: confirm the `interface_assignments` YAML in `envs/<env>/opnsense/` correctly maps each logical interface (LAN, WAN, OPT1, etc.) to its physical NIC or VLAN on `NEW`. The mapping is applied automatically during step 7 (`foundry infra apply`) via the in-tree `AssignSettingsController.php` fork ([ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions); production conversion landed in #720). No manual GUI step is required.
5. **Switch endpoint**: update `provider_settings.opnsense.api_url` in `envs/<env>/settings.yaml` to point at `NEW`. The interface-assignment controller install SSHes to the `api_url` host; if sshd is elsewhere (say the API is on the WAN and SSH only on the LAN), also set `provider_settings.opnsense.ssh_host`. `OPNSENSE_SSH_HOST` is honored only with `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`. Or, for a one-shot operator-driven cutover that doesn't touch the SOPS-encrypted `settings.yaml`, export `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1` together with `OPNSENSE_API_URL=<NEW>` (and optionally `OPNSENSE_API_KEY`, `OPNSENSE_API_SECRET`, `OPNSENSE_VERIFY_SSL`, `OPNSENSE_PROXY`) and run plan/apply directly — see [ADR-0014 §"Runtime credential resolution"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#runtime-credential-resolution-741-2026-05-05). Plan/apply emits a one-time WARNING naming the resolved URL so the redirect is loud. Without `INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`, env vars are ignored — this protects against forgotten direnv shells. If `NEW` is reachable only through an SSH tunnel (e.g. a Tailscale-only box whose GUI/API port is firewalled on the tailnet interface), set `OPNSENSE_PROXY` to a proxy that reaches it — e.g. `ssh -D 1080 root@NEW` plus `OPNSENSE_PROXY=socks5h://127.0.0.1:1080` (SOCKS needs the `infrafoundry[socks]` extra), or an `ssh -L` local-forward with `OPNSENSE_API_URL` pointed at the forwarded port.
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

## Endpoint registry and version check (#1239)

Every OPNsense API path the provider calls lives in `src/infrafoundry/providers/opnsense/endpoints.py`; no path literal appears anywhere else in the provider package, and `test_endpoint_literal_guard.py` fails when one does.

- **Offline conformance.** `test_endpoint_conformance.py` checks each stock endpoint against every spec bundled with `opnsense-openapi` for the supported series (`SUPPORTED_SERIES`, 26.1). It runs without a box. Gaps in newer series are reported as warnings, not failures.
- **Plan and doctor.** `infra plan` (and so `infra apply`) and `infra doctor` read the box version from `core/firmware/info` through `opnsense-openapi`'s `detect_version`. A resource type whose endpoints that version lacks is rejected, naming the endpoint and the version. A version with no exact bundled spec, or one that cannot be read, produces a warning and the check is skipped or run against the nearest older spec.
- **Extension exemption.** `interfaces/assign_settings/*` is served by the in-tree plugin, not stock OPNsense, so the check skips it; a test asserts it stays absent from the specs so the exemption is dropped if upstream ships it.
- **Plugin exemption.** `acmeclient/*` (`os-acme-client`) and `tailscale/*` (`os-tailscale`) are served by contrib plugins, so the check skips them; tests assert they stay absent from the specs and that only the expected `tailscale/*` endpoints are registered.
- **Strict mode stays off.** `opnsense-openapi`'s `validate_endpoints=True` needs a known box version, but the wrapper sets `auto_detect_version=False`, and strict mode cannot exempt the extension.

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
