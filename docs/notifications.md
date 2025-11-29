# Notifications Guide

**Version:** 1.0
**Last Updated:** 2025-11-29

## Overview

InfraFoundry includes a powerful notification system that allows you to receive real-time alerts about infrastructure events via Slack, webhooks, Discord, or custom channels. The notification system integrates with the event bus and can be configured to send notifications for specific events, environments, or severity levels.

## Quick Start

### 1. Create notifications.yaml

```bash
# In your config repository root or environment directory
touch notifications.yaml
```

### 2. Configure Slack Notifications

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

### 3. Test Notifications

```bash
# Notifications will be sent during any deployment
infra apply --env dev

# Or test drift detection notifications
infra drift --env prod
```

## Configuration

### File Location

Notifications are configured in `notifications.yaml` in:
- Config repository root: `<config-repo>/notifications.yaml`
- Environment-specific: `<config-repo>/envs/<env>/notifications.yaml`

Environment-specific configurations override global ones.

### Configuration Structure

```yaml
channels:
  - name: <channel-name>
    type: <slack|webhook|discord>
    enabled: <true|false>
    config:
      <channel-specific-config>
    events:  # Optional: filter by events
      - <event-name>
    levels:  # Optional: filter by severity
      - <info|warning|error|critical>
```

## Notification Channels

### Slack

Send notifications to Slack using incoming webhooks.

**Configuration:**
```yaml
channels:
  - name: slack-alerts
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
    events:
      - after_apply
      - apply_failed
      - drift_detected
```

**Setup Steps:**

1. **Create Slack App:**
   - Go to https://api.slack.com/apps
   - Click "Create New App" → "From scratch"
   - Name it "InfraFoundry" and select your workspace

2. **Enable Incoming Webhooks:**
   - Navigate to "Incoming Webhooks"
   - Toggle "Activate Incoming Webhooks" to ON
   - Click "Add New Webhook to Workspace"
   - Select channel and authorize

3. **Copy Webhook URL:**
   - Copy the webhook URL (starts with `https://hooks.slack.com/...`)
   - Add to `notifications.yaml`

**Message Format:**

Slack messages include:
- Event header with emoji
- Environment name
- Event type
- Event-specific details (errors, drift changes, policy violations)
- Formatted using Slack Block Kit

**Example Message:**
```
✅ InfraFoundry: after_apply
━━━━━━━━━━━━━━━━━━━━━━━
Environment: prod
Event: after_apply
Resources: 5 created, 3 updated
━━━━━━━━━━━━━━━━━━━━━━━
```

### Webhook

Send JSON payloads to custom webhook endpoints.

**Configuration:**
```yaml
channels:
  - name: webhook-general
    type: webhook
    enabled: true
    config:
      url: https://your-webhook-endpoint.com/infrafoundry
      headers:  # Optional
        Authorization: Bearer your-api-token
        X-Custom-Header: custom-value
      method: POST  # Optional, defaults to POST
      timeout: 10  # Optional, seconds, defaults to 10
```

**Payload Format:**

```json
{
  "event_type": "after_apply",
  "environment": "prod",
  "timestamp": "2025-11-29T10:30:00Z",
  "data": {
    "deployment_id": 42,
    "user": "alice",
    "resources_created": 5,
    "resources_updated": 3
  }
}
```

**Use Cases:**
- Integration with monitoring systems (Datadog, New Relic)
- Custom alerting platforms
- Ticketing systems (Jira, ServiceNow)
- Audit logging systems
- CI/CD pipeline triggers

**Example: Datadog Integration**

```yaml
channels:
  - name: datadog-events
    type: webhook
    enabled: true
    config:
      url: https://api.datadoghq.com/api/v1/events
      headers:
        DD-API-KEY: ${DATADOG_API_KEY}
        Content-Type: application/json
    events:
      - after_apply
      - apply_failed
```

### Discord

Send notifications to Discord channels using webhooks.

**Configuration:**
```yaml
channels:
  - name: discord-devops
    type: webhook  # Discord uses webhook type
    enabled: true
    config:
      url: https://discord.com/api/webhooks/123456789/abcdefghijklmnopqrstuvwxyz
```

**Setup Steps:**

1. **Create Webhook in Discord:**
   - Open Discord channel settings
   - Go to "Integrations" → "Webhooks"
   - Click "New Webhook"
   - Name it "InfraFoundry"
   - Copy webhook URL

2. **Format for Discord (optional):**

Webhook payload supports Discord's embed format. Customize in code or use standard webhook format.

## Event Types

### Deployment Lifecycle

```yaml
events:
  # Planning
  - before_plan
  - after_plan
  - plan_failed

  # Apply
  - before_apply
  - after_apply
  - apply_failed

  # Destroy
  - before_destroy
  - after_destroy
  - destroy_failed
```

