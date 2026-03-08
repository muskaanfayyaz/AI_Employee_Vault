/**
 * PM2 ecosystem configuration — Platinum Tier AI Employee (cloud VM)
 *
 * Usage:
 *   pm2 start ecosystem.config.js        # start all processes
 *   pm2 reload ecosystem.config.js       # zero-downtime reload
 *   pm2 stop all                         # stop
 *   pm2 startup && pm2 save              # auto-start on reboot
 *
 * All processes load secrets from ~/.ai-employee.env (OUTSIDE vault).
 * Adjust paths if vault is not at /home/ubuntu/vault.
 */

const VAULT = process.env.VAULT_ROOT || "/home/ubuntu/vault";
const VENV_PY = `${VAULT}/.venv/bin/python3`;
const ENV_FILE = `${process.env.HOME || "/home/ubuntu"}/.ai-employee.env`;

module.exports = {
  apps: [
    // ── 1. Main AI Employee agent (always-on, cloud mode) ──────────────────
    {
      name: "ai-employee-cloud",
      script: `${VAULT}/src/main.py`,
      interpreter: VENV_PY,
      args: "--schedule --cloud",
      cwd: VAULT,
      env_file: ENV_FILE,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      min_uptime: "10s",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: `${VAULT}/Logs/pm2-ai-employee-err.log`,
      out_file: `${VAULT}/Logs/pm2-ai-employee-out.log`,
    },

    // ── 2. Git sync service (pull every 60s, push after tasks) ────────────
    {
      name: "git-sync",
      script: `${VAULT}/src/sync/git_sync.py`,
      interpreter: VENV_PY,
      cwd: VAULT,
      env_file: ENV_FILE,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: `${VAULT}/Logs/pm2-git-sync-err.log`,
      out_file: `${VAULT}/Logs/pm2-git-sync-out.log`,
    },

    // ── 3. Health monitor (heartbeat staleness + orphan recovery) ─────────
    {
      name: "health-monitor",
      script: `${VAULT}/src/health/monitor.py`,
      interpreter: VENV_PY,
      cwd: VAULT,
      env_file: ENV_FILE,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: `${VAULT}/Logs/pm2-health-err.log`,
      out_file: `${VAULT}/Logs/pm2-health-out.log`,
    },

    // ── 4. Nightly backup (cron: 02:00 UTC daily) ─────────────────────────
    {
      name: "backup",
      script: `${VAULT}/src/sync/backup.py`,
      interpreter: VENV_PY,
      cwd: VAULT,
      env_file: ENV_FILE,
      autorestart: false,
      cron_restart: "0 2 * * *",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: `${VAULT}/Logs/pm2-backup-err.log`,
      out_file: `${VAULT}/Logs/pm2-backup-out.log`,
    },
  ],
};
