#!/bin/bash
# k3s Cluster Setup — Post-Terraform Event Handler (OCI variant)
#
# Triggered by the blueprint's on_create event after the OCI compute
# instances are provisioned. Builds an Ansible inventory on the fly from
# INFRAFOUNDRY_PACKAGE_VARS (so worker count is dynamic) and runs the
# k3s-server / k3s-agent roles shipped with the blueprint (roles/) via
# ansible-playbook. A config repo can override them with its own roles
# under envs/<env>/roles/ (local runs only).
#
# Variable cardinality: the worker count is derived from the workers:
# list in the package manifest. The script reads the JSON-serialized
# variable dict via python3 + stdlib json to iterate the list, so the
# same script handles 0, 1, or N workers without modification.
#
# Portability contract (runs on InfraFoundry host or jumphost):
#   - bash 4+
#   - python3 (stdlib only — json)
#   - ansible-playbook (checked at startup — the k3s roles ship in the
#     blueprint's roles/ directory, which travels to the jumphost with it)
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_VAR_<key>     - Individual package variables
#   INFRAFOUNDRY_PACKAGE_VARS  - JSON-serialized full variable dict
#   INFRAFOUNDRY_EVENT         - Event type (e.g., "resource_created")
#   INFRAFOUNDRY_ENV           - Environment name
#   INFRAFOUNDRY_CONFIG_DIR    - Env directory (<config>/envs/<env>); optional roles/ override
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
K3S_VCN_CIDR="${INFRAFOUNDRY_VAR_vcn_cidr:-192.0.2.0/24}"
K3S_SSH_PUBLIC_KEY="${INFRAFOUNDRY_VAR_ssh_public_key:-}"
export K3S_SSH_PUBLIC_KEY
KUBECONFIG_LOCAL=$(eval echo "${INFRAFOUNDRY_VAR_kubeconfig_local_path}")