### Resource Events

```yaml
events:
  - resource_planned
  - resource_creating
  - resource_created
  - resource_deleting
  - resource_deleted
```

### Advanced Events

```yaml
events:
  # Drift Detection
  - drift_check_started
  - drift_detected
  - drift_check_completed

  # Policy Enforcement
  - policy_check_started
  - policy_violation
  - policy_check_failed
  - policy_check_completed

  # State Management
  - rollback_started
  - rollback_completed
  - rollback_failed
```

## Filtering

### By Event

Only send notifications for specific events:

```yaml
channels:
  - name: slack-critical
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/...
    events:
      - apply_failed
      - destroy_failed
      - drift_detected
      - policy_check_failed
```

### By Severity Level

Filter by notification level (requires event data to include level):

```yaml
channels:
  - name: slack-errors-only
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/...
    levels:
      - error
      - critical
```

### Multiple Channels

Send different events to different channels:

```yaml
channels:
  # Critical alerts to on-call channel
  - name: slack-oncall
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../oncall
    events:
      - apply_failed
      - destroy_failed

  # All deployments to devops channel
  - name: slack-devops
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../devops
    events:
      - before_apply
      - after_apply
      - before_destroy
      - after_destroy

  # Policy violations to security channel
  - name: slack-security
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../security
    events:
      - policy_violation
      - policy_check_failed
```

## Environment-Specific Notifications

### Global Configuration

```yaml
# <config-repo>/notifications.yaml
channels:
  - name: slack-all-envs
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../all-envs
```

### Override Per Environment

```yaml
# <config-repo>/envs/prod/notifications.yaml
channels:
  - name: slack-prod
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../prod-only
    events:
      - apply_failed
      - drift_detected
```

## Common Patterns

### Pattern 1: Different Channels for Different Environments

```yaml
# <config-repo>/envs/dev/notifications.yaml
channels:
  - name: slack-dev
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../dev-channel

# <config-repo>/envs/prod/notifications.yaml
channels:
  - name: slack-prod
    type: slack
    enabled: true
    config:
      webhook_url: https://hooks.slack.com/services/.../prod-channel

  - name: pagerduty-prod
    type: webhook
    enabled: true
    config:
      url: https://events.pagerduty.com/v2/enqueue
      headers:
        Authorization: Token token=${PAGERDUTY_TOKEN}
    events:
      - apply_failed
      - destroy_failed
```

### Pattern 2: Comprehensive Monitoring

```yaml
channels:
  # Slack for team visibility
  - name: slack-deployments
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_WEBHOOK_URL}
    events:
      - after_apply
      - apply_failed

  # Datadog for metrics
  - name: datadog-events
    type: webhook
    enabled: true
    config:
      url: https://api.datadoghq.com/api/v1/events
      headers:
        DD-API-KEY: ${DATADOG_API_KEY}

  # PagerDuty for incidents
  - name: pagerduty-critical
    type: webhook
    enabled: true
    config:
      url: https://events.pagerduty.com/v2/enqueue
      headers:
        Authorization: Token token=${PAGERDUTY_TOKEN}
    events:
      - apply_failed
      - drift_detected
```

### Pattern 3: Audit Trail

```yaml
channels:
  # Webhook to audit logging system
  - name: audit-log
    type: webhook
    enabled: true
    config:
      url: https://audit-system.company.com/infrafoundry
      headers:
        Authorization: Bearer ${AUDIT_TOKEN}
    # All events for complete audit trail
    # events: omitted = all events
```

## Security Considerations

### 1. Protect Webhook URLs

**DO NOT commit webhook URLs to git:**

```yaml
# Bad - hardcoded secret
config:
  webhook_url: https://hooks.slack.com/services/T00/B00/XXXX

# Good - environment variable
config:
  webhook_url: ${SLACK_WEBHOOK_URL}
```

**Set environment variables:**
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DATADOG_API_KEY="..."
```

### 2. Use Per-Environment Secrets

```yaml
# envs/dev/notifications.yaml
channels:
  - name: slack-dev
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_WEBHOOK_DEV}  # Different webhook for dev

# envs/prod/notifications.yaml
channels:
  - name: slack-prod
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_WEBHOOK_PROD}  # Separate webhook for prod
```

### 3. Rate Limiting

Configure appropriate rate limits to avoid overwhelming notification channels:

```yaml
channels:
  - name: slack-alerts
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_WEBHOOK_URL}
    # Only critical events to avoid spam
    events:
      - apply_failed
      - drift_detected
      - policy_check_failed
