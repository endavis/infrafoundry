# Tailscale OAuth Authentication Guide

This guide explains how to use OAuth authentication with the Tailscale exit node role instead of traditional auth keys.

## Why Use OAuth?

### Benefits

✅ **More Secure**
- Short-lived tokens instead of long-lived keys
- OAuth tokens expire and rotate automatically
- Less risk if credentials are accidentally exposed

✅ **Better Audit Trail**
- Each device authenticated with specific user identity
- Clear attribution in Tailscale logs
- Easy to track who deployed what

✅ **Granular Revocation**
- Revoke individual devices without affecting others
- No need to rotate shared auth keys
- More control over access

✅ **Compliance Friendly**
- Meets security requirements for many organizations
- Better separation of duties
- Audit-friendly authentication

### Tradeoffs

⚠️ **Requires User Interaction**
- Ansible playbook pauses for user to approve
- Not suitable for fully automated CI/CD pipelines
- Someone needs to click the OAuth approval link

⚠️ **Slightly More Complex Setup**
- Need to create OAuth client in Tailscale admin
- Two credentials (client ID + secret) instead of one key
- Additional configuration in playbooks

## When to Use Each Method

### Use OAuth When:
- 👤 Deploying to personal homelab
- 🔐 Security is top priority
- 👥 Multiple people manage infrastructure
- 📊 Need detailed audit trails
- 🖥️ Interactive deployments are acceptable

### Use Auth Keys When:
- 🤖 Fully automated CI/CD pipelines
- 🏭 Production deployments without human intervention
- 📦 Provisioning many nodes at once
- ⏱️ Speed is more important than enhanced security
- 🔄 Infrastructure is frequently rebuilt

## Setting Up OAuth

### Step 1: Create OAuth Client

1. Go to https://login.tailscale.com/admin/settings/oauth
2. Click "Generate OAuth client"
3. Fill in details:
   - **Description**: "InfraFoundry Deployments" (or your preferred name)
   - **Client ID**: (automatically generated, copy this)
   - **Client Secret**: (shown once, copy immediately!)

### Step 2: Store Credentials Securely

Add OAuth credentials to your environment's `settings.yaml`:

```yaml
# envs/prod/settings.yaml (add to provider_settings or ansible_vars)
ansible_vars:
  vault_tailscale_oauth_client_id: "kxxxxxxxxxxxxxx"
  vault_tailscale_oauth_client_secret: "tskey-client-kxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Encrypt the file if not already encrypted:

```bash
sops --encrypt --in-place envs/prod/settings.yaml
```

### Step 3: Configure VM with OAuth

In your VM configuration (e.g., `envs/prod/resources/vms.yaml`):

```yaml
vms:
  - name: exit-node-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 2048
    ipconfig: ip=192.168.100.20/24,gw=192.168.100.1

    ansible_roles:
      - tailscale-exit-node

    ansible_vars:
      # Specify OAuth authentication
      tailscale_auth_method: "oauth"
      tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
      tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"

      # Optional: Increase timeout if you need more time to approve
      tailscale_oauth_timeout: 600  # 10 minutes
```

### Step 4: Deploy with OAuth

```bash
# Start deployment
infra apply --env prod
```

**What happens during deployment:**

1. Ansible provisions the VM with Terraform
2. Ansible installs and configures Tailscale
3. Tailscale starts OAuth authentication flow
4. **Playbook pauses and displays:**
   ```
   ========================================
   Tailscale OAuth Authentication Required
   ========================================

   Please authenticate by visiting:
   https://login.tailscale.com/a/xxxxxxxx

   Waiting up to 300 seconds for authentication...
   ========================================
   ```
5. You visit the URL and approve the device
6. Tailscale completes authentication
7. Playbook continues automatically

### Step 5: Approve the Device

When prompted:

1. Click the OAuth URL shown in the Ansible output
2. Browser opens to Tailscale admin console
3. You'll see: "Approve device: exit-node-01"
4. Review the details
5. Click "Approve"
6. Done! Return to terminal to see deployment continue

## Configuration Examples

### Basic OAuth Exit Node

```yaml
ansible_vars:
  tailscale_auth_method: "oauth"
  tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
  tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
```

### OAuth with Subnet Routes

```yaml
ansible_vars:
  tailscale_auth_method: "oauth"
  tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
  tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
  tailscale_advertise_routes:
    - "192.168.100.0/24"
    - "10.0.0.0/8"
```

### OAuth with Extended Timeout

```yaml
ansible_vars:
  tailscale_auth_method: "oauth"
  tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
  tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
  tailscale_oauth_timeout: 900  # 15 minutes - useful if you're busy
```

### Mix and Match: OAuth for Some, Auth Key for Others

You can use different auth methods for different VMs:

```yaml
vms:
  # Production exit node - use OAuth for security
  - name: exit-prod-01
    # ... VM config ...
    ansible_vars:
      tailscale_auth_method: "oauth"
      tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
      tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"

  # Dev/test nodes - use auth key for automation
  - name: exit-dev-01
    # ... VM config ...
    ansible_vars:
      tailscale_auth_method: "authkey"
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

