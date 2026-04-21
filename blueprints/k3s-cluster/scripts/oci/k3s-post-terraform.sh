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
# variable dict via python3 + stdlib json to iterate the list, so the
# same script handles 0, 1, or N workers without modification.
#
# Portability contract (runs on InfraFoundry host or jumphost):
#   - bash 4+
#   - python3 (stdlib only — json)
#   - ansible-playbook (checked at startup — the shared k3s roles live
#     in ${INFRAFOUNDRY_CONFIG_DIR}/roles)
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

# --- Read worker list from the JSON-serialized package vars via python3 ---
mapfile -t WORKER_NAMES < <(python3 -c 'import json,sys
for w in json.load(sys.stdin).get("workers",[]): print(w["name"])' <<< "${INFRAFOUNDRY_PACKAGE_VARS}")

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

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook is required but was not found on PATH" >&2
    echo "Install ansible and ensure ansible-playbook is on PATH (on the jumphost if jumphost is set in the package)" >&2
    exit 127
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

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

# --- Phase 0: Preflight — catch obvious local SSH problems before the wait
# loop. Loops that silently retry for minutes are confusing when ssh-agent has
# no keys loaded or the first hop is fundamentally broken.
echo ""
echo "--- Phase 0: Preflight checks ---"

if ! ssh-add -l >/dev/null 2>&1; then
    rc=$?
    if [ ${rc} -eq 1 ]; then
        echo "ERROR: ssh-agent on $(hostname) has no keys loaded" >&2
        echo "       Load your key (e.g. 'ssh-add ~/.ssh/id_ed25519') and re-apply" >&2
    else
        echo "ERROR: cannot reach ssh-agent on $(hostname) (rc=${rc}, SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-unset})" >&2
    fi
    exit 1
fi
echo "  ssh-agent: $(ssh-add -l | wc -l) key(s) loaded"

PREFLIGHT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR"' EXIT
if ! ${SSH} "ubuntu@${CONTROL_HOST}" "echo ok" >"${PREFLIGHT_ERR}" 2>&1; then
    echo "ERROR: preflight ssh to ${CONTROL_NAME} (${CONTROL_HOST}) failed:" >&2
    sed 's/^/    /' "${PREFLIGHT_ERR}" >&2
    exit 1
fi
echo "  ssh probe to ${CONTROL_NAME} (${CONTROL_HOST}): OK"

# --- Phase 1: wait for SSH reachability on every host ---
echo ""
echo "--- Phase 1: waiting for SSH reachability ---"
MAX_WAIT=600
WAIT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR"' EXIT

wait_for_ssh() {
    local host="$1"
    local elapsed=0
    while ! ${SSH} "ubuntu@${host}" "echo ready" >"${WAIT_ERR}" 2>&1; do
        if [ ${elapsed} -ge ${MAX_WAIT} ]; then
            echo "ERROR: ${host} not reachable after ${MAX_WAIT}s"
            echo "  Last ssh attempt:" >&2
            sed 's/^/    /' "${WAIT_ERR}" >&2
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
