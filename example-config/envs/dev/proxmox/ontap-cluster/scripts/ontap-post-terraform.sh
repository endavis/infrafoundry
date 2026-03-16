#!/bin/bash
# ONTAP Lab Cluster Setup — Post-Terraform Event Handler
#
# Triggered by on_create resource lifecycle event after both ONTAP VMs are created.
# Runs the full ONTAP lab playbook: serial setup, cluster create, join, post-config.
#
# All configuration is read from infrafoundry.yml — no other files need editing.
# The script generates a dynamic Ansible inventory and extra-vars from
# the infrafoundry.yml variables section.
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_EVENT    - event type (e.g., "resource_created")
#   INFRAFOUNDRY_RESOURCE - resource name (if per-resource event)
#   INFRAFOUNDRY_ENV      - environment name (e.g., "prod")
#   INFRAFOUNDRY_PROVIDER - provider name (if set)
#   INFRAFOUNDRY_CONFIG_DIR - path to envs/<env>/

set -euo pipefail

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

# Build host lookup from target names
host_lookup = {}
for key in v:
    if key.endswith('_host') and key.startswith('pve'):
        # e.g., pve1_host -> pve1
        host_lookup[key.replace('_host', '')] = v[key]

# Build proxmox_hosts inventory — handle both nodes on same host
node01_target = v.get('node01_target', 'pve1')
node02_target = v.get('node02_target', 'pve2')
proxmox_hosts = {}

# Node 01
proxmox_hosts[node01_target] = {
    'ansible_host': host_lookup.get(node01_target, node01_target),
    'ansible_user': 'root',
    'ontap_vmid': v['node01_vmid'],
}

# Node 02 — if same host, add vmid as node02_vmid
if node02_target == node01_target:
    proxmox_hosts[node01_target]['ontap_node02_vmid'] = v['node02_vmid']
else:
    proxmox_hosts[node02_target] = {
        'ansible_host': host_lookup.get(node02_target, node02_target),
        'ansible_user': 'root',
        'ontap_vmid': v['node02_vmid'],
    }

# Generate inventory
inventory = {
    'all': {
        'children': {
            'proxmox_hosts': {
                'hosts': proxmox_hosts,
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
