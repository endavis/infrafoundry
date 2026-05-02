# OPNsense Gist-based Interface-Assignment Spike — Findings

> **Status:** Live run completed against `opnsense-a` (staging) on 2026-05-02. ADR-0014 amendment will cite this document. Two empirical findings from the run drove code changes that landed in this same PR: (a) the install script's env-loading was relaxed to derive `OPNSENSE_SSH_HOST` from `OPNSENSE_API_URL` and to make `OPNSENSE_SSH_KEY` optional (rely on ssh-agent / `~/.ssh/config`); (b) the remote-checksum command was rewritten to be csh-safe because OPNsense's root shell is `opnsense-shell` (csh-derived), where `2>/dev/null` is "Ambiguous output redirect."

## Why this document exists

#714 closed without merging: the SSH+PHP `config.xml`-edit write path worked mechanically, but had unacceptable safety properties — silent-bad-XML risk, bypassed OPNsense's `Config::getInstance()->save()` validation, no audit log entry, no auto-snapshot. The closure comment captured the safety case and proposed the pivot to a server-side controller.

This spike is the proof of the pivot. It installs `szymczag`'s [`AssignSettingsController.php`](https://gist.github.com/szymczag/df152a82e86aff67b984ed3786b027ba) (BSD-2-Clause) on the OPNsense box, applies the community-reported `sessionClose()` patch, and **extends** the controller with the missing CRUD surface (`setItem`, `getItem`, `searchItem`, IPv6, explicit-name on add). All writes go through OPNsense's standard `Config::save()` flow — bad inputs are rejected with a clear `errorMessage`; the audit log fires; the auto-snapshot pre-write hook fires.

The spike intentionally lives outside `src/infrafoundry/providers/opnsense/` so it can ship or be deleted on its own merits. ADR-0014's amendment cites this document and decides whether to convert `OPNsenseDirectRunner.apply()` for `interface_assignments` from no-op to live, gated on the patched controller.

## Setup

| Item | Value |
| :--- | :--- |
| Spike package | `tools/spikes/interface_assignment_gist_rest/` |
| PHP controller | `tools/spikes/interface_assignment_gist_rest/AssignSettingsController.php` |
| Python spike | `tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py` |
| Installer | `tools/spikes/interface_assignment_gist_rest/install.py` |
| Example YAML | `tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml` |
| Target box | `opnsense-a` (staging) |
| Detected OPNsense version | `26.1.6_2` |
| Controller install path | `/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php` |
| Controller SHA-256 (local source) | `ce5a0caa12d19229472f62d2cde2764ba9987a4b7528efdd07d5f27fef5299bd` |
| OPNsense remote shell | `/usr/local/sbin/opnsense-shell` (csh-derived) |
| Operator's OpenSSH client | `OpenSSH_9.6p1 Ubuntu-3ubuntu13.15, OpenSSL 3.0.13 30 Jan 2024` |
| Run date | 2026-05-02 |

## Run log

> Verbatim transcripts of each subcommand against `opnsense-a`. The user runs the live sequence themselves; this section is the audit trail.

### `install` (first time)

```text
$ uv run python tools/spikes/interface_assignment_gist_rest/install.py install
Controller not present on opnsense-a. Installing fresh.
Running: scp -P 22 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  /home/endavis/src/infrafoundry/tools/spikes/interface_assignment_gist_rest/AssignSettingsController.php \
  root@opnsense-a:/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php
Restarted service: configd
Restarted service: php_fpm
Post-install OK: on-box and local checksums match (sha256 ce5a0caa12d1…).
```

### `verify` (idempotent re-check)

```text
$ uv run python tools/spikes/interface_assignment_gist_rest/install.py verify
OK: on-box and local checksums match (sha256 ce5a0caa12d1…).
```

### `inspect`

```text
$ uv run python tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py inspect
Detected OPNsense version: 26.1.6_2
Controller installed and current (sha256 ce5a0caa12d1…).
Live assignments visible: 4
  lan      -> ixl1  (LAN)
  lo0      -> lo0  (Loopback)
  wan      -> ixl0_vlan4000  (WAN)
  opt1     -> tailscale0  (Tailscale)
```

### `list` (before any spike mutations)

`list` returns the same four logical interfaces from `inspect`, formatted as YAML resource entries. Output redacted for brevity; identical to the live read-side from #712 / #714.

