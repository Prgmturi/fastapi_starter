FROM python:3.13-slim AS builder

WORKDIR /app

# UV_LINK_MODE=copy — necessario in Docker perché i hardlink non funzionano
# tra layer diversi del filesystem overlay di Docker.
# UV_COMPILE_BYTECODE=1 — compila .py → .pyc durante la build.
# Il container parte con il bytecode già pronto → cold start più veloce.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Pinniamo la versione di uv — mai usare :latest in produzione.
# La versione cambia silenziosamente e può rompere la build.
COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

# --frozen: usa esattamente uv.lock, non aggiorna niente.
#   Garantisce build riproducibili — stessa build oggi e fra 6 mesi.
# --no-install-project: installa solo le dipendenze, non il tuo pacchetto.
#   Perché? Il codice sorgente non è ancora stato copiato.
#   Se lo facessimo dopo il COPY src, ogni modifica al codice
#   invaliderebbe questo layer cache e rinstallare tutto.
RUN uv sync --frozen --no-install-project

# Solo ora copiamo il codice sorgente.
# Questo layer cambia ad ogni modifica del codice — è giusto che sia qui,
# dopo le dipendenze.
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# Ora installiamo anche il progetto stesso (fastapi_starter come package).
# uv legge [build-system] e [tool.hatch.build.targets.wheel] dal pyproject.toml
# e installa src/fastapi_starter come package editabile nel .venv.
RUN uv sync --frozen


# =============================================================================
# Stage 2: Runtime
# =============================================================================
# Partiamo da un'immagine base fresca — niente del builder ci segue
# a meno che non lo copiamo esplicitamente con COPY --from=builder.
# Risultato: niente uv, niente cache, niente pyproject.toml nell'immagine finale.
FROM python:3.13-slim AS runtime

WORKDIR /app

# PYTHONUNBUFFERED=1 — Python non bufferizza stdout/stderr.
#   Critico in container: se l'app crasha con output bufferizzato,
#   i log spariscono. Con =1 ogni log è scritto immediatamente.
# PYTHONDONTWRITEBYTECODE=1 — non scrivere .pyc a runtime.
#   Li abbiamo già compilati nel builder con UV_COMPILE_BYTECODE.
#   Evita scritture inutili su disco nel container.
# PATH — aggiunge il .venv al PATH così 'uvicorn', 'alembic' etc.
#   sono trovati senza dover scrivere il path completo.
# PYTHONPATH — necessario per il layout src/: Python deve sapere
#   dove trovare fastapi_starter. Senza questo, 'import fastapi_starter' fallisce.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Creiamo l'utente non-root PRIMA di copiare i file.
# --no-create-home: non serve /home/appuser per un'app web.
# La seconda riga assegna la proprietà di /app all'utente
# (WORKDIR crea /app come root).
RUN useradd --no-create-home --shell /bin/bash appuser \
    && chown appuser:appuser /app

# Copiamo solo quello che serve a runtime dal builder:
# - .venv: Python + tutte le dipendenze installate
# - src: il codice dell'applicazione
# - alembic + alembic.ini: necessari per le migrazioni
# Non copiamo: uv, pyproject.toml, uv.lock, cache — non servono.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini

# Passiamo all'utente non-root.
# Tutto quello che succede da qui in poi (incluso il processo uvicorn)
# gira senza privilegi di root — se c'è una vulnerabilità nell'app,
# l'attaccante non ha accesso root al container.
USER appuser

EXPOSE 8000

# HEALTHCHECK — Docker controlla periodicamente che l'app risponda.
# Se fallisce N volte consecutive, il container è marcato "unhealthy"
# e docker-compose / Traefik lo toglie dalla rotazione.
# Usiamo Python stdlib (urllib) perché curl/wget non sono in slim.
# --start-period=10s: aspetta 10s prima di iniziare i check
#   (il lifespan startup — db connect, JWKS fetch — richiede tempo).
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

# ENTRYPOINT fissa il comando base — non sostituibile a runtime.
# CMD fornisce gli argomenti di default — sovrascrivibili.
# Pattern: docker run myimage --workers 4
#   → uvicorn fastapi_starter.main:app --workers 4
# In produzione: workers va gestito da fuori (env var o compose),
# non hardcoded qui — ogni progetto derivato dallo starter può avere esigenze diverse.
ENTRYPOINT ["uvicorn", "fastapi_starter.main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]