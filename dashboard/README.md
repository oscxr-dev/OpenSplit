# OpenSplit Dashboard

Frontend PWA para el sistema de cobros y repartos Lightning Network de **BitCrew**.

## Stack

- **Framework:** React 18 + TypeScript
- **Build:** Vite 5
- **Routing:** React Router v6
- **State/Server:** TanStack React Query v5
- **Forms:** React Hook Form + Zod
- **Styling:** Tailwind CSS 3 + PostCSS
- **HTTP:** Axios (con interceptors JWT + refresh)
- **PWA:** vite-plugin-pwa + Workbox
- **UI Icons:** Lucide React
- **QR:** qrcode.react
- **Notificaciones:** Sonner
- **Fechas:** date-fns

## Requisitos

- Node.js 18+
- npm 9+

## Instalación

```bash
cd dashboard
npm install
```

## Variables de Entorno

Copia `.env.example` a `.env` y configura:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_NAME=OpenSplit
VITE_DEFAULT_CURRENCY=sats
```

## Desarrollo

```bash
npm run dev
```

Abre [http://localhost:3000](http://localhost:3000).

El servidor de desarrollo soporta HMR y proxy inverso.

## Build

```bash
npm run build
```

Genera los archivos estáticos en `dist/`. Incluye service worker y manifest PWA.

## Scripts Disponibles

| Script | Descripción |
|--------|-------------|
| `npm run dev` | Inicia servidor de desarrollo en puerto 3000 |
| `npm run build` | Compila TypeScript + empaqueta con Vite |
| `npm run preview` | Previsualiza build de producción localmente |
| `npm run lint` | TypeScript type-check (sin emit) |
| `npm test` | Ejecuta tests con Vitest |
| `npm run test:watch` | Tests en modo watch |

## Arquitectura

```
src/
├── components/
│   ├── layout/       # AppShell, TopBar, ProtectedRoute
│   ├── ui/           # Button, Input, Card, Dialog, Table, etc.
│   ├── pos/          # AmountKeypad, InvoiceQR, PaymentStatus
│   ├── splits/       # SplitRuleForm, SplitBar, TargetRow
│   └── shared/       # EmptyState, ErrorState, LoadingSpinner
├── hooks/            # useAuth, useSplits, useInvoices, useTenant, usePaymentPolling
├── lib/              # api (axios), auth, utils, queryClient
├── pages/            # LoginPage, PosPage, SplitsPage, WalletsPage, PaymentsPage
├── schemas/          # Zod schemas (auth, split)
├── styles/           # Tailwind globals
├── types/            # TypeScript type definitions
├── App.tsx           # Entry component
├── main.tsx          # Bootstrap
└── routes.tsx        # Route definitions
```

## API Endpoints

El dashboard consume la API REST en `http://localhost:8000/api/v1`:

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | /auth/login | Inicio de sesión |
| POST | /auth/refresh | Refrescar token JWT |
| GET | /tenants/me | Info del tenant + estado LNBits |
| GET | /splits | Listar reglas de reparto |
| POST | /splits | Crear regla de reparto |
| PATCH | /splits/{id} | Actualizar regla |
| POST | /invoices | Crear cobro (genera factura LN) |
| GET | /invoices/{id} | Detalle de cobro con splits |
| GET | /invoices | Listar cobros (filtro por status) |

## Docker

```bash
# Build imagen
docker build -t opensplit-dashboard .

# Ejecutar
docker run -p 8080:80 opensplit-dashboard
```

## Diseño

- **Idioma:** 100% español
- **Paleta:** Bitcoin naranja (#F7931A) como acento
- **Tipografía:** Inter (Google Fonts)
- **Mobile-first:** bottom nav en móvil, sidebar en desktop
- **UX:** skeletons, empty states, toasts, polling de pagos
