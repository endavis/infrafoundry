#!/bin/bash
# AIQUM RPM install script — runs on the AIQUM VM itself
#
# Installs all prerequisites identified by pre_install_check.sh,
# then installs the AIQUM RPM.
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
