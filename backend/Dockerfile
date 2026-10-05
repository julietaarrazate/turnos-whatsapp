# Imagen de la API. En la Fase 3 se suman las librerías de sistema de WeasyPrint (PDF).
# PYTHON_IMAGE permite usar un mirror (p. ej. public.ecr.aws/docker/library/python:3.12-slim).
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv==0.8.17

WORKDIR /app

# Dependencias primero (capa cacheable), después el código.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000

EXPOSE 8000

# --proxy-headers: la IP real del cliente llega en X-Forwarded-For (Vercel → Render).
# --no-access-log: el log de acceso lo escribe la app (estructurado y sin tokens en la URL).
# RUN_MIGRATIONS=true: migra antes de arrancar (planes sin pre-deploy command, p. ej. Render
# free). Si la migración falla, el contenedor no arranca y queda la versión anterior.
CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS\" = true ]; then alembic upgrade head || exit 1; fi; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header --no-access-log"]