## Troubleshooting

### OAuth URL Not Displayed

**Problem**: Playbook runs but doesn't show OAuth URL

**Solution**:
- Check that `tailscale_auth_method: "oauth"` is set
- Verify OAuth credentials are correct
- Check Ansible output for errors (may be hidden)

```bash
# Run with verbose output
infra apply --env prod -v
```

### OAuth Timeout

**Problem**: "OAuth authentication timed out"

**Solution**:
- Increase timeout: `tailscale_oauth_timeout: 900`
- Ensure you have the admin console open and ready
- Check if you missed the OAuth URL in output

### OAuth Approval Page Not Loading

**Problem**: OAuth URL gives error or doesn't load

**Solutions**:
- Verify OAuth client hasn't been deleted
- Check OAuth client secret is correct
- Ensure your Tailscale account is in good standing
- Try regenerating OAuth client

### Already Authenticated

**Problem**: Playbook skips OAuth step

**Solution**: This is normal! If the node is already authenticated, OAuth isn't needed. The role detects this and skips re-authentication.

To force re-authentication:
```bash
# SSH to the VM
ssh ubuntu@exit-node-01

# Log out of Tailscale
sudo tailscale logout

# Re-run playbook
```

## Security Best Practices

### OAuth Client Management

1. **Separate Clients for Different Purposes**
   ```yaml
   # Prod
   vault_tailscale_oauth_client_id_prod: "client-prod-xxxxx"

   # Dev
   vault_tailscale_oauth_client_id_dev: "client-dev-xxxxx"
   ```

2. **Rotate OAuth Secrets Regularly**
   - Delete old OAuth clients
   - Generate new ones
   - Update secrets file

3. **Limit OAuth Client Permissions**
   - If Tailscale adds OAuth scopes in future, use least privilege
   - Review OAuth client access in admin console

### Storing Credentials

Always use SOPS encryption:

```bash
# Check file is encrypted
file envs/prod/settings.yaml
# Should show: ASCII text (encrypted with SOPS)

# Not encrypted? Fix it:
sops --encrypt --in-place envs/prod/settings.yaml
```

### Audit Trail

OAuth provides better audit trails:

1. Go to https://login.tailscale.com/admin/machines
2. Click on your exit node
3. View authentication history
4. See which user/OAuth client authenticated it

## Migration Guide

### From Auth Key to OAuth

Already using auth keys? Here's how to migrate:

1. **Generate OAuth credentials** (see Step 1 above)

2. **Update your secrets file**:
   ```yaml
   # Keep existing auth key for backwards compatibility
   vault_tailscale_auth_key: "tskey-auth-xxxxx"

   # Add new OAuth credentials
   vault_tailscale_oauth_client_id: "kxxxxx"
   vault_tailscale_oauth_client_secret: "tskey-client-xxxxx"
   ```

3. **Update VM configurations** (one at a time):
   ```yaml
   ansible_vars:
     # Old way
     # tailscale_auth_key: "{{ vault_tailscale_auth_key }}"

     # New way
     tailscale_auth_method: "oauth"
     tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
     tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
   ```

4. **Re-deploy nodes gradually**:
   ```bash
   # Logout existing auth
   ssh exit-node-01 sudo tailscale logout

   # Re-run with OAuth
   infra apply --env prod
   ```

5. **Verify in admin console** that nodes are using OAuth

6. **Revoke old auth keys** once migration is complete

## FAQ

**Q: Can I use OAuth in CI/CD?**
A: Not recommended. OAuth requires user interaction, which breaks automation. Use auth keys for CI/CD.

**Q: How long do OAuth tokens last?**
A: OAuth tokens are short-lived and managed automatically by Tailscale. You don't need to worry about rotation.

**Q: Can I use the same OAuth client for multiple nodes?**
A: Yes! One OAuth client can authenticate multiple devices. Each device gets its own approval.

**Q: What if I lose the OAuth client secret?**
A: Generate a new OAuth client. The secret is only shown once and cannot be recovered.

**Q: Does OAuth work with Ubuntu Core?**
A: Yes! OAuth works with both regular Linux and immutable systems like Ubuntu Core.

**Q: Can I automate OAuth approval?**
A: Not really - that would defeat the purpose of interactive OAuth. For automation, use auth keys.

**Q: Is OAuth more expensive?**
A: No, OAuth is available on all Tailscale plans at no extra cost.

## References

- [Tailscale OAuth Clients](https://tailscale.com/kb/1215/oauth-clients/)
- [Tailscale Authentication](https://tailscale.com/kb/1085/auth-keys/)
- [Security Best Practices](https://tailscale.com/kb/1018/acls/)
- [Role README](README.md)
- [Quick Start Guide](QUICKSTART.md)
