from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.observability import init_sentry
from app.modules import (
    auth,
    budgets,
    catalog,
    clients,
    dashboard,
    events,
    finance,
    organizations,
    pricing,
    production,
    proposals,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    init_sentry()
    app = FastAPI(title=settings.app_name, version="0.1.0", openapi_url="/api/v1/openapi.json")
    install_error_handlers(app)
    app.add_middleware(CSRFMiddleware)
    # El último agregado es el más externo: el request id existe para todo lo demás.
    app.add_middleware(RequestContextMiddleware)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        """El proceso responde."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"], response_model=None)
    def readyz() -> dict[str, str] | JSONResponse:
        """El proceso puede atender: llega a la base de datos."""
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(organizations.router)
    app.include_router(clients.router)
    app.include_router(catalog.router)
    app.include_router(pricing.router)
    app.include_router(events.router)
    app.include_router(budgets.router)
    app.include_router(proposals.router)
    app.include_router(proposals.public_router)
    app.include_router(production.router)
    app.include_router(finance.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
