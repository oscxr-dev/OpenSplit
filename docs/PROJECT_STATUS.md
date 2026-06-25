# Coffee Split — Estado del proyecto

Última actualización: 2026-05-19

## Fases completadas
- [x] Fase 1 — Infra regtest (bitcoind, lnd, lnd2, lnbits, postgres)
- [x] Fase 1.5 — Canal Lightning + flujo invoice
- [x] Fase 2 — Split payments (regla 30/35/15/10/10)
- [x] Fase 3 — POS (LNDHub + tpos)
- [x] Fase 4 — Orchestrator FastAPI multi-tenant
- [x] Fase 5 — Dashboard PWA React
- [x] Bugfix P1 — Webhook LNBits → Orchestrator (auto-reconciliación)
- [x] Bugfix P5 — Algoritmo del residuo en splits (largest remainder, 0 sats huérfanos)
- [x] Issue A — LND healthcheck (SERVER_ACTIVE → RPC_ACTIVE en LND 0.18)
- [x] Issue B — Wallet IDs lookup por nombre (columna lnbits_wallet_name + resolución vía API)

## Próxima fase
- [ ] Fase 6 — Migración a signet (red de pruebas pública)

## Reportes
- `docs/e2e-report-2026-05-13.md` — validación E2E completa
- `docs/backlog.md` — bugs no críticos diferidos

## Bugs abiertos (backlog)
- ✅ Todos resueltos — ver `docs/backlog.md`

## Resumen 2026-05-19
- P3 — Activar regla: hook frontend conectado al endpoint dedicado
- Balances wallets: `GET /api/v1/wallets/balances` con acumulado + balance real LNBits
- sats→USD en POS: `useBtcPrice` hook con CoinGecko
- Deploy: `deploy.sh` unificado (build + up + healthcheck)
- F6 signet: explorada, documentada en `docs/signet_status.md`, bloqueada (bitcoind v26 sin soporte signet mining)

## Comandos útiles
- Levantar todo: `docker compose up -d`
- Ver logs: `docker compose logs -f <service>`
- Seed: `docker compose exec orchestrator python -m scripts.seed`
- Smoke test: ejecutar manual con login → create invoice → pay → verify

## Notas técnicas
- LND 0.18 reporta `RPC_ACTIVE` (no `SERVER_ACTIVE`) — healthcheck actualizado
- LND necesita que bitcoind mine un bloque post-restart para sincronizar (`generatetoaddress 1 <addr>`)
- Wallets LNBits persisten en PostgreSQL (IDs estables entre restarts)
- Split targets ahora guardan `lnbits_wallet_name` para resolución por nombre
- `pip install -e /app` necesario en orchestrator para que alembic funcione
