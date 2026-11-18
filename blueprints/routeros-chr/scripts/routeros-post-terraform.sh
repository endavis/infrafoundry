#!/bin/bash
# RouterOS CHR VM — Post-Terraform Event Handler
#
# Triggered by the on_create resource lifecycle event once the VM exists.
# Boots it and bootstraps it over the serial console (routeros-bootstrap.yml),
# then, when a static mgmt_ip is set, waits until the REST API answers, so the
# mikrotik provider can manage the box straight away.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_VAR_<key>     - package variables, including the secret
#                                routeros_admin_password
#   On a jumphost run both directories are the framework's remote copies:
#   BLUEPRINT_DIR is the rsynced blueprint tree, PACKAGE_DIR an empty per-run
#   scratch directory (consumer files are not copied).

set -euo pipefail

PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
PLAYBOOK="${BLUEPRINT_DIR}/routeros-bootstrap.yml"

for var in vmid vm_name target_node pve_host routeros_admin_password; do
    name="INFRAFOUNDRY_VAR_${var}"
    if [ -z "${!name:-}" ]; then
        echo "ERROR: ${name} is not set — run via 'foundry infra apply' with the package secrets" >&2
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

echo "Bootstrapping RouterOS CHR VM ${INFRAFOUNDRY_VAR_vmid} on ${INFRAFOUNDRY_VAR_target_node}..."
cd "$BLUEPRINT_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK"

MGMT_IP="${INFRAFOUNDRY_VAR_mgmt_ip:-}"
if [ -z "$MGMT_IP" ]; then
    echo "mgmt_ip is empty: the address comes from DHCP, skipping the REST readiness probe"
    exit 0
fi

# The probe sends no credentials, so the password never appears on a command
# line: an unauthenticated request being turned away (401) is the readiness signal.
URL="http://${MGMT_IP}/rest/system/resource"
TIMEOUT="${INFRAFOUNDRY_VAR_boot_timeout:-300}"
echo "Waiting up to ${TIMEOUT}s for ${URL}..."
ELAPSED=0
while :; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" || true)
    if [ "$code" = "401" ]; then
        echo "RouterOS REST API is up at http://${MGMT_IP}"
        exit 0
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: REST API did not answer within ${TIMEOUT}s (last status: ${code:-none})" >&2
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
