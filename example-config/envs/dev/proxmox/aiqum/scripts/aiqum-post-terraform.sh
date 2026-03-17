#!/bin/bash
# AIQUM Post-Terraform Setup
#
# Installs AIQUM RPM on the Rocky 9 VM, waits for the web UI,
# then runs the initial setup wizard (FEW) via REST API.
#
# All remote commands run through the ansible jumphost since the SSH key
# for the AIQUM VM only exists there.
#
# Prerequisites:
# - Rocky 9 VM created and booted with cloud-init
# - AIQUM RPM available at a web server (set aiqum_url_base in infrafoundry.yml)
# - ONTAP cluster running and reachable
# - SSH jumphost reachable (set jumphost in infrafoundry.yml)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(dirname "$SCRIPT_DIR")"

# Read variables from infrafoundry.yml + secrets.yaml
eval "$(python3 -c "
import subprocess, sys, yaml
from pathlib import Path

with open('${PACKAGE_DIR}/infrafoundry.yml') as f:
    data = yaml.safe_load(f)
v = data.get('variables', {})

# Merge secrets.yaml if it exists (SOPS-encrypted)
secrets_path = Path('${PACKAGE_DIR}/secrets.yaml')
if secrets_path.exists():
    raw = secrets_path.read_text()
    if 'sops:' in raw and 'ENC[AES256_GCM,' in raw:
        result = subprocess.run(['sops', '--decrypt', str(secrets_path)],
                                capture_output=True, text=True, check=True)
        secrets = yaml.safe_load(result.stdout) or {}
    else:
        secrets = yaml.safe_load(raw) or {}
    v.update(secrets.get('variables', {}))

for k, val in v.items():
    print(f'{k}={val}')
")"

JUMPHOST="${jumphost:-ansible@ansible.example.com}"
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

echo "=== AIQUM Post-Terraform Setup ==="
echo "VM: ${vm_name} (${ip_address})"
echo "Jumphost: ${JUMPHOST}"

# --- Phase 1: Wait for VM to be reachable ---
echo ""
echo "--- Phase 1: Waiting for VM to be reachable ---"
MAX_WAIT=300
ELAPSED=0
while ! ${SSH} ${JUMPHOST} "${SSH} ansible@${ip_address} 'echo ready'" &>/dev/null; do
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
echo "--- Phase 2: Installing AIQUM RPM ---"

REMOTE_SCRIPT="${SCRIPT_DIR}/aiqum-install-remote.sh"
if [ ! -f "${REMOTE_SCRIPT}" ]; then
    echo "ERROR: Install script not found: ${REMOTE_SCRIPT}"
    exit 1
fi

# Step 1: Upload install script to jumphost
echo "  Uploading install script to jumphost..."
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "${REMOTE_SCRIPT}" "${JUMPHOST}:/tmp/aiqum-install-remote.sh"

# Step 2: Copy from jumphost to VM
echo "  Copying install script to VM..."
${SSH} ${JUMPHOST} "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    /tmp/aiqum-install-remote.sh ansible@${ip_address}:/tmp/aiqum-install-remote.sh"

# Step 3: Run the install script on the VM (via jumphost)
echo "  Running install script on VM (downloading 1.9GB RPM + installing)..."
${SSH} -o ServerAliveInterval=30 ${JUMPHOST} \
    "${SSH} -o ServerAliveInterval=30 ansible@${ip_address} 'chmod +x /tmp/aiqum-install-remote.sh && bash /tmp/aiqum-install-remote.sh'"

echo "  AIQUM RPM installed successfully"

# --- Phase 3: Wait for AIQUM web UI ---
echo ""
echo "--- Phase 3: Waiting for AIQUM web UI ---"
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

# --- Phase 4: Run initial setup wizard (FEW) ---
echo ""
echo "--- Phase 4: Running initial setup wizard ---"
python3 "${SCRIPT_DIR}/aiqum-initial-setup.py"

echo ""
echo "=== AIQUM Setup Complete ==="
echo "  URL: https://${ip_address}/"
echo "  User: ${aiqum_admin_user}"
