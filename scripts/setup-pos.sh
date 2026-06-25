#!/usr/bin/env bash
# =====================================================================
# setup-pos.sh — Configura el POS (Tiaaki vía LNDHub) y crea terminal
# =====================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[pos]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }

LNBITS_URL="${LNBITS_URL:-http://localhost:5000}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
set -a; source ./.env; set +a

HOST_IP=$(ip -4 addr show | grep -oP 'inet \K[0-9.]+(?=.*global)' | head -1 || echo "localhost")

# -- 1) Get source wallet ----------------------------------------------
SUPER_USER_ID=$(docker exec lnbits sh -c 'cat /app/data/.super_user 2>/dev/null' | tr -d '\r\n')
WALLETS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/wallets?usr=${SUPER_USER_ID}")
SOURCE_ADMIN=$(echo "$WALLETS_JSON" | jq -r '.[0].adminkey')
SOURCE_NAME=$(echo "$WALLETS_JSON" | jq -r '.[0].name')
ok "Wallet fuente: ${SOURCE_NAME}"

# -- 2) Create POS terminal in tpos ------------------------------------
log "Creando terminal POS en tpos…"
EXISTING=$(curl -fsS "${LNBITS_URL}/tpos/api/v1/tposs" \
  -H "X-Api-Key: ${SOURCE_ADMIN}" 2>/dev/null | jq -r '.[0].id // empty')

if [[ -n "$EXISTING" ]]; then
  POS_ID="$EXISTING"
  ok "Terminal ya existe: ${POS_ID}"
else
  POS_JSON=$(curl -fsS -X POST "${LNBITS_URL}/tpos/api/v1/tposs" \
    -H "X-Api-Key: ${SOURCE_ADMIN}" \
    -H "Content-Type: application/json" \
    -d '{"name": "Cafeteria", "currency": "sat"}')
  POS_ID=$(echo "$POS_JSON" | jq -r '.id')
  ok "Terminal creada: ${POS_ID}"
fi

# -- 3) Verify LNDHub connection ---------------------------------------
log "Verificando LNDHub…"
AUTH_JSON=$(curl -fsS -X POST "${LNBITS_URL}/lndhub/ext/auth" \
  -H "Content-Type: application/json" \
  -d "{\"login\":\"${SOURCE_ADMIN}\",\"password\":\"${SOURCE_ADMIN}\"}")
ACCESS_TOKEN=$(echo "$AUTH_JSON" | jq -r '.access_token')

# Test invoice creation
INVOICE_JSON=$(curl -fsS -X POST "${LNBITS_URL}/lndhub/ext/addinvoice" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d '{"amt": 1, "memo": "POS Connection Test"}')
BOLT11=$(echo "$INVOICE_JSON" | jq -r '.payment_request // empty')

if [[ -n "$BOLT11" ]]; then
  ok "LNDHub responde — invoice de prueba creada"
else
  log "LNDHub no generó invoice (puede necesitar fondos on-chain)"
fi

# -- 4) Print connection info ------------------------------------------
echo ""
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN} POS Listo para Conectar${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo ""
echo "  📱 Tiaaki POS (app móvil):"
echo "     ───────────────────────────────────────"
echo "     LNDHub URL:  ${LNBITS_URL}/lndhub/ext/"
echo "     Login:       ${SOURCE_ADMIN}"
echo "     Password:    ${SOURCE_ADMIN}"
echo ""
echo "  🌐 LNBits tpos (web):"
echo "     ───────────────────────────────────────"
echo "     Terminal:    ${LNBITS_URL}/tpos/${POS_ID}"
echo ""
echo "  🔌 LNDHub desde red local:"
echo "     ───────────────────────────────────────"
echo "     URL:         http://${HOST_IP}:5000/lndhub/ext/"
echo "     Login:       ${SOURCE_ADMIN}"
echo ""
echo "  💡 El POS usa '${SOURCE_NAME}' como wallet fuente."
echo "     Los pagos entrantes se dividen automáticamente:"
echo "     Barista 35% | Dueño 30% | Proveedor 15% | Impuestos 10% | Reserva 10%"
echo ""
echo "  Para probar: ./scripts/test-split.sh"
echo ""