# --- Read worker list from the JSON-serialized package vars via python3 ---
mapfile -t WORKER_NAMES < <(python3 -c 'import json,sys
for w in json.load(sys.stdin).get("workers",[]): print(w["name"])' <<< "${INFRAFOUNDRY_PACKAGE_VARS}")

# --- Paths ---
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BLUEPRINT_ROLES_DIR="${BLUEPRINT_DIR}/roles"
PLAYBOOK="${BLUEPRINT_DIR}/playbooks/k3s.yml"
# Blueprint roles are the default; an env's own roles/ goes first and wins.
# The env directory is not copied to a jumphost, so the override is local only.
ROLES_PATH="${BLUEPRINT_ROLES_DIR}"
if [ -z "${INFRAFOUNDRY_ON_JUMPHOST:-}" ] && [ -n "${INFRAFOUNDRY_CONFIG_DIR:-}" ] && [ -d "${INFRAFOUNDRY_CONFIG_DIR}/roles" ]; then ROLES_PATH="${INFRAFOUNDRY_CONFIG_DIR}/roles:${ROLES_PATH}"; fi
INVENTORY_FILE="$(mktemp -t k3s-inventory-XXXXXX.yml)"
trap 'rm -f "${INVENTORY_FILE}"; k3s_ssh_cleanup' EXIT

if [ ! -d "${BLUEPRINT_ROLES_DIR}" ]; then
    echo "ERROR: Roles directory not found: ${BLUEPRINT_ROLES_DIR}"
    echo "Expected k3s-server and k3s-agent roles in the blueprint's roles/ directory"
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
source "${BLUEPRINT_DIR}/scripts/oci/k3s-lib.sh"
# Strict host key checking against the pinned keys (#1583); fails closed when none.
k3s_pin_host_keys || exit 1

CONTROL_HOST=$(host_fqdn "${CONTROL_NAME}")

# --- Cluster DNS inputs (k3s-dns role; empty nameservers = step disabled) ---
eval "$(python3 -c 'import json,shlex,sys
v = json.load(sys.stdin)
def j(k):
    x = v.get(k) or []
    return ",".join(x) if isinstance(x, list) else str(x)
print("export K3S_DNS_NAMESERVERS=" + shlex.quote(j("k3s_dns_nameservers")))
print("export K3S_DNS_SEARCH=" + shlex.quote(j("k3s_dns_search")))
print("export K3S_VCN_DNS_LABEL=" + shlex.quote(str(v.get("vcn_dns_label") or "")))' <<< "${INFRAFOUNDRY_PACKAGE_VARS}")"
DNS_VARS_FILE="$(mktemp -t k3s-dns-vars-XXXXXX.json)"
trap 'rm -f "${INVENTORY_FILE}" "${DNS_VARS_FILE}"; k3s_ssh_cleanup' EXIT
write_k3s_dns_extra_vars "${DNS_VARS_FILE}"

# --- Validate the SSH public key before any connection (it feeds the bootstrap) ---
BOOTSTRAP_VARS_CHECK="$(mktemp -t k3s-bootstrap-check-XXXXXX.json)"
if ! write_k3s_bootstrap_extra_vars "${BOOTSTRAP_VARS_CHECK}"; then
    rm -f "${BOOTSTRAP_VARS_CHECK}"
    exit 1
fi
rm -f "${BOOTSTRAP_VARS_CHECK}"

# --- Write inventory ---
write_k3s_inventory "${INVENTORY_FILE}" \
    "cluster_name: ${CLUSTER_NAME}" \
    "k3s_version: \"${K3S_VERSION}\"" \
    "k3s_server_args: \"${K3S_SERVER_ARGS}\"" \
    "k3s_oci_firewall_fix: ${K3S_OCI_FIREWALL_FIX}" \
    "k3s_vcn_cidr: \"${K3S_VCN_CIDR}\"" \
    "kubeconfig_local_path: \"${KUBECONFIG_LOCAL}\""

echo "=== k3s Cluster Setup (OCI) ==="
echo "Cluster: ${CLUSTER_NAME}"
echo "Control: ${CONTROL_NAME} (${CONTROL_HOST})"
echo "Workers (${#WORKER_NAMES[@]}):"
for name in "${WORKER_NAMES[@]}"; do
    echo "  - ${name} ($(host_fqdn "${name}"))"
done
echo "Tailnet: ${TAILNET:-<direct>}"
echo "Inventory: ${INVENTORY_FILE}"
echo "Roles:     ${ROLES_PATH}"
echo "Playbook:  ${PLAYBOOK}"

SSH="${K3S_SSH}"

# --- Phase 0: Preflight — catch obvious local SSH problems before the wait
# loop. Loops that silently retry for minutes are confusing when ssh-agent has
# no keys loaded. Only local state is checked here: on first create the control
# node has not joined the tailnet yet, so a remote probe would fail spuriously.
# Remote problems are classified in Phase 1.
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

# --- Phase 1: wait for SSH reachability on every host ---
# A new node needs time to boot and join the tailnet, so name-resolution,
# refused, timed-out and no-route errors keep waiting. Authentication and
# host-key errors will not fix themselves, so they fail fast.
echo ""
echo "--- Phase 1: waiting for SSH reachability ---"
MAX_WAIT=600
WAIT_ERR=$(mktemp)
trap 'rm -f "${INVENTORY_FILE}" "${DNS_VARS_FILE}" "${WAIT_ERR}"; k3s_ssh_cleanup' EXIT

wait_for_ssh() {
    local user="$1"
    local host="$2"
    local elapsed=0
    while ! ${SSH} "${user}@${host}" "echo ready" >"${WAIT_ERR}" 2>&1; do
        if k3s_host_key_error "${WAIT_ERR}"; then
            echo "ERROR: ${host} does not present the pinned SSH host key." >&2
            echo "  The key recorded under ssh_host_keys.${host%%.*} in the package's secrets.yaml does not match." >&2
            echo "  If the node was rebuilt, destroy it, run 'foundry secrets host-keys --env <env> --regenerate ${host%%.*}'," >&2
            echo "  then apply again." >&2
            sed 's/^/    /' "${WAIT_ERR}" >&2
            return 1
        fi
        if grep -qiE 'Permission denied|Too many authentication failures' "${WAIT_ERR}"; then
            echo "ERROR: ssh to ${user}@${host} failed with a non-retryable error:" >&2
            sed 's/^/    /' "${WAIT_ERR}" >&2
            return 1
        fi
        if grep -qi 'tailnet policy does not permit' "${WAIT_ERR}"; then
            echo "ERROR: Tailscale SSH to ${host} was denied by the tailnet policy." >&2
            echo "  The policy's ssh rules need a rule allowing this controller's tag to SSH" >&2
            echo "  to the nodes' tags (for example tag:controller -> tag:k3s-node), and" >&2
            echo "  the rule must allow the user '${user}'." >&2
            sed 's/^/    /' "${WAIT_ERR}" >&2
            return 1
        fi
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

wait_for_all() {
    local user="$1"
    wait_for_ssh "${user}" "${CONTROL_HOST}"
    for name in "${WORKER_NAMES[@]}"; do
        wait_for_ssh "${user}" "$(host_fqdn "${name}")"
    done
}

wait_for_all "${K3S_BOOTSTRAP_USER}"

# --- Phase 1b: create the login user (as the image's own user) ---
echo ""
echo "--- Phase 1b: creating the ${K3S_LOGIN_USER} login user ---"
run_k3s_bootstrap

# --- Phase 1c: wait for SSH as the login user ---
echo ""
echo "--- Phase 1c: waiting for SSH as ${K3S_LOGIN_USER} ---"
wait_for_all "${K3S_LOGIN_USER}"

# --- Phase 2: run the ansible playbook ---
echo ""
echo "--- Phase 2: running ansible-playbook ---"
export ANSIBLE_ROLES_PATH="${ROLES_PATH}"

ansible-playbook -i "${INVENTORY_FILE}" -e "@${DNS_VARS_FILE}" "${PLAYBOOK}"

echo ""
echo "=== k3s Cluster Setup Complete ==="
echo "  Control: ${CONTROL_NAME}"
echo "  Workers: ${#WORKER_NAMES[@]} node(s)"
echo "  Kubeconfig: ${KUBECONFIG_LOCAL}"
if [ -n "${INFRAFOUNDRY_ON_JUMPHOST:-}" ]; then
    echo "  (That path is on the jumphost; InfraFoundry copies the kubeconfig to the"
    echo "   same ~ path on your workstation after this script succeeds.)"
fi
