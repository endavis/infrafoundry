# ADR-0006: Explicit script handler output declarations

## Status

Accepted

Related issue: [#660](https://github.com/endavis/infrafoundry/issues/660)

## Context

When a blueprint event-handler script runs on a jumphost via
`ScriptHandler._execute_on_jumphost`, any file the script writes to a
path like `~/.kube/k3s-homelab.yaml` lands on the **jumphost's**
filesystem — because `~` expands against the jumphost user's home, not
the operator's. The concrete motivator was Phase 6 of
`blueprints/k3s-cluster/scripts/proxmox/k3s-post-terraform.sh`, which
emits a rendered kubeconfig that the operator then has to `scp` back
from the jumphost on every apply.

This is a generic gap in the jumphost reexec story. Any blueprint that
produces operator-consumable artifacts (kubeconfigs, CA certs, deploy
reports, Terraform outputs) hits the same problem, and every blueprint
author reaches for ad-hoc `scp` glue inside the script. That glue:

- Has to know the operator's workstation address and user from inside
  the jumphost context, where those aren't naturally available.
- Duplicates transport logic that the framework already performs
  elsewhere (e.g. `_fetch_remote_warnings`).
- Makes the blueprint script non-portable to the local execution path,
  because the `scp` glue is predicated on a jumphost being present.

Two options were considered for a framework-level solution:

- **Option A — Convention-based outputs directory.** The framework
  exports `INFRAFOUNDRY_OUTPUTS_DIR` pointing at a per-handler temp dir
  on the execution host, and rsync's its contents back at the end of
  the run. Cheap to add, but loose: anything the script drops into the
  dir ships back, without the blueprint author having declared the
  contract. Renaming, permissions, and conditional outputs end up
  scattered across shell scripts.
- **Option B — Explicit per-output declaration.** Blueprints declare
  what they produce (`outputs: [{source, dest}]`) and the framework
  maps each declared source to a specific operator-side dest.

## Decision

**Adopt Option B.** The `script` event handler gains an optional
`outputs:` field on its config:

```yaml
events:
  on_create:
    - type: script
      script: scripts/proxmox/k3s-post-terraform.sh
      outputs:
        - source: "/tmp/k3s-{{ cluster_name }}/kubeconfig.yaml"
          dest:   "{{ kubeconfig_local_path }}"
```

Contract:

- `outputs:` is optional. Missing / `None` / `[]` means no pull-back —
  fully backwards compatible with every existing handler config.
- Each entry is a mapping with two required string keys: `source`
  (path on the execution host — jumphost during reexec, operator host
  during local execution) and `dest` (path on the operator's
  workstation).
- Both values are rendered through the same Jinja2 environment the
  blueprint resolver uses (`create_jinja2_env`) against the package
  variables carried on `EventContext`. Rendering happens at execute
  time so runtime-computed variables are visible.
- Both rendered paths must be absolute (start with `/` or `~`). A
  non-absolute path emits a warning and skips that entry without
  failing the handler.
- Pull-back runs **only when the script succeeds** (exit code 0). Failed
  runs skip outputs processing entirely so partial or stale artifacts
  don't leak to the operator.
- Transport:
  - Local execution: `shutil.copy2(source, dest)`; if the two resolve
    to the same path, the copy is a no-op.
  - Jumphost execution: one `scp` per entry, run inside the existing
    `finally` block between `_fetch_remote_warnings(...)` and
    `_cleanup_remote(...)` so the remote tmp dir still contains the
    artifact when `scp` executes.
- `Path(dest).parent.mkdir(parents=True, exist_ok=True)` is applied
  before every copy/scp so authors don't have to pre-create
  `~/.kube/`, `~/reports/`, etc.
- Failure modes — missing source, scp non-zero, permission errors,
  template errors — are **non-fatal**. Each surfaces as a JSONL record
  under the source tag `script_handler_outputs` via the existing
  `INFRAFOUNDRY_WARNINGS_FILE` mechanism, which renders in the apply
  summary panel.

Structural validation (shape of the list and entry keys) runs at config
load time inside `ScriptHandler.validate_config`. The absolute-path
check is deferred to execute time because values may be Jinja2-templated
and need runtime context to resolve.

## Consequences

**Easier:**

- Blueprint authors declare artifacts once, in the manifest, and the
  framework handles transport. No more ad-hoc `scp` glue inside
  scripts.
- Local and jumphost execution are covered by the same declaration —
  authors don't branch on `jumphost` to decide whether to copy.
- Operators don't rerun a manual post-apply step to fetch the
  kubeconfig. The deploy is genuinely one-shot.
- The declaration is discoverable in the manifest instead of buried in
  a shell script.

**More difficult:**

- Blueprint authors must now think about *where* a script writes an
  artifact on the execution host. Previously that detail lived inside
  the script; now the manifest points at it too, and the two must
  agree. The `{{ package variables }}` rendering on both sides
  mitigates this, but it's one more coupling point.
- The schema is additive, so existing config is unaffected — but any
  blueprint that currently does its own `scp` back needs a follow-up
  to migrate to `outputs:`. A separate issue tracks the k3s-cluster
  migration.

**Neutral:**

- No new Python dependency. `jinja2` is already a project dep and the
  framework's own `create_jinja2_env` helper (with all custom filters
  registered) is reused.
- The warnings-file mechanism already existed; this ADR just adds a
  new well-known source tag (`script_handler_outputs`) to it.
- The restructure of `_execute_on_jumphost` to track a `success` flag
  across the `try`/`finally` boundary is small (one flag, two
  assignments) and the existing warning-fetch/cleanup ordering is
  preserved.

## Implementation

- Handler: `src/infrafoundry/core/events/handlers/script.py`
  - `validate_config` — structural validation of the new field.
  - `_process_outputs`, `_process_output_local`,
    `_process_output_remote`, `_is_absolute_output_path` — new
    helpers.
  - `_execute_locally` — call `_process_outputs(outputs, context)` on
    success.
  - `_execute_on_jumphost` — track `success`; call
    `_process_outputs(..., jumphost=..., ssh_opts=...)` in the
    `finally` block between the remote warnings fetch and the remote
    tmp-dir cleanup.
- Tests: `tests/unit/test_events.py` — new
  `TestScriptHandlerOutputs` class covering validation, absent/empty
  no-ops, local copy / same-path / missing-source / relative-path /
  template / parent-dir / failure-skip cases, and jumphost
  scp-on-success / skipped-on-failure / non-fatal-scp-error /
  multiple-outputs / cleanup-ordering / ssh-opts-forwarded cases.
- Documentation:
  - [Event System → Declaring script outputs](../development/event-system.md#declaring-script-outputs)
  - [Blueprint script portability → Outputs](../development/blueprint-script-portability.md#outputs-pulling-artifacts-back-to-the-operator)

