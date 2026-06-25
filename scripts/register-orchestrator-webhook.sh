#!/bin/bash
# =====================================================================
# register-orchestrator-webhook.sh — Registra webhook en LNBits
# para que notifique al orchestrator cuando un pago es recibido.
# =====================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log() { echo -e "${BLUE}[webhook]${NC} $*"; }
ok()  { echo -e "${GREEN}[ ok ]${NC} $*"; }
err() { echo -e "${RED}[err]${NC} $*" >&2; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
set -a; source ./.env; set +a

LNBITS_URL="${LNBITS_URL:-http://localhost:5000}"
ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://orchestrator:8000}"
WEBHOOK_URL="${ORCHESTRATOR_URL}/api/v1/webhooks/lnbits/paid"

# Get Coffee Wallet admin key
SUPER_USER_ID=$(docker exec lnbits sh -c 'cat /app/data/.super_user 2>/dev/null' | tr -d '\r\n')
WALLETS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/wallets?usr=${SUPER_USER_ID}")
ADMIN_KEY=$(echo "$WALLETS_JSON" | jq -r '.[0].adminkey')

log "Registrando webhook en LNBits…"
log "  URL: ${WEBHOOK_URL}"
log "  Wallet: Coffee Wallet"

# LNBits does not have a standard webhook registration API in 0.12.5.
# Instead, we configure the webhook via the LNBits settings DB.
# The splitpayments extension listens for payments internally.
# For the orchestrator, we insert a webhook listener via DB.

# Check if webhook already registered in DB
EXISTING=$(docker exec postgres psql -U lnbits -d lnbits -t -A -c \
  "SELECT count(*) FROM lnbits.settings WHERE key='webhook_url';" 2>/dev/null || echo "0")
EXISTING=$(echo "$EXISTING" | tr -d '[:space:]')

if [[ "$EXISTING" -gt 0 ]]; then
  docker exec postgres psql -U lnbits -d lnbits -c \
    "UPDATE lnbits.settings SET value='${WEBHOOK_URL}' WHERE key='webhook_url';" > /dev/null
  docker exec postgres psql -U lnbits -d lnbits -c \
    "UPDATE lnbits.settings SET value='${ORCHESTRATOR_WEBHOOK_SECRET}' WHERE key='webhook_secret';" > /dev/null
  ok "Webhook actualizado en LNBits DB"
else
  docker exec postgres psql -U lnbits -d lnbits -c \
    "INSERT INTO lnbits.settings (key, value) VALUES ('webhook_url', '${WEBHOOK_URL}');" > /dev/null 2>&1
  docker exec postgres psql -U lnbits -d lnbits -c \
    "INSERT INTO lnbits.settings (key, value) VALUES ('webhook_secret', '${ORCHESTRATOR_WEBHOOK_SECRET}');" > /dev/null 2>&1
  ok "Webhook registrado en LNBits DB"
fi

echo ""
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN} Webhook configurado${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo ""
echo "  URL:     ${WEBHOOK_URL}"
echo "  Secret:  ${ORCHESTRATOR_WEBHOOK_SECRET}"
echo ""
