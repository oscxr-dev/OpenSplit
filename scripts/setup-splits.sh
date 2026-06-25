#!/usr/bin/env bash
# =====================================================================
# setup-splits.sh — Configura splitpayments con wallets destino
# Idempotente: si las wallets existen, las reutiliza.
# Usa la DB directamente porque la API de splitpayments solo soporta GET.
# =====================================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[split]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

LNBITS_URL="${LNBITS_URL:-http://localhost:5000}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
set -a; source ./.env; set +a

db_query() { docker exec postgres psql -U lnbits -d lnbits -t -A -c "$1" 2>/dev/null; }

# -- 1) Get super user & source wallet ---------------------------------
log "Obteniendo super-user y wallet fuente…"
SUPER_USER_ID=$(docker exec lnbits sh -c 'cat /app/data/.super_user 2>/dev/null' | tr -d '\r\n')
WALLETS_JSON=$(curl -fsS "${LNBITS_URL}/api/v1/wallets?usr=${SUPER_USER_ID}")
SOURCE_ID=$(echo "$WALLETS_JSON" | jq -r '.[0].id')
SOURCE_NAME=$(echo "$WALLETS_JSON" | jq -r '.[0].name')
SOURCE_ADMIN=$(echo "$WALLETS_JSON" | jq -r '.[0].adminkey')
ok "Wallet fuente: ${SOURCE_NAME} (${SOURCE_ID:0:8}…)"

# -- 2) Define target wallets ------------------------------------------
declare -A TARGETS
TARGETS=(
  ["Dueño"]=30
  ["Barista"]=35
  ["Proveedor"]=15
  ["Impuestos"]=10
  ["Reserva"]=10
)

log "Creando/verificando wallets destino…"
declare -A WALLET_IDS

for name in "${!TARGETS[@]}"; do
  # Check if wallet exists in DB
  existing_id=$(db_query "SELECT id FROM lnbits.wallets WHERE name='${name}' AND \"user\"!='${SUPER_USER_ID}' LIMIT 1;" | tr -d '[:space:]')
  
  if [[ -n "$existing_id" ]]; then
    ok "Wallet '${name}' ya existe: ${existing_id:0:8}…"
    WALLET_IDS[$name]="$existing_id"
  else
    # Create via API
    CREATE_JSON=$(curl -fsS -X POST \
      "${LNBITS_URL}/api/v1/account?usr=${SUPER_USER_ID}" \
      -H "Content-Type: application/json" \
      -d "{\"name\": \"${name}\"}")
    new_id=$(echo "$CREATE_JSON" | jq -r '.id')
    WALLET_IDS[$name]="$new_id"
    ok "Wallet '${name}' creada: ${new_id:0:8}…"
  fi
done

# -- 3) Configure splitpayments targets (via DB) -----------------------
log "Configurando splitpayments…"

# Generate short IDs
gen_id() { python3 -c "import random,string;print(''.join(random.choices(string.ascii_letters+string.digits,k=22)))"; }

# Clear existing targets for this source
db_query "DELETE FROM splitpayments.targets WHERE source='${SOURCE_ID}';"

# Insert new targets
for name in "${!TARGETS[@]}"; do
  percent="${TARGETS[$name]}"
  wid="${WALLET_IDS[$name]}"
  sid=$(gen_id)
  
  db_query "INSERT INTO splitpayments.targets (id, wallet, source, percent, alias) VALUES ('${sid}', '${wid}', '${SOURCE_ID}', ${percent}, '${name}');"
  ok "  ${name}: ${percent}% → ${wid:0:8}…"
done

# -- 4) Verify ----------------------------------------------------------
echo ""
log "Verificando configuración…"
FINAL=$(curl -fsS "${LNBITS_URL}/splitpayments/api/v1/targets" \
  -H "X-Api-Key: ${SOURCE_ADMIN}")

echo "$FINAL" | jq -r '.[] | "  \(.alias)\t\(.percent)%\t\(.wallet)"'
TOTAL_PCT=$(echo "$FINAL" | jq '[.[].percent] | add')
echo ""
echo -e "  Total: ${TOTAL_PCT}%"

echo ""
echo -e "${GREEN}=========================================================${NC}"
echo -e "${GREEN} Splitpayments configurado — ${#TARGETS[@]} wallets${NC}"
echo -e "${GREEN}=========================================================${NC}"
echo ""
echo "  Para probar: ./scripts/test-split.sh"
echo ""