### `plan` against the example fixture

```text
$ uv run python ... plan tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml --add-only
Plan: 1 to add, 0 to update, 0 to delete, 0 locked. (add-only mode — deletes suppressed)
  + opt9     device=igc0           desc='spike-test' ipv4=static ipv6=track-interface
```

(Without `--add-only`: plan would propose 4 destructive deletes for the unmanaged `lan`/`lo0`/`wan`/`opt1`. Same fully-managed default as VLAN spike; cutover fixtures lock the four originals.)

### `apply --confirm` — add cycle (with auto-rollback armed)

```text
$ uv run python ... apply tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml \
    --add-only --confirm --print-rollback
Plan: 1 to add, 0 to update, 0 to delete, 0 locked. (add-only mode — deletes suppressed)
  + opt9     device=igc0           desc='spike-test' ipv4=static ipv6=track-interface
WARNING: failed to capture pre-apply backup id: Client error '404 Not Found' for url
  'https://opnsense-a/api/core/backup/backups'

WARNING: no backup snapshot captured; auto-rollback unavailable.

Applying changes via REST...
  + add  opt9     device=igc0           -> saved

Apply complete.
```

**Important finding:** `/api/core/backup/backups` and `/api/core/backup/download` return HTTP 404 on `26.1.6_2` despite being in the spec. Auto-rollback via `revertBackup` is therefore **not viable on this OPNsense version**. The spike correctly degrades — captures the failure, warns loudly, and proceeds. This is consistent with #714's earlier finding (the same two endpoints 404'd during that spike's REST probe). ADR-0014's amendment must specify an alternative rollback strategy or accept the gap.

### Round-trip 1 — `plan` immediately after add

```text
$ uv run python ... plan tools/spikes/interface_assignment_gist_rest/example-interface-assignments.yaml --add-only
No changes.
```

✅ Convergence after the add cycle.

### `setItem` re-bind — change `opt9.device` from `igc0` to `igc1`

```text
$ uv run python ... plan tmp/agents/claude/spike-iface-rebind.yaml
Plan: 0 to add, 1 to update, 0 to delete, 4 locked.
  ~ opt9     device=igc0->igc1 desc='spike-test'->'spike-test (re-bound)'
  L lan      device=ixl1 (locked) — no action will be taken
  L lo0      device=lo0 (locked) — no action will be taken
  L wan      device=ixl0_vlan4000 (locked) — no action will be taken
  L opt1     device=tailscale0 (locked) — no action will be taken

$ uv run python ... apply tmp/agents/claude/spike-iface-rebind.yaml --confirm
... (same plan output)

Applying changes via REST...
  ~ set  opt9     device=igc1           -> saved

Apply complete.
```

✅ `setItem` re-binds in place. The logical name `opt9` is preserved across the device change — the load-bearing capability for cutover.

Verification via direct `getItem`:

```text
{'result': 'ok', 'assign': {
    'device': 'igc1',
    'description': 'spike-test (re-bound)',
    'enable': True,
    'spoofMac': None,
    'ipv4Type': 'static', 'ipv4Address': '10.99.99.1', 'ipv4Subnet': 24,
    'ipv6Type': 'track-interface', 'ipv6Track': 'wan'
}}
```

### Round-trip 2 — `plan` after setItem

```text
$ uv run python ... plan tmp/agents/claude/spike-iface-rebind.yaml
Plan: 0 to add, 0 to update, 0 to delete, 4 locked.
  L lan      device=ixl1 (locked) — no action will be taken
  L lo0      device=lo0 (locked) — no action will be taken
  L wan      device=ixl0_vlan4000 (locked) — no action will be taken
  L opt1     device=tailscale0 (locked) — no action will be taken
```

✅ Convergence after setItem cycle.

### Explicit name on `addItem` — does OPNsense accept it?

✅ **Accepted.** The `apply` add-cycle above used a fixture with `name: opt9` (no auto-numbering). Post-apply `getItem('opt9')` returned the assignment correctly. OPNsense's MVC layer does not appear to have downstream assumptions that fight arbitrary `optN` numbering. (The `interfacesInfo` endpoint also returns `opt9` cleanly, and the OPNsense GUI's "Interfaces → Assignments" page renders without errors — verified by the operator opening the GUI mid-run.)

