# Current State — Pixel Split (pre-OpenSplit)

> Snapshot for Claude Opus to continue safely. Describes what exists today,
> what works, what doesn't, and how to run it. No code changed by this pass.

---

## Repository structure (top level)

```
pixel-split/
├── orchestrator/         # FastAPI backend (async SQLAlchemy + Alembic)
├── dashboard/            # React + Vite PWA frontend
├── docker-compose.yml            # full regtest stack (bitcoind, lnd, lnd2, lnbits, postgres, orchestrator, dashboard)
├── docker-compose.regtest.yml    # regtest lab variant
├── docker-compose.signet.yml     # signet variant (exploratory)
├── docker-compose.cherito.yml    # deploy variant (UNTRACKED — sensitive, see SECURITY_CLEANUP.md)
├── bitcoind/ lnd/ signet/ postgres/   # node configs & dev scaffolding
├── scripts/              # bootstrap, funding, channel, split/POS setup helpers
├── docs/                 # status, e2e report, ADRs, + these OpenSplit docs
└── backups/
```

---

## Backend status (`orchestrator/`)

**Stack:** FastAPI, async SQLAlchemy, PostgreSQL, Alembic, structlog, httpx.

**Routers** (`app/routers/`): `auth`, `tenants`, `splits`, `invoices`, `wallets`,
`webhooks`, `payments`, `dashboard` — all mounted under `/api/v1`.

**Services** (`app/services/`):
- `split_engine.py` — exact integer split via **largest-remainder** algorithm
  (guarantee: `sum(splits) == amount_sats`; tiebreak by `order`). Property-tested.
- `btcpay_client.py` — BTCPay Greenfield client: invoices, **HMAC webhook verification**,
  payouts to Lightning addresses via pull payments. Per-tenant keys.
- `lnbits_client.py` — legacy LNbits path (split via LNbits wallets).
- `payout_reconciliation.py` — background worker polling payout status, retry + finalize.

**Data model** (`app/models/__init__.py`): `Tenant` (supports `adapter_type` =
`lnbits` | `btcpay`, plus brand + notify fields), `User` (roles owner/staff),
`SplitRule` (versioned, `parent_rule_id`), `SplitTarget` (label, %, `order`,
`ln_address`, lnbits wallet refs), `Payment`, `PaymentSplit` (audit trail:
`btcpay_payout_id`, status, `failure_reason`, `retry_count`, `last_checked_at`).

**Migrations:** `001_initial` → `002_add_wallet_name` → `003_add_ln_address` →
`004_tenant_btcpay` → `005_dashboard_foundation`.

**Status:** Functional. Multi-tenant, BTCPay + LNbits adapters, reconciliation worker
runs in the FastAPI lifespan. Mainnet demo flow reported tested previously.

---

## Frontend status (`dashboard/`)

**Stack:** React 18, Vite 5, TypeScript, Tailwind v3, React Query, React Router,
react-hook-form + zod, vite-plugin-pwa.

**Pages** (`src/pages/`): Login, Summary (index), Pos, Splits, Wallets, Payments, Settings.
Protected routing via `ProtectedRoute` + `AuthProvider`.

**Design system:** token-driven (`src/styles/tokens.css` — source of truth), wired into
`tailwind.config.ts`; dark + light (mempool-style) themes with a working toggle
(`hooks/useTheme.tsx`, sets `html[data-theme]`). Fonts: JetBrains Mono + Inter.

**Status:** Builds clean (typecheck + `vite build` green). PWA enabled.

---

## Docker status

- `docker-compose.yml` defines the full regtest lab: `bitcoind`, `lnd`, `lnd2`,
  `lnbits`, `postgres`, `orchestrator`, `dashboard` on a private network.
- Orchestrator has a `Dockerfile`; dashboard has a `Dockerfile` + `nginx.conf` for
  static serving.
- `docker-compose.cherito.yml` is a deploy variant and is **untracked** and contains
  sensitive infra references — see `SECURITY_CLEANUP.md`.

---

## What works

- Multi-tenant auth (JWT) and tenant-scoped endpoints.
- BTCPay invoice creation, signed webhook receipt, split execution, payouts.
- Exact split math (no orphaned sats), frozen rule per payment, idempotency.
- Payout reconciliation (status transitions, retry).
- Dashboard: summary, payments list + detail + retry, splits rules, themes.

## What does NOT work / incomplete

- **CORS is fully open** (`allow_origins=["*"]` in `orchestrator/app/main.py`) — must be
  restricted per environment before release.
- **Auth hardening incomplete** — no httpOnly cookie/refresh rotation/rate limiting
  (tracked in `docs/dashboard-implementation-status.md`).
- **LND liquidity** is shown as unavailable (no real LND balance adapter wired).
- **Signet path** explored but blocked (documented in `docs/signet_status.md`).
- **Notifications, reporting/exports, branding UI** not built.
- No PostgreSQL integration test suite yet (unit/property tests exist for split logic).
- Frontend still uses **coffee-shop/POS framing** (pre-rebrand).

---

## How to run locally

> Exact commands live in `README.md` / `orchestrator/README.md`. Summary below.
> Provide secrets via environment / local `.env` files — never commit them.

**Full stack (regtest):**
```bash
docker compose up -d
docker exec orchestrator python3 -m alembic upgrade head
docker exec orchestrator sh -c "PYTHONPATH=/app python3 /app/scripts/seed.py"
```

**Backend only (dev):**
```bash
cd orchestrator
# set ORCHESTRATOR_* env vars (DB URL, JWT secret, BTCPay/LNbits config) — do not hardcode
python3 -m alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000  (/docs for OpenAPI)
```

**Frontend (dev):**
```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
npm run build      # tsc + vite build
npm test           # vitest
```

> **Dev note:** the project was previously named `coffee-split`. If a stale Vite dev
> server from the old path is still bound to a port, kill it before starting — it can
> serve old cached assets. PWA service workers can also cache an old build; use a
> private window or unregister the SW to verify fresh changes.

---

## Configuration surface (names only — set via env, never commit values)

- Backend: `ORCHESTRATOR_DB_URL`, `ORCHESTRATOR_JWT_SECRET`,
  `ORCHESTRATOR_LNBITS_*`, `ORCHESTRATOR_*WEBHOOK_SECRET`,
  `ORCHESTRATOR_SEED_ADMIN_PASSWORD`, per-tenant BTCPay key/store/webhook (in DB).
- Frontend: `VITE_API_BASE_URL`, `VITE_APP_NAME`, `VITE_DEFAULT_CURRENCY`.
