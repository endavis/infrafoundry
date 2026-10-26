#!/bin/bash
# OPNsense VM — Post-Terraform Event Handler
#
# Triggered by the on_create resource lifecycle event once the VM exists.
# Boots it and bootstraps it over the serial console (opnsense-bootstrap.yml),
# then waits until the API answers again, so the opnsense provider can
# manage the box straight away.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_VAR_<key>     - package variables, including the secrets
#                                opnsense_root_password, opnsense_api_key and
#                                opnsense_api_secret

set -euo pipefail

PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
PLAYBOOK="${BLUEPRINT_DIR}/opnsense-bootstrap.yml"

for var in vmid vm_name target_node pve_host wan_ip \
           opnsense_root_password opnsense_api_key opnsense_api_secret; do
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

echo "Bootstrapping OPNsense VM ${INFRAFOUNDRY_VAR_vmid} on ${INFRAFOUNDRY_VAR_target_node}..."
cd "$BLUEPRINT_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK"

# The box reboots after the bootstrap; wait for the API to come back. The probe
# sends no credentials: the box's certificate is self-signed and unverified, so
# an unauthenticated request being turned away (302 to the login page, or
# 401) is the readiness signal.
URL="https://${INFRAFOUNDRY_VAR_wan_ip}/api/core/firmware/status"
TIMEOUT="${INFRAFOUNDRY_VAR_boot_timeout:-600}"
echo "Waiting up to ${TIMEOUT}s for ${URL}..."
ELAPSED=0
while :; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$URL" || true)
    if [ "$code" = "302" ] || [ "$code" = "401" ]; then
        echo "OPNsense API is up at https://${INFRAFOUNDRY_VAR_wan_ip}"
        exit 0
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: API did not answer within ${TIMEOUT}s (last status: ${code:-none})" >&2
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done
