#!/bin/bash
# k3s Cluster Setup — Post-Terraform Event Handler
#
# Triggered by on_create resource lifecycle event after the cluster VMs are
# created. Installs k3s server on the first node, retrieves the join token,
# then installs k3s agent on the remaining N nodes.
#
# Variable cardinality: the agent count is derived from the agents: list in
# the package manifest. The script reads INFRAFOUNDRY_PACKAGE_VARS (JSON-
# serialized full variable dict) via python3 + stdlib json to iterate the
# list, so the same script handles 0, 1, or N agents without modification.
#
# Portability contract (runs on InfraFoundry host or jumphost):
#   - bash 4+ (mapfile / readarray)
#   - python3 (stdlib only — json)
#   - standard GNU coreutils + ssh/scp
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_VAR_<key>     - Individual package variables
#   INFRAFOUNDRY_PACKAGE_VARS  - JSON-serialized full variable dict
#   INFRAFOUNDRY_EVENT         - Event type (e.g., "resource_created")
#   INFRAFOUNDRY_ENV           - Environment name (e.g., "prod")

set -euo pipefail

# --- Read scalar variables from environment ---
SERVER_IP="${INFRAFOUNDRY_VAR_server_ip}"
SERVER_NAME="${INFRAFOUNDRY_VAR_server_name}"
JUMPHOST="${INFRAFOUNDRY_VAR_jumphost:-}"
K3S_SERVER_ARGS="${INFRAFOUNDRY_VAR_k3s_server_args}"
CLUSTER_NAME="${INFRAFOUNDRY_VAR_cluster_name}"
KUBECONFIG_DIR=$(eval echo "${INFRAFOUNDRY_VAR_kubeconfig_dir}")
KUBECONFIG_LOCAL="${KUBECONFIG_DIR}/${CLUSTER_NAME}.yaml"

# --- Read agents list from the JSON-serialized package vars via python3 ---
mapfile -t AGENT_NAMES < <(python3 -c 'import json,sys
for a in json.load(sys.stdin).get("agents",[]): print(a["name"])' <<< "${INFRAFOUNDRY_PACKAGE_VARS}")
mapfile -t AGENT_IPS   < <(python3 -c 'import json,sys
for a in json.load(sys.stdin).get("agents",[]): print(a["ip"])' <<< "${INFRAFOUNDRY_PACKAGE_VARS}")

# Expected total node count = 1 server + N agents
EXPECTED_NODES=$(( ${#AGENT_IPS[@]} + 1 ))

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
SSH_KEEPALIVE="${SSH} -o ServerAliveInterval=30"

# All node IPs and names for iteration
ALL_IPS=("${SERVER_IP}" "${AGENT_IPS[@]}")
ALL_NAMES=("${SERVER_NAME}" "${AGENT_NAMES[@]}")

# SSH helpers — when JUMPHOST is set, tunnel through it (run inner ssh on the
# jumphost). When JUMPHOST is empty, ssh directly from the InfraFoundry host
# to the target node. Direct mode is suitable when the workstation has line-of-
# sight to the cluster network.

if [ -n "${JUMPHOST}" ]; then
    # Helper: run command on a remote node via jumphost (as ansible user)
    remote_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} '$*'"
    }

    # Helper: run command as root on a remote node via jumphost (for installs/system config)
    remote_root_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'sudo PATH=/usr/local/bin:\$PATH bash -c \"$*\"'"
    }

    # Helper: run kubectl on k3s server as ansible user (no sudo needed)
    remote_kubectl() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'KUBECONFIG=/etc/rancher/k3s/k3s.yaml PATH=/usr/local/bin:\$PATH $*'"
    }
else
    # Helper: run command on a remote node directly (as ansible user)
    remote_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "ansible@${ip}" "$*"
    }

    # Helper: run command as root on a remote node directly (for installs/system config)
    remote_root_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "ansible@${ip}" "sudo PATH=/usr/local/bin:\$PATH bash -c \"$*\""
    }

    # Helper: run kubectl on k3s server as ansible user directly (no sudo needed)
    remote_kubectl() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "ansible@${ip}" "KUBECONFIG=/etc/rancher/k3s/k3s.yaml PATH=/usr/local/bin:\$PATH $*"
    }
fi

echo "=== k3s Cluster Setup ==="
echo "Server: ${SERVER_NAME} (${SERVER_IP})"
echo "Agents (${#AGENT_NAMES[@]}):"
for i in "${!AGENT_NAMES[@]}"; do
    echo "  - ${AGENT_NAMES[$i]} (${AGENT_IPS[$i]})"
