# Contributing to OpenSplit

Thanks for your interest. OpenSplit moves real money via BTCPay payouts, so we
optimize for correctness and small, reviewable changes over speed.

## Dev setup

```bash
cp .env.example .env      # fill the secrets marked <CHANGE_ME>
docker compose up -d
```

For the full stack with receiver LND nodes (the demo/regtest payout path):

```bash
cp docker-compose.receivers.example.yml docker-compose.receivers.yml
docker compose -f docker-compose.yml -f docker-compose.receivers.yml up -d
```

For a complete end-to-end environment (Polar + BTCPay + Zeus, settle a real
regtest invoice and watch it split), follow
[`docs/REGTEST_E2E.md`](docs/REGTEST_E2E.md).

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs

## Before opening a PR: the verification ritual

Run all four; all four must pass.

```bash
docker compose exec orchestrator pytest
npm --prefix dashboard test
npm --prefix dashboard run build
docker compose up -d --build
```

> **Gotcha:** a freshly built orchestrator container doesn't ship the test
> dependencies. If pytest fails to import, install them first:
>
> ```bash
> docker compose exec orchestrator pip install pytest pytest-asyncio httpx hypothesis
> ```

## PR guidelines

- **Small, scoped changes.** One concern per PR.
- **Money paths need discussion first.** Never touch payment, webhook, payout,
  reconciliation, or split-math code without opening an issue and discussing
  the change before writing it.
- **Tests required.** New behavior gets tests; bug fixes get a regression
  test. Split-math logic is property-tested (Hypothesis) — keep it that way.
- **UI changes: verify both themes.** Check light and dark mode before
  submitting.

## Code style

- Match the existing patterns in the file you're editing — naming, comment
  density, error handling.
- Extract testable logic into pure helper functions rather than embedding it
  in route handlers or components.
- Backend: FastAPI + async SQLAlchemy + Alembic migrations. Frontend:
  React + TypeScript + Vite.
