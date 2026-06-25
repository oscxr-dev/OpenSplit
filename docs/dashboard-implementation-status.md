# Dashboard del comercio: estado de implementación

Fecha: 2026-06-07

## Decisión de arquitectura

Se mantiene el dashboard React/Vite existente en vez de migrarlo a Next.js durante F1.
Ya incluye React Query, rutas protegidas, componentes UI, PWA y despliegue con Nginx.
La migración de framework no aporta valor al problema principal: mostrar estados reales de payout.

## Implementado en esta primera entrega

- Migración Alembic `005_dashboard_foundation`.
- Ciclo de estados `pending`, `in_progress`, `completed`, `failed`, `cancelled`.
- Persistencia de `btcpay_payout_id`, motivo de fallo, reintentos y timestamps de revisión.
- Captura del payout id al crear envíos BTCPay.
- Worker de reconciliación cada 20 segundos dentro del proceso FastAPI.
- Endpoints tenant-scoped:
  - `GET /api/v1/dashboard/summary`
  - `GET /api/v1/payments`
  - `GET /api/v1/payments/{id}`
  - `POST /api/v1/payments/{id}/splits/{split_id}/retry`
- Edición de reglas por versión; no se borran ni mutan targets históricos.
- Resumen móvil con ventas, fallidos y cobros recientes.
- Pagos con filtros, detalle por destino, motivo de fallo y reintento.
- Estado de conexión compatible con tenants LNbits y BTCPay.

## Decisiones de seguridad y exactitud

- `in_progress` significa que BTCPay aceptó la orden, no que el pago terminó.
- Solo `Completed` de BTCPay se presenta como `completed`.
- Todos los endpoints nuevos obtienen el tenant del usuario autenticado.
- La liquidez se presenta como no disponible hasta conectar una fuente real de LND.

## Pendiente

1. Ejecutar la migración y validar reconciliación contra BTCPay 2.3.9 en staging.
2. Completar auth con cookie `httpOnly`, refresh rotation y rate limiting.
3. Implementar adaptador de liquidez LND y semáforo configurable.
4. Adaptar el formulario de reparto a Lightning addresses para tenants BTCPay.
5. Agregar notificaciones email/Telegram y campana de eventos.
6. Construir reportes, exportación PDF/CSV y ajustes de branding.
7. Restringir CORS por entorno y agregar pruebas de integración con PostgreSQL.
