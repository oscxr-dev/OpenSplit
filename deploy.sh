#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Coffee Split Infrastructure unified deploy script
#
# Usage:
#   ./deploy.sh               # Full deploy: build + up
#   ./deploy.sh --build       # Force rebuild all images, then up
#   ./deploy.sh --up          # Just docker compose up (no build)
#   ./deploy.sh --restart     # Recreate containers with existing images
#   ./deploy.sh --status      # Show current state
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.yml"
BUILD_FLAG=""

# ── Parse args ────────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
  BUILD_FLAG="--build"
fi

for arg in "$@"; do
  case "$arg" in
    --build)   BUILD_FLAG="--build" ;;
    --up)      BUILD_FLAG="" ;;
    --restart) echo "→ Recreating containers..."; docker compose -f "$COMPOSE_FILE" up -d --force-recreate; exit 0 ;;
    --status)  echo "→ Current state:"; docker compose -f "$COMPOSE_FILE" ps; exit 0 ;;
    --help|-h) sed -n '3,14p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────
echo "→ Pre-flight checks..."

# Check Docker
if ! docker info > /dev/null 2>&1; then
  echo "✗ Docker is not running." >&2
  exit 1
fi

# Check compose file
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "✗ $COMPOSE_FILE not found." >&2
  exit 1
fi

# ── Build ─────────────────────────────────────────────────────────────
if [[ -n "$BUILD_FLAG" ]]; then
  echo "→ Building images (dashboard, orchestrator)..."
  docker compose -f "$COMPOSE_FILE" build dashboard orchestrator
  echo "  ✓ Build complete"
fi

# ── Start services ────────────────────────────────────────────────────
echo "→ Starting all services..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "  ✓ All services started"
echo ""

# ── Wait for health ───────────────────────────────────────────────────
echo "→ Waiting for services to become healthy..."
WAIT_SECONDS=90
INTERVAL=5
ELAPSED=0

while [[ $ELAPSED -lt $WAIT_SECONDS ]]; do
  UNHEALTHY=$(docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null \
    | grep -v "healthy\|NAME" \
    | wc -l)

  if [[ "$UNHEALTHY" -eq 0 ]]; then
    echo "  ✓ All services healthy!"
    echo ""
    docker compose -f "$COMPOSE_FILE" ps
    exit 0
  fi

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

# ── Timeout ───────────────────────────────────────────────────────────
echo "  ⚠ Timeout reached ($WAIT_SECONDS s). Some services may still be starting:"
docker compose -f "$COMPOSE_FILE" ps
exit 1
