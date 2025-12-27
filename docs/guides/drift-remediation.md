# Automated Drift Remediation Guide

## Overview

InfraFoundry provides automated drift remediation to detect and automatically fix infrastructure drift when changes are within configured safety thresholds. This feature helps maintain infrastructure state consistency without manual intervention.

## Audience and Prerequisites

- **Audience:** DevOps engineers, platform teams, and infrastructure operators
- **Prerequisites:**
  - Familiarity with drift detection concepts
  - Understanding of infrastructure as code principles
  - Access to environment configuration files

## When to Use Drift Remediation

Use automated drift remediation when:
- You want to automatically fix small, expected drift (e.g., automatic patches)
- Changes are predictable and within safety limits
- You need to maintain infrastructure consistency across environments
- Manual intervention for small changes is inefficient

**Do NOT use** for:
- Large-scale infrastructure changes
- Production environments without proper testing
- Destructive operations (unless carefully configured)
- Changes that require manual review

## Configuration

### Environment Settings

Add drift remediation configuration to your environment's `settings.yaml`:

```yaml
# envs/dev/settings.yaml
drift_remediation:
  enabled: true
  check_interval_minutes: 60
  auto_apply_threshold: 5        # Max total changes to auto-apply
  max_to_add: 3                  # Max resources to add
  max_to_change: 3               # Max resources to change
  max_to_destroy: 0              # Max resources to destroy (0 = never)
  notify_on_drift: true          # Emit events when drift detected
  notify_on_remediation: true    # Emit events when remediated
  dry_run: false                 # If true, detect but never apply
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable automated drift remediation |
| `check_interval_minutes` | int | `60` | How often to check for drift (for scheduled jobs) |
| `auto_apply_threshold` | int | `5` | Maximum total changes to auto-apply (0 = disabled) |
| `max_to_add` | int | `3` | Maximum resources to add automatically |
| `max_to_change` | int | `3` | Maximum resources to change automatically |
| `max_to_destroy` | int | `0` | Maximum resources to destroy (0 = never destroy) |
| `notify_on_drift` | bool | `true` | Emit events when drift is detected |
| `notify_on_remediation` | bool | `true` | Emit events when remediation is applied |
| `dry_run` | bool | `false` | Detect drift but never auto-apply |

## CLI Commands

### Detect Drift

```bash
# Detect drift without remediation
infra drift detect --env dev
```

### Remediate Drift

```bash
# Dry-run: detect and show what would be remediated
infra drift remediate --env dev --dry-run

# Auto-remediate if within configured thresholds
infra drift remediate --env dev --auto-approve

# Override max changes threshold for this run
infra drift remediate --env dev --auto-approve --max-changes 10

# Set custom thresholds for different operations
infra drift remediate --env dev --auto-approve \
  --max-add 5 \
  --max-change 3 \
  --max-destroy 0
```

### View Remediation History

```bash
# Show last 10 remediation entries
infra drift history

# Show last 20 entries for dev environment
infra drift history --env dev --limit 20

# Show all recent remediation attempts
infra drift history --limit 50
```

## Safety Features

### Threshold-Based Decision Making

Drift remediation uses multiple thresholds to ensure safety:

1. **Total Changes Threshold**: Maximum combined changes (add + change + destroy)
2. **Per-Operation Thresholds**: Separate limits for add, change, and destroy operations
3. **Destroy Protection**: Default is 0 (never auto-destroy) for safety

**Example:**
```yaml
auto_apply_threshold: 10  # Total changes
max_to_add: 5             # Can add up to 5 resources
max_to_change: 5          # Can change up to 5 resources
max_to_destroy: 0         # Never destroy automatically
```

With this configuration:
- ✅ 3 adds, 2 changes → Auto-applied (5 total, within limits)
- ✅ 5 adds, 0 changes → Auto-applied (5 total, within limits)
- ❌ 6 adds, 0 changes → NOT auto-applied (exceeds max_to_add)
- ❌ 3 adds, 3 changes, 1 destroy → NOT auto-applied (has destroy)
- ❌ 6 adds, 5 changes → NOT auto-applied (11 total, exceeds threshold)

### History Tracking

All remediation actions are tracked in `.drift_history/` with:
- Timestamp of remediation attempt
- Environment name
- Drift detected (yes/no)
- Auto-applied (yes/no)
- Reason for decision
- Full results

### Dry-Run Mode

Always test with `--dry-run` first:
```bash
# See what would be remediated without applying
infra drift remediate --env dev --dry-run --auto-approve
```

### Event Notifications

Drift remediation emits events for:
- Drift check started
- Drift detected
- Remediation apply started (before_apply)
- Remediation completed (after_apply)

Configure notification handlers in `notifications.yaml` to get alerts.

## Common Workflows

### Development Environment Auto-Remediation

For development environments where small drift is acceptable:

```yaml
# envs/dev/settings.yaml
drift_remediation:
  enabled: true
  auto_apply_threshold: 10
  max_to_add: 5
  max_to_change: 5
  max_to_destroy: 2  # Allow some cleanup
  dry_run: false
