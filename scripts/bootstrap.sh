#!/usr/bin/env bash
set -euo pipefail
set -a
source "$(dirname "$0")/../.env"
set +a

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LN="http://localhost:5000"; OC="http://localhost:8000"
ADMIN_EMAIL="admin@bitcrew.example"; SMOKE=3333; MAX_WAIT=180; POLL=5
cd "$PROJECT_DIR"
log()  { echo "[bootstrap] $*"; }
die()  { log "❌ $*"; exit 1; }

# 1. Prereqs
log "Paso 1: prerequisitos"
docker compose version >/dev/null 2>&1 || die "docker compose no instalado"
[[ -f .env ]] || die ".env no encontrado"
# Read RPC creds from .env
RPC_USER=$(grep -oP 'BITCOIN_RPC_USER=\K.*' .env)
RPC_PASS=$(grep -oP 'BITCOIN_RPC_PASSWORD=\K.*' .env)
[[ -n "$RPC_USER" && -n "$RPC_PASS" ]] || die "BITCOIN_RPC_USER/PASSWORD no encontrados en .env"

# 2. Start
log "Paso 2: docker compose up -d"
docker compose up -d 2>&1 | tail -3

# 3. Wait healthy
log "Paso 3: esperando 7/7 healthy (max ${MAX_WAIT}s)"
for ((i=0; i<MAX_WAIT; i+=POLL)); do
    h=$(docker compose ps --format json 2>/dev/null | grep -c '"Health":"healthy"' || echo 0)
    [[ $h -eq 7 ]] && break; sleep $POLL; log "  +${i}s: ${h}/7"
done
[[ $h -eq 7 ]] || { docker compose ps; die "servicios no healthy"; }
log "  ✅ 7/7 healthy"

# 4. LNBits health (200 or 307 = first_install)
log "Paso 4: LNBits /api/v1/health (con retry)"
LNBITS_OK=false
for i in $(seq 1 30); do
    HC=$(curl -s -o /dev/null -w '%{http_code}' "${LN}/api/v1/health" 2>/dev/null || echo "000")
    if [[ "$HC" == "200" || "$HC" == "307" ]]; then
        LNBITS_OK=true
        break
    fi
    sleep 2
done
[[ "$LNBITS_OK" == "true" ]] || die "LNBits no responde tras 60s (último HTTP ${HC})"
log "  ✅ HTTP ${HC}"

# 5. Admin user (first_install)
log "Paso 5: first_install"
FI=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "${LN}/api/v1/auth/first_install" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"${LNBITS_ADMIN_PASS}","password_repeat":"${LNBITS_ADMIN_PASS}"}')
if [[ "$FI" =~ ^(200|400|401)$ ]]; then
    log "  ✅ HTTP ${FI}"
else
    die "first_install falló con HTTP ${FI}"
fi
# Fix LND_REST_MACAROON in DB + restart LNbits
docker exec postgres psql -U lnbits -d lnbits -c \
    "UPDATE settings SET editable_settings = editable_settings::jsonb || '{\"lnd_rest_macaroon\":\"/lnd_data/data/chain/bitcoin/regtest/admin.macaroon\"}'::jsonb;" >/dev/null
docker restart lnbits >/dev/null 2>&1; sleep 10
# Wait for LNbits to be ready after restart
for i in $(seq 1 15); do
    [[ "$(curl -s -o /dev/null -w '%{http_code}' "${LN}/api/v1/health")" == "200" ]] && break
    sleep 2
done

# 6. Backend check
log "Paso 6: verificando backend LNBits"
BACKEND=$(docker logs lnbits 2>&1 | { grep -oP 'Backend \K\w+Wallet' || true; } | tail -1)
log "  backend: ${BACKEND:-UNKNOWN}"
if [[ "$BACKEND" != "LndRestWallet" ]]; then
    die "LNBits backend=${BACKEND:-UNKNOWN}, esperado LndRestWallet. Verificá LND_REST_MACAROON."
