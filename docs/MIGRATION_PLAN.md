# Migration Plan — Pixel Split → OpenSplit

> Step-by-step plan to evolve the existing repo into OpenSplit.
> **This document is a plan only. No code is changed by this pass.**
> Execute steps later, with explicit approval, ideally one PR per phase.

---

## Guiding principles

- **Do not break working payment behavior.** The split engine, BTCPay flow,
  idempotency, frozen rules, and reconciliation worker are the crown jewels — keep them.
- **Rebrand is mostly naming + framing**, not a rewrite.
- **BTCPay-first.** Keep the LNbits adapter but treat BTCPay as the primary path.
- **Security cleanup before any public/open-source release** (see `SECURITY_CLEANUP.md`).

---

## What to KEEP (high value, proven)

| Area | Paths |
|---|---|
| Split calculation (largest remainder, exact sums) | `orchestrator/app/services/split_engine.py` |
| BTCPay Greenfield client (invoices, webhooks, payouts) | `orchestrator/app/services/btcpay_client.py` |
| Payout reconciliation worker | `orchestrator/app/services/payout_reconciliation.py` |
| Data model (tenants, users, split_rules/targets, payments, payment_splits) | `orchestrator/app/models/__init__.py` |
| Rule versioning + frozen-per-payment design | models + `routers/splits.py` |
| API routers | `orchestrator/app/routers/*.py` |
| Migrations | `orchestrator/alembic/versions/001…005_*.py` |
| Auth/security primitives | `orchestrator/app/core/security.py`, `core/deps.py` |
| React dashboard (rebrand, don't rewrite) | `dashboard/src/**` |
| Design token system | `dashboard/src/styles/tokens.css`, `tailwind.config.ts` |

## What to REMOVE / DE-EMPHASIZE

- **Coffee-shop / POS framing** that does not fit revenue-sharing for teams
  (POS keypad as a primary flow can become an optional "manual charge" later).
  - `dashboard/src/pages/PosPage.tsx`, `dashboard/src/components/pos/**` — keep code,
    demote from primary navigation; revisit during UI rebrand.
- **Regtest/signet lab scaffolding** is dev-only; keep for local dev but exclude
  from the OpenSplit product narrative.
  - `bitcoind/`, `lnd/`, `signet/`, `scripts/*lnd*`, `scripts/*signet*`,
    `docker-compose.regtest.yml`, `docker-compose.signet.yml`.
- **Environment-specific deploy artifacts** that contain real infra references must be
  removed from version control / rotated (see `SECURITY_CLEANUP.md`):
  - `docker-compose.cherito.yml` (untracked), `dashboard/.env.production` (tracked),
    `dashboard/.env.local` (untracked).

> Per current rules: this pass does **not** delete anything. The above are *recommendations*.

## What to RENAME (rebrand — defer to a dedicated phase)

- Product name strings **Pixel Split / Coffee Split → OpenSplit** in:
  - `README.md`, `dashboard/index.html`, `dashboard/manifest.json`,
    `dashboard/package.json` (`name`, `description`), `dashboard/.env.example`
    (`VITE_APP_NAME`), `orchestrator/README.md`, FastAPI `title` in
    `orchestrator/app/main.py`.
- Internal domain language: "tenant" → consider "workspace"/"group"; "POS/charge" →
  "incoming payment"; "split target" → "member". (Naming only; keep DB columns stable
  or migrate deliberately.)
- **Do not** rename DB tables/columns casually — wrap any rename in an Alembic migration.

## What to REWRITE (later, scoped)

- **Frontend information architecture** for the team/community audience
  (members view, transparency page) — additive, not a teardown.
- **CORS / auth hardening** (currently permissive) — see `CURRENT_STATE.md` known issues.
- **Branding/theming** surface (already token-driven; extend per-tenant brand fields
  already present in the `Tenant` model).

---

## Step-by-step migration

**Phase 0 — Safety (do first)**
1. Execute `SECURITY_CLEANUP.md`: stop tracking env/deploy files, fix `.gitignore`,
   rotate exposed secrets, scrub history if needed. Gate any public release on this.

**Phase 1 — Documentation & context (this pass)**
2. Land `OPENSPLIT_CONTEXT.md`, `MIGRATION_PLAN.md`, `CURRENT_STATE.md`,
   `SECURITY_CLEANUP.md`. ✅ (this commit)

**Phase 2 — Rebrand (naming only, no behavior change)**
3. Replace product-name strings (see "What to RENAME"). One PR, no logic changes.
4. Update icons/manifest/theme color to OpenSplit branding.

**Phase 3 — Domain reframing (BTCPay-first)**
5. Promote BTCPay tenant onboarding; demote LNbits + POS from primary nav.
6. Reframe UI copy: members, incoming payments, shares.

**Phase 4 — New MVP surfaces**
7. Add **Members view** (read from existing split_targets + payment_splits).
8. Design **public transparency page** data contract (build later).

**Phase 5 — Hardening**
9. Lock down CORS per environment; finish auth (httpOnly cookies, refresh rotation,
   rate limiting); add PostgreSQL integration tests.

**Phase 6 — Release prep**
10. Re-run security checklist; verify mainnet demo flow still green; tag release.

> Recommended: one PR per phase, each independently reviewable and revertible.