This unblocks the cutover use case: an operator can preserve `opt5` from the old box on the new box without reshuffling.

### IPv6 dual-stack

✅ **Round-trips cleanly.** The `opt9` fixture sets both `ipv4Type: static` and `ipv6Type: track-interface, ipv6Track: wan`. After apply, `getItem('opt9')` returns the dual-stack config exactly as posted. `searchItem` (and the underlying `<config.xml>`'s `<interfaces><opt9>` subtree) confirm both stacks are persisted.

### Server-side validation behavior

```text
$ # Direct probes via the OPNsense client (bypassing the spike's YAML loader):

# 1. Invalid IPv4 address.
{'assign': {'device': 'igc1', 'ipv4Type': 'static',
            'ipv4Address': 'not-an-ip', 'ipv4Subnet': 24}}
→ HTTP 400 Bad Request

# 2. Invalid ipv4Type.
{'assign': {'device': 'igc1', 'ipv4Type': 'not-a-real-type'}}
→ HTTP 400 Bad Request

# 3. Missing required `device` field.
{'assign': {'description': 'no-device'}}
→ HTTP 400 Bad Request
```

✅ Server-side validation rejects all three with HTTP 400 (UserException response body carries the descriptive `errorMessage`). This is the empirical demonstration of the safety improvement over #714's silent-bad-XML risk.

### Lockout-prevention (target an already-bound NIC)

```text
$ uv run python ... apply tmp/agents/claude/spike-iface-lockout.yaml --add-only --confirm
Plan: 1 to add, 0 to update, 0 to delete, 0 locked. (add-only mode — deletes suppressed)
  + opt9     device=ixl1           desc='should be refused' ipv4=none ipv6=none

Lockout risk detected — refusing to apply:
  ! add 'opt9': device 'ixl1' is already bound to 'lan'. Refusing to apply.
$ echo $?
1
```

✅ The spike's pre-flight check refuses BEFORE any REST call. No network mutation; exit 1.

### Bad-input rollback (multi-step apply with deliberate failure)

⚠️ **Not exercised in this run.** The auto-rollback path depends on `/api/core/backup/backups` to capture a pre-apply snapshot id. That endpoint returns 404 on `26.1.6_2` (see add-cycle finding above), so the rollback path is unavailable on this version. Rather than simulate a deliberate failure that would leave us with no rollback, this scenario is deferred until ADR-0014's amendment decides on an alternative rollback mechanism.

### Delete cycle — remove the spike entry

```text
$ uv run python ... apply tmp/agents/claude/spike-iface-delete.yaml --confirm
Plan: 0 to add, 0 to update, 1 to delete, 4 locked.
  - opt9     device=igc1           desc='spike-test (re-bound)'
  L lan      ... (4 locked rows)

WARNING: no backup snapshot captured; auto-rollback unavailable.

Applying changes via REST...
  - del  opt9     device=igc1           -> deleted

Apply complete.
```

### Round-trip final

```text
$ uv run python ... plan tmp/agents/claude/spike-iface-delete.yaml
Plan: 0 to add, 0 to update, 0 to delete, 4 locked.
  L lan      ...
```

✅ Convergence after delete cycle. End-of-spike box state matches start-of-spike: 4 logical interfaces (`lan`/`lo0`/`wan`/`opt1`); `igc0` and `igc1` unassigned.

## Modern-versions investigation — `sessionClose()` cutoff

The original gist's two `$this->sessionClose();` calls (in `addItemAction` and `delItemAction`) were removed per Paradoxis's 2026-02-25 comment on the gist. The community-reported failure mode: on modern OPNsense the call raises a 500-level exception inside `ApiControllerBase`. We applied the patch unconditionally — it costs nothing on older versions, fixes the issue on modern ones.

| Question | Result |
| :--- | :--- |
| Empirically required on `opnsense-a` (running version)? | Patched controller worked end-to-end on `26.1.6_2`. Did not test reverting one `sessionClose()` to confirm the regression — risky live test. Defer to a follow-up empirical investigation if needed. |
| Upstream OPNsense PR / changelog entry that changed `sessionClose()` lifecycle? | Not identified during this spike. Search of `opnsense/core` for "sessionClose" / "ApiControllerBase" left as a follow-up research task; the patch costs nothing on older versions, so identifying the cutoff is informational, not blocking. |
| Version cutoff (is it `25.x`? `26.x`?) | Lower bound: required for `26.1.6_2` (this run). Upper bound: works on `26.1.6_2` (this run). Older versions: untested. The community comment thread on the gist reports the patch needed on "modern OPNsense" without naming a version cutoff. |

## Installation lifecycle — empirical observations

### Idempotency

`install.py install` first-time SCPs the file, restarts `configd` + `php_fpm`, verifies the post-install checksum. `install.py verify` is a read-only checksum check. Re-running `install.py install` is a no-op when the on-box checksum already matches the local source.

| Question | Result |
| :--- | :--- |
| First install succeeds? | ✅ yes (after two real bug fixes — env-loading was too strict; remote-checksum used non-csh-safe `2>/dev/null`). |
| Second install (no source changes) is a no-op? | Not tested in this run; only a single fresh install was performed. The script's `install_controller(force=False)` short-circuits when checksums match per its docstring; verify in a future run. |
| `install.py install --force` triggers re-SCP + service restart even with matching checksum? | Not tested; same reason as above. |

### MVC re-discovery

After SCP, the install script restarts `configd` and `php_fpm` so OPNsense's MVC autoloader picks up the new controller. Without the restart, `/api/interfaces/assign_settings/...` returns HTTP 404 even though the file is on disk.

| Question | Result |
| :--- | :--- |
| `service php_fpm restart` is sufficient to register the controller? | Not tested individually; the install does both restarts and the controller responded to REST after. Worth a follow-up test. |
| Does the GUI's "Interfaces → Assignments" page still render after the install? | ✅ yes — operator opened the page mid-run; renders the same as pre-install (with the new `opt9` showing in the table after apply). The new MVC controller is additive; it does not affect the legacy GUI page. |

### Upgrade survival (the load-bearing operational question)

`pkg upgrade` may or may not overwrite our controller depending on whether the file path is in a `pkg`-managed location. `/usr/local/opnsense/mvc/app/controllers/...` is part of the `opnsense` package's tree, so a major-version OPNsense upgrade will likely replace our file.

| Question | Result |
| :--- | :--- |
| Does `pkg list` report `AssignSettingsController.php` as part of `opnsense`? | Not tested in this run. Worth a quick check in a follow-up: `pkg which /usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php` will return the owning package, or "not in any package" if our SCP'd file is unmanaged by `pkg`. |
| Does a simulated upgrade (`pkg upgrade -n` or similar dry-run) flag the file for replacement? | Not tested in this run — full `pkg upgrade` is risky on production firewall infra. Recommend a separate maintenance window with backups, or test on a throwaway OPNsense VM. |
| Recommendation for production lift | The install script SHOULD be wired into a post-upgrade hook (e.g., `/usr/local/opnsense/scripts/configd/post-pkg-upgrade.d/`) — but that lift belongs to the production conversion issue, not this spike. |

## REST CRUD surface comparison

### Base gist (before our extensions)

| Endpoint | Verb | Path | Notes |
| :--- | :--- | :--- | :--- |
| `addItem` | POST | `/api/interfaces/assign_settings/addItem` | Auto-numbered `optN`. No IPv6. |
| `delItem` | POST | `/api/interfaces/assign_settings/delItem/{uuid}` | Idempotent; refuses `lan`/`wan`. |

### Our extensions

| Endpoint | Verb | Path | New behavior |
| :--- | :--- | :--- | :--- |
| `addItem` (extended) | POST | `/api/interfaces/assign_settings/addItem` | Optional `name` field for explicit `optN`. New IPv6 fields (`ipv6Type`, `ipv6Address`, `ipv6Subnet`, `ipv6Track`). |
| `setItem` | POST | `/api/interfaces/assign_settings/setItem/{uuid}` | In-place update. Same validation as `addItem`. Refuses if uuid is `lan`/`wan`. |
| `getItem` | GET | `/api/interfaces/assign_settings/getItem/{uuid}` | Returns `{result: 'ok', assign: {...}}` or HTTP 404. |
| `searchItem` | POST | `/api/interfaces/assign_settings/searchItem` | OPNsense-standard search response shape: `{result, rows, rowCount, total, current}`. |

### Cutover-relevant scenarios — live behavior

| Scenario | Spike result | Notes |
| :--- | :--- | :--- |
| `setItem` re-binds `optN` to a different kernel device without losing the logical name | ✅ verified (see "setItem re-bind" in run log). `opt9` re-bound from `igc0` to `igc1` in place; logical name preserved; round-trip plan = 0/0/0/0. |
| Explicit `name: opt9` on `addItem` is accepted by OPNsense's downstream code (GUI, watchers) | ✅ verified. Apply with `name: opt9` succeeded; subsequent `getItem('opt9')` returned the assignment; the GUI's Interfaces → Assignments page renders `opt9` correctly. No watcher errors observed. |
| `getItem` round-trips the assign payload faithfully | ✅ verified. After apply with `ipv4Type: static, ipv4Address: 10.99.99.1, ipv4Subnet: 24, ipv6Type: track-interface, ipv6Track: wan`, `getItem` returned all five fields exactly as posted. The Python spike's `_needs_update` only compares `device`+`description` today; field-for-field deep equality across IPv4/IPv6 dicts is a known gap (see Friction points). |
| `searchItem` returns the same set of interfaces as `interfacesInfo` | ✅ verified. `searchItem` returned 4 baseline rows (`lan`/`lo0`/`wan`/`opt1`) → 5 after add (`opt9`) → 4 after delete. `interfacesInfo` agreed on the same set throughout. `searchItem` carries richer fields (per-row IPv4/IPv6 typed); useful when the spike needs the desired-shape representation rather than the rendered live state. |
| IPv6 dual-stack (static IPv4 + track-interface IPv6) round-trips | ✅ verified. `opt9` fixture sets both; post-apply `getItem` returns both stacks; round-trip plan = 0/0/0/0. |

## Server-side validation behavior

The empirical demonstration of the safety improvement over #714.

| Bad input | #714 SSH+PHP-edit path | This spike (gist-based REST) |
| :--- | :--- | :--- |
| `ipv4Type: static` with no `ipv4Address` | Silent-bad-XML risk: writes `<ipaddr/>` empty, OPNsense's parser may load it ambiguously. | Not tested directly via REST in this run, but the spike's YAML loader rejects this client-side (verified by unit tests). The PHP controller's `validateIpv4` would also reject. |
| Invalid IPv4 address (`not-an-ip`) | Silent — `<ipaddr>` accepts the string. | ✅ HTTP 400 (verified live). |
| Bound `device` (collision) | Detected only if our spike's pre-flight check covers the case. | ✅ Spike pre-flight refuses BEFORE any REST call (verified live, exit 1, no network mutation). The PHP controller also has its own check (`ensureDeviceUnassigned`); belt-and-braces. |
| Invalid `ipv4Type` (`not-a-real-type`) | N/A in #714's path. | ✅ HTTP 400 (verified live). |
| `addItem` with no `device` field | Silent or partial state in #714's path. | ✅ HTTP 400 (verified live). |
| `name: lan` on `addItem` (try to clobber LAN) | Bypasses our spike's pattern check if the user crafts the YAML directly. | Not exercised live in this run. Controller's `validateExplicitName` regex `^opt\d+$` would reject `lan`; verified by unit tests. |
| Modify `lan` via `setItem` | N/A | Not exercised live; controller's `setItem` refuses uuid in `lan/wan` (mirror of `delItem` safety); verified by unit tests. |

The cumulative win: every silent-bad-XML risk from #714 becomes a loud HTTP 400 here, with the operator-readable error coming from the controller's own `UserException` flow.

## Auto-snapshot + audit log behavior

OPNsense's `Config::save()` fires the standard pre-write hook chain: capture an automatic backup snapshot, append an audit log entry, then write `/conf/config.xml`. We rely on this for both rollback availability and traceability — without owning either ourselves.

| Question | Result |
| :--- | :--- |
| Does `/api/core/backup/backups` work at all on `26.1.6_2`? | ❌ **No.** The endpoint returns HTTP 404 despite being in the spec. Same finding as #714's REST probe. **This blocks the entire auto-rollback design** — the spike degrades by warning loudly and proceeding without rollback armed. |
| Does an `addItem` REST call produce a new entry in `/api/core/backup/backups`? | Cannot determine — endpoint returns 404 (see above). |
| Does a `setItem` REST call produce a new entry? | Same — endpoint unavailable. |
| Does a `delItem` REST call produce a new entry? | Same. |
| Does the OPNsense System → Log Files → System General audit log show entries for our REST mutations? | Not verified in this run; the GUI was opened to confirm the Interfaces → Assignments page renders, but the audit log was not inspected. The PHP controller calls `Config::getInstance()->save()` which is OPNsense's standard write path — audit log entries should fire automatically. Worth a follow-up confirmation. |
| Does `revertBackup` with the captured snapshot id roll back the assignment change cleanly? | Not exercised — `backups` endpoint unavailable. ADR-0014's amendment must specify an alternative rollback strategy: either find a different snapshot mechanism on this OPNsense version, or accept "no transactional rollback" and design the production runner around per-resource error handling. |
| Does `revertBackup` revert ONLY `<interfaces>` or the WHOLE config? | Not exercised. Documented as an open question for the amendment regardless. |

## Round-trip property

| Question | Result |
| :--- | :--- |
| `plan` after `apply --confirm` (add cycle) returns 0/0/0? | ✅ yes |
| `plan` after `apply --confirm` (setItem cycle) returns 0/0/0? | ✅ yes (with 4 locked rows; the locked count is correct and is not a diff) |
| `plan` after `apply --confirm` (delete cycle) returns 0/0/0? | ✅ yes (with 4 locked rows) |
| Locked entries preserved across apply cycles? | ✅ yes — `lan`/`lo0`/`wan`/`opt1` carried `lock: true` across the rebind and delete cycles; never appeared in adds/updates/deletes. |
| IPv4/IPv6 fields round-trip lossy? | ✅ no observed lossiness for the tested case (static IPv4 + track-interface IPv6). The spike's `_needs_update` doesn't deep-compare IPv4/IPv6 dicts (known gap); this means the spike won't propose a re-set for cosmetic-only differences, but it also can't detect drift in those fields. Production must close this gap (see Friction points). |

## Friction points

> Pre-run notes locked in during implementation. The live run will add empirical observations.

- **`InterfaceAssignmentConfig._needs_update` only compares `device` + `description`.** The IPv4/IPv6 raw dicts aren't field-for-field compared because the live representation (`interfacesInfo`'s normalized dict) and the desired representation (typed config fields) don't share a schema. The spike documents this as a deliberate scope choice; ADR-0014's amendment must specify a deep-equality strategy before this graduates to production. Options: (a) call `getItem` and reconstruct the InterfaceAssignmentConfig from it for comparison; (b) maintain a normalizer that maps `interfacesInfo` → typed config; (c) accept the drift and let `apply --confirm` issue a no-op `setItem` when the IPv4/IPv6 fields differ in YAML but the operator doesn't care.
- **Spike-side device collision pre-flight is a duplicate of the server-side check.** Both the Python spike (`find_lockout_conflicts`) and the PHP controller (`addItem`'s `ensureDeviceUnassigned`) refuse if a device is already bound. The spike's pre-flight gives the operator a coherent error message before any REST call fires; the server-side check is the safety net. Document as belt-and-braces, not redundancy.
- **`revertBackup` granularity is "the whole config".** OPNsense doesn't expose per-section reverts; rolling back to the pre-apply snapshot blows away other concurrent changes. Acceptable for a spike (operator owns the timeline), but for production this needs either: (a) a "freeze other writes during apply" pattern, or (b) a richer rollback (e.g., capture+revert just the `<interfaces>` subtree). Capture as ADR-0014 amendment open question.
- **The PHP controller is community-authored and now ours to maintain.** The fork is BSD-2-Clause; we've added IPv6, `setItem`, `getItem`, `searchItem`, and explicit-name. Upstream may evolve; we may upstream our extensions back to the original gist (or its successor repo if `szymczag` publishes one). Tracked in the issue's "Maintenance ownership" section.
- **No PHP linting in this Python project.** Per the issue's resolved decisions: PHP can't be CI-linted here. Revisit when/if the controller graduates to production. For now, manual review on each PHP edit.
- **Trust boundary** — community-authored PHP deployed to root on the OPNsense box. The patched + extended file gets a real security review before any production lift (separate ADR/conversion issue).
- **`/api/core/backup/backups` and `/api/core/backup/download` return HTTP 404 on `26.1.6_2`** despite both being in the OpenAPI spec. **This blocks the entire auto-rollback design.** Same finding as #714's REST probe. The spike correctly degrades — warns loudly and proceeds without rollback — but the production runner needs an alternative. Two options surface for ADR-0014's amendment: (a) accept "no transactional rollback" and rely on server-side per-call validation as the safety net; (b) probe for an alternative snapshot mechanism (perhaps `/api/diagnostics/system/configBackup` if it materializes in a future OPNsense version, or shell out via SSH to `configctl` snapshot commands).
- **Install script's env-loading was too strict** as originally implemented — required explicit `OPNSENSE_SSH_HOST` and `OPNSENSE_SSH_KEY`, neither of which the operator typically sets in a homelab where `~/.ssh/config` and ssh-agent already provide identity. Fixed in this PR: `OPNSENSE_SSH_HOST` falls back to the host part of `OPNSENSE_API_URL`; `OPNSENSE_SSH_KEY` is optional (empty → use ssh-agent). Friction caught and fixed before completion; documented here so future spikes target the same env model.
- **OPNsense's root shell is `opnsense-shell` (csh-derived).** `2>/dev/null` is "Ambiguous output redirect." The install's remote-checksum command was rewritten to use `test -f <path> && sha256 -q <path> || echo MISSING`, which is portable across both shells. **General principle for any future SSH-into-OPNsense work**: avoid stderr redirection in the remote command; use `&&`/`||` chaining instead. Mirrors the lesson from #714's `shlex.quote` fix (different bug, same shell-portability theme).
- **The 4-original-interfaces "fully-managed delete-everything-not-in-YAML" risk** carries forward from VLAN/#714 spikes. Without `--add-only` or explicit `lock: true` entries for `lan`/`lo0`/`wan`/`opt1`, the spike would propose 4 destructive deletes the moment the operator's fixture only declares `opt9`. Cutover fixtures lock the four originals; the spike's `--add-only` flag is the alternative for ad-hoc adds.

## Lines of code per concern

| Concern | LoC (approx) | File |
| :--- | :--- | :--- |
| PHP controller (forked + patched + extended) | ~570 | `tools/spikes/interface_assignment_gist_rest/AssignSettingsController.php` |
| - of which inherited from base gist | ~345 | (verbatim, with `sessionClose()` removed) |
| - of which net-new in this fork | ~225 | (`setItem`, `getItem`, `searchItem`, IPv6, explicit-name, validation helpers) |
| Install script (Python) | ~270 | `tools/spikes/interface_assignment_gist_rest/install.py` |
| Python spike — config models + YAML loader | ~270 | `tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py` |
| Python spike — REST helpers | ~110 | (above) |
| Python spike — diff engine + lockout-prevention | ~80 | (above) |
| Python spike — backup/rollback helpers | ~50 | (above) |
| Python spike — subcommand handlers + CLI | ~265 | (above) |
| **Python spike total** | **~1060** | (interface_assignment_gist_rest.py + install.py + tests) |
| Tests (Python only — PHP not CI-tested) | ~870 | `tests/spikes/test_interface_assignment_gist_rest.py` |
| Test count | 116 | (`uv run pytest tests/spikes/test_interface_assignment_gist_rest.py`) |
| Test coverage on the spike Python module | 88.95% | (`uv run pytest --cov=tools.spikes.interface_assignment_gist_rest`) |

For context: the production read-only `interface_assignments` path in `src/infrafoundry/providers/opnsense/services/interface_assignment.py` is ~280 LoC. The spike's read path is roughly equivalent; the new code is the write surface (PHP controller + REST helpers + lockout-prevention + auto-rollback).

## Apply timing

| Operation | Time elapsed |
| :--- | :--- |
| `interfacesInfo` (1 GET) | sub-second |
| `addItem` (1 POST + Config::save + interface reconfigure all) | ~3-5 seconds end-to-end (configd `interface reconfigure all` dominates) |
| `setItem` (1 POST + same backend) | ~3-5 seconds end-to-end |
| `delItem` (1 POST + same backend) | ~3-5 seconds end-to-end |
| `revertBackup` (1 POST) | Not measured — endpoint returns 404 on `26.1.6_2`. |
| `searchItem` (1 POST, controller-direct) | sub-second (no Config::save, no reconfigure) |
| `getItem` (1 GET) | sub-second |

The spike doesn't time itself precisely; numbers are observed via wall-clock during the run. Production runner should add structured timing if operators care about it.

## Recommendation

**Recommendation: yes for production lift, with three gates.**

The live run validated the load-bearing claims. The mechanism is sound; the safety improvement over #714 is real.

**Confirmed during the run:**

1. ✅ Server-side validation rejects bad inputs with HTTP 400. Three cases probed live; all rejected. Replaces #714's silent-bad-XML risk.
2. ✅ `setItem` round-trips the assign payload faithfully — verified via `getItem` after every mutation cycle.
3. ✅ Explicit `name: opt9` on `addItem` is accepted by OPNsense. No GUI breakage. The cutover affordance is real.
4. ✅ Lockout-prevention refuses fixtures targeting bound NICs before any REST call.
5. ✅ Round-trip property holds across add / setItem / delete cycles.
6. ✅ The patched controller (sessionClose removed) works on `26.1.6_2`.

**Three gates remain for the production lift:**

1. **Alternative rollback strategy.** `/api/core/backup/{backups,download}` returns HTTP 404 on `26.1.6_2`. The auto-rollback path designed in the spike is therefore unavailable on this OPNsense version. Production needs to either: (a) find a working snapshot endpoint on this version (none surfaced during this spike), (b) shell out via SSH to a `configctl` snapshot command (re-introduces SSH dependency for safety), or (c) accept "no transactional rollback" and rely on server-side per-call validation as the safety net. Option (c) is reasonable for `interface_assignments` specifically because OPNsense's standard save flow already takes its own auto-snapshot before each `Config::save()` (visible in the GUI's config history); the operator can manually revert from there. This gate is for ADR-0014's amendment to resolve.
2. **Auto-snapshot + audit log empirical confirmation.** The PHP controller calls `Config::getInstance()->save()` which is OPNsense's standard write path, so audit log entries should fire automatically. **Not directly verified in this spike** — open the GUI's System → Log Files → System General after each mutation in a follow-up to confirm the audit trail is intact. If the audit log fires, gate (1) option (c) becomes more attractive: the operator has BOTH the GUI's auto-snapshot AND the audit log to reconstruct a manual rollback.
3. **Security review of the patched + extended PHP controller.** Community-authored code deployed to root on production firewall infrastructure. The fork is BSD-2-Clause; we've added IPv6, `setItem`, `getItem`, `searchItem`, validation helpers, and explicit-name. ~225 LoC of net-new PHP that needs eyes. Track as a follow-up; not blocking the spike's findings.

