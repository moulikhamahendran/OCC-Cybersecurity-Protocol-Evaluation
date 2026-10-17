#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo " Docker Setup for OCC WireGuard Hub"
echo "========================================"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[FAIL] Linux required"
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "[FAIL] /etc/os-release missing"
    exit 1
fi

. /etc/os-release

if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "[FAIL] Ubuntu required by this installer"
    echo "Detected ID=${ID:-unknown}"
    exit 1
fi

echo
echo "===== REMOVE CONFLICTING DOCKER PACKAGES ====="

for pkg in \
    docker.io \
    docker-compose \
    docker-compose-v2 \
    docker-doc \
    docker-buildx \
    podman-docker \
    containerd \
    runc
do
    sudo apt-get remove -y "$pkg" 2>/dev/null || true
done

echo
echo "===== INSTALL DOCKER REPOSITORY REQUIREMENTS ====="

sudo apt-get update
sudo apt-get install -y ca-certificates curl

sudo install -m 0755 -d /etc/apt/keyrings

sudo curl -fsSL \
    https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc

sudo chmod a+r /etc/apt/keyrings/docker.asc

echo
echo "===== ADD OFFICIAL DOCKER REPOSITORY ====="

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update

echo
echo "===== INSTALL DOCKER ENGINE + COMPOSE ====="

sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

echo
echo "===== START DOCKER ====="

sudo systemctl enable docker
sudo systemctl start docker

echo
echo "===== VERIFY ====="

sudo docker version
sudo docker compose version

echo
echo "========================================"
echo " DOCKER HUB REQUIREMENTS: READY"
echo "========================================"