```

### Production Environment (Conservative)

For production, be more conservative:

```yaml
# envs/prod/settings.yaml
drift_remediation:
  enabled: true
  auto_apply_threshold: 3
  max_to_add: 2
  max_to_change: 1
  max_to_destroy: 0  # NEVER auto-destroy in production
  dry_run: false
```

### Scheduled Drift Checks

Use cron or systemd timers to run periodic checks:

```bash
# Example cron entry (every hour)
0 * * * * cd /path/to/infra && infra drift remediate --env dev --auto-approve
```

### Manual Review Workflow

1. Run drift detection:
   ```bash
   infra drift detect --env prod
   ```

2. If drift found, simulate remediation:
   ```bash
   infra drift remediate --env prod --dry-run --auto-approve
   ```

3. Review the decision and apply if safe:
   ```bash
   # If within thresholds, apply
   infra drift remediate --env prod --auto-approve

   # Or manually apply
   infra apply --env prod
   ```

4. Check history:
   ```bash
   infra drift history --env prod --limit 5
   ```

## Troubleshooting

### Issue: Drift remediation not auto-applying

**Symptoms:**
- Drift detected but not auto-applied
- Reason: "Drift remediation is disabled"

**Solutions:**
1. Check `drift_remediation.enabled` is `true` in settings.yaml
2. Use `--auto-approve` flag if not configured
3. Verify thresholds are not set to 0

### Issue: Changes exceed threshold

**Symptoms:**
- Drift detected but not auto-applied
- Reason: "Total changes (X) exceeds threshold (Y)"

**Solutions:**
1. Review the drift to ensure it's expected
2. Increase thresholds if appropriate:
   ```bash
   infra drift remediate --env dev --auto-approve --max-changes 15
   ```
3. Or manually apply:
   ```bash
   infra apply --env dev
   ```

### Issue: Won't remediate destroy operations

**Symptoms:**
- Drift detected but not auto-applied
- Reason: "Resources to destroy (X) exceeds threshold (0)"

**Solutions:**
1. This is intentional - destroys are dangerous
2. Review the resources being destroyed
3. Manually apply if safe:
   ```bash
   infra apply --env dev
   ```
4. Only increase `max_to_destroy` if you're certain it's safe

### Issue: No history files created

**Symptoms:**
- `infra drift history` shows no entries
- No files in `.drift_history/`

**Solutions:**
1. Check that remediation has been run at least once
2. Verify write permissions on `.drift_history/` directory
3. Check for errors in the command output

## Best Practices

### 1. Start with Dry-Run

Always test in dry-run mode first:
```yaml
drift_remediation:
  enabled: true
  dry_run: true  # Start here
```

### 2. Progressive Thresholds

Use conservative thresholds initially, then increase based on experience:
```yaml
# Week 1: Very conservative
auto_apply_threshold: 2
max_to_add: 1
max_to_change: 1
max_to_destroy: 0

# Week 2-4: Monitor and adjust
auto_apply_threshold: 5
max_to_add: 3
max_to_change: 3
max_to_destroy: 0

# Production-ready
auto_apply_threshold: 10
max_to_add: 5
max_to_change: 5
max_to_destroy: 0  # Still never auto-destroy
```

### 3. Environment-Specific Configuration

Use different thresholds for different environments:
- **Dev**: More permissive (faster iteration)
- **Staging**: Moderate (balance safety/speed)
- **Production**: Very conservative (safety first)

### 4. Monitor History

Regularly review remediation history:
```bash
# Weekly review
infra drift history --limit 50 > weekly_drift_report.txt
```

### 5. Combine with Notifications

Configure notifications for drift events:
```yaml
# notifications.yaml
notifications:
  - type: email
    events:
      - drift_detected
      - before_apply
      - after_apply
    recipients:
      - devops@example.com
```

### 6. Test Before Scheduling

Before setting up automated schedules:
1. Test manually multiple times
2. Review history for patterns
3. Adjust thresholds based on actual drift
4. Then enable scheduled automation

## Security Considerations

### 1. Never Auto-Destroy by Default

Always keep `max_to_destroy: 0` unless you have a very specific use case.

### 2. Review Remediation History

Regularly audit what's being auto-applied:
```bash
infra drift history --env prod --limit 100
```

### 3. Use Dry-Run in Production

Consider keeping production in dry-run mode and only auto-remediating in non-prod:
```yaml
# envs/prod/settings.yaml
drift_remediation:
  enabled: true
  dry_run: true  # Only detect, never apply
  notify_on_drift: true  # Get alerts for manual review
```

### 4. Limit Auto-Apply Scope

Use resource filters if you only want to auto-remediate specific resources:
```bash
# Only remediate specific resource types (future enhancement)
infra drift remediate --env dev --auto-approve --resources vm-*
```

## Related Documentation

- [Drift Detection](drift-detection.md)
- [State Management](../architecture/state-management.md)
- [Notifications Configuration](../configuration/notifications.md)
- [Event System](../architecture/events.md)

---

Last updated: 2025-12-27