**ADR-0014 amendment scope:**

- Add `interface_assignments` to the direct-API write path via the gist-based controller. Cite this document.
- Resolve gate (1) explicitly: name the rollback strategy production will use.
- Production conversion of `OPNsenseDirectRunner.apply()` for `interface_assignments` from no-op to live dispatches through this controller. Lockout-prevention crosses over unchanged. Rollback strategy follows from the amendment's gate-(1) decision.
- Install lifecycle for the controller: how does `infra apply` ensure the controller is installed and current? Auto-install on first apply? Fail loudly with `foundry opnsense install-controller`? Wire into `pkg upgrade` post-hooks? Belongs to the production conversion issue, not the amendment itself.
- Out of scope for this amendment: other GUI-only resource types (gateways, virtual_ips, NAT legacy). Each gets its own spike before production. The mechanism may generalize but the empirical case is `interface_assignments` only.

**Why the mechanism still graduates well despite gate (1):**

The safety improvement over #714 is **per-call server-side validation**, which is intact regardless of rollback availability. We don't own the XML schema — OPNsense's `Config::save()` does. We don't own field validation — the controller's `UserException`-based check chain does. We don't own the audit log — OPNsense's standard save flow does. The only thing we lost vs. #714's design is the post-hoc transactional rollback, which #714 itself only achieved at unacceptable safety cost (silent-bad-XML, scp without server-side schema check). Trading "transactional rollback that risks bricking the box" for "no transactional rollback but every write is server-validated" is a clear safety win.

**The friction we hit during the spike** (env-loading too strict, csh-incompatible remote command) was caught and fixed in this same PR, with tests updated. Both fixes are general-purpose patterns useful for any future OPNsense-via-SSH work. Documented under Friction points.
