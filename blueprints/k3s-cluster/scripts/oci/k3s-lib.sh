#!/bin/bash
# Shared helpers for the OCI k3s scripts. Sourced, never run directly.
#
# Expects the caller to set TAILNET, CONTROL_NAME, CONTROL_HOST and the
# WORKER_NAMES array before it calls write_k3s_inventory.

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
        echo "          ansible_user: ubuntu"
        echo "    k3s_workers:"
        echo "      hosts:"
        if [ ${#WORKER_NAMES[@]} -eq 0 ]; then
            echo "        {}"
        else
            for name in "${WORKER_NAMES[@]}"; do
                echo "        ${name}:"
                echo "          ansible_host: $(host_fqdn "${name}")"
                echo "          ansible_user: ubuntu"
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
