#!/bin/bash
# verify-cluster.sh
#
# Verify K3s cluster health after apply.
# This is an environment-level hook that runs after successful apply.
#
# Required environment variables:
#   INFRAFOUNDRY_ENV - Environment name (set automatically)
#   INFRAFOUNDRY_CONFIG_DIR - Config directory path (set automatically)
#
# Optional:
#   KUBECONFIG - Path to kubeconfig; a leading ~ is expanded. The blueprint
#                handler sets it to the package's kubeconfig_local_path
#                (falls back to ~/.kube/oci-k3s.yaml when unset)
#   K3S_CONTROL_NAME, K3S_TAILNET - Control node name and tailnet. Used only
#                when kubectl is not on PATH: the checks then run on the control
#                node over ssh (ubuntu@<host>) as `sudo k3s kubectl ...`.
#   INFRAFOUNDRY_WARNINGS_FILE - Receives a warning when verification is skipped

set -euo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
# shellcheck source=k3s-lib.sh
source "${BLUEPRINT_DIR}/scripts/oci/k3s-lib.sh"

warn() {
    if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
        printf '{"source": "verify-cluster", "message": "%s"}\n' "$1" >> "${INFRAFOUNDRY_WARNINGS_FILE}"
    fi
}

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/oci-k3s.yaml}"
# The handler env is not shell-expanded, so expand a leading ~ here.
KUBECONFIG="${KUBECONFIG/#\~/$HOME}"

echo "Verifying K3s cluster health for environment: ${INFRAFOUNDRY_ENV:-unknown}"
echo "Using kubeconfig: $KUBECONFIG"

# Check if kubeconfig exists
if [ ! -f "$KUBECONFIG" ]; then
    echo "Warning: Kubeconfig not found at $KUBECONFIG"
    echo "This is normal on first deploy - Ansible will create it"
    exit 0
fi

# Prefer a local kubectl with the fetched kubeconfig. Without one, run the same
# checks on the control node over ssh using the k3s bundled kubectl.
REMOTE_HOST=""
if command -v kubectl &> /dev/null; then
    export KUBECONFIG
else
    CONTROL_NAME="${K3S_CONTROL_NAME:-}"
    TAILNET="${K3S_TAILNET:-}"
    if [ -z "${CONTROL_NAME}" ] || ! command -v ssh &> /dev/null; then
        echo "Verification skipped: kubectl is not on PATH and the control node"
        echo "cannot be reached over ssh (no control name or no ssh client)."
        echo "Install kubectl to enable cluster verification"
        warn "cluster verification skipped: kubectl not found and ssh fallback unavailable"
        exit 0
    fi
    REMOTE_HOST="ubuntu@$(host_fqdn "${CONTROL_NAME}")"
    echo "kubectl not found locally; running checks on ${REMOTE_HOST} over ssh"
    if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_HOST}" true; then
        echo "Verification skipped: cannot ssh to ${REMOTE_HOST}"
        warn "cluster verification skipped: ssh to the control node failed"
        exit 0
    fi
fi

# kc ARGS...: run kubectl locally, or on the control node when REMOTE_HOST is set.
# The remote command is one argument built only from this script's fixed args.
kc() {
    if [ -n "${REMOTE_HOST}" ]; then
        ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_HOST}" "sudo k3s kubectl $*"
    else
        kubectl "$@"
    fi
}

echo ""
echo "=== Node Status ==="
if ! kc get nodes -o wide; then
    echo "Warning: Failed to get node status"
    exit 1
fi

echo ""
echo "=== System Pods ==="
if ! kc get pods -n kube-system; then
    echo "Warning: Failed to get system pods"
    exit 1
fi

echo ""
echo "=== Cluster Info ==="
kc cluster-info

# Check node readiness (grep exits 1 when every node is Ready; that is fine)
NODES=$(kc get nodes --no-headers)
NOT_READY=$(printf '%s\n' "$NODES" | { grep -v " Ready " || true; } | wc -l)
if [ "$NOT_READY" -gt 0 ]; then
    echo ""
    echo "Warning: $NOT_READY node(s) not in Ready state"
    echo "This may be normal if nodes are still initializing"
fi

echo ""
echo "Cluster verification complete"
