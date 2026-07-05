# OpenSplit

[![CI](https://github.com/oscxr-dev/OpenSplit/actions/workflows/ci.yml/badge.svg)](https://github.com/oscxr-dev/OpenSplit/actions/workflows/ci.yml)

OpenSplit is a self-hosted, **non-custodial Bitcoin revenue-sharing** app with a
**public proof dashboard**, built on **BTCPay Server**. It's for teams,
businesses, and communities that receive Bitcoin payments and need to split them
clearly, automatically, and verifiably.

OpenSplit never holds funds: it reads settled BTCPay invoices, applies your
split rules, and directs payouts through BTCPay. Every payment produces a
**Split Proof** — an auditable record showing the rule, the per-recipient
amounts, the payout status, and an integrity check that the splits sum to the
payment.

OpenSplit v0.1 is BTCPay-first.

## Core flow

```text
BTCPay payment → OpenSplit rule → split calculation → payouts → Split Proof
```

## What it does

* Percentage-based split rules for incoming Bitcoin payments
* BTCPay Server-first, non-custodial by design
* A Split Proof for every payment (rule, amounts, payout status, integrity check)
* Protection against double payouts
* Accurate payment status tracking through to `paid`
* Honest handling of zero-sat splits
* Docker-based local development

## Local development

```bash
cp .env.example .env      # fill the secrets marked <CHANGE_ME>
docker compose up -d
```

For the demo/regtest payout path (paying receiver LND nodes directly), also copy
the receivers overlay and bring the stack up with both files — see the runbook:

```bash
cp docker-compose.receivers.example.yml docker-compose.receivers.yml
docker compose -f docker-compose.yml -f docker-compose.receivers.yml up -d
```

| Service   | URL                        |
| --------- | -------------------------- |
| Dashboard | http://localhost:3000      |
| API docs  | http://localhost:8000/docs |

## Documentation

* [`docs/REGTEST_E2E.md`](docs/REGTEST_E2E.md) — end-to-end regtest walkthrough
  (Polar + BTCPay + Zeus): settle an invoice, watch splits → payouts →
  reconciliation → paid, and inspect the Split Proof.
* [`.env.example`](.env.example) — all configuration, with inline notes.

## Notes

LNbits is not the main flow in v0.1. It may be supported later as a community
adapter.

## License

MIT
