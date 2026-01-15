# Drift Detection Guide

## Overview

Drift detection identifies discrepancies between your declared infrastructure configuration and the actual state of deployed resources. InfraFoundry provides automated drift detection to help maintain infrastructure consistency.

## Audience and Prerequisites

- **Audience:** DevOps engineers, platform teams, and infrastructure operators
- **Prerequisites:**
  - Familiarity with infrastructure as code concepts
  - Understanding of state management
  - A deployed environment to check for drift

## What is Infrastructure Drift?

Infrastructure drift occurs when the actual state of resources diverges from the declared configuration. Common causes include:

- **Manual Changes:** Direct modifications via web console or CLI
- **Auto-Scaling:** Dynamic resource creation/deletion
- **External Updates:** OS patches, security updates
- **Configuration Management:** Changes by other automation tools
- **Resource Dependencies:** Cascading changes from related resources

## Drift Detection Capabilities

InfraFoundry drift detection supports runners that implement the `DriftDetectable` protocol:

- ✅ **Terraform** - Full drift detection support via plan output parsing
- ✅ **Pulumi** - Drift detection via preview/refresh operations
- ❌ **Ansible** - Not supported (Ansible is idempotent but doesn't track state)
- ❌ **PyInfra** - Not supported

## CLI Commands

### Detect Drift

```bash
# Detect drift in all providers for an environment
infra drift detect --env dev

# Detect drift for a specific provider
infra drift detect --env dev --provider proxmox

# Verbose output showing detailed changes
infra drift detect --env dev --verbose

# Output results as JSON
infra drift detect --env dev --format json
```

### View Drift Information

```bash
# Show drift summary for environment
infra drift status --env dev

# Show drift for specific provider
infra drift status --env dev --provider opnsense

# Show historical drift detection results
infra drift history --env dev --limit 10
```

## Understanding Drift Results

### Drift Summary

When drift is detected, you'll see a summary like this:

```
Drift Detection Results for 'dev' environment:

Provider: proxmox-homelab (terraform)
  Status: DRIFT DETECTED
  Resources Added: 0
  Resources Changed: 2
  Resources Destroyed: 0
  Details:
    - vm-web-01: configuration changed (CPU count: 2 → 4)
    - vm-db-01: configuration changed (Memory: 4096MB → 8192MB)

Provider: opnsense-gateway (terraform)
  Status: NO DRIFT
  Resources: 12 unchanged
```

### Drift Types

1. **Added Resources**: Resources exist in deployed state but not in configuration
   - Usually indicates manual creation or missing config

2. **Changed Resources**: Resources exist but with different properties
   - Most common type of drift
   - Can be intentional (manual scaling) or unintentional (configuration errors)

3. **Destroyed Resources**: Resources in configuration but not in deployed state
   - May indicate manual deletion or provisioning failures

## Configuration

### Enable Drift Detection

Configure drift detection in your environment settings:

```yaml
# envs/dev/settings.yaml
drift_detection:
  enabled: true
  check_on_plan: true          # Auto-detect drift during plan operations
  fail_on_drift: false          # Whether to fail if drift is detected
  ignore_resources: []          # Resources to exclude from drift checking
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable drift detection |
| `check_on_plan` | bool | `true` | Automatically check for drift during plan operations |
| `fail_on_drift` | bool | `false` | Exit with error if drift is detected |
| `ignore_resources` | list | `[]` | Resource patterns to ignore (regex) |

### Ignoring Expected Drift

Some drift is expected and can be safely ignored:

```yaml
# envs/prod/settings.yaml
drift_detection:
  enabled: true
  ignore_resources:
    - "aws_autoscaling_group.*"      # Ignore auto-scaling changes
    - ".*_security_patch"             # Ignore automatic security patches
    - "aws_instance.*\.tags"          # Ignore tag changes
```

## Common Workflows

### Daily Drift Monitoring

Run drift detection on a schedule:

```bash
# Cron entry (daily at 9 AM)
0 9 * * * cd /path/to/infra && infra drift detect --env prod --notify
```

### Pre-Apply Drift Check

Always check for drift before applying changes:

```bash
# Check for drift
infra drift detect --env prod

# If no drift, apply changes
infra apply --env prod

# If drift exists, review and decide:
# Option 1: Accept drift and apply anyway
infra apply --env prod --accept-drift

# Option 2: Remediate drift first
infra drift remediate --env prod --auto-approve
infra apply --env prod
```

### CI/CD Integration

Add drift detection to your CI/CD pipeline:

```yaml
# .gitlab-ci.yml
drift-check:
  stage: validate
  script:
    - infra drift detect --env $CI_ENVIRONMENT_NAME
    - infra drift status --env $CI_ENVIRONMENT_NAME --format json > drift-report.json
  artifacts:
    reports:
      drift: drift-report.json
  only:
    - schedules
```

## Troubleshooting

### Issue: "Provider does not support drift detection"

**Symptoms:**
- Error message when running drift detect
- Provider skipped during drift detection

**Cause:** Provider's runner doesn't implement the `DriftDetectable` protocol

**Solutions:**
1. Only Terraform and Pulumi runners support drift detection
2. For Ansible/PyInfra, use manual comparison or state tracking
3. Consider implementing drift detection for custom runners

### Issue: "State file not found"

**Symptoms:**
- Error: "Cannot detect drift: no state file"
- Drift detection fails immediately

**Cause:** Provider has never been applied or state file is missing

**Solutions:**
1. Run `infra apply --env <env>` first to create state
2. Verify state file exists in `generated/{env}/{runner}/{provider}/`
3. Check state backend configuration if using remote state

### Issue: False positive drift detected

**Symptoms:**
- Drift reported but configuration hasn't changed
- Same drift detected repeatedly

**Causes:**
- Dynamic resource properties (timestamps, auto-generated values)
- Computed fields that change on every read
- Time-based resources (expiration dates, etc.)

**Solutions:**
1. Add resources to `ignore_resources` list
2. Use lifecycle rules in provider configuration
3. Update configuration to match actual deployed state

### Issue: Drift not detected for manual changes

**Symptoms:**
- Manual changes made but drift detection shows no drift
- State seems out of sync

**Cause:** State hasn't been refreshed

**Solutions:**
```bash
# Force state refresh before drift detection
infra drift detect --env dev --refresh

# Or manually refresh state first
infra state refresh --env dev
infra drift detect --env dev
```

## Best Practices

### 1. Regular Drift Checks

Run drift detection on a schedule:
- **Development:** Daily or before deployments
- **Staging:** Daily
- **Production:** Multiple times per day

### 2. Drift Alerts

Configure notifications for drift detection:

```yaml
# notifications.yaml
notifications:
  - type: slack
    events:
      - drift_detected
    webhook_url: https://hooks.slack.com/services/...
    channels:
      - "#infrastructure-alerts"
```

### 3. Drift Categories

Classify drift to prioritize response:
- **Critical:** Security groups, IAM policies, encryption settings
- **High:** Resource configurations, networking changes
- **Medium:** Tags, metadata, non-critical attributes
- **Low:** Expected drift (auto-scaling, patches)

### 4. Drift Review Process

1. **Detect** drift regularly
2. **Classify** drift by severity and impact
3. **Investigate** unexpected drift
4. **Remediate** or accept drift based on classification
5. **Document** accepted drift in `ignore_resources`

### 5. Prevent Drift

- Use IAM policies to restrict manual changes
- Enable CloudTrail/audit logging for tracking
- Use read-only credentials for drift detection
- Implement approval workflows for manual changes

## Integration with Drift Remediation

Drift detection is the first step in drift remediation:

```bash
# Step 1: Detect drift
infra drift detect --env dev

# Step 2: Review drift
infra drift status --env dev

# Step 3: Remediate if within thresholds
infra drift remediate --env dev --auto-approve
```

See [Drift Remediation Guide](drift-remediation.md) for automated remediation.

## Related Documentation

- [Drift Remediation](drift-remediation.md) - Automated drift remediation
- [State Management](../architecture/state-management.md) - Understanding state tracking
- [Notifications](../configuration/notifications.md) - Setting up drift alerts
- [Runner Protocols](../development/runner-protocol-quick-reference.md) - DriftDetectable protocol

---

**Last Updated:** 2025-12-29