fi
log "  ✅ ${BACKEND}"

# 7. Create Coffee Wallet + rename
log "Paso 7: Coffee Wallet"
ACC=$(curl -s -X POST "${LN}/api/v1/account" -H "Content-Type: application/json" \
    -d '{"name":"BitCrew Admin"}')
USER_ID=$(echo "$ACC" | jq -r '.id'); AK=$(echo "$ACC" | jq -r '.adminkey')
[[ -n "$USER_ID" && "$USER_ID" != "null" ]] || die "account creation failed: ${ACC}"
curl -s -X PATCH "${LN}/api/v1/wallet" -H "X-Api-Key: ${AK}" \
    -H "Content-Type: application/json" -d '{"name":"Coffee Wallet"}' >/dev/null
log "  ✓ user_id=${USER_ID} adminkey=${AK:0:12}..."

# 8. 5 destination wallets
log "Paso 8: 5 wallets destino"
WLETS=("Dueno" "Barista" "Proveedor" "Impuestos" "Reserva"); declare -A WID
for w in "${WLETS[@]}"; do
    WID[$w]=$(curl -s -X POST "${LN}/api/v1/wallet?usr=${USER_ID}" \
        -H "X-Api-Key: ${AK}" -H "Content-Type: application/json" \
        -d "{\"name\":\"${w}\"}" | jq -r '.id')
    [[ -n "${WID[$w]}" && "${WID[$w]}" != "null" ]] || die "fallo wallet ${w}"
    log "  ✓ ${w}: ${WID[$w]}"
done

# 9. bootstrap-wallets.json
log "Paso 9: bootstrap-wallets.json"
jq -n --arg ak "$AK" --arg uid "$USER_ID" \
    --arg d "${WID[Dueno]}" --arg b "${WID[Barista]}" --arg p "${WID[Proveedor]}" \
    --arg i "${WID[Impuestos]}" --arg r "${WID[Reserva]}" \
'[{name:"Coffee Wallet",id:$uid,adminkey:$ak},{name:"Dueno",id:$d},{name:"Barista",id:$b},{name:"Proveedor",id:$p},{name:"Impuestos",id:$i},{name:"Reserva",id:$r}]' \
    > bootstrap-wallets.json
log "  ✓ 6 wallets"

# 10. Truncate (create DB + run alembic if fresh)
log "Paso 10: preparando orchestrator DB"
docker exec postgres psql -U lnbits -c "CREATE DATABASE orchestrator;" >/dev/null 2>&1 || true
docker exec orchestrator alembic -c /app/alembic.ini upgrade head >/dev/null 2>&1 || true
docker exec postgres psql -U lnbits -d orchestrator \
    -c "TRUNCATE payment_splits, payments, split_targets, split_rules, users, tenants CASCADE;" >/dev/null
log "  ✅ limpio"

# 11. Seed with env vars
log "Paso 11: seed"
docker exec \
    -e SEED_ADMIN_PASSWORD=${ORCHESTRATOR_SEED_ADMIN_PASSWORD} \
    -e SEED_LNBITS_ADMIN_KEY="$AK" \
    -e SEED_WALLET_DUENO_ID="${WID[Dueno]}" \
    -e SEED_WALLET_BARISTA_ID="${WID[Barista]}" \
    -e SEED_WALLET_PROVEEDOR_ID="${WID[Proveedor]}" \
    -e SEED_WALLET_IMPUESTOS_ID="${WID[Impuestos]}" \
    -e SEED_WALLET_RESERVA_ID="${WID[Reserva]}" \
    orchestrator python -m scripts.seed 2>&1 | while IFS= read -r l; do log "  $l"; done

