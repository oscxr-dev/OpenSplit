# OpenSplit v0.1.0

First public release. OpenSplit is a self-hosted, non-custodial revenue-sharing
layer for BTCPay Server: incoming payments are split by a versioned rule,
payouts are created and reconciled through BTCPay, and every payment gets a
Split Proof page showing exactly what happened.

## Core splitting

- **Versioned, immutable split rules** — one active rule at a time; editing
  creates a new version, so every historical split stays attached to the exact
  rule that produced it.
- **Largest-remainder integer split math** — sat amounts always sum to the
  payment total; no floating-point drift. Property-tested with Hypothesis.
- **Partial rules** — rules covering less than 100% are supported, with the
  uncovered remainder handled explicitly.
- **Dust/remainder policy** — zero-sat shares and rounding remainders are
  handled honestly and shown, not silently dropped.

## BTCPay integration

- **Guided connection** requesting only the minimal Greenfield permissions
  OpenSplit uses (create invoices, view invoices, manage pull payments, view
  store settings) — no wallet or admin access.
- **Guided webhook setup** with a one-time secret and signature verification.
- **Payout creation + reconciliation** — splits become BTCPay pull-payment
  payouts, and OpenSplit reconciles their status back to `paid`, with
  double-payout protection.
- **Lightning payout processor detection** — OpenSplit detects whether the
  store has an automated Lightning payout processor and tells you when payouts
  are waiting on manual processing in BTCPay.

## Visibility

- **Pipeline status** — a status pill on the Team page and a detailed
  breakdown in Settings show where each stage of the pipeline stands.
- **"Waiting in BTCPay" surfacing** — payouts stuck on the BTCPay side are
  labeled as such instead of appearing silently pending.
- **Destination badges** — each receiver's payout destination type is visible
  at a glance.
- **Split Proof with permalink** — every payment has a proof page
  (`/proof/:paymentId`) showing the rule version, split amounts, payout
  statuses, and an integrity check.

## Privacy

- **Public proof pages are opt-in**, and even when enabled, **amounts are
  hidden by default** — sharing a proof doesn't reveal revenue unless you
  explicitly choose to.
- **Credentials are redacted everywhere** they surface: UI, API responses,
  logs.

## Developer experience

- **Regtest E2E runbook** (`docs/REGTEST_E2E.md`) — full walkthrough with
  Polar, BTCPay, and Zeus: settle an invoice, watch splits → payouts →
  reconciliation → paid.
- **CI workflow** — GitHub Actions running backend tests (pytest + Postgres)
  and frontend tests + build (vitest).
- **~291 tests**, including property-based tests on the split math and privacy
  regression tests on the public pages.

## Known limitations

Stated plainly, because a payout tool shouldn't hide them:

- **Payout records commit at end-of-loop.** A crash mid-execution can lose the
  audit trail of payouts already sent in that loop (the sats went out; the DB
  row didn't land). A fix is planned.
- **"Balance verified" is DB-internal arithmetic** — it proves the stored
  numbers are consistent with each other, not (yet) a cryptographic proof
  against the chain or BTCPay.
- **No 2FA** on the dashboard login (single-tenant email/password). Don't
  expose it to the public internet unprotected — see `SECURITY.md`.
- **English-only UI.**
- BTCPay API credentials are stored in plaintext in the database — see
  `SECURITY.md` for the threat model and mitigations.
