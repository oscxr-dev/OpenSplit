# OpenSplit

OpenSplit is a self-hosted Bitcoin revenue-sharing app for teams, businesses, and communities that receive Bitcoin payments and need to split them clearly, automatically, and verifiably.

OpenSplit v0.1 is BTCPay-first.

## What it does

OpenSplit helps a team define percentage-based split rules for incoming Bitcoin payments.

Core flow:

```text
BTCPay payment → OpenSplit rule → split calculation → Split Proof
cat > README.md <<'EOF'

# OpenSplit

OpenSplit is a self-hosted Bitcoin revenue-sharing app for teams, businesses, and communities.

It helps split incoming Bitcoin payments clearly, automatically, and verifiably.

OpenSplit v0.1 is BTCPay-first.

## Core flow

```text
BTCPay payment → Split rule → Split calculation → Split Proof
```

## Features

* BTCPay Server-first integration
* Percentage-based split rules
* Split Proof for each payment
* Protection against double payouts
* Accurate payment status tracking
* Honest handling of zero-sat splits
* Docker local development

## Local development

```bash
docker compose up -d
```

## URLs

| Service          | URL                        |
| ---------------- | -------------------------- |
| Dashboard        | http://localhost:3000      |
| API docs         | http://localhost:8000/docs |
| LNbits auxiliary | http://localhost:5001      |

## Notes

LNbits is not the main flow in v0.1. It may be supported later as a community adapter.

## License

MIT
