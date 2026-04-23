# Lifecycle Hooks

## Overview

Lifecycle hooks allow you to run custom scripts at specific points during infrastructure operations (plan, apply, destroy). Common use cases include:

- Removing cloud resources not managed by Terraform (e.g., Tailscale devices)
- Sending notifications to Slack/Teams on deployment
- Running smoke tests after apply
- Backing up state before destroy
- Pre-flight validation checks

## Audience and Prerequisites

- **Audience:** Operators who need custom automation around infrastructure lifecycle events
- **Prerequisites:** Basic shell scripting knowledge, access to the config repo

## When to Use This

- You need to run external cleanup scripts before destroying infrastructure
- You want to integrate with external systems (Tailscale, DNS providers, monitoring)
- You need custom validation or notification beyond built-in features
- You want per-resource customization of lifecycle behavior

## Hook Levels

Hooks can be defined at two levels:

1. **Environment-level:** In `settings.yaml`, runs for all operations in that environment
2. **Resource-level:** In resource configs, runs only for that specific resource

### Execution Order

```
Environment before_X → Resource before_X → [Operation] → Resource after_X → Environment after_X
```

## Quick Start

### Environment-Level Hooks

Add hooks to your environment's `settings.yaml`:

```yaml
# envs/prod/settings.yaml
name: prod

hooks:
  after_apply:
    - script: scripts/notify-slack.sh
      description: "Notify team of deployment"
      env:
        SLACK_WEBHOOK: "{{ secrets.slack.webhook }}"
      continue_on_error: true

  before_destroy:
    - script: scripts/backup-state.sh
      description: "Backup Terraform state before destroy"
```

### Resource-Level Hooks

Add hooks to specific resources:

```yaml
# envs/prod/oci/instances.yaml
instance:
  - name: k3s-control
    shape: VM.Standard.A1.Flex
    hooks:
      before_destroy:
        - script: scripts/cleanup-tailscale.sh
          description: "Remove Tailscale device"
          env:
            TAILSCALE_API_KEY: "{{ secrets.tailscale.api_key }}"
            HOSTNAME: k3s-control
    # ... rest of config
```

## Configuration Reference

### Hook Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `script` | string | required | Path to script, relative to environment directory |
| `description` | string | null | Human-readable description shown during execution |
| `env` | dict | {} | Environment variables to pass to the script |
| `continue_on_error` | bool | false | Whether to continue if script fails |
| `timeout` | int | 300 | Script timeout in seconds (1-3600) |

### Supported Lifecycle Stages

| Stage | When it runs |
|-------|--------------|
| `before_plan` | Before generating Terraform/Ansible configs |
| `after_plan` | After successful plan operation |
| `before_apply` | Before applying infrastructure changes |
| `after_apply` | After successful apply operation |
| `before_destroy` | Before destroying infrastructure |
| `after_destroy` | After successful destroy operation |

### Environment Variables

Scripts receive these environment variables automatically:

| Variable | Description |
|----------|-------------|
| `INFRAFOUNDRY_ENV` | Environment name (e.g., "prod") |
| `INFRAFOUNDRY_CONFIG_DIR` | Path to environment config directory |
| `INFRAFOUNDRY_EVENT` | Lifecycle stage (e.g., "before_destroy") |
| `INFRAFOUNDRY_RESOURCE` | Resource name (resource-level hooks only) |
| `INFRAFOUNDRY_PROVIDER` | Provider name (resource-level hooks only) |

Plus any custom variables defined in the hook's `env` section.

### Secret Templating

Use `{{ secrets.file.key }}` syntax to inject secrets:

```yaml
hooks:
  after_apply:
    - script: scripts/notify.sh
      env:
        API_KEY: "{{ secrets.notifications.api_key }}"
        WEBHOOK: "{{ secrets.slack.webhook_url }}"
```

The secret path maps to `envs/{env}/secrets/{file}.yaml` and the specified key.

## Examples

### Tailscale Cleanup Before Destroy

```yaml
# envs/prod/settings.yaml
hooks:
  before_destroy:
    - script: scripts/cleanup-tailscale.sh
      description: "Remove Tailscale devices from admin console"
      env:
        TAILSCALE_API_KEY: "{{ secrets.tailscale.api_key }}"
      timeout: 60
```

