#!/bin/bash
# shellcheck shell=bash
# Shared SSH helpers for the Proxmox k3s scripts. Sourced, never run directly.
#
# The caller sets JUMPHOST (it may be empty) before sourcing; the helpers are
# chosen when this file is sourced.

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
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
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} '$*'"
    }

    # Helper: run command as root on a remote node via jumphost (for installs/system config)
    remote_root_cmd() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'sudo PATH=/usr/local/bin:\$PATH bash -c \"$*\"'"
    }

    # Helper: run kubectl on k3s server as root via sudo (the node kubeconfig is owner-only)
    remote_kubectl() {
        local ip="$1"
        shift
        ${SSH_KEEPALIVE} "${JUMPHOST}" "${SSH} ansible@${ip} 'sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml PATH=/usr/local/bin:\$PATH $*'"
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
