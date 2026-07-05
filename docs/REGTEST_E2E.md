# Regtest E2E — Polar + BTCPay + Zeus

The validated local end-to-end loop:

**Zeus pays a BTCPay Lightning invoice → BTCPay settles → OpenSplit detects it →
applies the active split rule → mints payouts to receiver LND nodes → BTCPay's
Lightning payout processor sends them → reconciliation flips the payment to
`paid` → the Split Proof balances.**

Two gotchas that will bite you if skipped — read these first:

1. **Always start the orchestrator with BOTH compose files:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.receivers.yml up -d
   ```
   A plain `docker compose up -d orchestrator` recreates the container WITHOUT
   the local-only receivers overlay and silently drops the six
   `LND_RECEIVER_{CAROL,DAVE}_*` env vars — receiver targets then fail
   validation (422 on rule create/activate) and payouts to them break.
2. **Enable BTCPay's Lightning payout processor** (Store → Settings → Payout
   Processors → *Automated Lightning Sender*). Without it, payouts stay in
   `AwaitingPayment` forever — the orchestrator only mirrors payout state, it
   never sends. With it enabled, approved payouts auto-send over Lightning.

---

## 0. Prerequisites

- **Polar** running a regtest network with:
  - a **bitcoind** node,
  - one LND node for **BTCPay**,
  - one LND node for **Zeus** (payer), with a funded channel Zeus → BTCPay,
  - one or two LND nodes for the **split receivers** (e.g. Carol, Dave), each
    with inbound liquidity so BTCPay can pay them.
- **BTCPay Server** connected to its Polar LND node, with a **Store** created.
- A **BTCPay Greenfield API key** scoped to the store (create invoices, view
  invoices, modify store settings for webhooks, create/manage payouts).
- **Zeus wallet** connected to its Polar node.

> Networking: inside a container, `localhost` is the container itself. Use
> `host.docker.internal` (or a LAN IP) so BTCPay reaches the orchestrator and
> the orchestrator reaches BTCPay / the receiver LND nodes.

---

## 1. Configure the receivers overlay

Copy the example and fill in real values for each split receiver's LND node:

```bash
cp docker-compose.receivers.example.yml docker-compose.receivers.yml
# edit docker-compose.receivers.yml:
#   LND_RECEIVER_CAROL_URL       -> https://host.docker.internal:8084 (Carol REST)
#   LND_RECEIVER_CAROL_MACAROON_HEX -> xxd -p -c 0 .../invoice.macaroon
#   LND_RECEIVER_CAROL_TLS_CERT_HEX -> xxd -p -c 0 .../tls.cert
#   ...same for DAVE
```

The label (`CAROL`, `DAVE`) must match the split target's label uppercased.

---

## 2. Bring up OpenSplit

```bash
cp .env.example .env    # fill POSTGRES_*, ORCHESTRATOR_JWT_SECRET, ORCHESTRATOR_SEED_ADMIN_PASSWORD
echo 'VITE_API_BASE_URL=http://localhost:8000/api/v1' > dashboard/.env.local

docker compose -f docker-compose.yml -f docker-compose.receivers.yml up -d
```

Startup runs `alembic upgrade head` and the admin seed automatically. Log in at
`http://localhost:3000` as the seeded admin
(`$SEED_ADMIN_EMAIL` / `$ORCHESTRATOR_SEED_ADMIN_PASSWORD`).

| Service   | URL                        |
| --------- | -------------------------- |
| Dashboard | http://localhost:3000      |
| API docs  | http://localhost:8000/docs |

---

## 3. Connect BTCPay in OpenSplit Settings

In the dashboard, go to **Settings → BTCPay** and enter:

