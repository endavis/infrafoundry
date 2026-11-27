#!/bin/bash
# shellcheck shell=bash
# Pinned SSH helpers for the reverse-proxy scripts. Sourced, never run directly.
#
# The caller sets RP_JUMPHOST (it may be empty), RP_SSH_USER and RP_KNOWN_HOSTS before
# sourcing, all validated. The VM's SSH host key is pinned (#1581): RP_KNOWN_HOSTS holds
# ";"-separated "<name>,<address> ssh-ed25519 <key>" lines, and nothing but that file is
# trusted for the VM. With a jumphost the file is staged there (mode 0600) for the inner
# hop; call rp_ssh_cleanup from the EXIT trap to remove it.

JUMPHOST="${RP_JUMPHOST:-}"
JUMP_SSH="ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=10"
JUMP_SSH_KEEPALIVE="${JUMP_SSH} -o ServerAliveInterval=30"

RP_KNOWN_HOSTS_FILE=$(mktemp)
RP_REMOTE_KNOWN_HOSTS=""

# Remove the local known_hosts file and the copy staged on the jumphost.
rp_ssh_cleanup() {
    rm -f "${RP_KNOWN_HOSTS_FILE}"
    if [ -n "${RP_REMOTE_KNOWN_HOSTS}" ]; then
        ${JUMP_SSH} "${JUMPHOST}" "rm -f '${RP_REMOTE_KNOWN_HOSTS}'" >/dev/null 2>&1 || true
        RP_REMOTE_KNOWN_HOSTS=""
    fi
}

# True when the ssh error file FILE shows the pinned host key did not match: retrying
# cannot help.
rp_host_key_error() {
    grep -Eq 'Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED|No ED25519 host key is known' "$1"
}

if [ -z "${RP_KNOWN_HOSTS:-}" ]; then
    echo "ERROR: no pinned SSH host keys (RP_KNOWN_HOSTS / ssh_known_hosts is empty)." >&2
    echo "       Run 'foundry secrets host-keys --env <env>' and re-apply." >&2
    rp_ssh_cleanup
    exit 1
fi
printf '%s\n' "${RP_KNOWN_HOSTS//;/$'\n'}" >"${RP_KNOWN_HOSTS_FILE}"
if grep -Evq '^[A-Za-z0-9._:,-]+ ssh-ed25519 [A-Za-z0-9+/]+={0,3}$' "${RP_KNOWN_HOSTS_FILE}"; then
    echo "ERROR: the pinned SSH host keys hold a malformed line; run 'foundry secrets host-keys --env <env>'" >&2
    rp_ssh_cleanup
    exit 1
fi

VM_KNOWN_HOSTS="${RP_KNOWN_HOSTS_FILE}"
if [ -n "${JUMPHOST}" ]; then
    RP_REMOTE_KNOWN_HOSTS=$(${JUMP_SSH} "${JUMPHOST}" 'umask 077; f=$(mktemp) && cat >"$f" && echo "$f"' <"${RP_KNOWN_HOSTS_FILE}") || {
        echo "ERROR: cannot stage the pinned host keys on ${JUMPHOST} (is the ssh-agent loaded?)" >&2
        RP_REMOTE_KNOWN_HOSTS=""
        rp_ssh_cleanup
        exit 1
    }
    VM_KNOWN_HOSTS="${RP_REMOTE_KNOWN_HOSTS}"
fi

SSH="ssh -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${VM_KNOWN_HOSTS} -o GlobalKnownHostsFile=/dev/null -o ConnectTimeout=10"
SSH_KEEPALIVE="${SSH} -o ServerAliveInterval=30"

# When JUMPHOST is set the inner ssh runs on the jumphost; otherwise ssh goes directly.
if [ -n "${JUMPHOST}" ]; then
    remote_cmd() {
        local ip="$1"
        shift
        ${JUMP_SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ${RP_SSH_USER}@${ip} '$*'"
    }
    remote_root_cmd() {
        local ip="$1"
        shift
        ${JUMP_SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ${RP_SSH_USER}@${ip} 'sudo bash -c \"$*\"'"
    }
else
    remote_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${RP_SSH_USER}@${ip}" "$*"
    }
    remote_root_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${RP_SSH_USER}@${ip}" "sudo bash -c \"$*\""
    }
fi
