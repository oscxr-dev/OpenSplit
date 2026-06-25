# Security Cleanup — pre-OpenSplit / pre-publish checklist

> **Required before making this repository public or shipping OpenSplit.**
> This document lists *locations and issue types only*. **No real secret values,
> domains, IPs, store IDs, keys, emails, or node references are reproduced here.**
> This pass does not modify code or delete files — it documents what to fix.

---

## Severity legend
- 🔴 **Critical** — real/sensitive value present and/or tracked in git. Rotate + remove.
- 🟠 **High** — risky default or untracked-but-not-ignored file (easy to leak).
- 🟡 **Medium** — weak default credential intended for dev; must not reach production.

---

## 1. Hardcoded / default credentials found

| Sev | Location | Issue type | Action |
|---|---|---|---|
| 🟡 | `orchestrator/app/config.py` | Default `jwt_secret` placeholder committed | Require env override; never run prod with default; rotate. |
| 🟡 | `orchestrator/app/config.py` | Default `lnbits_webhook_secret` placeholder | Require env override; rotate. |
| 🟡 | `orchestrator/app/config.py` | Default `seed_admin_password` (demo) | Force change on first run; never seed in prod. |
| 🟡 | `docker-compose.yml` | Inline dev credentials (DB / service users) | Move to env/secrets; do not reuse in prod. |
| 🟡 | `orchestrator/scripts/seed.py` | Demo admin/email seed values | Parameterize via env; exclude from prod seed. |
| 🟡 | Node configs `bitcoind/*.conf`, `lnd/*.conf` | RPC user/pass for local dev | Dev-only; ensure prod configs are not committed. |

> These are dev defaults, not production secrets — but they are **publish-blockers**:
> rotate and require env injection before the repo goes public.

---

## 2. Sensitive config references found

| Sev | Location | Issue type | Action |
|---|---|---|---|
| 🔴 | `dashboard/.env.production` | **Tracked in git**; contains a real deployment **domain** in `VITE_API_BASE_URL` | Stop tracking (`git rm --cached`), move value to deploy-time env, redact from history. |
| 🔴 | `docker-compose.cherito.yml` | Untracked; contains real **domain** + host/loopback references and service secrets (DB/orchestrator) | Keep out of git; ensure gitignored; rotate any secrets it contains. |
| 🟠 | `dashboard/.env.local` | Untracked **but not gitignored** (only `.env` is) — at risk of accidental commit | Add to `.gitignore`; confirm it is not staged. |
| 🟠 | Per-tenant BTCPay secrets (`btcpay_api_key`, `btcpay_store_id`, `btcpay_webhook_secret`) | Stored in DB (`orchestrator/app/models/__init__.py`) | Correct location; ensure DB dumps/backups are not committed (see `backups/`). |

> Real values intentionally omitted from this document per task rules.

---

## 3. Files that should NOT be public

| Path | Reason |
|---|---|
| `dashboard/.env.production` | Real domain; currently tracked — remove from VCS. |
| `dashboard/.env.local` | Local secrets/config — must be gitignored. |
| `docker-compose.cherito.yml` | Real deploy infra references + secrets. |
| `backups/` | May contain DB dumps / wallet/seed material — verify and exclude. |
| Any `lnd*/data/`, `*.macaroon`, `tls.cert`, `bootstrap-wallets.json` | Node keys/credentials (mostly already ignored — verify none are staged). |
| `*.env`, `*.env.*` except `*.env.example` | Environment secrets. |

---

## 4. Recommended `.gitignore` improvements

Current `.gitignore` ignores `.env`, `.env.backup`, node data dirs, `dist/`, etc.,
but **misses several env/deploy patterns**. Add:

```gitignore
# Environment files (keep only *.env.example)
.env
.env.*
!.env.example
!**/.env.example

# Frontend env variants
dashboard/.env.local
dashboard/.env.production
dashboard/.env.*.local

# Deploy/compose variants with real infra
docker-compose.cherito.yml
docker-compose.*.local.yml

# Backups / dumps / wallet material
backups/
*.sql.gz
*.dump
bootstrap-wallets.json

# Node credentials (defense in depth)
**/*.macaroon
**/tls.cert
**/admin.macaroon
```

> After updating `.gitignore`, untrack already-committed offenders:
> `git rm --cached dashboard/.env.production` (and any others), then commit.

---

## 5. Secrets to ROTATE before publishing

Rotate every value of these *types* (no current values listed here):

1. **JWT signing secret** (`ORCHESTRATOR_JWT_SECRET`).
2. **Webhook secrets** — LNbits + per-tenant BTCPay webhook secrets.
3. **BTCPay API keys** for any tenant whose key may have touched the repo/history.
4. **Database passwords** used in any committed compose/config.
5. **Seed/admin demo password**.
6. **Node RPC credentials** if the same configs were ever used outside local regtest.

Also:
- **Scrub git history** for the tracked `dashboard/.env.production` (and any secret that
  was ever committed) using `git filter-repo` / BFG before going public — removing the
  file in a new commit is **not** enough.
- Treat any **real domain / IP / store ID / email / Tailscale reference** as sensitive:
  remove from tracked files and from history.

---

## 6. Pre-publish gate (do not open-source until all checked)

- [ ] `dashboard/.env.production` untracked + value moved to deploy env.
- [ ] `.gitignore` updated; `git status` shows no env/deploy/backup files.
- [ ] All secret *types* in §5 rotated.
- [ ] Git history scrubbed of previously committed secrets/domains.
- [ ] `orchestrator/app/main.py` CORS restricted (no `["*"]`) for prod.
- [ ] Backups/dumps verified clean and excluded.
- [ ] Default credentials in `config.py` require env override (no usable defaults).
