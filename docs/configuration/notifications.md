# Notifications Guide

## Overview

InfraFoundry can emit deployment, drift, and policy events to Slack, Discord, or generic webhooks. Notifications are driven by the event bus and can be filtered by event type and severity.

## Audience and Prerequisites

- **Audience:** Operators who want deployment/drift alerts; platform teams integrating InfraFoundry events into chat/ops tools.
- **Prereqs:** Access to the config repo, channel webhook URLs (Slack/Discord/webhook), and knowledge of target environments.

## When to Use This

- You want real-time feedback for `plan/apply/destroy/drift` events.
- You need environment-specific notification rules.
- You want to route only certain severities or event types.

## Quick Start

1. Create `notifications.yaml` (root or `envs/{env}/notifications.yaml`):
   ```yaml
   channels:
     - name: slack-deployments
       type: slack
       enabled: true
       config:
         webhook_url: https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
       events:
         - after_apply
         - apply_failed
         - after_destroy
   ```
2. Run InfraFoundry; events matching the config will be sent:
   ```bash
   infra apply --env dev
   infra drift --env prod
   ```

## Configuration Details

- **File location:** `<config-repo>/notifications.yaml` (global) and/or `<config-repo>/envs/{env}/notifications.yaml` (overrides/extends per env).
- **Schema:**
  ```yaml
  channels:
    - name: <channel-name>
      type: <slack|webhook|discord>
      enabled: true
      config:
        webhook_url: <url>        # required for all types
        username: <optional>      # slack/discord
        avatar_url: <optional>    # slack/discord
      events:  # optional filter
        - after_apply
        - apply_failed
        - drift_detected
        - after_destroy
        - policy_violation
      levels:  # optional filter
        - info
        - warning
        - error
        - critical
  ```
- **Event source:** Notification manager subscribes to the event bus; only matching `events`/`levels` are delivered.
- **Environment precedence:** `envs/{env}/notifications.yaml` overrides/augments root definitions for that environment.

## Validation and Checks

- Validate config structure:
  ```bash
  infra validate --env dev
  ```
- Send a test event by running a dry plan/apply; check target channel for delivery.
- For Slack/Discord, verify webhook URL is active and workspace permissions allow incoming webhooks.

## Examples

- **Discord channel with level filter:**
  ```yaml
  channels:
    - name: discord-alerts
      type: discord
      enabled: true
      config:
        webhook_url: https://discord.com/api/webhooks/...
      levels:
        - error
        - critical
  ```
- **Generic webhook:**
  ```yaml
  channels:
    - name: ops-webhook
      type: webhook
      enabled: true
      config:
        webhook_url: https://ops.example.com/hooks/infra
      events:
        - drift_detected
        - policy_violation
  ```
- **Environment-specific overrides (prod only):**
  ```yaml
  # envs/prod/notifications.yaml
  channels:
    - name: slack-prod
      type: slack
      enabled: true
      config:
        webhook_url: https://hooks.slack.com/services/PROD/WEBHOOK
      levels:
        - warning
        - error
        - critical
  ```

## Related Documentation

- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Configuration Guide](overview.md)
- [Architecture: Event System](../development/event-system.md)

## Troubleshooting

- **Symptom:** No messages delivered. **Fix:** Confirm webhook URL, channel `enabled: true`, and that the event/level filters match emitted events.
- **Symptom:** Wrong environment config used. **Fix:** Ensure `envs/{env}/notifications.yaml` exists and `--env` matches; remove stale global entries if overriding per env.
- **Symptom:** Payload rejected by webhook. **Fix:** Check URL validity and required formatting for the target service; regenerate webhook if revoked.

---

Last updated: 2025-12-23 14:19 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
