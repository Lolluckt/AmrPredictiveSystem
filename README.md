# Дипломний проєкт — AMR Predictive Maintenance

**Інформаційна система збору телеметрії та предиктивного обслуговування
автономної наземної колісної платформи в умовах цехової виробничої лінії
з використанням технологій цифрових двійників.**

## Компоненти

```
диплом/
├── webots_project/   цифровий двійник цеху (Webots R2025a) + Python-контролер AMR
├── backend/          FastAPI + SQLAlchemy async + JWT + MQTT-ingest + WebSocket
├── frontend/         React 18 + Vite + TS + Tailwind + Live-WebSocket
├── db.txt            довідкова повна DDL-схема (50+ таблиць)
├── diplom_er_diagrams.html  ER-діаграми
├── Архітектура.docx  пояснювальна записка
├── .env.example      шаблон конфігурації
└── docker-compose.yml   локальний стек: postgres + mosquitto + backend + frontend
```

## Швидкий старт (Docker)

```bash
cp .env.example .env       # відредагуйте JWT_SECRET / POSTGRES_PASSWORD
docker compose up --build
# Backend:  http://localhost:8000/docs
# Healthz:  http://localhost:8000/health/ready
# Frontend: http://localhost:8080
# MQTT:     localhost:1883
# Postgres: localhost:5432
```

Запустіть Webots з `webots_project/worlds/factory_floor.wbt` із
змінною оточення `AMR_MQTT=1` — контролер AMR почне публікувати
телеметрію в брокер Mosquitto. Backend ingest приймає її,
зберігає в `telemetry_snapshots`, виконує оцінку правил аномалій
**та** транслює події через WebSocket до фронтенду.

## Архітектура потоку даних

```
Webots AMR (Python controller)                                   ┌────────────┐
   │ MQTT publish: factory/line_1/amr_XX/telemetry/<section>     │  Frontend  │
   │ MQTT subscribe: factory/line_1/amr_XX/commands              │  (React)   │
   ▼                                                             │            │
Mosquitto broker  ─◄─ MQTT publish_command(...)  ─◄─ POST /api/robots/<id>/command
   │                                                             │            │
   │ MQTT subscribe: factory/+/+/telemetry/#                     │   open WS  │
   ▼                                                             │            │
┌─────────────────── Backend (FastAPI) ────────────────────┐     │            │
│                                                          │     │            │
│  MQTT ingest (paho thread)                               │     │            │
│      ▼                                                   │     │            │
│  asyncio queue → consumer → PostgreSQL                   │     │            │
│      │           │  • telemetry_snapshots                │     │            │
│      │           │  • anomaly_events (rule engine)       │     │            │
│      │           │  • robots.last_x/y/zone/status        │     │            │
│      ▼                                                   │     │            │
│  Event bus (in-process pub/sub)                          │     │            │
│      ▼                                                   │     │            │
│  /api/ws (WebSocket)  ─────── live JSON envelopes ────►  │ ◄── WebSocket   │
│  /api/* (HTTP REST + JWT)                                │ ◄── HTTP        │
│                                                          │     │            │
└──────────────────────────────────────────────────────────┘     └────────────┘
```

Команди до робота йдуть зворотньо:
**UI → POST /api/robots/{id}/command → publish_command() → MQTT → controller**.
Контролер виконує (`stop`, `resume`, `return_to_charge`, `inject_fault`,
`clear_fault`, `mission`) і змінює стан, що знову проявляється в новій
телеметрії і живе піднімається на дашборді.

## Live-канал

Фронтенд відкриває одне постійне WebSocket-з'єднання
(`/api/ws?token=<JWT>`). Backend проксує туди всі помітні події:

| `type`        | `action`                  | Тригер                                                             |
|---------------|---------------------------|--------------------------------------------------------------------|
| `telemetry`   | `update`                  | Кожен flush MQTT-пачки (зазвичай раз на ~1.5 c)                    |
| `robot`       | `status` / `command` / `update` / `create` | Зміна статусу робота, надсилання команди, редагування |
| `anomaly`     | `create` / `ack` / `resolve` | Файл правила, підтвердження, закриття                          |
| `ticket`      | `create` / `update` / `comment` / `delete` | CMMS-редагування                                       |
| `mission`     | `create` / `update` / `cancel` | Логістичні місії                                                |
| `alert_rule`  | `create` / `update` / `delete` | Правила сповіщень                                              |
| `user`        | `create` / `update` / `delete` | Адмін UI                                                       |
| `audit`       | `*`                       | Кожен запис у `audit_log` (для адмінської історії)                 |

Клієнт інвалідовує відповідні React-Query кеші, тож вкладки оновлюються
без F5 і без polling-у.

## Ролі користувачів

| Роль       | Повноваження                                                                           |
|------------|----------------------------------------------------------------------------------------|
| **admin**  | Управління користувачами + усі права нижче                                             |
| **engineer** | Предиктивна аналітика, правила сповіщень, закриття заявок, редагування роботів, інжекція несправностей |
| **operator** | Дашборди, створення/скасування місій, підтвердження сповіщень, базові команди робота |

Демо-акаунти (створюються `python -m app.seed`):

| Роль     | Email                    | Пароль         |
|----------|--------------------------|----------------|
| admin    | admin@progress.ua        | `admin123`     |
| engineer | engineer@progress.ua     | `engineer123`  |
| operator | operator@progress.ua     | `operator123`  |

## Production-чеклист

- ✅ Структуроване логування (JSON-friendly), `X-Request-Id`, доступний у відповідях.
- ✅ Узгоджений формат помилок: `{"error":{"status":..., "detail":...}}`.
- ✅ Health-чеки: `/health` (liveness), `/health/ready` (DB + MQTT readiness).
- ✅ Audit-log: усі state-changing endpoints (auth/login, users/*, robots/*, tickets/*, alerts/*, missions/*).
- ✅ MQTT publisher з thread-safe lazy-init + auto-reconnect.
- ✅ Anomaly engine з 2-хвилинним cooldown'ом, щоб таблиця подій не спливала.
- ✅ Fleet-wide `/api/telemetry/latest` (одним запитом замість N).
- ✅ WebSocket проксі в Nginx + у Vite dev-server.
- ✅ Docker healthcheck + `restart: unless-stopped`.
- ✅ `.env.example` для секретів; попередження якщо JWT_SECRET дефолтний у `production`.
- ✅ Alembic skeleton (`backend/alembic/`).

Команди для міграцій:

```bash
docker compose exec backend alembic revision --autogenerate -m "init"
docker compose exec backend alembic upgrade head
```

## Локальний розвиток без Docker

* **Backend:** див. `backend/README.md`
* **Frontend:** див. `frontend/README.md`
* **Webots:** див. `webots_project/README.md`
