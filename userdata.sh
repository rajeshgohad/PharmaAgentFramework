#!/bin/bash
# EC2 bootstrap for PharmaAgentFramework (Amazon Linux 2023) — no Docker.
# Installs Python + Node, clones the public repo, builds the frontend, and runs
# the FastAPI backend (which serves the built frontend single-origin) via systemd.
exec > /var/log/pharmaagent-setup.log 2>&1
set -x

# AL2023's default python3 is 3.9; anthropic needs >=3.10, so use python3.11.
dnf install -y python3.11 git nodejs npm

# --- code ---
cd /opt
git clone https://github.com/rajeshgohad/PharmaAgentFramework.git
cd /opt/PharmaAgentFramework

# --- backend deps in a venv (avoids AL2023 PEP-668 restrictions) ---
python3.11 -m venv /opt/paf-venv
/opt/paf-venv/bin/pip install --upgrade pip
/opt/paf-venv/bin/pip install -r /opt/PharmaAgentFramework/backend/requirements.txt

# --- build frontend (served single-origin by FastAPI) ---
cd /opt/PharmaAgentFramework/frontend
npm ci
npm run build

# --- persistent data dir for SQLite ---
mkdir -p /opt/paf-data

# --- systemd service (binds :80, restarts on failure) ---
cat > /etc/systemd/system/pharmaagent.service << 'SVCEOF'
[Unit]
Description=PharmaAgentFramework (FastAPI + React, single-origin)
After=network.target

[Service]
User=root
WorkingDirectory=/opt/PharmaAgentFramework/backend
ExecStart=/opt/paf-venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=5
Environment=PHARMA_STATIC_DIR=/opt/PharmaAgentFramework/frontend/dist
Environment=PHARMA_DB_PATH=/opt/paf-data/pharma.db

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable pharmaagent
systemctl start pharmaagent

echo "PharmaAgentFramework setup complete at $(date)"
