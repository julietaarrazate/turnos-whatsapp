"""Errores de la API como ``application/problem+json`` (RFC 9457) con un ``code`` estable."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra


def not_found(code: str = "not_found", detail: str = "No encontrado") -> AppError:
    """Un recurso de otra organización también es 404: no se revela que existe."""
    return AppError(404, code, detail)


def problem(status: int, code: str, detail: str, **extra: Any) -> JSONResponse:
    body = {"type": "about:blank", "status": status, "code": code, "detail": detail, **extra}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return problem(exc.status, exc.code, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem(422, "validation_error", "Datos inválidos", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return problem(exc.status_code, code, str(exc.detail))


def ensure[T](value: T | None, what: str) -> T:
    """Invariante interna (no un error del usuario): falla fuerte si no se cumple."""
    if value is None:
        raise RuntimeError(f"Invariante violada: falta {what}")
    return value
