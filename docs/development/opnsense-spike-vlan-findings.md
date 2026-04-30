# OPNsense Direct-API VLAN Spike — Findings

> **Status:** Live run completed against `opnsense-a` (staging) on 2026-04-30. ADR-0014 cites this document.

## Why this document exists

ADR-0013 ([PR #704](https://github.com/endavis/infrafoundry/pull/704), on hold) deferred the OPNsense apply-mechanism choice. Today's provider mixes paths: VLANs/aliases/firewall rules go YAML → Jinja2 `.tf.j2` → `terraform` binary → `browningluke/opnsense` provider → OPNsense API, plus an Ansible playbook for service reload. Kea DHCP calls the OPNsense REST API directly via `opnsense_openapi` but uses the bare `client.request("METHOD", endpoint_string)` surface and discards the typed `client.api.<module>.<call>` interface that the package generates from the OpenAPI spec.

This spike is the proof. It builds the smallest sufficient direct-API path for **VLANs** so we can produce evidence — code we can read, run, and measure — that ADR-0014 cites. The spike is intentionally not integrated into the provider/runner; it lives under `tools/spikes/` so it can ship or be deleted on its own merits.

## Setup

| Item                              | Value                       |
| --------------------------------- | --------------------------- |
| Spike script                      | `tools/spikes/vlan_direct_api.py` |
| Example YAML                      | `tools/spikes/example-vlans.yaml` |
| Lock-fixture YAML (used live)     | `tmp/agents/claude/spike-vlans-with-lock.yaml` (ad hoc; tracks WAN trunk with `lock: true`) |
| Target box                        | `opnsense-a` (staging)      |
| Detected OPNsense version         | `26.1.6_2`                  |
| Matched spec                      | `specs/opnsense-26.1.6.json` (738 endpoints) |
| `opnsense_openapi` version        | 0.3.0                       |
| `openapi-python-client` installed | **No** — typed `.api` surface unavailable; spike ran entirely on the fallback `client.post(...)` path |
| Run date                          | 2026-04-30                  |

## Run log

### `inspect`

```text
$ python tools/spikes/vlan_direct_api.py inspect
WARNING: openapi-python-client is not on PATH.
  The typed .api surface cannot be generated; the spike will
  fall back to bare client.get/post(...) for every operation.
  Install with: uv tool install openapi-python-client

openapi-python-client not found. Install it with: uv pip install openapi-python-client
Detected OPNsense version: 26.1.6_2
Total endpoints in matched spec: 738
VLAN endpoints (interfaces/vlan_settings/*): 6
  POST  /api/interfaces/vlansettings/searchItem
  POST  /api/interfaces/vlansettings/setItem/{uuid}
  POST  /api/interfaces/vlansettings/addItem
  GET   /api/interfaces/vlansettings/getItem/{uuid}
  POST  /api/interfaces/vlansettings/delItem/{uuid}
  POST  /api/interfaces/vlansettings/reconfigure
Typed-surface search available: False
```

Note: the spec advertises paths under `vlansettings` (no underscore), but the live `26.1.6_2` API routes to `vlan_settings` (with underscore). See [Items to forward upstream](#items-to-forward-upstream-to-endavisopnsense-openapi).

### `list` (before)

```text
$ python tools/spikes/vlan_direct_api.py list
- provider: opnsense
  type: vlan
  name: live-ixl0-4000
  config:
    device: ixl0
    tag: 4000
    description: ''
    priority: 0
```

### `plan` against the lock-fixture YAML

```text
$ python tools/spikes/vlan_direct_api.py plan tmp/agents/claude/spike-vlans-with-lock.yaml
Plan: 3 to add, 0 to update, 0 to delete, 1 locked.
  + ixl1 tag=4001 desc='spike-test storage vlan' pcp=0
  + ixl1 tag=4002 desc='spike-test iot vlan' pcp=3
  + ixl1 tag=4003 desc='spike-test mgmt vlan' pcp=7
  L ixl0 tag=4000 (locked, uuid=56db737b-590e-42d3-ab82-1b32afc140f0) — no action will be taken
```

### `apply --confirm` — add cycle

```text
$ python tools/spikes/vlan_direct_api.py apply tmp/agents/claude/spike-vlans-with-lock.yaml --confirm
Plan: 3 to add, 0 to update, 0 to delete, 1 locked.
  + ixl1 tag=4001 desc='spike-test storage vlan' pcp=0
  + ixl1 tag=4002 desc='spike-test iot vlan' pcp=3
  + ixl1 tag=4003 desc='spike-test mgmt vlan' pcp=7
  L ixl0 tag=4000 (locked, uuid=56db737b-590e-42d3-ab82-1b32afc140f0) — no action will be taken

Applying changes...
  + add  ixl1 tag=4001  -> saved
  + add  ixl1 tag=4002  -> saved
  + add  ixl1 tag=4003  -> saved
Reconfiguring service...
  reconfigure -> ok
```

### Round-trip — `plan` immediately after `apply` (add cycle)

```text
$ python tools/spikes/vlan_direct_api.py plan tmp/agents/claude/spike-vlans-with-lock.yaml
Plan: 0 to add, 0 to update, 0 to delete, 1 locked.
  L ixl0 tag=4000 (locked, uuid=56db737b-590e-42d3-ab82-1b32afc140f0) — no action will be taken
```

✅ Convergence after the add cycle.

### Delete cycle

Removed all three `ixl1.400[123]` entries from the lock-fixture YAML, leaving only the locked WAN entry:

```text
$ python tools/spikes/vlan_direct_api.py plan tmp/agents/claude/spike-vlans-with-lock.yaml
Plan: 0 to add, 0 to update, 3 to delete, 1 locked.
  - ixl1 tag=4001 desc='spike-test storage vlan' (uuid=9b7d31cf-...)
  - ixl1 tag=4002 desc='spike-test iot vlan' (uuid=b8fe4add-...)
  - ixl1 tag=4003 desc='spike-test mgmt vlan' (uuid=70c18711-...)
  L ixl0 tag=4000 (locked, uuid=56db737b-...) — no action will be taken

$ python tools/spikes/vlan_direct_api.py apply tmp/agents/claude/spike-vlans-with-lock.yaml --confirm
...
Applying changes...
  - del  ixl1 tag=4001  -> deleted
  - del  ixl1 tag=4002  -> deleted
  - del  ixl1 tag=4003  -> deleted
Reconfiguring service...
  reconfigure -> ok

$ python tools/spikes/vlan_direct_api.py plan tmp/agents/claude/spike-vlans-with-lock.yaml
Plan: 0 to add, 0 to update, 0 to delete, 1 locked.
```

✅ Convergence after the delete cycle. `opnsense-a` returned to its pre-spike state (only the WAN VLAN remains).

## Round-trip property

| Question                                                     | Result   |
| ------------------------------------------------------------ | -------- |
| `plan` after `apply --confirm` (add cycle) returns 0/0/0?    | ✅ yes   |
| `plan` after `apply --confirm` (delete cycle) returns 0/0/0? | ✅ yes   |
| Any field round-trips lossy (description with quotes, etc.)? | Not exercised — descriptions in the test fixture are simple strings. Worth a follow-up test with quotes, unicode, and very long descriptions before any production lift. |
| Lock semantics preserved across apply cycles?                | ✅ yes — WAN VLAN UUID `56db737b-...` was identified by `searchItem` on every plan and never appeared in adds/updates/deletes. |

## Friction points

> Pre-run notes confirmed during the live run, plus new findings.

- **The spec's controller name is wrong.** Bundled `26.1.6.json` advertises `interfaces/vlansettings/*` (no underscore); live `26.1.6_2` routes to `interfaces/vlan_settings/*` (with underscore). The spike works around it by hardcoding `vlan_settings` in `VLAN_CONTROLLER`. Filed as [endavis/opnsense-openapi#32](https://github.com/endavis/opnsense-openapi/issues/32). The naming is heterogeneous across modules (Kea uses `dhcpv4`/`dhcpv6` no-underscore; VlanSettings uses snake_case), so a universal converter doesn't fix it.
- **`openapi-python-client` is an external CLI dep, not a Python dep.** Without it, `client.api.<...>` raises a misleading `RuntimeError("No OpenAPI spec found for version 26.1.6_2")` at attribute access time, even though the spec WAS found and is in active use. The spike's `_typed_call` was originally only catching `AttributeError`; the live run exposed the `RuntimeError` path. Fix is in this PR; the upstream error message could distinguish the failure modes — filed as [endavis/opnsense-openapi#33](https://github.com/endavis/opnsense-openapi/issues/33).
- **Spec resolution can pick a higher patch than the running box.** `find_best_matching_spec` picks the highest spec in the same major.minor; a box on `25.7.5` with `25.7.7` available gets `25.7.7`'s schema. Not exercised in this run (matched exactly to `26.1.6` from `26.1.6_2`'s major.minor), but the failure mode is real. Filed alongside the patch-revision module-path issue as [endavis/opnsense-openapi#34](https://github.com/endavis/opnsense-openapi/issues/34).
- **Plan does not validate `device:` against the live box's NICs.** An early version of the example YAML had `device: igb1` (a generic placeholder); `opnsense-a` has `ixl0`/`ixl1` only. `plan` showed three adds without flagging the bad NIC; only `apply` would have caught it via OPNsense's response. Production direct-API should weigh whether to probe `core.system.firmware.systemInformation` or similar at plan time.
- **Fully-managed semantics + incomplete YAML = silent delete.** First live `plan` showed `1 to delete: ixl0 tag=4000` — that's the WAN trunk on staging. The spike's diff was doing exactly what its production-IaC contract dictates (anything not in YAML → DELETE). For partial migrations (which is the OPNsense cutover use case in InfraFoundry), this is a footgun. **Mitigated in this PR** with `--add-only` flag (suppresses deletes) and resource-level `lock: true` (per-resource opt-out). ADR-0014 must specify which mode is the default for production direct-API.
- **The typed `.api` surface was never exercised.** The entire validation ran on the fallback `client.post(...)` path because `openapi-python-client` wasn't installed. **The fallback path covered every operation cleanly** — search, add, delete, reconfigure, idempotence. The typed surface's value-add is mypy/IDE help only, not a wire-protocol requirement. ADR-0014 should weigh whether mypy validation against `.api` (which the GeneratedAPI proxy can't actually deliver — see next point) is worth the dependency footprint.
- **`.api` is a runtime proxy, not a typed surface.** `GeneratedAPI` proxies every `__getattr__` access; typo'd function names don't fail at static-check time, only at `.sync()` call time. mypy/pyright cannot validate against it. The "typed" pitch is largely about the Pydantic *payload* models, not the *call sites*.
- **OPNsense's `auto_detect_version=True` works against a live box.** Detected `26.1.6_2` cleanly — including the `_2` security-patch suffix — without any explicit version pinning. The subsequent spec lookup resolved correctly. Auto-detect is a reasonable default for production use.

### Items to forward upstream to `endavis/opnsense-openapi`

All filed:

- [#32 — bug: spec generator emits wrong controller names for multi-word controllers](https://github.com/endavis/opnsense-openapi/issues/32). **Blocker** for any consumer of the typed surface or fallback against affected modules.
- [#33 — bug: misleading "No OpenAPI spec found" error when openapi-python-client is missing](https://github.com/endavis/opnsense-openapi/issues/33).
- [#34 — refactor: stabilize generated-client module path across patch revisions; add closest-floor spec matching](https://github.com/endavis/opnsense-openapi/issues/34).

ADR-0014's recommendation depends on at least #32 landing; without it the typed surface (and the spike's fallback) require per-controller workarounds.

## Lines of code per concern

| Concern                                  | LoC (approx) | File location                      |
| ---------------------------------------- | ------------ | ---------------------------------- |
| Constants                                | ~25          | `tools/spikes/vlan_direct_api.py` (header + spec/path bug comments) |
| Config model (`VlanConfig`, `LiveVlan`, `Diff`) | ~95   | `tools/spikes/vlan_direct_api.py` |
| Env / client construction / codegen warning | ~70       | `tools/spikes/vlan_direct_api.py` |
| Typed-call wrapper (`_typed_call`)       | ~25          | `tools/spikes/vlan_direct_api.py` |
| YAML loader                              | ~80          | `tools/spikes/vlan_direct_api.py` |
| Diff engine (`compute_diff`)             | ~55          | `tools/spikes/vlan_direct_api.py` |
| Subcommand handlers + `_print_diff`      | ~135         | `tools/spikes/vlan_direct_api.py` |
| CLI plumbing (argparse + main)           | ~80          | `tools/spikes/vlan_direct_api.py` |
| **Total spike script**                   | **736**      | `tools/spikes/vlan_direct_api.py` |
| Production VLAN path (in-repo)           | ~80          | `templates/opnsense/vlans.tf.j2` (15) + `validators/vlan_validator.py` (50) + scattered glue in `providers/opnsense/__init__.py` (~15) |

The 736 vs. 80 line comparison is intentionally apples-to-oranges. The spike includes its **own** diff engine, idempotency, dry-run guard, lock semantics, add-only mode, error handling, and a runnable CLI. The production VLAN path delegates almost all of that to terraform + the browningluke provider + the Ansible service-reload playbook — three external tools that the spike replaces with ~600 lines of in-repo Python.

What the spike's 736 lines buy:

- No terraform binary on the target machine.
- No browningluke provider plugin (and its shifting compatibility window relative to upstream OPNsense).
- No Ansible roundtrip for service reloads.
- One stack trace, one tool dependency (`opnsense_openapi`), one schema source.

What it costs:

- The dependency-graph parallelism, state file, and rollback semantics that terraform gives for free.
- Diff/apply discipline that we wrote by hand.
- Plumbing (argparse, env loading, dry-run guards) that's table stakes in a CLI.

ADR-0014 weighs this trade.

## Apply timing

| Operation                             | Time elapsed (approximate) |
| ------------------------------------- | -------------------------- |
| `searchItem` (1 call)                 | sub-second                 |
| `addItem` x3 + `reconfigure`          | ~1–2 seconds end-to-end    |
| `delItem` x3 + `reconfigure`          | ~1–2 seconds end-to-end    |
| Cold first-run client generation      | Not measured — `openapi-python-client` was not installed during this run, so codegen never ran. Upstream docs claim ~2 minutes per OPNsense version. |

These are coarse — the spike doesn't time itself. Production direct-API should add structured timing for `plan`/`apply` if operators need it.

## Typed-surface coverage

None. The entire validation ran on the fallback `client.post(...)` path. Filed [#32](https://github.com/endavis/opnsense-openapi/issues/32) is a precondition for the typed surface working at all against `interfaces/vlan_settings/*`; until that lands, this table is N/A.

| Function                              | Generated? | Worked first try? | Fallback used? | Notes |
| ------------------------------------- | ---------- | ----------------- | -------------- | ----- |
| `vlansettings_search_item`            | No (CLI not installed) | — | yes | Fallback works at the corrected `vlan_settings` path. |
| `vlansettings_add_item`               | No | — | yes | 3/3 returned `result: saved`. |
| `vlansettings_get_item`               | No | — | not exercised | Spike doesn't use `getItem` — search returns full rows. |
| `vlansettings_set_item`               | No | — | not exercised live | Unit-tested only. |
| `vlansettings_del_item`               | No | — | yes | 3/3 returned `result: deleted`. |
| `vlansettings_reconfigure`            | No | — | yes | Both apply cycles, `status: ok`. |

A future re-run with `openapi-python-client` installed and #32 fixed would populate this table with the typed-surface results.

## Recommendation

The spike's evidence is strong enough to support a **conditional** recommendation that ADR-0014 should consider. Items below are starting positions for the ADR discussion, not final answers.

- **Direct-API for VLAN mutations: feasible and clean.** The 736-line spike covers add/update/delete + idempotence + lock semantics + add-only mode in a single readable Python file with one runtime dependency and no external binaries. The round-trip property holds. **Recommend** moving forward with direct-API for net-new components (interface assignments, NAT rules, gateways, static routes, virtual IPs from ADR-0013) once upstream blockers (#32) land.
- **Typed `.api` surface: defer.** Without #32, it's blocked. Even with #32, the value-add is incremental (Pydantic payloads only — call sites are still a runtime proxy with no static checking). The fallback `client.get/post(...)` path is more than adequate for production. **Recommend** building production code against the fallback API by default, and revisiting whether the typed surface is worth the `openapi-python-client` dependency once #32 + #34 land.
- **Apply semantics: lock + add-only must be in the production contract.** Pure fully-managed mode is dangerous for partial migrations (the OPNsense cutover use case). Both safety affordances developed in this spike (`lock: true` per-resource and `--add-only` per-invocation) should ship with the production direct-API. ADR-0014 should specify the default mode (suggest: fully-managed for env-root packages, add-only as an opt-in CLI flag, `lock` always available).
- **Keep Terraform for: no clear case based on this spike.** All cited concerns (state, plan, apply, dependency ordering, parallelism) are surmountable in pure Python at the cost of ~600 lines of plumbing per provider. The browningluke compatibility lag with upstream OPNsense, plus the spec-vs-live drift caught by this spike, suggest the indirection is more cost than benefit. **Lean: migrate the existing Terraform-based VLAN/aliases/firewall_rules paths to direct-API as part of the ADR-0013 implementation phase.** ADR-0014 is the right place to commit.
- **Open questions for ADR-0014 to address:**
  - Does the production direct-API live in `BaseRunner` (new `OPNsenseDirectRunner`) or bypass the runner system (as Kea DHCP currently does)?
  - Where does `lock: true` live in the production schema — top-level meta-property (as in the spike) or under a dedicated `metadata.iac.*` namespace?
  - Should `plan` validate `device:` (and other interface refs) against the live box at plan time, or defer to apply-time errors?
  - Does the production model support **granular** locks (`lock: { delete: true, update: false }`) or just boolean?
  - How does direct-API integrate with `foundry config migrate`? The spike's `list` is the equivalent operation; a production version would dump *all* resource types into YAML.
