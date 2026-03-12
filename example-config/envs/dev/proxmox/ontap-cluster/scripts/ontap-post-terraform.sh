#!/bin/bash
# ONTAP Lab Cluster Setup — Post-Terraform Event Handler
#
# Triggered by RUNNER_COMPLETED event after Terraform finishes for proxmox.
# Runs the full ONTAP lab playbook: serial setup, cluster create, join, post-config.
#
# All configuration is read from infrafoundry.yml — no other files need editing.
# The script generates a dynamic Ansible inventory and extra-vars from
# the infrafoundry.yml variables section.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_RUNNER   - runner that completed (e.g., "terraform")
#   INFRAFOUNDRY_PROVIDER - provider name (e.g., "proxmox")
#   INFRAFOUNDRY_ENV      - environment name (e.g., "dev")
#   INFRAFOUNDRY_PHASE    - workflow phase (e.g., "plan", "apply", "destroy")
#   INFRAFOUNDRY_CONFIG_DIR - path to envs/<env>/

set -euo pipefail

# Only run after Terraform apply completes for proxmox
if [ "$INFRAFOUNDRY_RUNNER" != "terraform" ] || [ "$INFRAFOUNDRY_PROVIDER" != "proxmox" ] || [ "${INFRAFOUNDRY_PHASE:-}" != "apply" ]; then
    echo "Skipping: runner=$INFRAFOUNDRY_RUNNER provider=$INFRAFOUNDRY_PROVIDER phase=${INFRAFOUNDRY_PHASE:-unknown}"
    exit 0
fi

# Script lives in ontap-cluster/scripts/, so package dir is one level up
PACKAGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${PACKAGE_DIR}/infrafoundry.yml"
PLAYBOOK="${PACKAGE_DIR}/ontap-lab-playbook.yml"

# Verify required files exist
for f in "$MANIFEST" "$PLAYBOOK"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required file not found: $f"
        exit 1
    fi
done

# Generate Ansible inventory and extra-vars from infrafoundry.yml
echo "Generating Ansible configuration from infrafoundry.yml..."
INVENTORY="${PACKAGE_DIR}/.generated-inventory.yml"
VARS_FILE="${PACKAGE_DIR}/.generated-vars.json"

python3 -c "
import json, sys, yaml

with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)

v = data.get('variables', {})

# Generate inventory
inventory = {
    'all': {
        'children': {
            'proxmox_hosts': {
                'hosts': {
                    v.get('node01_target', 'pve1'): {
                        'ansible_host': v['pve1_host'],
                        'ansible_user': 'root',
                        'ontap_vmid': v['node01_vmid'],
                    },
                    v.get('node02_target', 'pve2'): {
                        'ansible_host': v['pve2_host'],
                        'ansible_user': 'root',
                        'ontap_vmid': v['node02_vmid'],
                    },
                },
            },
            'ontap_cluster': {
                'hosts': {
                    'ontap-cluster': {
                        'ansible_host': v['cluster_mgmt_ip'],
                        'ansible_connection': 'local',
                    },
                },
            },
        },
    },
}

with open(sys.argv[2], 'w') as f:
    yaml.dump(inventory, f, default_flow_style=False)

with open(sys.argv[3], 'w') as f:
    json.dump(v, f)
" "$MANIFEST" "$INVENTORY" "$VARS_FILE"

echo "Running ONTAP lab cluster setup playbook..."
cd "$PACKAGE_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK" -e "@${VARS_FILE}" -v
