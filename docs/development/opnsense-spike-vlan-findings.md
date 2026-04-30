# OPNsense Direct-API VLAN Spike — Findings

> **Status:** Placeholder. The operator fills these sections in after running [`tools/spikes/vlan_direct_api.py`](../../tools/spikes/README.md) against `opnsense-a` (staging). ADR-0014 cites this document.

## Why this document exists

ADR-0013 (PR #704, on hold) deferred the OPNsense apply-mechanism choice. Today's provider mixes paths: VLANs/aliases/firewall rules go YAML → Jinja2 `.tf.j2` → `terraform` binary → `browningluke/opnsense` provider → OPNsense API, plus an Ansible playbook for service reload. Kea DHCP calls the OPNsense REST API directly via `opnsense_openapi` but uses the bare `client.request("METHOD", endpoint_string)` surface and discards the typed `client.api.<module>.<call>` interface that the package generates from the OpenAPI spec.

This spike is the proof. It builds the smallest sufficient direct-API path for **VLANs** so we can produce evidence — code we can read, run, and measure — that ADR-0014 cites. The spike is intentionally not integrated into the provider/runner; it lives under `tools/spikes/` so it can ship or be deleted on its own merits.

## Setup

| Item                              | Value                       |
| --------------------------------- | --------------------------- |
| Spike script                      | `tools/spikes/vlan_direct_api.py` |
| Example YAML                      | `tools/spikes/example-vlans.yaml` |
| Target box                        | `opnsense-a` (staging)      |
| Detected OPNsense version         | _TBD — fill from `inspect`_ |
| Matched spec version              | _TBD — from `find_best_matching_spec`_ |
| `opnsense_openapi` version        | _TBD — `python -c "import opnsense_openapi; print(opnsense_openapi.__version__)"`_ |
| Run date                          | _TBD_                       |

## Run log

Capture the raw command output. Verbatim is fine — this is evidence, not prose.

### `inspect`

```text
$ uv run python tools/spikes/vlan_direct_api.py inspect
# (paste output)
```

### `list` (before)

```text
$ uv run python tools/spikes/vlan_direct_api.py list
# (paste output — should match what the OPNsense UI shows)
```

### `plan` (cold, against empty staging)

```text
$ uv run python tools/spikes/vlan_direct_api.py plan tools/spikes/example-vlans.yaml
# (paste output — expect N adds where N = entries in example-vlans.yaml)
```

### `apply --confirm`

```text
$ uv run python tools/spikes/vlan_direct_api.py apply tools/spikes/example-vlans.yaml --confirm
# (paste output)
```

### Round-trip — `plan` immediately after `apply`

```text
$ uv run python tools/spikes/vlan_direct_api.py plan tools/spikes/example-vlans.yaml
# (paste output — MUST be "No changes." for the spike to be considered a success)
```

### Delete cycle

Remove one VLAN from `example-vlans.yaml`, re-run `plan` (expect 1 delete), `apply --confirm`, re-run `plan` (expect "No changes.").

```text
# (paste output for each step)
```

## Round-trip property

| Question                                                     | Result   |
| ------------------------------------------------------------ | -------- |
| `plan` after `apply --confirm` returns "No changes."?        | _TBD_    |
| `plan` after delete-cycle apply returns "No changes."?       | _TBD_    |
| Any field round-trips lossy (description with quotes, etc.)? | _TBD_    |

If round-trip ever fails, paste the diff verbatim here. This is the load-bearing acceptance criterion for the direct-API pattern.

## Friction points

> Inline notes captured while wiring up the spike — pre-run observations, kept here so they travel with the run results.

- **`opnsense_openapi.OPNsenseClient` already defaults `auto_detect_version=True`.** Production wrapper at `src/infrafoundry/providers/opnsense/api_client.py:36` explicitly sets it to `False`. Why we set the default explicitly anyway: the spike has to be readable on its own without the reader chasing why detection works.
- **Typed `.api` surface is lazy-imported, not lazy-typed.** The `GeneratedAPI` proxy resolves `__getattr__` for *every* attribute access — there's no compile-time signal that a function exists. The error only surfaces at `sync()` time as `AttributeError: API function 'interfaces.vlansettings_search_item' not found...`. The spike catches this and falls back; ADR-0014 should weigh whether this is acceptable for production code.
- **`searchItem` is a POST, not a GET, despite the verb.** Easy to miss if you're skimming the spec. The spike's fallback uses `client.post(...)`.
- **First-use generation cost.** The package's `generated/` ships almost empty in the wheel — clients are auto-generated on first `client.api` access. Expect ~2 minutes of "where did my CLI go?" the first time the spike runs against a new version.
- **Spec resolution may pick a higher patch.** `find_best_matching_spec` selects the closest *available* spec and may resolve to a higher patch version than the running box. If the running box is `25.7.5` and the package only ships `25.7.6`, the typed surface is generated against `25.7.6`'s schema. Confirm `inspect` output shows version + matched-spec on the same line so future-us can tell at a glance.
- _TBD: anything else discovered during the live run._

### Items to forward upstream to `endavis/opnsense-openapi`

- _TBD: any missing `operationId` in the spec that forced a fallback._
- _TBD: any naming inconsistencies between OpenAPI tag names and generated module paths._
- _TBD: a `find_best_matching_spec` "closest-floor" mode (today it picks the closest, which can be higher than the running box and silently misalign schemas)._

## Lines of code per concern

Run `wc -l` against the spike script and split by section.

| Concern                                  | LoC  | File location                      |
| ---------------------------------------- | ---- | ---------------------------------- |
| Config model (`VlanConfig`, `LiveVlan`)  | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| Diff engine (`compute_diff`)             | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| Apply loop (`cmd_apply`, mutators)       | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| Error handling                           | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| CLI plumbing (argparse + main)           | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| **Total spike script**                   | _TBD_ | `tools/spikes/vlan_direct_api.py` |
| Production VLAN path (Terraform + provider) | _TBD_ | `src/infrafoundry/providers/opnsense/` (vlan validator, vlan template, terraform glue) |

The comparison is rough — the production path also handles things the spike doesn't (CLI-wide flags, multi-component reconciliation, drift detection, state DB). Note the discrepancy explicitly when filling this in.

## Apply timing

| Operation                          | Time elapsed |
| ---------------------------------- | ------------ |
| 3 VLAN adds + reconfigure          | _TBD_        |
| 1 VLAN delete + reconfigure        | _TBD_        |
| Cold first-run client generation   | _TBD_        |

## Typed-surface coverage

| Function                              | Generated? | Worked first try? | Fallback used? | Notes |
| ------------------------------------- | ---------- | ----------------- | -------------- | ----- |
| `vlansettings_search_item`            | _TBD_      | _TBD_             | _TBD_          | _TBD_ |
| `vlansettings_add_item`               | _TBD_      | _TBD_             | _TBD_          | _TBD_ |
| `vlansettings_get_item`               | _TBD_      | _TBD_             | _TBD_          | _TBD_ |
| `vlansettings_set_item`               | _TBD_      | _TBD_             | _TBD_          | _TBD_ |
| `vlansettings_del_item`               | _TBD_      | _TBD_             | _TBD_          | _TBD_ |
| `vlansettings_reconfigure`            | _TBD_      | _TBD_             | _TBD_          | _TBD_ |

## Recommendation

> Filled in after the run. ADR-0014 codifies the choice; this section is the input it cites.

- **Direct-API for VLAN mutations:** _recommend / do-not-recommend / unclear_ — _reasoning_.
- **Use the typed `.api` surface vs. raw `client.get/post(...)`:** _recommend / do-not-recommend / unclear_ — _reasoning_.
- **Keep Terraform for any OPNsense resource:** _yes / no / partial_ — _which resources, why_.
- **Open questions ADR-0014 must address:** _list_.