```

## Troubleshooting

### Notifications Not Sending

**Check configuration:**
```bash
# Verify notifications.yaml exists and is valid
cat notifications.yaml

# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('notifications.yaml'))"
```

**Enable debug logging:**
```bash
export INFRAFOUNDRY_LOG_LEVEL=DEBUG
infra apply --env dev
```

**Common Issues:**

1. **Invalid webhook URL**
   - Verify URL format
   - Test webhook manually with curl:
   ```bash
   curl -X POST https://hooks.slack.com/services/... \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test message"}'
   ```

2. **Channel disabled**
   - Ensure `enabled: true` in configuration

3. **Event filtering**
   - Check events list includes the event you expect
   - Remove events filter to test (omit = all events)

4. **Environment variables not set**
   ```bash
   # Check if variables are set
   echo $SLACK_WEBHOOK_URL

   # Set if missing
   export SLACK_WEBHOOK_URL="https://..."
   ```

### Testing Notifications

**Test with specific event:**
```bash
# Trigger after_apply notification
infra apply --env dev

# Trigger drift notification
infra drift --env prod

# Trigger policy notification
infra validate --env dev
```

**Manual test (for development):**

```python
# test_notification.py
from infrafoundry.core.events import EventManager, EventType, Event

event_manager = EventManager()
event_manager.emit(Event(
    event_type=EventType.AFTER_APPLY,
    environment="test",
    data={"deployment_id": 999, "resources_created": 5}
))
```

## Example Configurations

### Minimal (Slack Only)

```yaml
channels:
  - name: slack
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_WEBHOOK_URL}
```

### Production (Multi-Channel)

```yaml
channels:
  # Team notifications
  - name: slack-team
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_TEAM_WEBHOOK}
    events:
      - after_apply
      - after_destroy

  # Critical alerts
  - name: slack-oncall
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_ONCALL_WEBHOOK}
    events:
      - apply_failed
      - destroy_failed
      - drift_detected

  # Monitoring integration
  - name: datadog
    type: webhook
    enabled: true
    config:
      url: https://api.datadoghq.com/api/v1/events
      headers:
        DD-API-KEY: ${DATADOG_API_KEY}

  # Incident management
  - name: pagerduty
    type: webhook
    enabled: true
    config:
      url: https://events.pagerduty.com/v2/enqueue
      headers:
        Authorization: Token token=${PAGERDUTY_TOKEN}
    events:
      - apply_failed
      - destroy_failed
```

### Enterprise (Complete Setup)

```yaml
channels:
  # Real-time team chat
  - name: slack-devops
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_DEVOPS_WEBHOOK}
    events:
      - before_apply
      - after_apply
      - before_destroy
      - after_destroy
      - drift_detected

  # Critical incidents
  - name: pagerduty-critical
    type: webhook
    enabled: true
    config:
      url: https://events.pagerduty.com/v2/enqueue
      headers:
        Authorization: Token token=${PAGERDUTY_TOKEN}
    events:
      - apply_failed
      - destroy_failed

  # Security/compliance alerts
  - name: slack-security
    type: slack
    enabled: true
    config:
      webhook_url: ${SLACK_SECURITY_WEBHOOK}
    events:
      - policy_violation
      - policy_check_failed

  # Metrics and dashboards
  - name: datadog-metrics
    type: webhook
    enabled: true
    config:
      url: https://api.datadoghq.com/api/v1/events
      headers:
        DD-API-KEY: ${DATADOG_API_KEY}

  # Audit logging
  - name: audit-trail
    type: webhook
    enabled: true
    config:
      url: https://audit.company.com/events
      headers:
        Authorization: Bearer ${AUDIT_TOKEN}
        X-Service: infrafoundry
```

## Implementing Custom Notifiers

See [Event System Guide](development/event-system.md) for details on creating custom notification channels.

**Quick example:**

```python
# src/infrafoundry/core/notifications/notifiers/email.py
from infrafoundry.core.notifications.notifiers.base_notifier import Notifier

class EmailNotifier(Notifier):
    """Send notifications via email."""

    def send(self, event_type: str, environment: str, data: dict) -> bool:
        """Send email notification."""
        smtp_server = self.config.get("smtp_server")
        to_addresses = self.config.get("to")

        # Implement email sending logic
        send_email(
            to=to_addresses,
            subject=f"[InfraFoundry] {event_type} - {environment}",
            body=self._format_message(event_type, environment, data)
        )
        return True
```

## References

- [Event System Guide](development/event-system.md) - Understanding events and custom handlers
- [CLI Reference](CLI_REFERENCE.md) - Commands that trigger notifications
- [Configuration Guide](configuration.md) - General configuration patterns
- [Example Configuration](../example-config/notifications.yaml) - Complete example
