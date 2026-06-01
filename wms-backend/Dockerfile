# ─── WMS Panama — Dockerfile ──────────────────────────────────────────────────
# Multi-stage build: development | production
# Base: Python 3.12 slim
# ──────────────────────────────────────────────────────────────────────────────

ARG PYTHON_VERSION=3.12
ARG ENVIRONMENT=production

# ── Stage 1: Base ─────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias del sistema (libpq para psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        build-essential \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Development ───────────────────────────────────────────────────────
FROM base AS development

# Instalamos TODAS las dependencias (incluyendo dev)
COPY requirements.txt .
COPY requirements-dev.txt* ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# El código se monta como volumen en dev
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage 3: Builder (para produccion) ────────────────────────────────────────
FROM base AS builder

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt

# ── Stage 4: Production ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

WORKDIR /app

# Solo librerías runtime (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copiamos dependencias compiladas del builder
COPY --from=builder /install /usr/local

# Copiamos el código
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Usuario no-root para seguridad
RUN groupadd -r wms && useradd -r -g wms wmsuser
USER wmsuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--log-level", "info"]
