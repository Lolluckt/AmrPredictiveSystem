# Frontend — AMR Predictive Maintenance Dashboard

Stack: **Vite · React 18 · TypeScript · TailwindCSS · TanStack Query · Zustand · Recharts · React Router · Axios**.

## Local development

```bash
npm install
npm run dev
```

By default Vite proxies `/api` → `http://localhost:8000`, so start the backend
first.

## Project layout

```
src/
├── api/            axios client + typed endpoint wrappers
├── components/     shared UI (Layout sidebar, PageHeader, StatusBadge, guards)
├── lib/            cn helper (tailwind-merge)
├── pages/          route modules
├── store/          Zustand auth store (persisted)
├── types.ts        API types mirrored from backend schemas
├── App.tsx         router (role-aware)
└── main.tsx        React entrypoint
```

## Role-based UI

| Role      | Sees pages                                                        |
|-----------|-------------------------------------------------------------------|
| admin     | all pages, including `/admin/users`                               |
| engineer  | dashboard, robots (incl. fault injection), predictive, alerts, tickets, missions |
| operator  | dashboard, robots (view + basic commands), alerts (ack), tickets, missions |

The guards live in `src/components/RequireRole.tsx` and are mirrored by the
backend's `require_permission` dependency.
