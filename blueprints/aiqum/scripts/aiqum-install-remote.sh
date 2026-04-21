#!/bin/bash
# AIQUM RPM install script — runs on the target AIQUM VM
#
# This is **not** a framework event-handler script and does **not** follow the
# jumphost portability contract used by `aiqum-post-terraform.sh`. It is
# specifically Rocky 9 RPM-family tooling and is uploaded + executed on the
# provisioned AIQUM VM itself.
#
# Runs on:
#   The AIQUM Rocky 9 Proxmox VM (cloned from the `rocky9-template` blueprint).
#   NOT the jumphost, NOT the InfraFoundry orchestration host.
#
# Invoked by:
#   `aiqum-post-terraform.sh` via `remote_upload` (scp) + `remote_cmd_long`
#   (ssh) in Phase 2 of the post-deploy flow. The caller runs as the
#   non-root `ansible` user; this script uses `sudo` for privileged steps.
#
# Environment variables:
#   AIQUM_URL_BASE  Required. Base URL hosting the AIQUM RPM and sibling
#                   install scripts:
#                     - netapp-um-9.18-el9.x86_64.rpm (~1.9 GB)
#                     - pre_install_check.sh
#                     - install7zip.sh
#
# Target OS tool assumptions (all present in the Rocky 9 base install
# unless noted):
#   - bash 4+
#   - sudo
#   - yum (RPM package manager)
#   - curl
#   - systemctl (systemd)
#   - firewall-cmd (installed by step 5 if absent — firewalld is not in the
#     minimal Rocky 9 base)
#   - rpm
#   - awk, ls (coreutils)
#   `wget` is NOT assumed — step 1 installs it before use.
#
# Side effects (on the target VM):
#   - Installs `wget` + `unzip`
#   - Configures the EPEL and MySQL 8.4 Community yum repositories
#   - Installs 7-Zip (via the hosted `install7zip.sh`)
#   - Installs and enables `firewalld`; opens AIQUM ports
#     (80, 443, 8080, 9443, 56072, 56080, 56443)
#   - Downloads the AIQUM RPM (~1.9 GB) to `/tmp/aiqum-install/`
#   - Runs `pre_install_check.sh`
#   - Installs the `netapp-um-9.18-el9.x86_64.rpm` + ~225 dependencies
set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

AIQUM_URL_BASE="${AIQUM_URL_BASE:-http://your-web-server/applications/aiqum}"

mkdir -p /tmp/aiqum-install
cd /tmp/aiqum-install

# --- Step 1: Install basic tools ---
log "=== Step 1: Installing basic tools ==="
sudo yum install -y wget unzip

# --- Step 2: Configure EPEL repository ---
echo ""
log "=== Step 2: Configuring EPEL repository ==="
wget -4 -q https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm -O epel-release-latest-9.noarch.rpm
sudo yum install -y ./epel-release-latest-9.noarch.rpm

# --- Step 3: Configure MySQL 8.4 Community repository ---
echo ""
log "=== Step 3: Configuring MySQL 8.4 Community repository ==="
wget -4 -q http://repo.mysql.com/yum/mysql-8.4-community/el/9/x86_64/mysql84-community-release-el9-1.noarch.rpm -O mysql84-community-release-el9-1.noarch.rpm
sudo yum install -y ./mysql84-community-release-el9-1.noarch.rpm

# --- Step 4: Install 7-Zip ---
echo ""
log "=== Step 4: Installing 7-Zip ==="
curl -4 -sO "${AIQUM_URL_BASE}/install7zip.sh"
chmod +x install7zip.sh
sudo bash install7zip.sh

# --- Step 5: Install firewalld and open AIQUM ports ---
echo ""
log "=== Step 5: Configuring firewall ==="
sudo yum install -y firewalld
sudo systemctl enable firewalld
sudo systemctl start firewalld
# AIQUM requires: 443 (web/API), 9443 (cluster agent AMQP), 80, 8080, 56072, 56080, 56443
sudo firewall-cmd --permanent \
    --add-port=80/tcp --add-port=443/tcp --add-port=9443/tcp \
    --add-port=8080/tcp --add-port=56072/tcp --add-port=56080/tcp --add-port=56443/tcp
sudo firewall-cmd --reload

# --- Step 6: Download AIQUM files ---
echo ""
log "=== Step 6: Downloading AIQUM files ==="
curl -4 -sO "${AIQUM_URL_BASE}/pre_install_check.sh"
chmod +x pre_install_check.sh

if [ ! -f netapp-um-9.18-el9.x86_64.rpm ]; then
    echo "Downloading netapp-um RPM (~1.9GB, please wait)..."
    curl -4 -sO "${AIQUM_URL_BASE}/netapp-um-9.18-el9.x86_64.rpm"
    echo "Download complete ($(ls -lh netapp-um-9.18-el9.x86_64.rpm | awk '{print $5}'))"
else
    echo "RPM already downloaded ($(ls -lh netapp-um-9.18-el9.x86_64.rpm | awk '{print $5}'))"
fi

# --- Step 7: Verify prerequisites ---
echo ""
log "=== Step 7: Verifying prerequisites ==="
sudo bash pre_install_check.sh || true

# --- Step 8: Install AIQUM RPM ---
echo ""
log "=== Step 8: Installing AIQUM RPM ==="
echo "This may take several minutes..."
sudo yum install -y ./netapp-um-9.18-el9.x86_64.rpm

echo ""
echo "AIQUM_INSTALL_COMPLETE"
