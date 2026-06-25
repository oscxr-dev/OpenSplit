# OpenSplit Demo Runbook — Polar + BTCPay + Zeus

Live regtest demo of the full flow:

**Zeus pays a BTCPay POS invoice → BTCPay settles → OpenSplit detects it →
applies the split rule → Team updates → Payments shows the Split Proof.**

This runbook only *configures and runs* the demo. It does not change any
application logic.

---

## 0. Prerequisites

- **Polar** running a regtest network with: a Bitcoin node, a Lightning node
  for **BTCPay**, and a Lightning node for **Zeus** (with a funded channel from
  Zeus → BTCPay so Zeus can pay).
- **BTCPay Server** connected to its Polar Lightning node, with a **Store** and
  a **POS app** (or Point of Sale plugin) created.
- A **BTCPay Greenfield API key** scoped to the store (permissions:
  `btcpay.store.cancreateinvoice`, `btcpay.store.canviewinvoices`,
  `btcpay.store.cancreatenonapprovedpullpayments` / payouts,
  `btcpay.store.canmodifystoresettings` for webhooks).
- **Zeus wallet** connected to its Polar node.
- OpenSplit stack runnable via `docker-compose.regtest.yml`.

> Networking note: inside containers, `localhost` is the container itself. Use
> `host.docker.internal` (or a LAN IP) so BTCPay can reach the orchestrator and
> the orchestrator can reach BTCPay.

---

## 1. Bring up OpenSplit

```bash
cp .env.example .env          # fill POSTGRES_*, ORCHESTRATOR_JWT_SECRET, ORCHESTRATOR_SEED_ADMIN_PASSWORD
echo 'VITE_API_BASE_URL=http://localhost:8000/api/v1' > dashboard/.env.local

docker compose -f docker-compose.regtest.yml up -d postgres orchestrator dashboard
```

Migrations and the base seed are **not** automatic:

```bash
docker exec orchestrator alembic upgrade head
docker exec orchestrator python scripts/seed.py     # creates the demo tenant + admin user
```

Default login (unless overridden): `admin@bitcrew.example` / `$ORCHESTRATOR_SEED_ADMIN_PASSWORD`.

---

## 2. Provision the BTCPay demo tenant

Set the BTCPay values from your store, define the split targets (each **must**
have an `ln_address` that resolves inside your regtest), then run the helper.

```bash
export BTCPAY_URL="http://host.docker.internal:14142"
export BTCPAY_API_KEY="<greenfield-api-key>"
export BTCPAY_STORE_ID="<store-id>"
export BTCPAY_WEBHOOK_SECRET="<choose-a-strong-secret>"
export ORCHESTRATOR_PUBLIC_URL="http://host.docker.internal:8000"   # what BTCPay will call
export DEMO_TARGETS_JSON='[
  {"label":"Barista","ln_address":"barista@lnurl.regtest","percentage":60,"order":0},
  {"label":"Owner","ln_address":"owner@lnurl.regtest","percentage":40,"order":1}
]'

docker compose -f docker-compose.regtest.yml exec \
  -e BTCPAY_URL -e BTCPAY_API_KEY -e BTCPAY_STORE_ID -e BTCPAY_WEBHOOK_SECRET \
  -e ORCHESTRATOR_PUBLIC_URL -e DEMO_TARGETS_JSON \
  orchestrator python scripts/seed_btcpay_demo.py
```

The script is idempotent (safe to re-run) and prints the **Tenant ID** and the
**webhook URL + secret** to paste into BTCPay. Copy them.

---

## 3. Register the webhook in BTCPay

In **BTCPay → Store → Settings → Webhooks → Create**:

- **Payload URL**: `http://host.docker.internal:8000/api/v1/webhooks/btcpay/<tenant-id>`
  (use the exact URL the script printed)
- **Secret**: the `BTCPAY_WEBHOOK_SECRET` you set
- **Events**: just **“An invoice has been settled”** (`InvoiceSettled`)

Set the store **invoice speed policy** so Lightning payments settle
immediately (Store → Settings → “Consider the invoice settled when…”).

---

## 4. Run the demo

1. **POS invoice** — In BTCPay, open the **POS** and create a charge.
   ⚠️ Denominate it in **SATS** (a fiat-denominated POS amount is mis-scaled on
   auto-create). Display the QR / Lightning invoice.
2. **Zeus pays** — Scan with **Zeus** and pay over the Polar regtest channel.
3. **BTCPay settles** — The invoice flips to **Settled**; BTCPay fires the
   `InvoiceSettled` webhook.
4. **OpenSplit detects** — The orchestrator receives the webhook, creates the
   `Payment`, applies the active split rule, records the per-target split audit
   trail, and submits a BTCPay payout per `ln_address`.
5. **Team updates** — Open the dashboard (`http://localhost:3000`),
   log in, and watch the **Team** page reflect the new activity.
6. **Split Proof** — Go to **Payments**, open the payment, and expand
   **Split Proof**: percentages, per-target amounts, payout status, and the
   integrity check (sum of splits == payment amount).

---

## 5. Verify the settled event reached OpenSplit

- **BTCPay** → Store → Webhooks → **Recent deliveries** shows `200`.
- **Logs**: `docker logs -f orchestrator`.
- **API** (auth as the demo admin):
  ```bash
  TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
    -d '{"email":"admin@bitcrew.example","password":"<seed-pw>"}' | jq -r .access_token)
  curl -s localhost:8000/api/v1/payments -H "authorization: Bearer $TOKEN" | jq '.items[0]'
  curl -s localhost:8000/api/v1/payments/<payment-id>/proof -H "authorization: Bearer $TOKEN" | jq '.integrity'
  ```
  Expect `"balanced": true`.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Webhook delivery `401` | Secret mismatch | Make BTCPay webhook secret == `BTCPAY_WEBHOOK_SECRET` |
| Webhook delivery `404` | Wrong tenant id in URL | Use the Tenant ID the script printed |
| Payment amount wrong (e.g. 5 sats) | POS invoice in fiat | Denominate the POS in **SATS** |
| All payouts show **failed** | `ln_address` not resolvable in regtest, or no channel liquidity | Use regtest-resolvable LNURL hosts + fund BTCPay’s node. Proof still balances. |
| No webhook fires | Invoice not “settled” | Set the store speed policy so LN settles immediately |
| Orchestrator can’t reach BTCPay | `localhost` inside container | Use `host.docker.internal` / LAN IP in `BTCPAY_URL` |
| Empty dashboard / 500 on login | Migrations or seed not run | `alembic upgrade head` + `python scripts/seed.py` |

> The **detect → split → proof** path succeeds even if live Lightning payout
> delivery fails — the split proof is recorded from the settled invoice
> regardless of payout outcome.
