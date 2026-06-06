# Backend — AMR Predictive Maintenance API

Stack: **Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg · JWT · paho-mqtt**.

## Local development

```bash
python -m venv .venv && . .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env
# Make sure Postgres is running at the URL from .env
python -m app.seed              # creates tables + demo users/robots/rules
uvicorn app.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs).

### Demo accounts (created by `app.seed`)

| Role      | Email                 | Password      |
|-----------|-----------------------|---------------|
| admin     | admin@progress.ua     | `admin123`    |
| engineer  | engineer@progress.ua  | `engineer123` |
| operator  | operator@progress.ua  | `operator123` |

## Project layout

```
app/
├── main.py            FastAPI app factory + lifespan
├── config.py          pydantic-settings
├── db.py              async engine, session scope
├── seed.py            bootstrap demo data (idempotent)
├── core/
│   ├── roles.py       3 roles + permissions matrix
│   ├── security.py    bcrypt + JWT
│   └── deps.py        `current_user`, role / permission guards
├── models/            SQLAlchemy ORM
├── schemas/           pydantic request / response
├── routers/           HTTP endpoints (auth, users, robots, telemetry,
│                      alerts, tickets, missions, predictive)
└── services/
    ├── mqtt_ingest.py   paho-mqtt loop → TelemetrySnapshot + anomaly eval
    ├── mqtt_publisher.py outbound commands (stop/resume/inject_fault)
    ├── anomaly.py       rule-based alerting
    └── predictive.py    component health + RUL analytics
```

## Roles

Three roles map cleanly onto factory-floor responsibilities:

* **admin** — user & system management, full override.
* **engineer** — predictive-maintenance owner; tickets, alert rules,
  component replacement, firmware.
* **operator** — shift dispatcher; dashboards, missions, immediate commands.

Permission checks flow through `core.deps.require_permission(<perm>)` so new
capabilities are added declaratively in `core/roles.py`.
