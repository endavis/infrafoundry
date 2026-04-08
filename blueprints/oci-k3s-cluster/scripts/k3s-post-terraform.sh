#!/bin/bash
# k3s Cluster Setup — Post-Terraform Event Handler (OCI variant)
#
# Triggered by the blueprint's on_create event after the OCI compute
# instances are provisioned. Builds an Ansible inventory on the fly from
# INFRAFOUNDRY_PACKAGE_VARS (so worker count is dynamic) and runs the
# shared k3s-server / k3s-agent roles from the config repo via
# ansible-playbook.
#
# Variable cardinality: the worker count is derived from the workers:
# list in the package manifest. The script reads the JSON-serialized
# variable dict via jq to iterate the list, so the same script handles
# 0, 1, or N workers without modification.
#
# Requirements on the InfraFoundry host:
#   - jq
#   - bash 4+
#   - ansible-playbook (the shared k3s roles live in
#     ${INFRAFOUNDRY_CONFIG_DIR}/roles)
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_VAR_<key>     - Individual package variables
#   INFRAFOUNDRY_PACKAGE_VARS  - JSON-serialized full variable dict
#   INFRAFOUNDRY_EVENT         - Event type (e.g., "resource_created")
#   INFRAFOUNDRY_ENV           - Environment name
#   INFRAFOUNDRY_CONFIG_DIR    - Config repository root
#   INFRAFOUNDRY_BLUEPRINT_DIR - Absolute path to the blueprint directory
#
# Additional (optional) env vars:
#   TAILSCALE_AUTH_KEY         - Passed via the blueprint event's env block

set -euo pipefail

# --- Required scalars ---
CONTROL_NAME="${INFRAFOUNDRY_VAR_control_name}"
CLUSTER_NAME="${INFRAFOUNDRY_VAR_cluster_name}"
TAILNET="${INFRAFOUNDRY_VAR_tailnet:-}"
K3S_VERSION="${INFRAFOUNDRY_VAR_k3s_version:-}"
K3S_SERVER_ARGS="${INFRAFOUNDRY_VAR_k3s_server_args:-}"
K3S_OCI_FIREWALL_FIX="${INFRAFOUNDRY_VAR_k3s_oci_firewall_fix:-true}"
K3S_VCN_CIDR="${INFRAFOUNDRY_VAR_vcn_cidr:-10.0.0.0/16}"
KUBECONFIG_LOCAL=$(eval echo "${INFRAFOUNDRY_VAR_kubeconfig_local_path}")

# --- Read worker list from the JSON-serialized package vars via jq ---
mapfile -t WORKER_NAMES < <(echo "${INFRAFOUNDRY_PACKAGE_VARS}" | jq -r '.workers[].name')

# --- Paths ---
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
CONFIG_DIR="${INFRAFOUNDRY_CONFIG_DIR}"
ROLES_DIR="${CONFIG_DIR}/roles"
PLAYBOOK="${BLUEPRINT_DIR}/playbook.yml"
INVENTORY_FILE="$(mktemp -t k3s-inventory-XXXXXX.yml)"
trap 'rm -f "${INVENTORY_FILE}"' EXIT

if [ ! -d "${ROLES_DIR}" ]; then
    echo "ERROR: Roles directory not found: ${ROLES_DIR}"
    echo "Expected k3s-server and k3s-agent roles under \${INFRAFOUNDRY_CONFIG_DIR}/roles"
    exit 1
fi

if [ ! -f "${PLAYBOOK}" ]; then
    echo "ERROR: Playbook not found: ${PLAYBOOK}"
    exit 1
fi

# --- Compute ansible_host values (FQDN on the tailnet if provided) ---
host_fqdn() {
    local name="$1"
    if [ -n "${TAILNET}" ]; then
        echo "${name}.${TAILNET}"
    else
        echo "${name}"
    fi
}

CONTROL_HOST=$(host_fqdn "${CONTROL_NAME}")

# --- Write inventory ---
{
    echo "all:"
    echo "  children:"
    echo "    k3s_control:"
    echo "      hosts:"
    echo "        ${CONTROL_NAME}:"
    echo "          ansible_host: ${CONTROL_HOST}"
    echo "          ansible_user: ubuntu"
    echo "    k3s_workers:"
    echo "      hosts:"
    if [ ${#WORKER_NAMES[@]} -eq 0 ]; then
        echo "        {}"
    else
        for name in "${WORKER_NAMES[@]}"; do
            echo "        ${name}:"
            echo "          ansible_host: $(host_fqdn "${name}")"
            echo "          ansible_user: ubuntu"
        done
    fi
    echo "    k3s_cluster:"
    echo "      children:"
    echo "        k3s_control: {}"
    echo "        k3s_workers: {}"
    echo "      vars:"
    echo "        cluster_name: ${CLUSTER_NAME}"
    echo "        k3s_version: \"${K3S_VERSION}\""
    echo "        k3s_server_args: \"${K3S_SERVER_ARGS}\""
    echo "        k3s_oci_firewall_fix: ${K3S_OCI_FIREWALL_FIX}"
    echo "        k3s_vcn_cidr: \"${K3S_VCN_CIDR}\""
    echo "        kubeconfig_local_path: \"${KUBECONFIG_LOCAL}\""
} > "${INVENTORY_FILE}"

echo "=== k3s Cluster Setup (OCI) ==="
echo "Cluster: ${CLUSTER_NAME}"
echo "Control: ${CONTROL_NAME} (${CONTROL_HOST})"
echo "Workers (${#WORKER_NAMES[@]}):"
for name in "${WORKER_NAMES[@]}"; do
    echo "  - ${name} ($(host_fqdn "${name}"))"
done
echo "Tailnet: ${TAILNET:-<direct>}"
echo "Inventory: ${INVENTORY_FILE}"
echo "Roles:     ${ROLES_DIR}"
echo "Playbook:  ${PLAYBOOK}"

# --- Phase 1: wait for SSH reachability on every host ---
echo ""
echo "--- Phase 1: waiting for SSH reachability ---"
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
MAX_WAIT=600

wait_for_ssh() {
    local host="$1"
    local elapsed=0
    while ! ${SSH} "ubuntu@${host}" "echo ready" &>/dev/null; do
        if [ ${elapsed} -ge ${MAX_WAIT} ]; then
            echo "ERROR: ${host} not reachable after ${MAX_WAIT}s"
            return 1
        fi
        echo "  Waiting for ${host}... (${elapsed}s)"
        sleep 15
        elapsed=$((elapsed + 15))
    done
    echo "  ${host} is reachable"
}

wait_for_ssh "${CONTROL_HOST}"
for name in "${WORKER_NAMES[@]}"; do
    wait_for_ssh "$(host_fqdn "${name}")"
done

# --- Phase 2: run the ansible playbook ---
echo ""
echo "--- Phase 2: running ansible-playbook ---"
export ANSIBLE_ROLES_PATH="${ROLES_DIR}"
export ANSIBLE_HOST_KEY_CHECKING=False

ansible-playbook -i "${INVENTORY_FILE}" "${PLAYBOOK}"

echo ""
echo "=== k3s Cluster Setup Complete ==="
echo "  Control: ${CONTROL_NAME}"
echo "  Workers: ${#WORKER_NAMES[@]} node(s)"
echo "  Kubeconfig: ${KUBECONFIG_LOCAL}"
