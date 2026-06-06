"""FastAPI application entrypoint.

Start with:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import Base, engine
from .middleware import RequestContextMiddleware
from .routers import (
    alerts, analytics, auth, factory, missions, predictive, robots,
    telemetry, tickets, users, ws,
)
from .services.mqtt_ingest import MqttIngestor, consume_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()


    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


    try:
        from .db import session_scope
        from .services.dock_allocator import reset_all as reset_docks
        async with session_scope() as db:
            await reset_docks(db)
    except Exception:
        log.exception("dock reservation reset failed")

    queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
    ingestor = MqttIngestor(queue)
    await ingestor.start()
    consumer_task = asyncio.create_task(consume_queue(queue), name="mqtt_consumer")
    log.info("App started (env=%s)", settings.app_env)
    _app.state.started_at = time.time()
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.CancelledError, Exception):
            pass
        await ingestor.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )


    @app.exception_handler(HTTPException)
    async def _http_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"status": exc.status_code,
                               "detail": exc.detail,
                               "request_id": getattr(request.state, "request_id", None)}},
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"status": 422,
                               "detail": "Validation error",
                               "errors": exc.errors(),
                               "request_id": getattr(request.state, "request_id", None)}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"status": 500,
                               "detail": "Внутрішня помилка сервера",
                               "request_id": getattr(request.state, "request_id", None)}},
        )


    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(robots.router)
    app.include_router(telemetry.router)
    app.include_router(alerts.router)
    app.include_router(tickets.router)
    app.include_router(missions.router)
    app.include_router(predictive.router)
    app.include_router(factory.router)
    app.include_router(analytics.router)
    app.include_router(ws.router)


    @app.get("/", tags=["meta"])
    async def root():
        return {"service": settings.app_name, "env": settings.app_env, "status": "ok"}

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["meta"])
    async def ready():
        """Liveness + DB connectivity check used by docker healthchecks."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ready", "db": "ok"}
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "db": "fail", "error": str(exc)},
            )

    @app.get("/api/meta", tags=["meta"])
    async def meta():
        return {
            "name":     settings.app_name,
            "env":      settings.app_env,
            "version":  app.version,
            "uptime_s": round(time.time() - getattr(app.state, "started_at", time.time()), 1),
            "mqtt_enabled": settings.mqtt_enabled,
            "mqtt_broker":  settings.mqtt_broker,
        }

    return app


app = create_app()
