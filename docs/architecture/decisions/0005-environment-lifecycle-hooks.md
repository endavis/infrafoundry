# 5. Environment Lifecycle Hooks

**Date:** 2025-01-26
**Status:** Accepted

## Context

Users need the ability to execute custom scripts at specific points during infrastructure operations. Common use cases include:

- **Before destroy:** Remove a Tailscale device before the VM is destroyed
- **After apply:** Notify Slack about successful deployments
- **Before plan:** Run pre-flight validation scripts
- **After destroy:** Clean up external resources not managed by Terraform

The current event system (ADR-0003) provides internal observability but doesn't support user-defined script execution with proper environment injection, secret access, and error handling.

## Decision

We will implement a **two-level hook system**:

1. **Environment-level hooks** in `settings.yaml` - run for all operations in that environment
2. **Resource-level hooks** in resource configs - run only for that specific resource

### Execution Order

```
Environment before_X → Resource before_X → [Operation] → Resource after_X → Environment after_X
```

### Hook Configuration Model

```yaml
# settings.yaml (environment-level)
hooks:
  before_destroy:
    - script: scripts/backup-state.sh
      description: "Backup Terraform state"
      timeout: 300
      continue_on_error: false
      env:
        BACKUP_BUCKET: "{{ secrets.backup_bucket }}"

# resource config (resource-level)
- name: k3s-control
  type: instance
  hooks:
    before_destroy:
      - script: scripts/cleanup-tailscale.sh
        env:
          TAILSCALE_API_KEY: "{{ secrets.tailscale_api_key }}"
```

### HookManager Responsibilities

1. **Script execution** via subprocess with:
   - Working directory = environment config directory
   - Timeout handling (default 300s, max 3600s)
   - stdout/stderr capture and logging

2. **Environment variable injection:**
   - `INFRAFOUNDRY_ENV` - environment name
   - `INFRAFOUNDRY_CONFIG_DIR` - path to env config
   - `INFRAFOUNDRY_EVENT` - event type (e.g., "before_destroy")
   - `INFRAFOUNDRY_RESOURCE` - resource name (for resource-level hooks)
   - `INFRAFOUNDRY_PROVIDER` - provider name
   - Custom env vars from hook config

3. **Secret template resolution:** `{{ secrets.xxx }}` in env values resolved via SecretManager

4. **Error handling:**
   - Non-zero exit or timeout = failure
   - `continue_on_error: true` allows operation to proceed despite hook failure
   - Missing script = immediate failure with clear error message

## Consequences

**Positive:**

- **Flexibility:** Users can integrate with any external system (Tailscale, Slack, backup services)
- **Separation of concerns:** Scripts live in user's config repo, not framework code
- **Secret access:** Scripts receive secrets via environment variables, no hardcoding
- **Granularity:** Resource-level hooks enable per-resource customization
- **Safety:** `continue_on_error: false` (default) ensures operations fail fast on hook errors

**Negative:**

- **Complexity:** Two-level execution order requires careful documentation
- **Debugging:** Script failures may be harder to debug than native integrations
- **Security surface:** Scripts run with access to secrets; users must secure their config repos
- **Platform dependency:** Scripts must be POSIX-compatible (or users must handle Windows separately)

## Alternatives Considered

1. **Plugin system with Python modules:** Rejected because it requires users to write Python code and understand the InfraFoundry internals. Shell scripts are more accessible.

2. **Event webhooks only:** Rejected because webhooks require an external HTTP server, adding infrastructure overhead. Local scripts are simpler for most use cases.

3. **Single-level hooks (environment only):** Rejected because per-resource hooks are essential for use cases like per-VM Tailscale cleanup where each resource has different parameters.

4. **Inline script content in YAML:** Rejected because external script files are easier to test, version, and maintain. Also avoids YAML escaping issues.
