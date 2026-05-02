# Gist-based REST spike — OPNsense interface_assignments

Forks and extends [`szymczag`'s `AssignSettingsController.php`](https://gist.github.com/szymczag/df152a82e86aff67b984ed3786b027ba) (BSD-2-Clause) so we can drive OPNsense `interface_assignments` writes through a single, server-side-validated REST surface. Pairs with [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../../../docs/development/opnsense-spike-interface-assignment-gist-findings.md). This is the pivot from #714 (SSH+PHP `config.xml` editor — closed without merging on safety grounds): server-side `Config::save()` rejects bad input loudly, fires the standard audit log, and triggers an auto-snapshot.

## What's in this directory

| File | Purpose |
| :--- | :--- |
| `AssignSettingsController.php` | Forked + patched + extended PHP controller. Installed at `/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/`. |
| `install.py` | Idempotent installer: SCP + service restart + checksum verify. Standalone-runnable. |
| `interface_assignment_gist_rest.py` | Python spike: `inspect`, `list`, `plan`, `apply`, `install`, `verify-install`. |
| `example-interface-assignments.yaml` | Fixture targeting the spare NIC `igc0` on `opnsense-a`. |
| `__init__.py` | Module marker. |

### What the fork changes vs. the original gist

| Concern | Base gist | This fork |
| :--- | :--- | :--- |
| `addItem` (auto-numbered) | yes | yes |
| `delItem` | yes | yes |
| `setItem` (in-place update) | NO | yes (added) |
| `getItem` (single fetch) | NO | yes (added) |
| `searchItem` (list all) | NO | yes (added) |
| IPv6 fields on add/set | NO | yes (added: `ipv6Type`, `ipv6Address`, `ipv6Subnet`, `ipv6Track`) |
| Explicit name on `addItem` | NO | yes (added; required for cutover continuity — preserve `optN` numbering across box swaps) |
| `sessionClose()` calls | yes (breaks on modern OPNsense) | removed (community patch — Paradoxis comment 2026-02-25) |

## Prerequisites

1. An OPNsense box you don't mind reconfiguring. **Use `opnsense-a` (staging), NOT prod.**
2. SSH access to the box (root) — used for the install lifecycle only.
3. A REST API key/secret with permission for:
   - `interfaces/overview/interfacesInfo` (read baseline)
   - `interfaces/assign_settings/*` (controller endpoints)
   - `core/backup/{backups,revertBackup}` (auto-snapshot capture + rollback)

## Environment variables

Source these from your secrets repo. **Never commit them.**

### REST (always required for non-install commands)

| Variable | Required | Purpose |
| :--- | :--- | :--- |
| `OPNSENSE_API_URL` | yes | e.g. `https://opnsense-a.example.lan` |
| `OPNSENSE_API_KEY` | yes | API key from System → Access → Users → API keys |
| `OPNSENSE_API_SECRET` | yes | Paired secret |
| `OPNSENSE_VERIFY_SSL` | no | `true` (default) / `false` / `0` / `no` — case-insensitive |

### SSH (required for `install`/`verify-install`/`inspect` checksum probe)

| Variable | Required | Purpose |
| :--- | :--- | :--- |
| `OPNSENSE_SSH_HOST` | yes | e.g. `opnsense-a.lan` |
| `OPNSENSE_SSH_USER` | no | Defaults to `root` |
| `OPNSENSE_SSH_PORT` | no | Defaults to `22` |
| `OPNSENSE_SSH_KEY` | yes | Path to SSH private key (e.g. `~/.ssh/id_ed25519`) |
| `OPNSENSE_INSTALL_PATH` | no | Override the canonical MVC controller path |

## Install lifecycle

```bash
# First install — copies the .php to the OPNsense box, restarts configd + php_fpm,
# verifies the post-install checksum.
uv run python tools/spikes/interface_assignment_gist_rest/install.py install

# Verify the on-box file matches the local source (no SCP, no service restart).
uv run python tools/spikes/interface_assignment_gist_rest/install.py verify

# Force-reinstall (e.g., after editing the .php locally).
uv run python tools/spikes/interface_assignment_gist_rest/install.py install --force
```

The same operations are also reachable through the spike's main entry point:

```bash
SPIKE=tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py
uv run python $SPIKE install
uv run python $SPIKE verify-install
uv run python $SPIKE install --force
```

The install script is idempotent: re-running with no source changes is a no-op (checksum match short-circuits SCP + service restart).

## Subcommands

```bash
SPIKE=tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py

# 1. Sanity check — version detect, controller install probe, REST baseline.
uv run python $SPIKE inspect

# 2. Print the current interface assignments on the box as YAML.
uv run python $SPIKE list

# 3. Diff a YAML file against live state (no mutations).
uv run python $SPIKE plan tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml

# 4. Apply the diff. Without --confirm, this is a dry run identical to `plan`.
uv run python $SPIKE apply tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml --confirm
```

### Safety flags

- **`--add-only`** (on `plan` and `apply`) — suppresses deletes for live assignments not in the YAML. Use this on partial migrations where the YAML doesn't yet describe the box's full set of `lan`/`wan`/`optN` entries. Adds and updates still happen.
- **`lock: true`** at the resource level in YAML — observed but untouchable. The spike records it in plan output and never adds/updates/deletes the matching live resource. Use this for `lan`/`wan` until the migration is complete. See `example-interface-assignments.yaml` for the syntax.
- **`--no-rollback`** (on `apply`) — disables the auto-rollback path. Useful when you want to inspect intermediate state after a failure.
- **`--print-rollback`** (on `apply`) — prints the captured pre-apply backup id before mutations. Use with `--confirm` to record the rollback target in your run log.
- **`--backup-snapshot-id <id>`** (on `apply`) — operator-supplied override for the auto-captured snapshot id. Use when you want to roll back to a specific older snapshot instead of the freshest one.

### Lockout-prevention (carried forward from #714's design)

Before any REST call fires, the spike refuses to apply if a planned `add` targets a `device` (kernel NIC name) that's already bound to another logical interface. This is a Python-side pre-flight; the PHP controller has its own server-side check too (the original gist's `addItem` refuses if `<interfaces>` already contains the device).

For `setItem` the same rule applies, but only when the device is changing.

## Round-trip recipe (load-bearing acceptance)

```bash
SPIKE=tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py
FIXTURE=tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml

# 1. Apply.
uv run python $SPIKE apply $FIXTURE --confirm

# 2. Re-plan. Must print "No changes." (or only locked entries).
uv run python $SPIKE plan $FIXTURE

# 3. Modify $FIXTURE (rebind device, add an entry, etc.); re-plan should reflect.
# 4. Apply with --confirm; box reconciles. Re-plan: "No changes."
```

If step 2 ever shows a non-empty diff right after a successful apply, the round-trip property is broken — capture the diff verbatim in the findings doc.

## Cleanup

```bash
# Remove the spike's test entry. The base gist's delItem is idempotent —
# running this twice is fine.
SPIKE=tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py
# Either edit the YAML to remove the entry and re-apply, or delete directly:
# (no built-in CLI for direct delete; remove from YAML and apply with --confirm.)
```

## After running

Fill in [`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../../../docs/development/opnsense-spike-interface-assignment-gist-findings.md) with the live-run output for each placeholder section.
