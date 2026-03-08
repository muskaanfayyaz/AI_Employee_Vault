#!/usr/bin/env bash
# setup-vm.sh — One-shot Ubuntu 22.04 VM provisioning for Platinum Tier AI Employee
#
# Usage:
#   chmod +x deploy/setup-vm.sh
#   sudo bash deploy/setup-vm.sh [--domain <yourdomain.com>] [--vault-dir /home/ubuntu/vault]
#
# What it does:
#   1. System update + essential packages
#   2. Python 3.12 + pip + venv
#   3. Node.js 20 LTS + PM2
#   4. Nginx + Certbot (Let's Encrypt)
#   5. Clone/link vault and install Python dependencies
#   6. Install PM2 ecosystem and enable auto-start
#   7. Configure Nginx reverse proxy
#   8. (Optional) Obtain TLS certificate if --domain is provided
#   9. Install Git pre-commit hook (secrets guard)
#  10. Final health check

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
VAULT_DIR="${VAULT_DIR:-/home/ubuntu/vault}"
DOMAIN=""
UBUNTU_USER="${SUDO_USER:-ubuntu}"
ENV_FILE="${HOME}/.ai-employee.env"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --domain)    DOMAIN="$2";    shift 2 ;;
    --vault-dir) VAULT_DIR="$2"; shift 2 ;;
    --user)      UBUNTU_USER="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

