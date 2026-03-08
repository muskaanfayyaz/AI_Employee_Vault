# Quickstart: Platinum Tier VM Deployment

**Branch**: `001-platinum-tier` | **Date**: 2026-03-08
**Target**: Ubuntu 22.04 LTS cloud VM (1–2 vCPU, 2GB RAM minimum)

---

## Prerequisites

- [ ] Cloud VM provisioned (Ubuntu 22.04 LTS)
- [ ] SSH access to VM
- [ ] Domain name pointed at VM IP (for HTTPS)
- [ ] Git remote repository (GitHub / GitLab) with vault content
- [ ] SSH deploy key generated for the vault repo

---

## Step 1: Initial VM Setup

```bash
# Connect to VM
ssh ubuntu@<your-vm-ip>

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.12
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Install Git
sudo apt-get install -y git

# Install Node.js (for PM2)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install PM2 globally
sudo npm install -g pm2

# Install Nginx + Certbot (for HTTPS)
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

---

## Step 2: Clone the Vault Repository

```bash
# Set up SSH deploy key (generated separately, public key added to GitHub/GitLab)
mkdir -p ~/.ssh
# Copy your deploy key private file to the VM:
# scp deploy_key ubuntu@<vm-ip>:~/.ssh/vault_deploy_key
chmod 600 ~/.ssh/vault_deploy_key

# Add SSH config for the vault remote
cat >> ~/.ssh/config << 'EOF'
Host vault-git
  HostName github.com        # or your Git host
  User git
  IdentityFile ~/.ssh/vault_deploy_key
  StrictHostKeyChecking no
EOF

# Clone vault (replace with your repo URL)
git clone vault-git:youruser/your-vault.git ~/vault
cd ~/vault
git checkout main
```

---

## Step 3: Configure Environment (Secrets — NOT in vault)

```bash
# Create .env OUTSIDE the vault directory
cat > ~/.ai-employee.env << 'EOF'
# === Agent Identity ===
AGENT_ID=cloud-vm-001
AGENT_ENV=cloud

# === Vault ===
VAULT_ROOT=/home/ubuntu/vault

# === Runtime ===
DRY_RUN=false
STABILITY_SECONDS=2.0
LOG_LEVEL=INFO

# === Git Sync ===
GIT_SYNC_INTERVAL_SECONDS=60
GIT_REMOTE=origin
GIT_BRANCH=main

# === Claim & Dashboard ===
CLAIM_TIMEOUT_MINUTES=30
DASHBOARD_LOCK_STALE_SECONDS=60

# === Heartbeat & Health ===
HEARTBEAT_INTERVAL_SECONDS=60
HEARTBEAT_STALE_MINUTES=5

# === API Keys (never commit these) ===
ANTHROPIC_API_KEY=sk-ant-...
# GMAIL_OAUTH_TOKEN_PATH=
# LINKEDIN_ACCESS_TOKEN=

# === Backup (optional) ===
BACKUP_ENABLED=true
BACKUP_LOCAL_PATH=/backups/vault
BACKUP_RETENTION_DAYS=30
RCLONE_REMOTE=   # leave empty to disable off-VM backup
EOF

chmod 600 ~/.ai-employee.env
```

---

## Step 4: Install Python Dependencies

```bash
cd ~/vault
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt   # existing Gold Tier requirements
# Platinum additions (add to requirements.txt):
# watchdog>=4.0
# schedule>=1.2
# python-dotenv>=1.0
# pyyaml>=6.0
```

---

## Step 5: Install Git Secrets Hook

```bash
cd ~/vault

# Install the pre-commit secrets guard hook
cp deploy/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Verify .gitignore blocks secrets
grep -q ".env" .gitignore || echo ".env" >> .gitignore
grep -q "*.key" .gitignore || echo "*.key" >> .gitignore
grep -q ".Dashboard.lock" .gitignore || echo ".Dashboard.lock" >> .gitignore
```

---

## Step 6: Initialise Vault Folders

```bash
cd ~/vault
source .venv/bin/activate
set -a && source ~/.ai-employee.env && set +a

python -m src.main --init
# Creates: Inbox/, In_Progress/, Done/, Errors/, Logs/, Config/, etc.

# Create Platinum-specific folders
mkdir -p Logs/heartbeats
```

---

## Step 7: Configure PM2

```bash
# Copy the PM2 ecosystem config (from deploy/)
cd ~/vault

# Edit ecosystem.config.js to set correct paths
# (replace /home/ubuntu with your actual home directory if different)
cp deploy/ecosystem.config.js ~/ecosystem.config.js

# Start all processes
pm2 start ~/ecosystem.config.js

# Verify all processes are online
pm2 list

