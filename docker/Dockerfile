# =============================================================================
# FastAPI Production Dockerfile
# =============================================================================
# Multi-stage build per immagine leggera e sicura.
#
# Build:
#   docker build -t fastapi-starter -f docker/Dockerfile .
#
# Run:
#   docker run -p 8000:8000 --env-file .env fastapi-starter
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Installa uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copia dependency files
COPY pyproject.toml uv.lock ./

# Installa dipendenze (senza il progetto)
RUN uv sync --frozen --no-install-project

# Copia il codice sorgente
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# Installa il progetto
RUN uv sync --frozen


# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Crea utente non-root
RUN useradd --create-home --shell /bin/bash appuser

# Copia virtual environment dal builder
COPY --from=builder /app/.venv /app/.venv

# Copia codice e configurazioni
COPY --from=builder /app/src ./src
COPY --from=builder /app/alembic ./alembic
COPY --from=builder /app/alembic.ini ./

# Imposta PATH per usare il venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Cambia a utente non-root
USER appuser

# Esponi porta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

# Comando di avvio
CMD ["uvicorn", "fastapi_starter.main:app", "--host", "0.0.0.0", "--port", "8000"]