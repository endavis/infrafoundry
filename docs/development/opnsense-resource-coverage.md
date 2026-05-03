# OPNsense Provider Resource Coverage

This document tracks which OPNsense resource types are managed by the InfraFoundry provider today, which are known gaps, and how to plan a box-to-box migration when the provider doesn't yet cover every section of `config.xml`.

It exists to support the decision in [ADR-0013](../decisions/0013-opnsense-full-iac-migration.md): **drop-in OPNsense replacement should be achievable by re-applying YAML against a new endpoint.** Closing the gaps below is a prerequisite for that to work end-to-end.

## Coverage matrix

Source of truth for "supported": `OPNsenseProvider.get_resource_types()` in `src/infrafoundry/providers/opnsense/__init__.py`.

| Section in `config.xml` | InfraFoundry resource type | Status |
| --- | --- | --- |
| `<vlans>` | `vlans` | Supported (direct-API via `OPNsenseDirectRunner`; ADR-0014, #709) |
| `<OPNsense>/Firewall/Alias` | `aliases` | Supported |
| `<filter>/rule` | `firewall_rules` | Supported |
| `<OPNsense>/Kea` (DHCPv4 subnets) | `kea_subnet` | Supported |
| `<OPNsense>/Kea` (DHCPv4 reservations) | `kea_reservation` | Supported |
| `<OPNsense>/Kea` (DHCPv6 subnets) | `kea_dhcp6_subnet` | Supported |
| `<OPNsense>/Kea` (DHCPv6 reservations) | `kea_dhcp6_reservation` | Supported |
| `<OPNsense>/unboundplus/hosts/host` | `unbound_host_override` | Supported |
| `<dhcpd>` (legacy ISC) | `dhcp_static_maps` | Supported (legacy; new deployments should use Kea) |
| `<interfaces>` | `interface_assignments` | Read-only / migrate (direct-API; #711). Write-path mechanism decided in [ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions) (#717): server-side-validated REST via a forked OPNsense PHP controller (PR #716). Production conversion of `OPNsenseDirectRunner.apply()` is a separate follow-up; until it ships, logical-to-physical interface mapping remains a one-time manual GUI step during cutover. |
| `<nat>/rule` and `<nat>/outbound/rule` | — | **Gap** |
| `<OPNsense>/Gateways` | — | **Gap** |
| `<staticroutes>/route` | — | **Gap** |
| `<virtualip>/vip` | — | **Gap** |
| `<OPNsense>/unboundplus/hosts/host/alias` | — | **Gap** (Unbound host alias) |
| `<OPNsense>/unboundplus/domains/domain` | — | **Gap** (Unbound domain override) |
| `<OPNsense>/unboundplus/forwarding/host` | — | **Gap** (Unbound forward) |

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
4. **Manual GUI step — interface assignments** (one-time per cutover): on `NEW`, navigate to **Interfaces → Assignments** and bind each logical interface (LAN, WAN, OPT1, etc.) to the correct physical NIC or VLAN per the `interface_assignments` YAML in `envs/<env>/opnsense/`. The write-path mechanism is decided ([ADR-0014 §"Per-component decisions"](../decisions/0014-opnsense-direct-api-apply-mechanism.md#per-component-decisions), #717) but production conversion of `OPNsenseDirectRunner.apply()` is a separate follow-up; until it ships, the YAML is the source of truth and `foundry` reads-and-validates it but cannot apply it. Save and apply within the GUI before continuing.
5. **Switch endpoint**: update `provider_settings.opnsense.api_url` in `envs/<env>/settings.yaml` to point at `NEW`.
6. **Plan**: `foundry infra plan --env <env>` and review the diff. The `interface_assignments` line will show "read-only / 0 changes" — that's expected; the manual step above is the current source of writes (the direct-API write path lands in a follow-up to #717). Expect a clean apply against the (mostly empty) `NEW` box for everything else.
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

1. `interface_assignments` (read-only / migrate shipped in #711; write-path mechanism decided in ADR-0014 amendment #717 via a forked PHP REST controller; production conversion of `OPNsenseDirectRunner.apply()` is a follow-up issue)
2. `nat_rules`
3. `gateways`, `static_routes`
4. `virtual_ips`
5. Unbound extensions (`domain_override`, `host_alias`, `forward`)
6. `config migrate` extractors for every supported and newly-added resource type

The follow-up issues will be filed against the InfraFoundry repo and linked from ADR-0013 as they're created.
