#!/bin/bash
# Shared helpers for the OCI k3s scripts. Sourced, never run directly.
#
# Expects the caller to set TAILNET, CONTROL_NAME, CONTROL_HOST and the
# WORKER_NAMES array before it calls write_k3s_inventory.

# Login users. Every connection uses K3S_LOGIN_USER (ansible) once the
# k3s-bootstrap role has created it; the bootstrap itself connects as
# K3S_BOOTSTRAP_USER (ubuntu), the only user a fresh image has.
K3S_LOGIN_USER="${K3S_LOGIN_USER:-ansible}"
K3S_BOOTSTRAP_USER="${K3S_BOOTSTRAP_USER:-ubuntu}"

# host_fqdn NAME: the ansible_host for a node (FQDN on the tailnet if provided).
host_fqdn() {
    local name="$1"
    if [ -n "${TAILNET:-}" ]; then
        echo "${name}.${TAILNET}"
    else
        echo "${name}"
    fi
}

# write_k3s_inventory FILE [KEY: VALUE...]: write the Ansible inventory; each
# extra argument becomes a line under k3s_cluster vars.
write_k3s_inventory() {
    local file="$1"
    shift
    local name line
    {
        echo "all:"
        echo "  children:"
        echo "    k3s_control:"
        echo "      hosts:"
        echo "        ${CONTROL_NAME}:"
        echo "          ansible_host: ${CONTROL_HOST}"
        echo "          ansible_user: ${K3S_INVENTORY_USER:-${K3S_LOGIN_USER}}"
        echo "    k3s_workers:"
        echo "      hosts:"
        if [ ${#WORKER_NAMES[@]} -eq 0 ]; then
            echo "        {}"
        else
            for name in "${WORKER_NAMES[@]}"; do
                echo "        ${name}:"
                echo "          ansible_host: $(host_fqdn "${name}")"
                echo "          ansible_user: ${K3S_INVENTORY_USER:-${K3S_LOGIN_USER}}"
            done
        fi
        echo "    k3s_cluster:"
        echo "      children:"
        echo "        k3s_control: {}"
        echo "        k3s_workers: {}"
        echo "      vars:"
        for line in "$@"; do
            echo "        ${line}"
        done
    } > "${file}"
}

# write_k3s_dns_extra_vars OUTFILE: write the ansible extra vars (JSON) for the
# k3s-dns role from K3S_DNS_NAMESERVERS and K3S_DNS_SEARCH (comma-separated) and
# K3S_VCN_DNS_LABEL. An empty search list defaults to <label>.oraclevcn.com.
# Nameservers must be IP addresses and search domains plain hostnames, so
# nothing can inject lines into resolv.conf. Exits non-zero on invalid input.
write_k3s_dns_extra_vars() {
    python3 - "$1" <<'PY'
import ipaddress
import json
import os
import re
import sys


def items(name: str) -> list[str]:
    return [p.strip() for p in os.environ.get(name, "").split(",") if p.strip()]


servers = items("K3S_DNS_NAMESERVERS")
search = items("K3S_DNS_SEARCH")
label = os.environ.get("K3S_VCN_DNS_LABEL", "").strip()

try:
    servers = [str(ipaddress.ip_address(s)) for s in servers]
except ValueError as exc:
    sys.exit(f"ERROR: invalid k3s_dns_nameservers entry: {exc}")
if len(servers) > 3:
    sys.exit("ERROR: k3s_dns_nameservers takes at most 3 entries")
if servers and not search and label:
    search = [f"{label}.oraclevcn.com"]
for domain in search:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        sys.exit(f"ERROR: invalid k3s_dns_search entry: {domain!r}")
if not servers:
    search = []

with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({"k3s_dns_nameservers": servers, "k3s_dns_search": search}, fh)
PY
}

# write_k3s_bootstrap_extra_vars OUTFILE: write the ansible extra vars (JSON) for
# the k3s-bootstrap role from K3S_SSH_PUBLIC_KEY (one key per line). Every line
# must look like "<type> <base64> [comment]" with no control characters; empty
# input or anything else exits non-zero, so nothing can inject into
# authorized_keys.
write_k3s_bootstrap_extra_vars() {
    python3 - "$1" <<'PY'
import json
import os
import re
import sys

raw = os.environ.get("K3S_SSH_PUBLIC_KEY", "")
if "\r" in raw:
    sys.exit("ERROR: ssh_public_key must not contain carriage returns")
keys = [line.strip() for line in raw.split("\n") if line.strip()]
if not keys:
    sys.exit("ERROR: ssh_public_key is empty")
pattern = re.compile(r"(ssh-[a-z0-9]+|ecdsa-sha2-[a-z0-9]+|sk-[a-z0-9@.-]+) [A-Za-z0-9+/=]+( [ -~]*)?")
for key in keys:
    if not pattern.fullmatch(key):
        sys.exit("ERROR: ssh_public_key has an invalid line (expected '<type> <base64> [comment]')")

with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({"k3s_bootstrap_ssh_public_keys": keys}, fh)
PY
}

# run_k3s_bootstrap: run playbooks/k3s-bootstrap.yml as K3S_BOOTSTRAP_USER. Needs
# BLUEPRINT_DIR, CONTROL_NAME, CONTROL_HOST, WORKER_NAMES and K3S_SSH_PUBLIC_KEY.
# Uses only the blueprint's own roles. Returns ansible-playbook's exit code.
run_k3s_bootstrap() {
    local inv vars rc=0
    inv="$(mktemp -t k3s-bootstrap-inventory-XXXXXX.yml)"
    vars="$(mktemp -t k3s-bootstrap-vars-XXXXXX.json)"
    if ! write_k3s_bootstrap_extra_vars "${vars}"; then
        rm -f "${inv}" "${vars}"
        return 1
    fi
    K3S_INVENTORY_USER="${K3S_BOOTSTRAP_USER}" write_k3s_inventory "${inv}"
    ANSIBLE_ROLES_PATH="${BLUEPRINT_DIR}/roles" ANSIBLE_HOST_KEY_CHECKING=False \
        ansible-playbook -i "${inv}" -e "@${vars}" "${BLUEPRINT_DIR}/playbooks/k3s-bootstrap.yml" || rc=$?
    rm -f "${inv}" "${vars}"
    return "${rc}"
}
