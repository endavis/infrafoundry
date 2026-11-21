#!/bin/bash
# k3s node kubeconfig mode — node-side script (Proxmox variant)
#
# Runs as root on the k3s server node; the after_apply handler pipes it over
# ssh (`bash -s`). Makes the node kubeconfig owner-only and keeps it that way
# across a k3s restart:
#   1. config.yaml: write-kubeconfig-mode: "0600"
#   2. systemd unit: rewrite a --write-kubeconfig-mode flag to 600 (command-line
#      flags take precedence over config.yaml), then daemon-reload
#   3. chmod 600 on k3s.yaml
# It restarts nothing and is idempotent.
#
# Arguments exist for tests only:
#   $1  config directory   (default /etc/rancher/k3s)
#   $2  systemd unit file  (default /etc/systemd/system/k3s.service)

set -euo pipefail

CONFIG_DIR="${1:-/etc/rancher/k3s}"
UNIT_FILE="${2:-/etc/systemd/system/k3s.service}"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
KUBECONFIG_FILE="${CONFIG_DIR}/k3s.yaml"
WANT_LINE='write-kubeconfig-mode: "0600"'

# --- 1. config.yaml ---
mkdir -p "${CONFIG_DIR}"
if [ ! -f "${CONFIG_FILE}" ]; then
    printf '%s\n' "${WANT_LINE}" > "${CONFIG_FILE}"
    echo "config.yaml: created with ${WANT_LINE}"
else
    tmp_cfg="$(mktemp)"
    if grep -q '^write-kubeconfig-mode:' "${CONFIG_FILE}"; then
        # Keep the first such line (rewritten), drop any duplicates.
        awk -v want="${WANT_LINE}" '
            /^write-kubeconfig-mode:/ { if (!seen) { print want; seen = 1 } ; next }
            { print }
        ' "${CONFIG_FILE}" > "${tmp_cfg}"
    else
        cat "${CONFIG_FILE}" > "${tmp_cfg}"
        if [ -s "${tmp_cfg}" ] && [ -n "$(tail -c1 "${tmp_cfg}")" ]; then
            printf '\n' >> "${tmp_cfg}"
        fi
        printf '%s\n' "${WANT_LINE}" >> "${tmp_cfg}"
    fi
    if cmp -s "${tmp_cfg}" "${CONFIG_FILE}"; then
        echo "config.yaml: already set"
    else
        cat "${tmp_cfg}" > "${CONFIG_FILE}"
        echo "config.yaml: set ${WANT_LINE}"
    fi
    rm -f "${tmp_cfg}"
fi

# --- 2. systemd unit ---
if [ -f "${UNIT_FILE}" ]; then
    tmp_unit="$(mktemp)"
    sed -E \
        -e "/^[[:space:]]*'--write-kubeconfig-mode'[[:space:]]*\\\\?\$/{n;s/'[0-7]{3,4}'/'600'/}" \
        -e "s/'--write-kubeconfig-mode=[0-7]{3,4}'/'--write-kubeconfig-mode=600'/" \
        "${UNIT_FILE}" > "${tmp_unit}"
    if ! cmp -s "${tmp_unit}" "${UNIT_FILE}"; then
        chmod --reference="${UNIT_FILE}" "${tmp_unit}"
        mv "${tmp_unit}" "${UNIT_FILE}"
        systemctl daemon-reload
        echo "unit: set --write-kubeconfig-mode to 600 and ran daemon-reload"
    else
        rm -f "${tmp_unit}"
        echo "unit: no change"
    fi

    # Post-check: every flag occurrence must carry 600/0600.
    flat="$(tr '\n\\' '  ' < "${UNIT_FILE}")"
    total=$(printf '%s' "${flat}" | grep -o 'write-kubeconfig-mode' | wc -l || true)
    good=$(printf '%s' "${flat}" \
        | grep -oE "write-kubeconfig-mode'?[[:space:]=]+'?0?600('|[[:space:]]|\$)" | wc -l || true)
    if [ "${total}" -ne "${good}" ]; then
        echo "ERROR: ${UNIT_FILE} still sets --write-kubeconfig-mode to a value other than 600" >&2
        exit 3
    fi
else
    echo "unit: ${UNIT_FILE} not present"
fi

# --- 3. kubeconfig file mode ---
if [ -f "${KUBECONFIG_FILE}" ]; then
    chmod 600 "${KUBECONFIG_FILE}"
    echo "k3s.yaml: mode 600"
else
    echo "k3s.yaml: not present"
fi
