#!/bin/bash
# ONTAP Lab Cluster Setup — Post-Terraform Event Handler
#
# Triggered by on_create resource lifecycle event after both ONTAP VMs are created.
# Runs the full ONTAP lab playbook: serial setup, cluster create, join, post-config.
#
# All variables are provided by the framework via INFRAFOUNDRY_VAR_* env vars.
# Ansible playbooks read variables directly from the environment via lookup('env', ...).
# The script only generates a dynamic inventory (host mappings).
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_PACKAGE_VARS - JSON string of all package variables (including secrets)
#   INFRAFOUNDRY_VAR_<key>    - Individual package variables
#   INFRAFOUNDRY_EVENT        - event type (e.g., "resource_created")
#   INFRAFOUNDRY_ENV          - environment name (e.g., "prod")
#   INFRAFOUNDRY_CONFIG_DIR   - path to envs/<env>/

set -euo pipefail

# Script lives in ontap-cluster/scripts/, so package dir is one level up
PACKAGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYBOOK="${PACKAGE_DIR}/ontap-lab-playbook.yml"

# Verify required files exist
if [ ! -f "$PLAYBOOK" ]; then
    echo "ERROR: Playbook not found: $PLAYBOOK"
    exit 1
fi

# Generate Ansible inventory from package variables
echo "Generating Ansible inventory from environment variables..."
INVENTORY="${PACKAGE_DIR}/.generated-inventory.yml"

python3 -c "
import json, os, sys, yaml

# Read variables from INFRAFOUNDRY_PACKAGE_VARS env var (set by framework)
vars_json = os.environ.get('INFRAFOUNDRY_PACKAGE_VARS')
if vars_json:
    v = json.loads(vars_json)
else:
    # Fallback: read from infrafoundry.yml directly (for manual runs)
    print('Warning: INFRAFOUNDRY_PACKAGE_VARS not set, reading from infrafoundry.yml')
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f)
    v = data.get('variables', {})

# Build host lookup from target names
host_lookup = {}
for key in v:
    if key.endswith('_host') and key.startswith('pve'):
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
" "${PACKAGE_DIR}/infrafoundry.yml" "$INVENTORY"

echo "Running ONTAP lab cluster setup playbook..."
cd "$PACKAGE_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK" -v
