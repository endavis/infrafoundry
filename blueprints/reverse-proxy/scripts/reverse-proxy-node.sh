#!/bin/bash
# Reverse proxy node step. Runs on the proxy VM as root, piped over ssh after the lines
# RP_CADDYFILE_B64=<base64 Caddyfile or empty> and RP_CERT_DIR=<dir>. Idempotent:
# installs Caddy if missing, ensures the certificate directory, and replaces the Caddyfile
# and reloads Caddy only when the validated candidate differs from the live file.
#
# Exit codes: 0 done or unchanged; 3 certificate files are missing; other: failure.

set -euo pipefail

CADDYFILE_B64="${RP_CADDYFILE_B64:-}"
CERT_DIR="${RP_CERT_DIR:?RP_CERT_DIR is not set}"
CADDYFILE_PATH="${RP_CADDYFILE_PATH:-/etc/caddy/Caddyfile}"

[[ "${CADDYFILE_B64}" =~ ^[A-Za-z0-9+/=]*$ ]] || { echo "ERROR: malformed Caddyfile payload" >&2; exit 1; }
[[ "${CERT_DIR}" =~ ^/[A-Za-z0-9._/-]*$ ]] || { echo "ERROR: invalid certificate directory" >&2; exit 1; }

if ! command -v caddy >/dev/null 2>&1; then
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "ERROR: caddy is missing and this system is not apt-based" >&2
        exit 1
    fi
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
fi

install -d -o root -g caddy -m 0750 "${CERT_DIR}"

if [ -z "${CADDYFILE_B64}" ]; then
    echo "no Caddyfile to install"
    exit 0
fi

tmp=$(mktemp)
trap 'rm -f "${tmp}"' EXIT
printf '%s' "${CADDYFILE_B64}" | base64 -d >"${tmp}"

if [ ! -s "${CERT_DIR}/proxy.fullchain.pem" ] || [ ! -s "${CERT_DIR}/proxy.key" ]; then
    echo "certificate files missing in ${CERT_DIR}; run 'foundry certs issue'" >&2
    exit 3
fi

if [ -f "${CADDYFILE_PATH}" ] && cmp -s "${tmp}" "${CADDYFILE_PATH}"; then
    echo "Caddyfile unchanged"
    exit 0
fi

caddy validate --adapter caddyfile --config "${tmp}"

install -o root -g caddy -m 0640 "${tmp}" "${CADDYFILE_PATH}.new"
mv -f "${CADDYFILE_PATH}.new" "${CADDYFILE_PATH}"

systemctl enable caddy
if systemctl is-active --quiet caddy; then
    systemctl reload caddy
else
    systemctl restart caddy
fi
echo "Caddyfile installed and Caddy reloaded"
