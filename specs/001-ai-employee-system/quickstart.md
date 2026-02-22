# Quickstart: AI Employee System

## Prerequisites

- Python 3.12+
- pip (comes with Python)
- Claude Code CLI installed and authenticated
- An Obsidian vault directory (or any folder — Obsidian is optional)

## Bronze Tier Setup (5 minutes)

### 1. Clone and install

```bash
cd AI_Employee_Vault
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — DRY_RUN=true is already set by default
```

### 3. Initialize vault folders

```bash
python -m src.main --init
```

This creates: `Inbox/`, `Needs_Action/`, `Plans/`, `In_Progress/`,
`Pending_Approval/`, `Approved/`, `Rejected/`, `Done/`, `Errors/`,
`Reports/`, `Logs/`, `Config/`, `Skills/`, and `Dashboard.md`.

### 4. Start the AI Employee (DRY_RUN)

```bash
python -m src.main
```

### 5. Test it

```bash
# In another terminal:
cp "tests/fixtures/sample_inbox_item.md" Inbox/

# Watch the logs:
cat Logs/$(date +%Y-%m-%d).json | python -m json.tool

# Check the dashboard:
cat Dashboard.md
```

### 6. Go live

```bash
# Edit .env:
DRY_RUN=false

# Restart:
python -m src.main
```

## Silver Tier Setup (adds email + messaging)

### 1. Install additional dependencies

```bash
pip install -e ".[silver]"
```

### 2. Configure Gmail

1. Create a Google Cloud project and enable Gmail API
2. Download OAuth2 credentials JSON
3. Add to `.env`:
   ```
   GMAIL_OAUTH_TOKEN_PATH=/path/to/credentials.json
   GMAIL_POLL_INTERVAL=60
   ```

### 3. Configure watchers

Edit `Config/gmail_watcher.yaml`:
```yaml
watcher:
  name: "gmail-inbox"
  type: "gmail"
  enabled: true
  polling_interval_seconds: 60
  filters:
    keywords: ["urgent", "invoice", "action required"]
    senders: []
    labels: ["IMPORTANT"]
  credential_ref: "GMAIL_OAUTH_TOKEN_PATH"
```

### 4. Start with scheduling

```bash
python -m src.main --schedule
```

## Gold Tier Setup (adds Odoo + social + Ralph Wiggum)

### 1. Install additional dependencies

```bash
pip install -e ".[gold]"
```

### 2. Configure Odoo

Add to `.env`:
```
ODOO_URL=https://your-odoo-instance.com
ODOO_DB=your-database
ODOO_USERNAME=your-username
ODOO_API_KEY=your-api-key
```

### 3. Configure social media

Add platform tokens to `.env`:
```
LINKEDIN_TOKEN=your-token
FACEBOOK_TOKEN=your-token
INSTAGRAM_TOKEN=your-token
TWITTER_TOKEN=your-token
```

### 4. Start with Gold features

```bash
python -m src.main --schedule --gold
```

### 5. Trigger CEO Briefing manually

```bash
python -m src.main --briefing
```

### 6. Trigger Ralph Wiggum loop manually

```bash
python -m src.main --ralph-wiggum
```

## Platinum Tier Setup (adds cloud deployment + sync)

### 1. Install additional dependencies

```bash
pip install -e ".[platinum]"
```

### 2. Build the Docker image

```bash
docker build -t ai-employee .
```

### 3. Configure cloud credentials

Create an encrypted `.env.cloud` file:
```bash
# On the cloud server:
cp .env .env.cloud
# Edit .env.cloud with cloud-specific credentials
# Encrypt at rest (the credential proxy loads and decrypts at startup)
```

### 4. Configure sync

Edit `Config/sync.yaml`:
```yaml
sync:
  enabled: true
  cloud_url: "ssh://user@your-cloud-server:/opt/ai-employee/vault"
  interval_seconds: 300
  direction: "bidirectional"
  conflict_policy: "flag_for_human"
  auth:
    method: "ssh_key"
    key_ref: "SYNC_SSH_KEY_PATH"
```

### 5. Configure health monitoring

Edit `Config/health_monitor.yaml`:
```yaml
health_monitor:
  check_interval_seconds: 60
  alert_channel: "email"
  alert_recipient: "admin@company.com"
  auto_recovery_max_attempts: 3
  report_interval: "hourly"
```

### 6. Deploy to cloud

```bash
# On the cloud server:
docker-compose up -d

# Verify health:
docker-compose logs -f ai-employee
```

### 7. Start local with sync

```bash
python -m src.main --schedule --gold --sync
```

### 8. Verify cloud health

```bash
python -m src.main --health
cat Reports/Health_$(date +%Y-%m-%d_%H).json | python -m json.tool
```

### 9. Zero-downtime deployment

```bash
# On the cloud server:
./scripts/deploy.sh --image ai-employee:v2.0.0
# Blue-green swap happens automatically
```

## Verification Checklist

### Bronze
- [ ] `python -m src.main --init` creates all folders
- [ ] Dropping a file in `Inbox/` triggers processing
- [ ] File ends up in `Done/` within 5 minutes
- [ ] `Logs/YYYY-MM-DD.json` has entries
- [ ] `Dashboard.md` shows correct counts
- [ ] DRY_RUN mode: no files move, logs show `[DRY_RUN]`

### Silver
- [ ] Gmail watcher detects test email
- [ ] Draft appears in `Pending_Approval/`
- [ ] Approving sends the email
- [ ] Rejecting does NOT send
- [ ] Scheduler runs at configured interval

### Gold
- [ ] Odoo watcher detects new sales order
- [ ] Social media draft routes to approval
- [ ] CEO Briefing generates with correct data
- [ ] Ralph Wiggum creates improvement proposals
- [ ] Multi-MCP operations handle partial failure

### Platinum
- [ ] Docker image builds successfully
- [ ] Cloud instance starts and passes health check
- [ ] Data classifier tags sensitive items as `local_only`
- [ ] Untagged items default to `local_only` (fail-safe)
- [ ] Sync excludes `local_only` items from cloud payload
- [ ] Sync transfers `syncable` items in full
- [ ] Sync sends `redacted_summary` with masked values
- [ ] Conflict detection flags dual-modified items
- [ ] Local offline → cloud processes event → sync on reconnect
- [ ] Approval on local propagates to cloud within 5 minutes
- [ ] Cloud audit logs sync to local `/Logs`
- [ ] Health monitor detects component failure
- [ ] Auto-recovery restarts failed component (up to 3x)
- [ ] Alert sent within 5 minutes of unrecoverable failure
- [ ] Zero-downtime deployment: no items lost during update
- [ ] No `local_only` data in cloud storage or logs (SC-013)