- **BTCPay URL** — `http://host.docker.internal:3003` (your store's BTCPay)
- **API key** — the Greenfield key
- **Store ID**

Save. OpenSplit verifies the connection and shows the store.

---

## 4. Guided webhook

Still in **Settings → BTCPay**, use the **guided webhook** flow. OpenSplit
generates the webhook URL (`/api/v1/webhooks/btcpay/<tenant-id>`) and a secret.
Create the webhook in **BTCPay → Store → Settings → Webhooks** with:

- **Payload URL**: the URL OpenSplit shows,
- **Secret**: the secret OpenSplit shows,
- **Events**: *An invoice has been settled* (`InvoiceSettled`).

Set the store invoice speed policy so Lightning settles immediately
(Store → Settings → "Consider the invoice settled when…").

Enable the **Automated Lightning Sender** payout processor now (gotcha #2).

---

## 5. Create an active split rule

In the dashboard, create a rule with percentage targets whose **labels match
the receiver overlay** (e.g. `Carol` 60%, `Dave` 40%). Activate it. Percentages
must sum to 100. Activation validates each receiver target against its
`LND_RECEIVER_<LABEL>_*` config — a 422 here means the overlay wasn't applied
(gotcha #1).

---

## 6. Pay an invoice from Zeus

1. Create an invoice in BTCPay denominated in **SATS** (a fiat-denominated
   amount is mis-scaled on auto-create).
2. Scan and pay it from **Zeus** over the Polar regtest channel.

If paying from a Polar node's CLI instead of Zeus:

```bash
docker exec polar-n1-alice lncli --network=regtest --lnddir=/home/lnd/.lnd \
  payinvoice --force <bolt11>
```

---

## 7. Watch splits → payouts → reconciliation → paid

1. **Settle** — BTCPay flips the invoice to *Settled* and fires
   `InvoiceSettled`.
2. **Detect + split** — OpenSplit creates the `Payment`, applies the active
   rule, and records the per-target split audit trail.
3. **Payout** — for each receiver target it mints a fresh BOLT11 on that
   receiver's LND node and submits a BTCPay payout.
4. **Auto-send** — BTCPay's Lightning payout processor sends the approved
   payouts.
5. **Reconcile** — orchestrator reconciliation mirrors payout state; once all
   payouts complete the payment flips to **paid**.
6. **Split Proof** — open the payment in **Payments → Split Proof**:
   percentages, per-target amounts, payout status, and the integrity check
   (sum of splits == payment amount) with `balanced: true`. The authenticated
   permalink is `/proof/:paymentId`.

---

## 8. Verify

- **BTCPay** → Store → Webhooks → *Recent deliveries* shows `200`.
- **Logs**: `docker logs -f orchestrator`.
- **API**:
  ```bash
  TOKEN=$(curl -s localhost:8000/api/v1/auth/login \
    -H 'content-type: application/json' \
    -d '{"email":"<seed-email>","password":"<seed-pw>"}' | jq -r .access_token)
  curl -s localhost:8000/api/v1/payments -H "authorization: Bearer $TOKEN" | jq '.items[0]'
  curl -s localhost:8000/api/v1/payments/<payment-id>/proof \
    -H "authorization: Bearer $TOKEN" | jq '.integrity'
  ```
  Expect `"balanced": true`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 422 on rule create/activate | receivers overlay not applied | bring the stack up with BOTH `-f` files (gotcha #1) |
| Payouts stuck `AwaitingPayment` | no automated payout processor | enable *Automated Lightning Sender* (gotcha #2) |
| Payment amount wrong (e.g. 5 sats) | invoice denominated in fiat | denominate in **SATS** |
| Webhook delivery `401` | secret mismatch | make the BTCPay webhook secret match the one OpenSplit generated |
| Webhook delivery `404` | wrong tenant id in URL | use the exact URL from the guided webhook |
| No webhook fires | invoice not "settled" | set the store speed policy so LN settles immediately |
| Orchestrator can't reach BTCPay | `localhost` inside container | use `host.docker.internal` / LAN IP |
| Payout fails on send | receiver has no inbound liquidity | fund a channel to the receiver's LND node |

> The **detect → split → proof** path succeeds even if live payout delivery
> fails — the Split Proof is recorded from the settled invoice regardless of
> payout outcome.
