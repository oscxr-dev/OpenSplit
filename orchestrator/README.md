# OpenSplit Orchestrator

Multi-tenant FastAPI layer over LNBits — Lightning payments with automatic splits.
The client never sees LNBits; only this API.

## Architecture

```
POST /invoices → orchestrator → LNBits (create invoice)
                                LNBits splitpayments (auto-distribute)
                                PostgreSQL (audit trail)
                                → PaymentSplits recorded per target
```

## Quick Start

```bash
docker compose up -d orchestrator
docker exec orchestrator python3 -m alembic upgrade head
docker exec orchestrator sh -c "PYTHONPATH=/app python3 /app/scripts/seed.py"
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | DB + LNBits health |
| `GET` | `/docs` | OpenAPI docs |
| `POST` | `/api/v1/auth/register` | Create tenant + admin |
| `POST` | `/api/v1/auth/login` | Get JWT token |
| `POST` | `/api/v1/auth/refresh` | Refresh JWT |
| `GET` | `/api/v1/tenants/me` | Tenant info + LNBits status |
| `PATCH` | `/api/v1/tenants/me` | Update tenant config |
| `GET` | `/api/v1/splits` | List split rules |
| `POST` | `/api/v1/splits` | Create rule (validates 100%) |
| `PATCH` | `/api/v1/splits/{id}` | Update rule |
| `POST` | `/api/v1/splits/{id}/activate` | Activate rule |
| `POST` | `/api/v1/invoices` | Create Lightning invoice |
| `GET` | `/api/v1/invoices/{id}` | Get invoice + splits |
| `GET` | `/api/v1/invoices` | List invoices (paginated) |
| `POST` | `/api/v1/webhooks/lnbits/paid` | LNBits payment webhook |

## Aritmética de Splits

El algoritmo de distribución de splits garantiza **suma exacta para cualquier monto**.

### Garantía
`sum(splits) == amount_sats` para cualquier combinación válida de porcentajes (que sumen 100%) y cualquier monto positivo.

Verificado con 2000 casos aleatorios vía property-based testing (hypothesis).

### Algoritmo
Se usa el **método del residuo (largest remainder)**:

1. Calcular el valor exacto de cada split: `amount × percentage / 100`
2. Tomar la parte entera (floor) de cada uno
3. Calcular el residuo: `amount - sum(floors)`
4. Distribuir el residuo (1 sat a la vez) a los targets con **mayor fracción perdida**, con tiebreak por `order` (menor orden gana)

### Por qué importa
En mainnet con volumen real, cada sat cuenta. Sin este algoritmo, los montos no divisibles por 100 generan sats huérfanos acumulados en la wallet fuente — plata sin asignar y un riesgo legal.

### Ejemplo
Pago de 12,345 sats con regla 30/35/15/10/10:

| Destino | % | Exacto | Floor | Fracción | Extra | Final |
|---------|---|--------|-------|----------|-------|-------|
| Dueño | 30% | 3703.50 | 3703 | 0.50 | +1 | 3704 |
| Barista | 35% | 4320.75 | 4320 | 0.75 | +1 | 4321 |
| Proveedor | 15% | 1851.75 | 1851 | 0.75 | +1 | 1852 |
| Impuestos | 10% | 1234.50 | 1234 | 0.50 | 0 | 1234 |
| Reserva | 10% | 1234.50 | 1234 | 0.50 | 0 | 1234 |
| **Total** | **100%** | — | **12342** | — | **3** | **12345** ✅ |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_DB_URL` | `postgresql+asyncpg://...` | Database URL |
| `ORCHESTRATOR_JWT_SECRET` | `change-me` | JWT signing secret |
| `ORCHESTRATOR_JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ORCHESTRATOR_LNBITS_INTERNAL_URL` | `http://lnbits:5000` | LNBits container URL |
| `ORCHESTRATOR_LNBITS_WEBHOOK_SECRET` | `change-me` | Webhook HMAC secret |
| `ORCHESTRATOR_SEED_ADMIN_PASSWORD` | `admin123` | Demo admin password |

## Examples

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bitcrew.example","password":"admin123"}' \
  | jq -r .access_token)

# Create invoice
curl -s -X POST http://localhost:8000/api/v1/invoices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount_sats": 5000, "memo": "Latte + croissant"}'

# Check status
curl -s http://localhost:8000/api/v1/invoices \
  -H "Authorization: Bearer $TOKEN"
```

## Tests

```bash
# Start server first, then:
cd orchestrator
PYTHONPATH=. ORCHESTRATOR_DB_URL="postgresql+asyncpg://lnbits:lnbits@localhost:5432/orchestrator" \
  python3 -m pytest tests/ -v --cov=app/services --cov=app/routers
```

## Database Migrations

```bash
# Create new migration
docker exec orchestrator python3 -m alembic revision --autogenerate -m "description"

# Apply
docker exec orchestrator python3 -m alembic upgrade head
```