done
echo "Jumphost: ${JUMPHOST:-<direct>}"

# ===========================================================================
# Phase 0: Preflight — catch obvious local SSH problems before the wait loop.
# Loops that silently retry for minutes are confusing when ssh-agent has no
# keys loaded or the first hop is fundamentally broken.
# ===========================================================================
echo ""
echo "--- Phase 0: Preflight checks ---"

if ! ssh-add -l >/dev/null 2>&1; then
    rc=$?
    if [ $rc -eq 1 ]; then
        echo "ERROR: ssh-agent on $(hostname) has no keys loaded" >&2
        echo "       Load your key (e.g. 'ssh-add ~/.ssh/id_ed25519') and re-apply" >&2
    else
        echo "ERROR: cannot reach ssh-agent on $(hostname) (rc=$rc, SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-unset})" >&2
    fi
    exit 1
fi
echo "  ssh-agent: $(ssh-add -l | wc -l) key(s) loaded"

PREFLIGHT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR"' EXIT
if ! remote_cmd "${SERVER_IP}" "echo ok" >"$PREFLIGHT_ERR" 2>&1; then
    echo "ERROR: preflight ssh to ${SERVER_NAME} (${SERVER_IP}) failed:" >&2
    sed 's/^/    /' "$PREFLIGHT_ERR" >&2
    exit 1
fi
echo "  ssh probe to ${SERVER_NAME} (${SERVER_IP}): OK"

# ===========================================================================
# Phase 1: Wait for all VMs to be reachable
# ===========================================================================
echo ""
echo "--- Phase 1: Waiting for all VMs to be reachable ---"
MAX_WAIT=300
WAIT_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR"' EXIT

for i in "${!ALL_IPS[@]}"; do
    ip="${ALL_IPS[$i]}"
    name="${ALL_NAMES[$i]}"
    ELAPSED=0
    while ! remote_cmd "${ip}" "echo ready" >"$WAIT_ERR" 2>&1; do
        if [ $ELAPSED -ge $MAX_WAIT ]; then
            echo "ERROR: ${name} (${ip}) not reachable after ${MAX_WAIT}s"
            echo "  Last ssh attempt:" >&2
            sed 's/^/    /' "$WAIT_ERR" >&2
            exit 1
        fi
        echo "  Waiting for ${name} (${ip})... (${ELAPSED}s)"
        sleep 10
        ELAPSED=$((ELAPSED + 10))
    done
    echo "  ${name} (${ip}) is reachable"
done

# ===========================================================================
# Phase 2: Prepare all nodes (requires root)
# ===========================================================================
echo ""
echo "--- Phase 2: Preparing all nodes ---"

for i in "${!ALL_IPS[@]}"; do
    ip="${ALL_IPS[$i]}"
    name="${ALL_NAMES[$i]}"
    echo "  Preparing ${name}..."

    # Enable required kernel modules
    remote_root_cmd "${ip}" "
        cat > /etc/modules-load.d/k3s.conf <<EOF
br_netfilter
overlay
EOF
        modprobe br_netfilter
        modprobe overlay
    "

    # Set required sysctl parameters
    remote_root_cmd "${ip}" "
        cat > /etc/sysctl.d/k3s.conf <<EOF
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
EOF
        sysctl --system > /dev/null 2>&1
    "

    # Disable firewalld (k3s manages its own iptables rules)
    remote_root_cmd "${ip}" "systemctl disable --now firewalld 2>/dev/null || true"

    # Create MinIO data directory
    remote_root_cmd "${ip}" "mkdir -p /var/lib/minio/data && chmod 750 /var/lib/minio/data"

    echo "  ${name} prepared"
done

# ===========================================================================
# Phase 3: Install k3s server (requires root)
# ===========================================================================
echo ""
echo "--- Phase 3: Installing k3s server on ${SERVER_NAME} ---"

remote_root_cmd "${SERVER_IP}" "
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='server' sh -s - \
        --write-kubeconfig-mode 644 \
        ${K3S_SERVER_ARGS} \
        --node-name ${SERVER_NAME}
"

# Wait for k3s server to be ready (kubectl as ansible user).
# Capture combined output each iteration so the timeout path can dump
# kubectl's actual error instead of a black-box "not ready after 180s".
KUBECTL_ERR=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR" "$KUBECTL_ERR"' EXIT
echo "  Waiting for k3s server to be ready..."
ELAPSED=0
while ! remote_kubectl "${SERVER_IP}" "kubectl get nodes" >"$KUBECTL_ERR" 2>&1; do
    if [ $ELAPSED -ge 180 ]; then
        echo "ERROR: k3s server not ready after 180s"
        echo "  Last kubectl attempt:" >&2
        sed 's/^/    /' "$KUBECTL_ERR" >&2
        exit 1
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done
echo "  k3s server is ready"

