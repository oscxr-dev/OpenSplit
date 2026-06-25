#!/usr/bin/env bash
# =====================================================================
# setup.sh - Bring up the coffee-split signet stack and wait for LNBits
# =====================================================================
set -euo pipefail

# Move to the project root (parent of scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Load .env so we can echo credentials at the end.
# shellcheck disable=SC1091
set -a; source ./.env; set +a

# -- Pretty printing -------------------------------------------------
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[setup]${NC} $*"; }
ok()   { echo -e "${GREEN}[ ok ]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err ]${NC} $*" >&2; }

# -- Pre-flight ------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  err "Docker is not installed."; exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  err "Docker Compose v2 is required (try: docker compose version)."; exit 1
fi

# -- Bring the stack up ---------------------------------------------
log "Pulling images (this may take a moment the first time)…"
docker compose pull

log "Starting the stack…"
docker compose up -d

# -- Wait for bitcoind ---------------------------------------------
log "Waiting for bitcoind to become healthy…"
for i in {1..60}; do
  status=$(docker inspect -f '{{.State.Health.Status}}' bitcoind 2>/dev/null || echo "starting")
  if [[ "$status" == "healthy" ]]; then ok "bitcoind is healthy."; break; fi
  sleep 2
  if [[ "$i" == "60" ]]; then err "bitcoind did not become healthy in time."; docker compose logs --tail=50 bitcoind; exit 1; fi
done

# -- Wait for LND --------------------------------------------------
log "Waiting for LND to become healthy (wallet auto-init)…"
for i in {1..90}; do
  status=$(docker inspect -f '{{.State.Health.Status}}' lnd 2>/dev/null || echo "starting")
  if [[ "$status" == "healthy" ]]; then ok "lnd is healthy."; break; fi
  sleep 2
  if [[ "$i" == "90" ]]; then err "lnd did not become healthy in time."; docker compose logs --tail=80 lnd; exit 1; fi
done

# -- Wait for Postgres --------------------------------------------
log "Waiting for postgres to become healthy…"
for i in {1..30}; do
  status=$(docker inspect -f '{{.State.Health.Status}}' postgres 2>/dev/null || echo "starting")
  if [[ "$status" == "healthy" ]]; then ok "postgres is healthy."; break; fi
  sleep 2
done

# -- Wait for LNBits HTTP 200 -------------------------------------
log "Waiting for LNBits to answer HTTP 200 on http://localhost:5000 …"
deadline=$(( $(date +%s) + 240 ))
while :; do
  if code=$(curl -fsS -o /dev/null -w '%{http_code}' http://localhost:5000/ 2>/dev/null) \
     && [[ "$code" == "200" || "$code" == "302" || "$code" == "307" ]]; then
    ok "LNBits is responding (HTTP $code)."
    break
  fi
  if (( $(date +%s) > deadline )); then
    err "LNBits did not respond in time."
    docker compose logs --tail=80 lnbits
    exit 1
  fi
  sleep 3
done

# -- Done ---------------------------------------------------------
cat <<EOF

$(echo -e "${GREEN}=========================================================${NC}")
 Coffee Split Infrastructure - Phase 1 is up!
$(echo -e "${GREEN}=========================================================${NC}")

 Service URLs (host -> container):
   • bitcoind RPC : http://localhost:18443    (user: ${BITCOIN_RPC_USER})
   • LND REST     : https://localhost:8080
   • LND gRPC     : localhost:10009
   • LND P2P      : localhost:9735
   • Postgres     : localhost:5432            (db: ${POSTGRES_DB})
   • LNBits UI    : http://localhost:5000

 LNBits admin credentials (from .env):
   • Username     : ${LNBITS_ADMIN_USER}
   • Password     : ${LNBITS_ADMIN_PASS}

 Next steps:
   1) ./scripts/fund-lnd.sh        # mine blocks + fund LND on-chain
   2) ./scripts/test-lnbits.sh     # create a test LN invoice via LNBits
   3) Open http://localhost:5000   # log in with the admin credentials

EOF
