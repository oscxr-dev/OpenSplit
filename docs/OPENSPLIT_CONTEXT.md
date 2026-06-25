# OpenSplit — Product Context

> Direction document for the rebrand/evolution of **Pixel Split → OpenSplit**.
> This file defines *what we are building and why*. It does not change code.

---

## Final product definition

**OpenSplit** is a Bitcoin revenue-sharing dashboard for teams, projects,
communities, and Bitcoin businesses that run on **BTCPay Server**. It lets a
group accept BTC payments and automatically split them among members according
to clear, versioned rules — with member visibility, full payment history, and
optional public transparency pages.

It is the layer *on top of* BTCPay that turns "one store receiving Bitcoin" into
"a group sharing Bitcoin fairly, visibly, and verifiably."

---

## Target users

- **Open-source / project teams** splitting donations or sponsorships among contributors.
- **Communities & collectives** (clubs, DAOs-lite, meetups) sharing pooled income.
- **Small Bitcoin businesses** distributing revenue among owners/staff/suppliers.
- **Creators / co-ops** splitting earnings between collaborators.

Primary persona: a **non-developer admin** who can run (or already runs) a BTCPay
store and wants fair, automatic, transparent splits without spreadsheets.

---

## Core problem

Groups receiving Bitcoin together have **no trustworthy, transparent way to split
income**. Today they rely on manual transfers, spreadsheets, and informal trust —
which is error-prone, opaque, and unverifiable. Existing tooling either requires
custodial wallets per member or gives no audit trail / member-facing visibility.

---

## Core value

1. **Fairness** — exact, deterministic splits (no orphaned sats; rules frozen per payment).
2. **Visibility** — every member sees their share and history.
3. **Transparency (optional)** — public page proving how income was shared.
4. **Non-custodial-friendly** — pays members at their own Lightning addresses via BTCPay.
5. **Auditability** — immutable per-payment split records and payout reconciliation.

---

## MVP scope

**In scope:**
- BTCPay-backed tenants (single backend focus; LNbits path kept but de-emphasized).
- Create/edit **versioned split rules** (members + percentages, summing to 100%).
- Members defined by **label + Lightning address**.
- Receive payment → freeze active rule → compute splits → execute payouts → reconcile.
- **Payment history** with per-split status (pending / in_progress / completed / failed) and retry.
- **Dashboard summary** (totals, recent payments, failures needing attention).
- **Auth** (tenant + users, roles owner/staff).
- Connection/health status for the BTCPay backend.

**Out of scope for MVP (see "Features to avoid"):**
- Public transparency pages (design now, build after MVP).
- Notifications (email/Telegram), reporting/exports, branding customization.
- Multi-currency accounting, LND liquidity gauge.

---

## What makes OpenSplit different

| | **OpenSplit** | **BTCPay Prism** | **LNbits Split Payments** |
|---|---|---|---|
| Split target | Lightning addresses, % rules | Pull-payment destinations, % | LNbits wallets, % |
| Rule versioning | ✅ frozen per payment | ❌ | ❌ |
| Per-payment audit trail | ✅ immutable records | limited | limited |
| Payout reconciliation worker | ✅ status + retry | ❌ | n/a (internal transfer) |
| Member-facing visibility | ✅ (planned core) | ❌ | ❌ |
| Optional public transparency | ✅ (roadmap) | ❌ | ❌ |
| Audience | teams/communities/businesses | BTCPay power users | LNbits users |

**One-line positioning:** Prism and LNbits Split *route* sats; **OpenSplit makes the
split a first-class, versioned, auditable, member-visible object.**

---

## Recommended architecture

Keep the proven Pixel Split spine; rebrand and narrow it.

```
Payer ── BTCPay invoice ──▶ BTCPay Server (per-tenant store)
                               │ webhook (signed)
                               ▼
                       FastAPI orchestrator
              ┌──────────────┼─────────────────────┐
        freeze active     calculate_splits     execute payouts
        split rule       (largest remainder)   (BTCPay pull payments
              │                 │               → Lightning addresses)
              ▼                 ▼                     │
         PostgreSQL (payments, payment_splits audit) ◀┘
              ▲
   payout_reconciliation_worker (polls payout status, retries, marks final)
              │
        React dashboard (history, rules, summary, member views)
```

- **Backend:** FastAPI (async SQLAlchemy) + PostgreSQL + Alembic. Keep as-is.
- **Payments:** BTCPay Greenfield API (invoices + pull payments). Keep as-is.
- **Frontend:** existing React/Vite PWA, rebranded. (Migration to Next.js explicitly
  deferred — see `MIGRATION_PLAN.md`.)
- **Multi-tenant** model already supports `adapter_type` (`lnbits` | `btcpay`).

---

## Screens needed (MVP)

1. **Login / auth**
2. **Dashboard / summary** — totals, recent payments, failures needing attention
3. **Split rules** — list + create/edit versioned rules (members, %, sums to 100%)
4. **Payments / history** — filterable list + per-payment detail with per-split status & retry
5. **Members view** — each member's share + history (lightweight in MVP)
6. **Settings / connection** — BTCPay store connection status, tenant profile
7. *(Roadmap)* **Public transparency page** — read-only proof of how income was shared

---

## Features to avoid (for now)

- Public transparency pages (design the data model, defer the build).
- Email / Telegram notifications and event bell.
- Reporting, PDF/CSV export, branding/theme customization beyond tokens.
- LND liquidity gauge / on-chain balance integration.
- Framework migration (Next.js) — no value to MVP.
- Mainnet hardening beyond the security cleanup checklist until launch is scheduled.