# 12. Verify seed
log "Paso 12: verificando"
t=$(docker exec postgres psql -U lnbits -d orchestrator -t -c "SELECT COUNT(*) FROM tenants;" | tr -d ' ')
u=$(docker exec postgres psql -U lnbits -d orchestrator -t -c "SELECT COUNT(*) FROM users;" | tr -d ' ')
r=$(docker exec postgres psql -U lnbits -d orchestrator -t -c "SELECT COUNT(*) FROM split_rules;" | tr -d ' ')
g=$(docker exec postgres psql -U lnbits -d orchestrator -t -c "SELECT COUNT(*) FROM split_targets;" | tr -d ' ')
[[ "$t" -eq 1 && "$u" -eq 1 && "$r" -eq 1 && "$g" -eq 5 ]] \
    || die "seed incompleto: t=${t} u=${u} r=${r} g=${g}"
log "  ✅ t=${t} u=${u} r=${r} g=${g}"

# 13. Channel (warmup: mine blocks, wait for LND RPC)
log "Paso 13: canal Lightning"
# Mine some blocks so LND syncs (bitcoin-cli without -rpcwallet needs default wallet)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} createwallet "default" >/dev/null 2>&1 || true
ADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} getnewaddress)
docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} generatetoaddress 250 "$ADDR" >/dev/null
log "  minados 250 bloques, esperando LND..."
sleep 10
# Wait for LND RPC with getinfo (most reliable endpoint)
for attempt in $(seq 1 15); do
    info=$(docker exec lnd lncli --network=regtest getinfo 2>/dev/null)
    synced=$(echo "$info" | jq -r '.synced_to_chain // false')
    [[ "$synced" == "true" ]] && break
    log "  LND syncing... (intento ${attempt})"
    sleep 5
done
[[ "$synced" == "true" ]] || die "LND no sincronizó en 75s"
log "  LND synced, height=$(echo "$info" | jq -r '.block_height')"
chan=$(docker exec lnd lncli --network=regtest listchannels 2>/dev/null | jq '.channels | length // 0')
log "  canales: ${chan}"
if [[ "$chan" -eq 0 ]]; then
    L2PK=$(docker exec lnd2 lncli --network=regtest getinfo | jq -r '.identity_pubkey')
    docker exec lnd lncli --network=regtest connect "${L2PK}@lnd2:9735" >/dev/null 2>&1 || true
    sleep 2
    # Fund LND from bitcoind
    LND_ADDR=$(docker exec lnd lncli --network=regtest newaddress np2wkh | jq -r '.address')
    docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} \
        sendtoaddress "$LND_ADDR" 40 >/dev/null
    CADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} getnewaddress)
    docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} generatetoaddress 6 "$CADDR" >/dev/null
    sleep 3
    log "  LND fondeado (40 BTC), abriendo canal..."
    docker exec lnd lncli --network=regtest openchannel --node_key="${L2PK}" --local_amt=5000000 >/dev/null
    CADDR=$(docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} getnewaddress)
    docker exec bitcoind bitcoin-cli -regtest -rpcuser=${RPC_USER} -rpcpassword=${RPC_PASS} generatetoaddress 6 "$CADDR" >/dev/null
    log "  ✅ canal abierto + 6 bloques"
else
    log "  canal existente (${chan})"
fi

# 14. Wait active
log "Paso 14: esperando canal active (max 60s)"
for ((i=0; i<60; i+=POLL)); do
    active=$(docker exec lnd lncli --network=regtest listchannels 2>/dev/null | jq -r '.channels[0].active // false')
    [[ "$active" == "true" ]] && break; sleep $POLL
done
[[ "$active" == "true" ]] || die "canal no active en 60s"
l2bal=$(docker exec lnd2 lncli --network=regtest listchannels 2>/dev/null | jq -r '(.channels[0].local_balance // "0") | tonumber / 1000 | floor')
log "  ✅ active, lnd2 outbound: ${l2bal} sats"

