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
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
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

# SCRIPT_DIR points at this blueprint's scripts/ dir; it is the right source
# for sibling helpers (aiqum-install-remote.sh, aiqum-initial-setup.py).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# PACKAGE_DIR must come from the framework — deriving it from $(dirname "$0")
# resolves to the blueprint dir, which is wrong for a consuming package.
PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"

# Read variables from INFRAFOUNDRY_PACKAGE_VARS (JSON, set by framework).
if [ -z "${INFRAFOUNDRY_PACKAGE_VARS:-}" ]; then
    echo "ERROR: INFRAFOUNDRY_PACKAGE_VARS is not set — run via 'foundry infra apply', not directly" >&2
    exit 1
fi
eval "$(python3 -c "
import json, os
v = json.loads(os.environ['INFRAFOUNDRY_PACKAGE_VARS'])
for k, val in v.items():
    print(f'{k}={val}')
")"

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

# --- Phase 0: Preflight — catch obvious local SSH problems before the wait
# loop. Loops that silently retry for minutes are confusing when ssh-agent has
# no keys loaded or the first hop is fundamentally broken.
echo ""
log "--- Phase 0: Preflight checks ---"

if ! ssh-add -l >/dev/null 2>&1; then
    rc=$?
    if [ $rc -eq 1 ]; then
        echo "ERROR: ssh-agent on $(hostname) has no keys loaded" >&2
        echo "       Load your key (e.g. 'ssh-add ~/.ssh/id_ed25519') and re-apply" >&2
    else
        echo "ERROR: cannot reach ssh-agent on $(hostname) (rc=$rc, SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-unset})" >&2
    fi
    exit 1
fi
echo "  ssh-agent: $(ssh-add -l | wc -l) key(s) loaded"

PREFLIGHT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR"' EXIT
if ! remote_cmd "${ip_address}" "echo ok" >"$PREFLIGHT_ERR" 2>&1; then
    echo "ERROR: preflight ssh to ${vm_name} (${ip_address}) failed:" >&2
    sed 's/^/    /' "$PREFLIGHT_ERR" >&2
    exit 1
fi
echo "  ssh probe to ${vm_name} (${ip_address}): OK"

# --- Phase 1: Wait for VM to be reachable ---
echo ""
log "--- Phase 1: Waiting for VM to be reachable ---"
MAX_WAIT=300
ELAPSED=0
WAIT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR"' EXIT
while ! remote_cmd "${ip_address}" "echo ready" >"$WAIT_ERR" 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: VM not reachable after ${MAX_WAIT}s"
        echo "  Last ssh attempt:" >&2
        sed 's/^/    /' "$WAIT_ERR" >&2
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
# Capture curl's stderr so a wait-loop timeout can dump the actual
# error (connection refused, TLS handshake fail, etc.) instead of just
# "not available after Ns".
CURL_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR" "$CURL_ERR"' EXIT
echo ""
log "--- Phase 3: Waiting for AIQUM web UI ---"
MAX_WAIT=600
ELAPSED=0
while ! curl -skS -o /dev/null -w "%{http_code}" "https://${ip_address}/" 2>"$CURL_ERR" | grep -q "200\|302\|401"; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "ERROR: AIQUM web UI not available after ${MAX_WAIT}s"
        if [ -s "$CURL_ERR" ]; then
            echo "  Last curl error:" >&2
            sed 's/^/    /' "$CURL_ERR" >&2
        fi
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

# Wait for web UI to come back. Reuses $CURL_ERR from Phase 3 so the
# timeout path can surface curl's actual error.
echo "  Waiting for AIQUM web UI to restart..."
sleep 15
ELAPSED=0
while ! curl -skS -o /dev/null -w "%{http_code}" "https://${ip_address}/" 2>"$CURL_ERR" | grep -q "200\|302\|401"; do
    if [ $ELAPSED -ge 300 ]; then
        echo "ERROR: AIQUM web UI not available after restart"
        if [ -s "$CURL_ERR" ]; then
            echo "  Last curl error:" >&2
            sed 's/^/    /' "$CURL_ERR" >&2
        fi
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
