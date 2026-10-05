#!/bin/bash
set -e

# Update and install dependencies
apt-get update
apt-get install -y git curl apt-transport-https ca-certificates software-properties-common

# Install Docker
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
fi

# Clone repository
mkdir -p /opt
cd /opt
if [ ! -d "syroce-pms" ]; then
    git clone https://github.com/beyinsiz1903/Syroce-PMS.git syroce-pms
fi

cd syroce-pms
git checkout main
git pull origin main

# Environment file will be copied here via scp