# 15. Rebalance
log "Paso 15: rebalance"
if [[ "$l2bal" -lt 100000 ]]; then
    log "  esperando 10s para routing..."
    sleep 10
    log "  rebalance 1M sats lnd→lnd2"
    for rtry in $(seq 1 5); do
        inv=$(docker exec lnd2 lncli --network=regtest addinvoice --amt=1000000 2>/dev/null | jq -r '.payment_request // empty')
        if [[ -z "$inv" ]]; then
            log "  addinvoice falló (intento ${rtry}/5)"
            sleep 3; continue
        fi
        pay_out=$(docker exec lnd lncli --network=regtest payinvoice --force --pay_req="$inv" 2>&1 || true)
        if echo "$pay_out" | grep -q 'SUCCEEDED'; then
            log "  ✅ pago exitoso"
            break
        fi
        [[ $rtry -eq 5 ]] && { log "  último intento falló: $(echo "$pay_out" | tail -5)"; die "rebalance falló tras 5 intentos"; }
        log "  intento ${rtry}/5 falló, retry..."
        sleep 3
    done
    sleep 2
    l2bal=$(docker exec lnd2 lncli --network=regtest listchannels 2>/dev/null | jq -r '(.channels[0].local_balance // "0") | tonumber / 1000 | floor')
    log "  ✅ lnd2 outbound: ${l2bal} sats"
else
    log "  lnd2 outbound ${l2bal} >= 100k, skip"
fi

# 16. Smoke test (orchestrator)
log "Paso 16: smoke test (${SMOKE} sats)"
# a. Login (retry — orchestrator API may need warmup)
for ltry in $(seq 1 15); do
    TOKEN=$(curl -s -X POST "${OC}/api/v1/auth/login" -H "Content-Type: application/json" \
        -d '{"email":"'"${ADMIN_EMAIL}"'","password":"'"${ORCHESTRATOR_SEED_ADMIN_PASSWORD}"'"}' | jq -r '.access_token // .token // empty')
    [[ -n "$TOKEN" ]] && break
    sleep 3
done
[[ -n "$TOKEN" ]] || die "login orchestrator falló tras 15 intentos"
log "  a. token: ${TOKEN:0:16}..."
# b. Invoice
INV=$(curl -s -X POST "${OC}/api/v1/invoices" -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" -d "{\"amount_sats\":${SMOKE},\"memo\":\"smoke\"}")
IID=$(echo "$INV" | jq -r '.id'); B11=$(echo "$INV" | jq -r '.bolt11 // .payment_request')
[[ -n "$IID" && "$IID" != "null" ]] || die "invoice creation failed: ${INV}"
log "  b. invoice id=${IID}"
# c. Pay
docker exec lnd2 lncli --network=regtest payinvoice --force --pay_req="${B11}" >/dev/null \
    || die "payinvoice falló"
log "  c. pago enviado"
# d. Wait webhook
sleep 6
# e. Check splits
SUM=$(curl -s "${OC}/api/v1/invoices/${IID}" -H "Authorization: Bearer ${TOKEN}" \
    | jq '[.splits[]?.amount_sats // 0] | add // 0')
log "  d. suma splits: ${SUM}"
[[ "$SUM" -eq "$SMOKE" ]] || die "smoke test FAIL: suma=${SUM} esperado=${SMOKE}"
log "  ✅ smoke test OK"

# 17. Summary
l2bal=$(docker exec lnd2 lncli --network=regtest listchannels 2>/dev/null | jq -r '(.channels[0].local_balance // "0") | tonumber / 1000 | floor')
echo ""
echo "[bootstrap] ✅ Stack listo"
echo "   Dashboard: http://localhost:3000"
echo "   API:       http://localhost:8000"
echo "   LNBits:    http://localhost:5000"
echo "   Login:     ${ADMIN_EMAIL} / ${ORCHESTRATOR_SEED_ADMIN_PASSWORD}"
echo "   Canal:     lnd ↔ lnd2 (5M sats, ~${l2bal} outbound en lnd2)"
echo "   Smoke test: ${SMOKE} sats → 5 splits, suma exacta ✅"
