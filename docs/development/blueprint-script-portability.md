# Blueprint Script Portability

Blueprint event-handler scripts (`on_create`, `after_apply`, `before_destroy`, etc.) do not always run on the InfraFoundry orchestration host. Depending on the consuming package's configuration, the framework may rsync a script to a remote jumphost and execute it there, or a script may upload sibling helpers onto a target VM and run them via ssh. Each of those contexts has its own set of tools you can safely assume exist.

This page documents the portability contract that blueprint scripts must respect, so they don't silently break on minimal hosts the way #641 and #645 did.

## Execution contexts

A blueprint script may run in one of three contexts:

### 1. InfraFoundry orchestration host

The default — the host running `foundry infra apply`. Tools available here are whatever the user installed to operate InfraFoundry. `python3` and `uv` are always present.

### 2. Jumphost (framework reexec)

When the consuming package sets `jumphost` in its variables (`user@host`), the framework's `ScriptHandler._execute_on_jumphost` rsync's the blueprint's script directory to a temp dir on the jumphost and runs the script there via ssh. The wrapper (`src/infrafoundry/core/events/handlers/script.py`) forwards `INFRAFOUNDRY_PACKAGE_VARS` and re-exports each scalar as `INFRAFOUNDRY_VAR_<key>` on the remote side, matching local execution semantics.

The jumphost may be a minimal Debian/Ubuntu/Rocky host. **Treat it as a stock base install** — do not assume anything beyond the portable baseline below.

### 3. Target VM (scp + ssh)

A script running in context 1 or 2 may upload sibling scripts to a target VM (via `scp` / `rsync`) and execute them there via `ssh`. Example: `blueprints/aiqum/scripts/aiqum-post-terraform.sh` uploads `aiqum-install-remote.sh` to the AIQUM VM and runs it via `remote_cmd_long`.

Target VMs are **blueprint-controlled** — the OS is known because the blueprint provisions it. Target-VM scripts may reach for distro-specific tooling (`yum`, `apt`, `firewalld`, etc.), subject to the exemption rules below.

## The portable baseline

Every script that might run in context 1 or 2 must use only these tools:

| Tool | Notes |
|---|---|
| `bash` | 4+ (`mapfile` / `readarray`, process substitution, `<<<` here-strings) |
| `python3` | **stdlib only.** Allowed modules include `json`, `urllib.request`, `urllib.parse`, `os`, `sys`, `subprocess`, `pathlib`, `base64`, `re`, `smtplib`, `email.mime.*`. No `requests`, no `PyYAML`, no `jinja2`, no `boto3`. |
| GNU coreutils | `cat`, `printf`, `sed`, `grep`, `awk`, `mkdir`, `chmod`, `ls`, `mapfile`/`readarray`, etc. |
| `ssh`, `scp`, `rsync`, `curl` | Standard on any modern Linux host. |

Anything else requires an explicit presence check — see below.

## `jq` is not recommended

`jq` is the obvious tool for parsing JSON in bash, and it's tempting. **Don't use it in blueprint scripts.** It is not in the base install of:

- Debian / Ubuntu (all current versions)
- Rocky / RHEL / CentOS (all current versions)
- Alpine
- Most public cloud base images (AWS, Azure, GCP, OCI)
- Most minimal container base images

When `jq` is missing, `echo "$JSON" | jq -r '.foo'` emits `jq: command not found` to stderr but the outer `$(...)` or `< <(...)` substitution still returns an empty string, so the caller silently proceeds with an empty list or an empty variable. That failure mode is what caused the `Agents (0):` bug in #645.

Use stdlib `python3` instead. Equivalent one-liners:

| `jq` | Python equivalent |
|---|---|
| `jq -r '.foo'` | `python3 -c 'import json,sys; print(json.load(sys.stdin).get("foo",""))'` |
| `jq -r '.items[].name'` | `python3 -c 'import json,sys
for i in json.load(sys.stdin).get("items",[]): print(i["name"])'` |
| `jq -r '.items[] \| select(.x == true) \| .id'` | `python3 -c 'import json,sys
for i in json.load(sys.stdin).get("items",[]):
    if i.get("x"): print(i["id"])'` |

See `blueprints/k3s-cluster/scripts/proxmox/k3s-post-terraform.sh` (lines 34-37) and `blueprints/k3s-cluster/scripts/oci/cleanup-tailscale-devices.sh` for in-tree examples after the swap in PR #646.

## Tools outside the baseline

Scripts in context 1 or 2 may still need tools outside the baseline — `ansible-playbook`, `kubectl`, `yq`, `terraform`, etc. That's allowed, but the script must **fail fast with a clear error** if the tool is missing rather than degrading into a confusing later failure.

