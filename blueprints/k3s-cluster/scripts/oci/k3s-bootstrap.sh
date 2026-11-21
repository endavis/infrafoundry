#!/bin/bash
# k3s login user bootstrap — after_apply handler (OCI variant)
#
# Runs only playbooks/k3s-bootstrap.yml as the image's own user (ubuntu). The
# k3s-bootstrap role creates the ansible login user with the package's SSH
# public key and passwordless sudo. It is idempotent and never touches k3s, so
# it is safe on a running cluster and runs first on every apply, before the
# other handlers log in as ansible.
#
# Workflow after_apply handlers get no package variables, so the blueprint
# passes everything through its env: block:
#   K3S_CONTROL_NAME, K3S_WORKER_NAMES (comma-separated), K3S_TAILNET,
#   K3S_SSH_PUBLIC_KEY
#
# The handler has continue_on_error, so a failure is appended to
# INFRAFOUNDRY_WARNINGS_FILE and the step is retried on the next apply.

set -euo pipefail

BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
# shellcheck source=k3s-lib.sh
source "${BLUEPRINT_DIR}/scripts/oci/k3s-lib.sh"

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

warn() {
    if [ -n "${INFRAFOUNDRY_WARNINGS_FILE:-}" ]; then
        printf '{"source": "k3s-bootstrap", "message": "%s"}\n' "$1" >> "${INFRAFOUNDRY_WARNINGS_FILE}"
    fi
}

echo "=== k3s login user bootstrap ==="
echo "Control: ${CONTROL_NAME} (${CONTROL_HOST}), workers: ${#WORKER_NAMES[@]}"

rc=0
run_k3s_bootstrap || rc=$?
if [ "${rc}" -ne 0 ]; then
    warn "k3s login user bootstrap failed (exit ${rc}); it is retried on the next apply. It logs in as ${K3S_BOOTSTRAP_USER}, so the tailnet ssh rule must allow ${K3S_BOOTSTRAP_USER} as well as ${K3S_LOGIN_USER}"
    exit "${rc}"
fi
echo "=== k3s login user bootstrap done ==="