```bash
#!/bin/bash
# scripts/cleanup-tailscale.sh
# Remove Tailscale device when destroying VM

set -e

# INFRAFOUNDRY_RESOURCE is set for resource-level hooks
if [ -n "$INFRAFOUNDRY_RESOURCE" ]; then
    DEVICE_NAME="$INFRAFOUNDRY_RESOURCE"
else
    # For environment-level hooks, remove all devices in this environment
    DEVICE_NAME="*-${INFRAFOUNDRY_ENV}"
fi

echo "Removing Tailscale device: $DEVICE_NAME"

# Use Tailscale API to remove device
curl -s -X DELETE \
    -H "Authorization: Bearer $TAILSCALE_API_KEY" \
    "https://api.tailscale.com/api/v2/device/${DEVICE_NAME}"

echo "Device removed successfully"
```

### Slack Notification After Apply

```yaml
hooks:
  after_apply:
    - script: scripts/notify-slack.sh
      description: "Notify deployment channel"
      env:
        SLACK_WEBHOOK: "{{ secrets.slack.webhook }}"
        CHANNEL: "#deployments"
      continue_on_error: true  # Don't fail deploy if notification fails
```

```bash
#!/bin/bash
# scripts/notify-slack.sh

curl -s -X POST "$SLACK_WEBHOOK" \
    -H "Content-Type: application/json" \
    -d "{
        \"channel\": \"$CHANNEL\",
        \"text\": \"Deployment completed for $INFRAFOUNDRY_ENV\",
        \"username\": \"InfraFoundry\",
        \"icon_emoji\": \":rocket:\"
    }"
```

### Pre-Destroy State Backup

```yaml
hooks:
  before_destroy:
    - script: scripts/backup-state.sh
      description: "Backup Terraform state to S3"
      env:
        BACKUP_BUCKET: "{{ secrets.aws.backup_bucket }}"
      timeout: 120
```

### Per-Resource Hooks

For resources that need individual cleanup:

```yaml
# envs/prod/oci/instances.yaml
instance:
  - name: monitoring-server
    hooks:
      before_destroy:
        - script: scripts/deregister-monitoring.sh
          env:
            DATADOG_API_KEY: "{{ secrets.datadog.api_key }}"
            HOST_TAG: monitoring-server
      after_apply:
        - script: scripts/register-monitoring.sh
          env:
            DATADOG_API_KEY: "{{ secrets.datadog.api_key }}"
    # ... rest of instance config
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Script not found | Operation fails with clear error message |
| Script not executable | Operation fails with clear error message |
| Script exits non-zero | Operation fails (unless `continue_on_error: true`) |
| Script times out | Operation fails (unless `continue_on_error: true`) |
| Secret not found | Warning logged, empty string used |

## Validation

Test your hooks with a dry run:

```bash
# See what hooks would be executed
foundry infra plan --env prod --dry-run
```

Check script permissions:

```bash
# Ensure scripts are executable
chmod +x envs/prod/scripts/*.sh
```

## Related Documentation

- [Notifications Configuration](notifications.md) - Built-in event notifications
- [Secrets Management](per-environment-credentials.md) - Managing secrets for hooks
- [Architecture: Event System](../development/event-system.md) - Understanding lifecycle events
- [ADR-0011: Environment Lifecycle Hooks](../decisions/0011-environment-lifecycle-hooks.md)

## Troubleshooting

- **Symptom:** Hook not running. **Fix:** Verify script path is relative to environment directory, script is executable, and hook is defined for the correct lifecycle stage.

- **Symptom:** Secret not resolved. **Fix:** Check secret file exists at `envs/{env}/secrets/{file}.yaml` and key path is correct. Missing secrets become empty strings with a warning.

- **Symptom:** Script times out. **Fix:** Increase `timeout` value or optimize script. Default is 300 seconds, maximum is 3600.

- **Symptom:** Hook fails but operation continues. **Fix:** Remove `continue_on_error: true` if you want failures to stop the operation.

---

Last updated: 2025-01-26

---
[Back to Table of Contents](../index.md)
