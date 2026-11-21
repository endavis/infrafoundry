#!/bin/bash
# shellcheck shell=bash
# Shared SSH helpers for the Proxmox k3s scripts. Sourced, never run directly.
#
# The caller sets JUMPHOST (it may be empty) before sourcing; the helpers are
# chosen when this file is sourced.
#
# The nodes' SSH host keys are pinned (#1581): InfraFoundry generated them, cloud-init
# installed them, and K3S_KNOWN_HOSTS (or the INFRAFOUNDRY_VAR_ssh_known_hosts package
# variable) holds the public halves as ";"-separated "<name>,<address> ssh-ed25519 <key>"
# lines. Nothing but that file is trusted for a node. With a jumphost the file is staged
# there (mode 0600) for the inner hop; call k3s_ssh_cleanup from the EXIT trap to remove it.

# The hop to the jumphost is verified against the operator's own known_hosts.
JUMP_SSH="ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=10"
JUMP_SSH_KEEPALIVE="${JUMP_SSH} -o ServerAliveInterval=30"

K3S_KNOWN_HOSTS_FILE=$(mktemp)
K3S_REMOTE_KNOWN_HOSTS=""

# Remove the local known_hosts file and the copy staged on the jumphost.
k3s_ssh_cleanup() {
    rm -f "${K3S_KNOWN_HOSTS_FILE}"
    if [ -n "${K3S_REMOTE_KNOWN_HOSTS}" ]; then
        ${JUMP_SSH} "${JUMPHOST}" "rm -f '${K3S_REMOTE_KNOWN_HOSTS}'" >/dev/null 2>&1 || true
        K3S_REMOTE_KNOWN_HOSTS=""
    fi
}

# True when the ssh error file FILE shows the pinned host key did not match: retrying
# cannot help.
k3s_host_key_error() {
    grep -Eq 'Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED|No ED25519 host key is known' "$1"
}

_k3s_known_hosts_value="${K3S_KNOWN_HOSTS:-${INFRAFOUNDRY_VAR_ssh_known_hosts:-}}"
if [ -z "${_k3s_known_hosts_value}" ]; then
    echo "ERROR: no pinned SSH host keys (K3S_KNOWN_HOSTS / ssh_known_hosts is empty)." >&2
    echo "       Run 'foundry secrets host-keys --env <env>' and re-apply." >&2
    k3s_ssh_cleanup
    exit 1
fi
printf '%s\n' "${_k3s_known_hosts_value//;/$'\n'}" >"${K3S_KNOWN_HOSTS_FILE}"
if grep -Evq '^[A-Za-z0-9._:,-]+ ssh-ed25519 [A-Za-z0-9+/]+={0,3}$' "${K3S_KNOWN_HOSTS_FILE}"; then
    echo "ERROR: the pinned SSH host keys hold a malformed line; run 'foundry secrets host-keys --env <env>'" >&2
    k3s_ssh_cleanup
    exit 1
fi

VM_KNOWN_HOSTS="${K3S_KNOWN_HOSTS_FILE}"
if [ -n "${JUMPHOST}" ]; then
    K3S_REMOTE_KNOWN_HOSTS=$(${JUMP_SSH} "${JUMPHOST}" 'umask 077; f=$(mktemp) && cat >"$f" && echo "$f"' <"${K3S_KNOWN_HOSTS_FILE}") || {
        echo "ERROR: cannot stage the pinned host keys on ${JUMPHOST} (is the ssh-agent loaded?)" >&2
        K3S_REMOTE_KNOWN_HOSTS=""
        k3s_ssh_cleanup
        exit 1
    }
    VM_KNOWN_HOSTS="${K3S_REMOTE_KNOWN_HOSTS}"
fi

SSH="ssh -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${VM_KNOWN_HOSTS} -o GlobalKnownHostsFile=/dev/null -o ConnectTimeout=10"
SSH_KEEPALIVE="${SSH} -o ServerAliveInterval=30"

# SSH helpers — when JUMPHOST is set, tunnel through it (run inner ssh on the
# jumphost). When JUMPHOST is empty, ssh directly from the InfraFoundry host
# to the target node. Direct mode is suitable when the workstation has line-of-
# sight to the cluster network.

if [ -n "${JUMPHOST}" ]; then
    # Helper: run command on a remote node via jumphost (as ansible user)
    remote_cmd() {
        local ip="$1"
        shift
        ${JUMP_SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} '$*'"
    }

    # Helper: run command as root on a remote node via jumphost (for installs/system config)
    remote_root_cmd() {
        local ip="$1"
        shift
        ${JUMP_SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'sudo PATH=/usr/local/bin:\$PATH bash -c \"$*\"'"
    }

    # Helper: run kubectl on k3s server as root via sudo (the node kubeconfig is owner-only)
    remote_kubectl() {
        local ip="$1"
        shift
        ${JUMP_SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml PATH=/usr/local/bin:\$PATH $*'"
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

    # Helper: run kubectl on k3s server as root via sudo directly (the node kubeconfig is owner-only)
    remote_kubectl() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "ansible@${ip}" "sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml PATH=/usr/local/bin:\$PATH $*"
    }
fi
