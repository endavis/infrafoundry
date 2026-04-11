#!/bin/bash
# AIQUM Post-Terraform Setup
#
# Installs AIQUM RPM on the Rocky 9 VM, waits for the web UI,
# then runs the initial setup wizard (FEW) via REST API.
#
# All remote commands run through the ansible jumphost since the SSH key
# for the AIQUM VM only exists there.
#
# Package variables (including secrets) are injected by InfraFoundry as:
#   INFRAFOUNDRY_PACKAGE_VARS  - JSON string of all package variables
#   INFRAFOUNDRY_VAR_<key>     - Individual variables
#
# Prerequisites:
# - Rocky 9 VM created and booted with cloud-init
# - AIQUM RPM available at a web server (set aiqum_url_base in infrafoundry.yml)
# - ONTAP cluster running and reachable
# - SSH jumphost reachable (set jumphost in infrafoundry.yml)
set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(dirname "$SCRIPT_DIR")"

# Re-execute on the jumphost if one is configured. No-op otherwise.
# See blueprints/_lib/reexec-on-jumphost.sh for behavior details.
# The file-exists check is intentional: when the reexec'd copy of this
# script runs on the jumphost, _lib/ has not been rsynced alongside, so
# the helper is absent and the source is skipped. That's the base case
# that breaks the reexec loop.
_REEXEC_HELPER="${SCRIPT_DIR}/../../_lib/reexec-on-jumphost.sh"
[ -f "${_REEXEC_HELPER}" ] && source "${_REEXEC_HELPER}"

# Read variables from INFRAFOUNDRY_PACKAGE_VARS or fall back to infrafoundry.yml
if [ -n "${INFRAFOUNDRY_PACKAGE_VARS:-}" ]; then
    eval "$(python3 -c "
import json, os
v = json.loads(os.environ['INFRAFOUNDRY_PACKAGE_VARS'])
for k, val in v.items():
    print(f'{k}={val}')
")"
else
    eval "$(python3 -c "
import sys, yaml
with open('${PACKAGE_DIR}/infrafoundry.yml') as f:
    data = yaml.safe_load(f)
v = data.get('variables', {})
for k, val in v.items():
    print(f'{k}={val}')
")"
fi

JUMPHOST="${jumphost:-}"
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
SSH_USER="${ssh_user:-ansible}"

# Build remote command helpers based on whether a jumphost is configured
if [ -n "${JUMPHOST}" ]; then
    remote_cmd() { ${SSH} ${JUMPHOST} "${SSH} ${SSH_USER}@${1} '${2}'"; }
    remote_cmd_long() { ${SSH} -o ServerAliveInterval=30 ${JUMPHOST} "${SSH} -o ServerAliveInterval=30 ${SSH_USER}@${1} '${2}'"; }
    remote_upload() { scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$1" "${JUMPHOST}:/tmp/_aiqum_upload" && ${SSH} ${JUMPHOST} "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /tmp/_aiqum_upload ${SSH_USER}@${2}:${3}"; }
else
    remote_cmd() { ${SSH} ${SSH_USER}@${1} "${2}"; }
    remote_cmd_long() { ${SSH} -o ServerAliveInterval=30 ${SSH_USER}@${1} "${2}"; }
    remote_upload() { scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$1" "${SSH_USER}@${2}:${3}"; }
fi

log "=== AIQUM Post-Terraform Setup ==="
echo "VM: ${vm_name} (${ip_address})"
if [ -n "${JUMPHOST}" ]; then
    echo "Jumphost: ${JUMPHOST}"
else
    echo "Jumphost: (direct SSH)"
fi

# --- Phase 1: Wait for VM to be reachable ---
echo ""
log "--- Phase 1: Waiting for VM to be reachable ---"
MAX_WAIT=300
ELAPSED=0
while ! remote_cmd "${ip_address}" "echo ready" &>/dev/null; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: VM not reachable after ${MAX_WAIT}s"
        exit 1
    fi
    echo "  Waiting for SSH... (${ELAPSED}s)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
echo "  VM is reachable via SSH"

# --- Phase 2: Upload and run install script ---
echo ""
log "--- Phase 2: Installing AIQUM RPM ---"

REMOTE_SCRIPT="${SCRIPT_DIR}/aiqum-install-remote.sh"
if [ ! -f "${REMOTE_SCRIPT}" ]; then
    echo "ERROR: Install script not found: ${REMOTE_SCRIPT}"
    exit 1
fi

# Step 1: Upload install script to VM
echo "  Uploading install script to VM..."
remote_upload "${REMOTE_SCRIPT}" "${ip_address}" "/tmp/aiqum-install-remote.sh"

# Step 2: Run the install script on the VM
echo "  Running install script on VM (downloading 1.9GB RPM + installing)..."
remote_cmd_long "${ip_address}" "chmod +x /tmp/aiqum-install-remote.sh && AIQUM_URL_BASE='${aiqum_url_base}' bash /tmp/aiqum-install-remote.sh"

echo "  AIQUM RPM installed successfully"

# --- Phase 3: Wait for AIQUM web UI ---
echo ""
log "--- Phase 3: Waiting for AIQUM web UI ---"
MAX_WAIT=600
ELAPSED=0
while ! curl -sk -o /dev/null -w "%{http_code}" "https://${ip_address}/" 2>/dev/null | grep -q "200\|302\|401"; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: AIQUM web UI not available after ${MAX_WAIT}s"
        exit 1
    fi
    echo "  Waiting for AIQUM web UI... (${ELAPSED}s)"
    sleep 15
    ELAPSED=$((ELAPSED + 15))
done
echo "  AIQUM web UI is available"

# --- Phase 4: Regenerate certificates ---
# The AIQUM HTTPS cert is generated at install time with CN=<short hostname>.
# The acquisition unit connects to itself via FQDN, causing host verification
# failure. Regenerate both the HTTPS cert and the client cert (used for mutual
# auth with ONTAP) so they include the FQDN.
echo ""
log "--- Phase 4: Regenerating certificates ---"

# Regenerate client certificate (used for ONTAP mutual auth / EMS)
echo "  Regenerating client certificate..."
remote_cmd "${ip_address}" "sudo /opt/netapp/ocum/scripts/clientKeyManager.sh regenerate_client_cert jboss"
echo "  Client certificate regenerated"

# Restart AIQUM services to pick up new certs
echo "  Restarting AIQUM services..."
remote_cmd "${ip_address}" "sudo systemctl restart ocie ocieau"

# Wait for web UI to come back
echo "  Waiting for AIQUM web UI to restart..."
sleep 15
ELAPSED=0
while ! curl -sk -o /dev/null -w "%{http_code}" "https://${ip_address}/" 2>/dev/null | grep -q "200\|302\|401"; do
    if [ $ELAPSED -ge 300 ]; then
        echo "ERROR: AIQUM web UI not available after restart"
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
echo "  AIQUM web UI is back"

# --- Phase 5: Run initial setup wizard (FEW) ---
echo ""
log "--- Phase 5: Running initial setup wizard ---"
python3 "${SCRIPT_DIR}/aiqum-initial-setup.py"

echo ""
log "=== AIQUM Setup Complete ==="
echo "  URL: https://${ip_address}/"
echo "  User: ${aiqum_admin_user}"