# Retrieve the join token (root-owned file, needs sudo)
echo "  Retrieving join token..."
K3S_TOKEN=$(remote_root_cmd "${SERVER_IP}" "cat /var/lib/rancher/k3s/server/node-token")
echo "  Join token retrieved"

# ===========================================================================
# Phase 4: Install k3s agents (requires root)
# ===========================================================================
echo ""
echo "--- Phase 4: Installing k3s agents ---"

for i in "${!AGENT_IPS[@]}"; do
    ip="${AGENT_IPS[$i]}"
    name="${AGENT_NAMES[$i]}"
    echo "  Installing k3s agent on ${name} (${ip})..."

    remote_root_cmd "${ip}" "
        curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='agent' sh -s - \
            --server https://${SERVER_IP}:6443 \
            --token ${K3S_TOKEN} \
            --node-name ${name}
    "

    echo "  k3s agent installed on ${name}"
done

# ===========================================================================
# Phase 5: Verify cluster (kubectl as ansible user)
# ===========================================================================
echo ""
echo "--- Phase 5: Verifying cluster ---"

# Wait for all nodes to be Ready. Split the kubectl call so stdout (the
# count) and stderr (diagnostics) are separable on the local side; the
# previous remote-side `2>/dev/null` discarded errors before they could
# cross the ssh boundary, leaving the operator staring at "0/4 ready"
# with no clue why.
KUBECTL_OUT=$(mktemp)
trap 'rm -f "$PREFLIGHT_ERR" "$WAIT_ERR" "$KUBECTL_ERR" "$KUBECTL_OUT"' EXIT
echo "  Waiting for all ${EXPECTED_NODES} nodes to be Ready..."
ELAPSED=0
while true; do
    if remote_kubectl "${SERVER_IP}" "kubectl get nodes --no-headers" >"$KUBECTL_OUT" 2>"$KUBECTL_ERR"; then
        # grep -c exits 1 with stdout '0' when there are zero matches; `|| true`
        # keeps the assignment clean (the original `|| echo 0` produced '0\n0').
        READY_COUNT=$(grep -c ' Ready ' "$KUBECTL_OUT" || true)
    else
        READY_COUNT=0
    fi
    if [ "${READY_COUNT}" -ge "${EXPECTED_NODES}" ]; then
        break
    fi
    if [ $ELAPSED -ge 180 ]; then
        echo "ERROR: Not all nodes ready after 180s (${READY_COUNT}/${EXPECTED_NODES})"
        if [ -s "$KUBECTL_ERR" ]; then
            echo "  Last kubectl error:" >&2
            sed 's/^/    /' "$KUBECTL_ERR" >&2
        fi
        remote_kubectl "${SERVER_IP}" "kubectl get nodes" >&2 || true
        exit 1
    fi
    echo "  ${READY_COUNT}/${EXPECTED_NODES} nodes ready... (${ELAPSED}s)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

echo "  All nodes are Ready:"
remote_kubectl "${SERVER_IP}" "kubectl get nodes -o wide"

# ===========================================================================
# Phase 6: Save kubeconfig locally
# ===========================================================================
echo ""
echo "--- Phase 6: Saving kubeconfig locally ---"

mkdir -p "$(dirname "${KUBECONFIG_LOCAL}")"

# Fetch kubeconfig and rewrite localhost to the server IP
remote_cmd "${SERVER_IP}" "cat /etc/rancher/k3s/k3s.yaml" | sed "s|127.0.0.1|${SERVER_IP}|g" > "${KUBECONFIG_LOCAL}"
chmod 600 "${KUBECONFIG_LOCAL}"
echo "  Kubeconfig saved to ${KUBECONFIG_LOCAL}"

echo ""
echo "=== k3s Cluster Setup Complete ==="
echo "  Server: ${SERVER_NAME} (${SERVER_IP})"
echo "  Agents: ${#AGENT_NAMES[@]} node(s)"
for i in "${!AGENT_NAMES[@]}"; do
    echo "    - ${AGENT_NAMES[$i]}"
done
echo "  Kubeconfig: export KUBECONFIG=${KUBECONFIG_LOCAL}"
echo "  kubectl: KUBECONFIG=${KUBECONFIG_LOCAL} kubectl get nodes"
