#!/bin/bash
# OpenWrt VM — Post-Terraform Event Handler
#
# Triggered by the on_create resource lifecycle event once the VM exists.
# Boots it and bootstraps it over the serial console (openwrt-bootstrap.yml),
# then waits until the SSH server at mgmt_ip sends its banner and presents the
# pinned host key (#1650).
#
# Environment variables (injected by ScriptHandler):
#   INFRAFOUNDRY_PACKAGE_DIR   - required: path to the consuming env package dir
#   INFRAFOUNDRY_BLUEPRINT_DIR - required: path to this blueprint dir
#   INFRAFOUNDRY_VAR_<key>     - package variables. ssh_host_keys_dropbear holds the
#                                pinned host key for the bootstrap: never print it.
#   On a jumphost run both directories are the framework's remote copies:
#   BLUEPRINT_DIR is the rsynced blueprint tree, PACKAGE_DIR an empty per-run
#   scratch directory (consumer files are not copied).

set -euo pipefail

PACKAGE_DIR="${INFRAFOUNDRY_PACKAGE_DIR:?required: run via foundry, not directly}"
BLUEPRINT_DIR="${INFRAFOUNDRY_BLUEPRINT_DIR:?required: run via foundry, not directly}"
PLAYBOOK="${BLUEPRINT_DIR}/openwrt-bootstrap.yml"

for var in vmid vm_name target_node pve_host ssh_public_key mgmt_ip; do
    name="INFRAFOUNDRY_VAR_${var}"
    if [ -z "${!name:-}" ]; then
        echo "ERROR: ${name} is not set — run via 'foundry infra apply' with the package variables" >&2
        exit 1
    fi
done

# The VM's host key is pinned (ADR-0032): ssh_known_hosts (";"-separated
# "<name>,<address> ssh-ed25519 <key>" lines) holds the public half and
# ssh_host_keys_dropbear the key the bootstrap installs. Neither value is printed.
VM_NAME="${INFRAFOUNDRY_VAR_vm_name}"
HINT="run 'foundry secrets host-keys --env <env>' and apply again"
KNOWN_HOSTS_LINES=""
IFS=';' read -r -a _known <<<"${INFRAFOUNDRY_VAR_ssh_known_hosts:-}"
_line_re='^([A-Za-z0-9._:,-]+) ssh-ed25519 [A-Za-z0-9+/]+={0,3}$'
for _line in ${_known[@]+"${_known[@]}"}; do
    if [[ $_line =~ $_line_re ]]; then
        case ",${BASH_REMATCH[1]}," in
        *",${VM_NAME},"*) KNOWN_HOSTS_LINES+="${_line}"$'\n' ;;
        esac
    fi
done
if [ -z "$KNOWN_HOSTS_LINES" ]; then
    echo "ERROR: ssh_known_hosts has no well-formed pinned host key for ${VM_NAME}; ${HINT}" >&2
    exit 1
fi
if ! [[ ";${INFRAFOUNDRY_VAR_ssh_host_keys_dropbear:-};" =~ \;${VM_NAME}=[0-9a-f]{166}\; ]]; then
    echo "ERROR: ssh_host_keys_dropbear has no usable key for ${VM_NAME}; ${HINT}" >&2
    exit 1
fi

for tool in ssh ssh-keyscan; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: ${tool} is required but was not found on PATH" >&2
        exit 127
    fi
done

if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "ERROR: ansible-playbook is required but was not found on PATH" >&2
    exit 127
fi

INVENTORY="${PACKAGE_DIR}/.generated-inventory.json"
python3 -c "
import json, os, sys
inventory = {
    'proxmox_host': {
        'hosts': {
            os.environ['INFRAFOUNDRY_VAR_target_node']: {
                'ansible_host': os.environ['INFRAFOUNDRY_VAR_pve_host'],
                'ansible_user': 'root',
            },
        },
    },
}
with open(sys.argv[1], 'w') as f:
    json.dump(inventory, f, indent=2)
" "$INVENTORY"

echo "Bootstrapping OpenWrt VM ${INFRAFOUNDRY_VAR_vmid} on ${INFRAFOUNDRY_VAR_target_node}..."
cd "$BLUEPRINT_DIR"
ansible-playbook -i "$INVENTORY" "$PLAYBOOK"

# The probe reads the SSH banner only: no key or credential is used.
MGMT_IP="${INFRAFOUNDRY_VAR_mgmt_ip}"
TIMEOUT="${INFRAFOUNDRY_VAR_boot_timeout:-300}"
echo "Waiting up to ${TIMEOUT}s for an SSH banner from ${MGMT_IP}:22..."
ELAPSED=0
while :; do
    banner=$(timeout 5 bash -c 'exec 3<>/dev/tcp/$1/22; head -c 4 <&3' _ "$MGMT_IP" 2>/dev/null || true)
    if [ "$banner" = "SSH-" ]; then
        echo "OpenWrt SSH is up at ${MGMT_IP}"
        break
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: SSH did not answer within ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

# Verify the pinned host key: strict checking against a file that holds only this VM's
# pinned lines. Authentication is switched off, so no credential is used; the key is
# checked before authentication, and "Permission denied" therefore means it matched.
KNOWN_HOSTS=$(mktemp)
trap 'rm -f "$KNOWN_HOSTS"' EXIT
printf '%s' "$KNOWN_HOSTS_LINES" >"$KNOWN_HOSTS"
while :; do
    rc=0
    out=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
        -o "UserKnownHostsFile=${KNOWN_HOSTS}" -o GlobalKnownHostsFile=/dev/null \
        -o HostKeyAlgorithms=ssh-ed25519 -o PreferredAuthentications=none \
        -o ConnectTimeout=10 "root@${MGMT_IP}" true 2>&1) || rc=$?
    if grep -Eq 'Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED|No ED25519 host key is known' <<<"$out"; then
        echo "ERROR: ${VM_NAME} (${MGMT_IP}) does not present the pinned host key" >&2
        echo "       (ssh_host_keys.${VM_NAME} in the package secrets.yaml). If the VM was rebuilt," >&2
        echo "       destroy it, run 'foundry secrets host-keys --env <env> --regenerate ${VM_NAME}'," >&2
        echo "       then apply again." >&2
        exit 1
    fi
    if [ "$rc" -eq 0 ] || grep -q 'Permission denied' <<<"$out"; then
        echo "Pinned host key verified for ${VM_NAME} at ${MGMT_IP}"
        break
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: could not verify the host key within ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

# Only the pinned ed25519 key may be served; the bootstrap limits dropbear to it (keyfile).
other=$(ssh-keyscan -t rsa,ecdsa -T 5 "$MGMT_IP" 2>/dev/null | grep -v '^#' || true)
if [ -n "$other" ]; then
    echo "ERROR: ${VM_NAME} (${MGMT_IP}) still serves an unpinned RSA or ECDSA host key" >&2
    exit 1
fi
echo "OpenWrt SSH is up at ${MGMT_IP} with the pinned host key"
