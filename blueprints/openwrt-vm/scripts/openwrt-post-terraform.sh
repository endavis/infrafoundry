#!/bin/bash
# OpenWrt VM — Post-Terraform Event Handler
#
# Triggered by the on_create resource lifecycle event once the VM exists.
# Boots it and bootstraps it over the serial console (openwrt-bootstrap.yml),
# then waits until the SSH server at mgmt_ip sends its banner.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_VAR_<key>     - package variables (there is no secret)
#   On a jumphost run both directories are the framework's remote copies:
#   BLUEPRINT_DIR is the rsynced blueprint tree, PACKAGE_DIR an empty per-run
#   scratch directory (consumer files are not copied).

set -euo pipefail

PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
PLAYBOOK="${BLUEPRINT_DIR}/openwrt-bootstrap.yml"

for var in vmid vm_name target_node pve_host ssh_public_key mgmt_ip; do
    name="INFRAFOUNDRY_VAR_${var}"
    if [ -z "${!name:-}" ]; then
        echo "ERROR: ${name} is not set — run via 'foundry infra apply' with the package variables" >&2
        exit 1
    fi
done

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook is required but was not found on PATH" >&2
    exit 127
fi

INVENTORY="${PACKAGE_DIR}/.generated-inventory.json"
python3 -c "
import json, os, sys
inventory = {
    'proxmox_host': {
        'hosts': {
            os.environ['INFRAFOUNDRY_VAR_target_node']: {
                'ansible_host': os.environ['INFRAFOUNDRY_VAR_pve_host'],
                'ansible_user': 'root',
            },
        },
    },
}
with open(sys.argv[1], 'w') as f:
    json.dump(inventory, f, indent=2)
" "$INVENTORY"

echo "Bootstrapping OpenWrt VM ${INFRAFOUNDRY_VAR_vmid} on ${INFRAFOUNDRY_VAR_target_node}..."
cd "$BLUEPRINT_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK"

# The probe reads the SSH banner only: no key or credential is used.
MGMT_IP="${INFRAFOUNDRY_VAR_mgmt_ip}"
TIMEOUT="${INFRAFOUNDRY_VAR_boot_timeout:-300}"
echo "Waiting up to ${TIMEOUT}s for an SSH banner from ${MGMT_IP}:22..."
ELAPSED=0
while :; do
    banner=$(timeout 5 bash -c 'exec 3<>/dev/tcp/$1/22; head -c 4 <&3' _ "$MGMT_IP" 2>/dev/null || true)
    if [ "$banner" = "SSH-" ]; then
        echo "OpenWrt SSH is up at ${MGMT_IP}"
        exit 0
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: SSH did not answer within ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
