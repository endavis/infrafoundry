#!/bin/bash
# k3s cluster DNS — after_apply handler (OCI variant)
#
# Runs only playbooks/k3s-dns.yml, which writes a resolver file and a kubelet
# drop-in on every node and restarts the existing k3s units when they changed.
# It never runs the k3s-server or k3s-agent roles and never uninstalls k3s, so
# it is safe on a running cluster.
#
# Workflow after_apply handlers get no package variables, so the blueprint
# passes everything through its env: block:
#   K3S_CONTROL_NAME, K3S_WORKER_NAMES (comma-separated), K3S_TAILNET,
#   K3S_DNS_NAMESERVERS (comma-separated), K3S_DNS_SEARCH (comma-separated),
#   K3S_VCN_DNS_LABEL, K3S_KNOWN_HOSTS (the pinned SSH host keys, ";"-separated)
#
# The handler runs on the operator host (never a jumphost) and has
# continue_on_error, so a failure is appended to INFRAFOUNDRY_WARNINGS_FILE and
# the step is retried on the next apply.

set -euo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
# shellcheck source=k3s-lib.sh
source "${BLUEPRINT_DIR}/scripts/oci/k3s-lib.sh"

if [ -z "${K3S_DNS_NAMESERVERS:-}" ]; then
    echo "k3s cluster DNS isolation is disabled (k3s_dns_nameservers is empty)"
    exit 0
fi

CONTROL_NAME="${K3S_CONTROL_NAME:-}"
if [ -z "${CONTROL_NAME}" ]; then
    echo "ERROR: K3S_CONTROL_NAME is not set" >&2
    exit 1
fi
TAILNET="${K3S_TAILNET:-}"
CONTROL_HOST=$(host_fqdn "${CONTROL_NAME}")
WORKER_NAMES=()
IFS=',' read -r -a _workers <<< "${K3S_WORKER_NAMES:-}"
for _w in "${_workers[@]}"; do
    [ -n "${_w}" ] && WORKER_NAMES+=("${_w}")
done

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook is required but was not found on PATH" >&2
    exit 127
fi

PLAYBOOK="${BLUEPRINT_DIR}/playbooks/k3s-dns.yml"
# Only the blueprint's own k3s-dns role is used here; this step never takes a
# roles/ override from the config repo.
ROLES_PATH="${BLUEPRINT_DIR}/roles"

INVENTORY_FILE="$(mktemp -t k3s-dns-inventory-XXXXXX.yml)"
EXTRA_VARS_FILE="$(mktemp -t k3s-dns-vars-XXXXXX.json)"
trap 'rm -f "${INVENTORY_FILE}" "${EXTRA_VARS_FILE}"; k3s_ssh_cleanup' EXIT

warn() {
    if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
        printf '{"source": "k3s-dns", "message": "%s"}\n' "$1" >> "${INFRAFOUNDRY_WARNINGS_FILE}"
    fi
}

k3s_pin_host_keys || { warn "no pinned SSH host keys; run 'foundry secrets host-keys --env <env>'"; exit 1; }

write_k3s_inventory "${INVENTORY_FILE}"
write_k3s_dns_extra_vars "${EXTRA_VARS_FILE}"

echo "=== k3s cluster DNS ==="
echo "Control: ${CONTROL_NAME} (${CONTROL_HOST}), workers: ${#WORKER_NAMES[@]}"

export ANSIBLE_ROLES_PATH="${ROLES_PATH}"

rc=0
ansible-playbook -i "${INVENTORY_FILE}" -e "@${EXTRA_VARS_FILE}" "${PLAYBOOK}" || rc=$?
if [ "${rc}" -ne 0 ]; then
    warn "k3s cluster DNS step failed (exit ${rc}); it is retried on the next apply. If CoreDNS was not restarted, run: kubectl -n kube-system rollout restart deployment/coredns"
    exit "${rc}"
fi
echo "=== k3s cluster DNS done ==="
