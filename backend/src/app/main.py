from fastapi import FastAPI

from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.errors import install_error_handlers
from app.modules import auth


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", openapi_url="/api/v1/openapi.json")
    install_error_handlers(app)
    app.add_middleware(CSRFMiddleware)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    return app


app = create_app()
