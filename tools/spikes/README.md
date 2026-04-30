# Engineering spikes

Throw-away code that produces evidence for an ADR. Each spike pairs with a findings doc under `docs/development/`. Spikes ship or get deleted on their own merits — they do not modify production code.

## `vlan_direct_api.py` — direct-API VLAN management (informs ADR-0014)

Demonstrates end-to-end VLAN management against OPNsense via `opnsense_openapi`'s typed `.api.<module>.<function>` surface, with a `client.get/post(...)` fallback. Pairs with [`docs/development/opnsense-spike-vlan-findings.md`](../../docs/development/opnsense-spike-vlan-findings.md).

### Prerequisites

1. An OPNsense box you don't mind reconfiguring. **Use `opnsense-a` (staging), NOT prod.**
2. An API key/secret with permission for `interfaces/vlan_settings/*` (the live URL — the bundled OpenAPI spec at `opnsense-openapi` 0.3.0 calls it `vlansettings`, but live OPNsense routes to `vlan_settings`; see findings doc for details).
3. The `opnsense_openapi` package (already in `pyproject.toml`).

### Environment variables

Source these from your secrets repo before running. **Never commit them to this repo.**

| Variable                | Required | Purpose                                              |
| ----------------------- | -------- | ---------------------------------------------------- |
| `OPNSENSE_API_URL`      | yes      | e.g. `https://opnsense-a.example.lan`                |
| `OPNSENSE_API_KEY`      | yes      | API key from System → Access → Users → API keys      |
| `OPNSENSE_API_SECRET`   | yes      | Paired secret                                        |
| `OPNSENSE_VERIFY_SSL`   | no       | `true` (default), `false`, `0`, `no` — case-insensitive |

These match the names the existing OPNsense validator already uses (`src/infrafoundry/providers/opnsense/validator.py:208-210`), so you can reuse the same `.envrc` snippet.

Example shell setup (sourced from your private secrets repo, never committed here):

```bash
# In ~/.envrc.local or your secrets repo's bootstrap script:
export OPNSENSE_API_URL="https://opnsense-a.example.lan"
export OPNSENSE_API_KEY="$(sops -d secrets/opnsense-a.yaml | yq '.api_key')"
export OPNSENSE_API_SECRET="$(sops -d secrets/opnsense-a.yaml | yq '.api_secret')"
```

### Subcommands

```bash
# 1. Sanity check — connect, detect version, count VLAN endpoints in the matched spec,
#    and report whether the typed search method is generated.
uv run python tools/spikes/vlan_direct_api.py inspect

# 2. Print the current VLANs on the box as YAML (visually compare against the OPNsense UI).
uv run python tools/spikes/vlan_direct_api.py list

# 3. Diff a YAML file against live state (no mutations).
uv run python tools/spikes/vlan_direct_api.py plan tools/spikes/example-vlans.yaml

# 4. Apply the diff. Without --confirm, this is a dry run identical to `plan`.
uv run python tools/spikes/vlan_direct_api.py apply tools/spikes/example-vlans.yaml --confirm
```

#### Safety flags

- **`--add-only`** (on `plan` and `apply`) — suppresses deletes for live VLANs that aren't in the YAML. Use this on partial migrations where the YAML doesn't yet describe everything on the box. Adds and updates still happen.
- **`lock: true`** at the resource level in YAML — observed but untouchable. The spike records the lock in the plan output and never adds/updates/deletes the matching live resource. Useful for things like the WAN trunk that you want IaC to be aware of but never touch. See `example-vlans.yaml` for the syntax.

The two are orthogonal: locks travel with specific resources in YAML; `--add-only` is a session-level "trust me, don't sweep deletes."

### Round-trip test (the load-bearing acceptance criterion)

```bash
# 1. Apply.
uv run python tools/spikes/vlan_direct_api.py apply tools/spikes/example-vlans.yaml --confirm

# 2. Re-plan. Must print "No changes."
uv run python tools/spikes/vlan_direct_api.py plan tools/spikes/example-vlans.yaml

# 3. Remove one VLAN from example-vlans.yaml; re-plan should show `1 to delete`.
# 4. Apply with --confirm; box reconciles. Re-plan: "No changes."
```

If step 2 ever shows a non-empty diff right after a successful apply, the round-trip property is broken — capture the diff verbatim in the findings doc.

### After running

Fill in `docs/development/opnsense-spike-vlan-findings.md` with:

- Detected version vs. matched spec version.
- Whether each typed function (`vlansettings_search_item`, `_add_item`, `_set_item`, `_del_item`, `_reconfigure`) was generated and worked, or required the fallback.
- Lines of code per concern (config model, diff engine, apply loop, error handling, CLI).
- Round-trip outcome.
- Subjective friction list — anything in `opnsense_openapi` that felt missing.

ADR-0014 is written after the findings doc lands.

### Cleanup

The spike adds VLANs with tags 4001-4003 on the example. Delete them via the OPNsense UI or by removing them from `example-vlans.yaml` and re-running `apply --confirm` when you're done.
