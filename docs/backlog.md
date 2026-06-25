# Backlog — Coffee Split Infrastructure

Issues que no son críticos para el MVP. Ordenados por prioridad estimada.

---

## ~~P3 — Agregar endpoint POST /splits/{id}/activate~~ ✅

**Origen:** E2E report 2026-05-13  
**Estado:** Completo  
- ✅ Endpoint `POST /{rule_id}/activate` en `routers/splits.py`
- ✅ Desactiva regla activa anterior automáticamente
- ✅ Botón "Activar" en `SplitsPage.tsx` (conectado al endpoint correcto via `useActivateSplit` hook)
- ✅ Dashboard rebuild sin errores

---

## P6 — LND Docker HEALTHCHECK lento (~3 min)

**Origen:** E2E report 2026-05-13  
**Prioridad:** Baja  
**Estimación:** 30min  
**Descripción:** El healthcheck de LND tarda ~3min post-restart. No es error real — LND arranca limpio pero el healthcheck tiene muchos retries.

**Fix sugerido:** En docker-compose.yml, reducir `retries: 30` a `retries: 15` para lnd y lnd2.

---

## ~~Mejora UX — Endpoint de balances de wallets~~ ✅

**Origen:** E2E report 2026-05-13  
**Estado:** Completo  
- ✅ Endpoint `GET /api/v1/wallets/balances` en `routers/wallets.py`
- ✅ Calcula acumulado por wallet desde PaymentSplit en DB
- ✅ Consulta balance real en LNBits vía `get_wallet()` (LNBitsClient ya existía)
- ✅ Hook `useWalletBalances` con polling cada 60s
- ✅ `WalletsPage.tsx` renovada: muestra acumulado + balance actual
- ✅ Orquestrador + Dashboard rebuild: ✅

---

## Mejora UX — Conversión sats→USD en POS

**Origen:** Spec Fase 5  
**Prioridad:** Baja  
**Estimación:** 2h  
**Descripción:** El POS muestra solo sats. Agregar conversión a USD con tipo de cambio fijo o vía API externa.

---

## Mejora DevOps — Script de deploy unificado

**Origen:** P2 fix  
**Prioridad:** Baja  
**Estimación:** 1h  
**Descripción:** `docker compose build dashboard` debe ejecutarse automáticamente en el deploy para evitar servir builds viejas.

## ~~Mejora UX — Conversión sats→USD en POS~~ ✅

**Origen:** Spec Fase 5  
**Estado:** Completo  
- ✅ `useBtcPrice` hook con CoinGecko API (cache 5 min, retry 3x)
- ✅ POS muestra ≈ $X.XX USD junto al monto en sats
- ✅ Muestra `< $0.01` para montos muy pequeños
- ✅ Dashboard rebuild: ✅

## ~~Mejora DevOps — Script de deploy unificado~~ ✅

**Origen:** P2 fix  
**Estado:** Completo  
- ✅ `deploy.sh` — build, up, healthcheck todo en uno
- ✅ Flags: `--build` (default), `--up`, `--restart`, `--status`
- ✅ Espera hasta 90s por servicios healthy
- ✅ chmod +x, funciona desde cualquier directorio
