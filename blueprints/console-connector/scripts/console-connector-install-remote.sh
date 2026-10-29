#!/bin/bash
# NetApp Console agent install script — runs on the target Console agent VM
#
# This is **not** a framework event-handler script and does **not** follow the
# jumphost portability contract used by `console-connector-post-terraform.sh`.
# It is Ubuntu 24.04 apt tooling, uploaded and executed on the provisioned VM.
#
# Runs on:
#   The Console agent Ubuntu 24.04 Proxmox VM (cloned from `ubuntu-template`).
#   NOT the jumphost, NOT the InfraFoundry orchestration host.
#
# Invoked by:
#   `console-connector-post-terraform.sh` via `remote_upload` (scp) +
#   `remote_cmd_long` (ssh) in Phase 3. The caller runs as the non-root
#   `ansible` user; this script uses `sudo` for privileged steps.
#
# Environment variables:
#   DOCKER_VERSION              Required. Docker Engine version, in the supported
#                               range 23.0.6 to 28.0.0 (e.g. 27.5.1). Matched against
#                               the docker-ce apt versions ("5:<version>-...").
#   CONSOLE_AGENT_URL_BASE      Required. Base URL hosting the installer.
#   CONSOLE_AGENT_INSTALLER     Required. Installer file name
#                               (NetApp_Console_Agent_Cloud_<version>).
#   CONSOLE_AGENT_INSTALL_ARGS  Optional. Extra installer flags (--proxy, --cacert).
#
# Target OS tool assumptions (Ubuntu 24.04 cloud image):
#   bash, sudo, apt-get, apt-cache, curl, gpg (gnupg), df, awk, tail, dpkg,
#   systemctl, docker (installed by this script)
#
# Side effects (on the target VM):
#   - Adds Docker's apt repository and installs docker-ce at DOCKER_VERSION
#   - Downloads the installer to /tmp/console-connector-install/
#   - Runs the installer as root (creates /opt/application/netapp, containers)
#
# Source for the requirements: docs.netapp.com/us-en/console-setup-admin/task-install-agent-on-prem.html
set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

: "${DOCKER_VERSION:?required}"
: "${CONSOLE_AGENT_URL_BASE:?required}"
: "${CONSOLE_AGENT_INSTALLER:?required}"
CONSOLE_AGENT_INSTALL_ARGS="${CONSOLE_AGENT_INSTALL_ARGS:-}"

# Free space required, in GiB (verified from the NetApp install page).
OPT_REQUIRED_GIB=120   # /opt/application/netapp
VAR_REQUIRED_GIB=40    # /var/lib/docker

# --- Idempotency: the ONLY place that decides "agent already installed". ---
# UNCONFIRMED: these markers are not documented by NetApp; verify on a live
# install and adjust here (and only here).
console_agent_installed() {
    [ -d /opt/application/netapp ] || return 1
    command -v docker >/dev/null 2>&1 || return 1
    # At least one running container means the agent services are up.
    [ -n "$(sudo docker ps -q 2>/dev/null)" ]
}

if console_agent_installed; then
    log "Console agent already installed; skipping"
    echo "CONSOLE_AGENT_INSTALL_COMPLETE"
    exit 0
fi

# The installer fails when proxy variables are set (use --proxy instead).
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

avail_gib() { df -BG --output=avail "$1" | tail -n 1 | tr -dc '0-9'; }
fs_source() { df --output=source "$1" | tail -n 1; }

log "=== Step 1: Checking free disk space ==="
mkdir -p /tmp/console-connector-install
sudo mkdir -p /opt /var/lib
opt_avail=$(avail_gib /opt)
var_avail=$(avail_gib /var)
if [ "$(fs_source /opt)" = "$(fs_source /var)" ]; then
    need=$((OPT_REQUIRED_GIB + VAR_REQUIRED_GIB))
    if [ "$opt_avail" -lt "$need" ]; then
        echo "ERROR: /opt and /var share a filesystem; need ${need} GiB, have ${opt_avail} GiB" >&2
        exit 1
    fi
else
    if [ "$opt_avail" -lt "$OPT_REQUIRED_GIB" ] || [ "$var_avail" -lt "$VAR_REQUIRED_GIB" ]; then
        echo "ERROR: need ${OPT_REQUIRED_GIB} GiB on /opt and ${VAR_REQUIRED_GIB} GiB on /var" >&2
        exit 1
    fi
fi

log "=== Step 2: Installing Docker Engine ${DOCKER_VERSION} ==="
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -y
docker_apt_version=$(apt-cache madison docker-ce | awk -F'|' -v v="5:${DOCKER_VERSION}-" 'index($2, v) > 0 { gsub(/ /, "", $2); print $2; exit }')
if [ -z "$docker_apt_version" ]; then
    echo "ERROR: docker-ce ${DOCKER_VERSION} not found in the apt repository; see 'apt-cache madison docker-ce'" >&2
    exit 1
fi
echo "  Installing docker-ce ${docker_apt_version}"
sudo apt-get install -y "docker-ce=${docker_apt_version}" "docker-ce-cli=${docker_apt_version}" containerd.io
sudo apt-mark hold docker-ce docker-ce-cli
sudo systemctl enable --now docker

log "=== Step 3: Downloading the Console agent installer ==="
cd /tmp/console-connector-install
curl -4 -fsSO "${CONSOLE_AGENT_URL_BASE}/${CONSOLE_AGENT_INSTALLER}"
chmod +x "${CONSOLE_AGENT_INSTALLER}"

log "=== Step 4: Running the Console agent installer ==="
echo "This may take several minutes..."
# CONSOLE_AGENT_INSTALL_ARGS is intentionally word-split (flags such as --proxy).
# shellcheck disable=SC2086
sudo env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY "./${CONSOLE_AGENT_INSTALLER}" ${CONSOLE_AGENT_INSTALL_ARGS}

echo ""
echo "CONSOLE_AGENT_INSTALL_COMPLETE"