Put a presence check at the top of the script, near the `set -euo pipefail`:

```bash
if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook is required but was not found on PATH" >&2
    echo "Install ansible and ensure ansible-playbook is on PATH (on the jumphost if jumphost is set in the package)" >&2
    exit 127
fi
```

For Python packages outside stdlib (`requests`, `pyyaml`, etc.), use an `import` check:

```bash
if ! python3 -c 'import requests' >/dev/null 2>&1; then
    echo "ERROR: the python3 'requests' package is required but is not installed" >&2
    echo "Install it via your system package manager or pip" >&2
    exit 127
fi
```

Exit code `127` is the conventional "command not found" status, so CI and shell-aware callers can detect it distinctly.

Exemplars in the codebase:

- **Tool check:** `blueprints/k3s-cluster/scripts/oci/k3s-post-terraform.sh` (`ansible-playbook` guard, added in PR #646).
- **Tool check:** `blueprints/ontap-cluster/scripts/ontap-post-terraform.sh` (`ansible-playbook` guard, added in PR #648).
- **Env-var check:** `blueprints/aiqum/scripts/aiqum-post-terraform.sh` (required `INFRAFOUNDRY_PACKAGE_VARS`, added in PR #648).

## Non-fatal warnings

During `infra apply`, the framework exports `INFRAFOUNDRY_WARNINGS_FILE` with a
path to a per-deployment JSONL file. Blueprint scripts running in any context
(operator host, jumphost, or target VM via `ssh` with the env var forwarded)
may append records of the form `{"source":"<handler>","message":"<text>"}` to
that file; the framework reads and renders them in a yellow-bordered summary
panel at the end of apply. On jumphost reexec, the remote wrapper seeds a file
under the remote tmp dir and the orchestrator `scp`'s the contents back before
cleanup, so remote warnings surface the same way local ones do.

Use this for abnormalities that are non-fatal but worth the operator seeing —
e.g. "sysctl reported errors but the params we care about did get set",
"kubeconfig copied with one warning". **Do not put credentials or raw secret
material into warning messages** — the file lives unencrypted in `/tmp` for
the duration of the apply and is printed to the console.

Simple append from a blueprint script (no tools beyond the portable baseline):

```bash
if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
    printf '%s\n' '{"source":"my-handler","message":"sysctl net.core.somaxconn not applied"}' \
        >> "$INFRAFOUNDRY_WARNINGS_FILE"
fi
```

The env var is only set during `infra apply`; guarding with `${…:-}` keeps
scripts portable to other phases and to manual invocation.

## Target-VM scripts: the exemption

Scripts that are uploaded to and executed on a blueprint-controlled target VM (context 3) are exempt from the portable baseline. Those scripts may assume any tool that the blueprint's VM template provides — `yum`, `apt`, `firewall-cmd`, `rpm`, distro-specific init systems, etc.

In exchange, a target-VM script **must**:

1. Have a header that documents (a) the target OS the script expects, (b) how it is invoked (upload-and-exec pattern), (c) required environment variables, and (d) every tool it assumes is on the target.
2. Be referenced from the blueprint's `README.md` so the OS expectation is discoverable without reading the script.

Exemplar: `blueprints/aiqum/scripts/aiqum-install-remote.sh` (headed up in PR #650).

## Checklist for blueprint authors

Before submitting a PR that adds or changes a blueprint script:

- [ ] Identify which execution context(s) this script runs in (1, 2, or 3). If it's an `on_create` / `after_apply` / `before_destroy` handler on a blueprint whose consumers might set `jumphost`, assume context 2.
- [ ] If context 1 or 2: confirm the script uses only the portable baseline. No `jq`, no `yq`, no third-party Python packages, no `ansible-playbook` / `kubectl` / etc. without a presence check.
- [ ] If the script uses a tool outside the baseline, add a `command -v` or `python3 -c 'import X'` check at the top with `exit 127` and a clear error message.
- [ ] If context 3 (target-VM upload): document the target OS, invocation pattern, env vars, and tool assumptions in the script header; confirm the blueprint README also states the OS expectation.
- [ ] Use `python3 -c 'import json ...'` (stdlib) instead of `jq` for JSON parsing.

## Related documentation

- [Event System](event-system.md) — how `on_create` / `after_apply` / etc. handlers are dispatched.
- `src/infrafoundry/core/events/handlers/script.py` — the framework's `ScriptHandler`, including `_execute_on_jumphost` and `_build_remote_bash`.
- [Issue #643](https://github.com/endavis/infrafoundry/issues/643) — the portability audit that produced this contract.