# Set up PM2 to start on system reboot
pm2 startup                    # follow the printed sudo command
pm2 save                       # persist current process list
```

**Expected PM2 process list**:
```
┌─────────────────────────┬─────┬──────┬───────┬──────────┐
│ Name                    │ id  │ mode │ pid   │ status   │
├─────────────────────────┼─────┼──────┼───────┼──────────┤
│ ai-employee-cloud       │ 0   │ fork │ 12345 │ online   │
│ git-sync                │ 1   │ fork │ 12346 │ online   │
│ health-monitor          │ 2   │ fork │ 12347 │ online   │
│ backup                  │ 3   │ fork │ 12348 │ online   │
└─────────────────────────┴─────┴──────┴───────┴──────────┘
```

---

## Step 8: Configure HTTPS (Nginx + Let's Encrypt)

```bash
# Copy Nginx config
sudo cp ~/vault/deploy/nginx.conf /etc/nginx/sites-available/ai-employee
sudo ln -s /etc/nginx/sites-available/ai-employee /etc/nginx/sites-enabled/

# Test Nginx config
sudo nginx -t

# Obtain TLS certificate (replace with your domain)
sudo certbot --nginx -d monitor.yourdomain.com

# Certbot auto-renews via systemd timer; verify:
sudo systemctl status certbot.timer

# Reload Nginx
sudo systemctl reload nginx
```

**Access the PM2 monitoring dashboard at**: `https://monitor.yourdomain.com`

---

## Step 9: Verify Deployment

```bash
# 1. Check all PM2 processes are online
pm2 list

# 2. Tail agent logs
pm2 logs ai-employee-cloud --lines 20

# 3. Check heartbeat file was created
ls -la ~/vault/Logs/heartbeats/

# 4. Check health monitor is running
pm2 logs health-monitor --lines 10

# 5. Test claim-by-move: drop a test task
echo "---
id: test-001
created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
type: test
---

# Test Task

## Description
Verify Platinum Tier cloud agent is operational." > ~/vault/Needs_Action/test-$(date +%s).md

# Wait 2 minutes, then check Done/
ls ~/vault/Done/

# 6. Verify Git sync pushed the output
git -C ~/vault log --oneline -5

# 7. Check secrets guard
echo 'API_KEY=sk-test-secret123' > /tmp/test-secret.md
cp /tmp/test-secret.md ~/vault/test-secret.md
git -C ~/vault add test-secret.md
git -C ~/vault commit -m "test"   # Should be BLOCKED by pre-commit hook
rm ~/vault/test-secret.md
git -C ~/vault restore --staged test-secret.md 2>/dev/null || true
```

---

## Step 10: Configure Local Agent (on your laptop)

```bash
# On your local machine:
cd /path/to/your/vault

# Create local .env (outside vault)
cat > ~/.ai-employee-local.env << 'EOF'
AGENT_ID=local-dev
AGENT_ENV=local
VAULT_ROOT=/path/to/your/vault
DRY_RUN=false
ANTHROPIC_API_KEY=sk-ant-...
GIT_SYNC_INTERVAL_SECONDS=60
HEARTBEAT_INTERVAL_SECONDS=60
HEARTBEAT_STALE_MINUTES=5
EOF

# Run local agent (with Git sync enabled)
set -a && source ~/.ai-employee-local.env && set +a
python -m src.main --schedule --cloud
```

---

## Operational Reference

### Common PM2 Commands
```bash
pm2 list                        # show all processes
pm2 logs                        # tail all logs
pm2 logs ai-employee-cloud      # tail specific process
pm2 restart ai-employee-cloud   # restart one process
pm2 reload ecosystem.config.js  # zero-downtime reload all
pm2 monit                       # interactive process monitor
```

### Manual Git Sync
```bash
cd ~/vault
git pull --rebase origin main
git push origin main
```

### Check Health Alerts
```bash
tail -f ~/vault/Logs/health-alerts.jsonl | python3 -m json.tool
```

### Rollback a Bad Commit
```bash
cd ~/vault
git log --oneline -10            # find the bad commit hash
git revert <hash>                # creates a revert commit (safe)
git push origin main
```

### Check Backup Status
```bash
ls -lah /backups/vault/          # list daily snapshots
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Agent not processing tasks | `pm2 ai-employee-cloud` crashed | `pm2 restart ai-employee-cloud` |
| Heartbeat file not updating | Agent process stopped | Check `pm2 list`, restart if needed |
| Git sync failures | SSH key or network issue | Check `pm2 logs git-sync`; verify SSH key |
| Dashboard.md corrupted | Stale lock file | Delete `vault/.Dashboard.lock`; restart agent |
| Task processed twice | Sync interval too long | Reduce `GIT_SYNC_INTERVAL_SECONDS` |
| Commit blocked by hook | Secret detected in staged file | Remove secret; use env vars instead |
| HTTPS not working | Certbot renewal failed | `sudo certbot renew --dry-run` to test |
