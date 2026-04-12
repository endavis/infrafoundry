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
#   KUBECONFIG - Path to kubeconfig (defaults to ~/.kube/oci-k3s.yaml)

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/oci-k3s.yaml}"

echo "Verifying K3s cluster health for environment: ${INFRAFOUNDRY_ENV:-unknown}"
echo "Using kubeconfig: $KUBECONFIG"

# Check if kubeconfig exists
if [ ! -f "$KUBECONFIG" ]; then
    echo "Warning: Kubeconfig not found at $KUBECONFIG"
    echo "This is normal on first deploy - Ansible will create it"
    exit 0
fi

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Warning: kubectl not found in PATH"
    echo "Install kubectl to enable cluster verification"
    exit 0
fi

export KUBECONFIG

echo ""
echo "=== Node Status ==="
if ! kubectl get nodes -o wide; then
    echo "Warning: Failed to get node status"
    exit 1
fi

echo ""
echo "=== System Pods ==="
if ! kubectl get pods -n kube-system; then
    echo "Warning: Failed to get system pods"
    exit 1
fi

echo ""
echo "=== Cluster Info ==="
kubectl cluster-info

# Check node readiness
NOT_READY=$(kubectl get nodes --no-headers | grep -v " Ready " | wc -l)
if [ "$NOT_READY" -gt 0 ]; then
    echo ""
    echo "Warning: $NOT_READY node(s) not in Ready state"
    echo "This may be normal if nodes are still initializing"
fi

echo ""
echo "Cluster verification complete"