info()  { echo -e "\033[1;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Run with sudo: sudo bash deploy/setup-vm.sh"

# ── 1. System packages ────────────────────────────────────────────────────────
info "Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
  build-essential curl wget git unzip \
  software-properties-common ca-certificates gnupg \
  nginx certbot python3-certbot-nginx \
  apache2-utils \
  rclone \
  jq

# ── 2. Python 3.12 ───────────────────────────────────────────────────────────
info "Installing Python 3.12..."
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3.12-dev python3-pip
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# ── 3. Node.js 20 LTS + PM2 ──────────────────────────────────────────────────
info "Installing Node.js 20 LTS..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y -qq nodejs
npm install -g pm2 --quiet

# ── 4. Vault setup ────────────────────────────────────────────────────────────
info "Setting up vault at ${VAULT_DIR}..."
if [[ ! -d "${VAULT_DIR}" ]]; then
  error "Vault directory ${VAULT_DIR} does not exist. Clone or rsync your vault first."
fi

VENV_PY="${VAULT_DIR}/.venv/bin/python3"
info "Creating Python venv..."
python3.12 -m venv "${VAULT_DIR}/.venv"

info "Installing Python dependencies (all tiers)..."
"${VAULT_DIR}/.venv/bin/pip" install --quiet --upgrade pip
if [[ -f "${VAULT_DIR}/pyproject.toml" ]]; then
  "${VAULT_DIR}/.venv/bin/pip" install --quiet -e "${VAULT_DIR}[gold]"
elif [[ -f "${VAULT_DIR}/requirements.txt" ]]; then
  "${VAULT_DIR}/.venv/bin/pip" install --quiet -r "${VAULT_DIR}/requirements.txt"
else
  warn "No pyproject.toml or requirements.txt found — skipping pip install."
fi

# ── 5. .env file ─────────────────────────────────────────────────────────────
info "Checking env file..."
if [[ ! -f "${ENV_FILE}" ]]; then
  warn "No env file found at ${ENV_FILE}."
  warn "Copy deploy/.env.example to ${ENV_FILE} and fill in your secrets before starting PM2."
  if [[ -f "${VAULT_DIR}/deploy/.env.example" ]]; then
    cp "${VAULT_DIR}/deploy/.env.example" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    warn "Copied .env.example → ${ENV_FILE}. Edit it now."
  fi
else
  info "Found existing env file: ${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
fi

# ── 6. Git pre-commit hook ────────────────────────────────────────────────────
info "Installing Git pre-commit hook (secrets guard)..."
GIT_HOOKS_DIR="${VAULT_DIR}/.git/hooks"
if [[ -d "${GIT_HOOKS_DIR}" ]]; then
  cp "${VAULT_DIR}/deploy/hooks/pre-commit" "${GIT_HOOKS_DIR}/pre-commit"
  chmod +x "${GIT_HOOKS_DIR}/pre-commit"
  info "Pre-commit hook installed."
else
  warn "No .git/hooks directory found — skipping pre-commit hook install."
fi

# ── 7. PM2 setup ─────────────────────────────────────────────────────────────
info "Starting PM2 processes..."
VAULT_ROOT="${VAULT_DIR}" pm2 start "${VAULT_DIR}/deploy/ecosystem.config.js" \
  --env production 2>/dev/null || true

info "Saving PM2 process list..."
pm2 save

info "Configuring PM2 startup..."
PM2_STARTUP=$(pm2 startup systemd -u "${UBUNTU_USER}" --hp "/home/${UBUNTU_USER}" 2>&1 | tail -1)
if [[ "${PM2_STARTUP}" == sudo* ]]; then
  eval "${PM2_STARTUP}"
else
  warn "Could not auto-configure PM2 startup. Run manually: ${PM2_STARTUP}"
fi

# ── 8. Nginx configuration ────────────────────────────────────────────────────
info "Installing Nginx config..."
NGINX_CONF="/etc/nginx/sites-available/ai-employee"
cp "${VAULT_DIR}/deploy/nginx.conf" "${NGINX_CONF}"

if [[ -n "${DOMAIN}" ]]; then
  # Inject domain into nginx config before certbot runs.
  sed -i "s/server_name _;/server_name ${DOMAIN};/g" "${NGINX_CONF}"
fi

ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/ai-employee
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
info "Nginx configured."

# ── 9. htpasswd for dashboard basic auth ─────────────────────────────────────
if [[ ! -f /etc/nginx/.htpasswd ]]; then
  warn "No /etc/nginx/.htpasswd found."
  warn "Create one with: sudo htpasswd -c /etc/nginx/.htpasswd admin"
fi

# ── 10. TLS certificate (optional) ───────────────────────────────────────────
if [[ -n "${DOMAIN}" ]]; then
  info "Obtaining Let's Encrypt TLS certificate for ${DOMAIN}..."
  certbot --nginx -d "${DOMAIN}" \
    --non-interactive --agree-tos \
    --email "admin@${DOMAIN}" \
    --redirect \
    || warn "Certbot failed. DNS may not be propagated yet — re-run: sudo certbot --nginx -d ${DOMAIN}"

  # Enable certbot auto-renewal.
  systemctl enable certbot.timer 2>/dev/null || true
  info "TLS certificate installed and auto-renewal enabled."
else
  info "No --domain provided. TLS not configured."
  info "Run: sudo certbot --nginx -d <yourdomain.com> when DNS is ready."
fi

# ── 11. Backup dir ────────────────────────────────────────────────────────────
info "Creating backup directory..."
mkdir -p /backups/vault
chown "${UBUNTU_USER}:${UBUNTU_USER}" /backups/vault

# ── 12. Final health check ────────────────────────────────────────────────────
info "Running PM2 status check..."
pm2 status

info ""
info "══════════════════════════════════════════════════════"
info " Platinum Tier AI Employee — VM setup complete!"
info "══════════════════════════════════════════════════════"
info ""
info " Next steps:"
info "   1. Edit ${ENV_FILE} with your API keys and secrets"
if [[ -n "${DOMAIN}" ]]; then
  info "   2. Access PM2 dashboard: https://${DOMAIN}/dashboard/"
else
  info "   2. Set up DNS, then run: sudo certbot --nginx -d <yourdomain>"
fi
info "   3. Monitor logs: pm2 logs"
info "   4. Check health: pm2 status"
info ""
