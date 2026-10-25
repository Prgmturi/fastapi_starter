# =============================================================================
# Stage 1: build the virtual environment
# =============================================================================
# The base image by tag and by digest. The tag says what it is; the digest
# makes every build of a commit start from the same image, because the tag
# moves whenever Debian or Python ship a fix. Both stages use the same one
# (tests/test_dockerfile.py).
FROM python:3.13-slim@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS builder

WORKDIR /app

# UV_LINK_MODE=copy: hard links do not work across the layers of Docker's
#   overlay filesystem.
# UV_COMPILE_BYTECODE=1: every module, the app's too, is compiled here, so
#   the container starts with its bytecode ready.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# The same uv as UV_VERSION in .github/workflows/ci.yml (tests/test_lockfile.py):
# the lock CI checks is the lock the image installs.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# README.md too: pyproject.toml names it as the readme, and building the
# package fails without it (OSError: Readme file does not exist).
COPY pyproject.toml uv.lock README.md ./

# --locked: installs exactly what uv.lock says, and stops if the lock is out
#   of date with pyproject.toml. The same build today and in six months.
# --no-install-project: only the dependencies, not the project, whose code
#   is not copied yet. A change to the code then leaves this layer cached.
# --no-dev: without the dev group (pytest, mypy, ruff, pre-commit), which
#   the app does not need to run.
RUN uv sync --locked --no-install-project --no-dev

# Then the project. --no-editable installs it into the virtual environment
# like any other package, so the runtime stage needs no src/ and no
# PYTHONPATH: an editable install would point back at this copy of src/.
COPY src ./src
RUN uv sync --locked --no-dev --no-editable


# =============================================================================
# Stage 2: runtime
# =============================================================================
# A fresh base: only what is copied from the builder comes along, so no uv,
# no build cache, no source tree.
FROM python:3.13-slim@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS runtime

WORKDIR /app

# PYTHONUNBUFFERED=1: every line reaches docker logs at once, even when the
#   process dies.
# PYTHONDONTWRITEBYTECODE=1: no .pyc written at run time; the builder
#   compiled them, and the app cannot write here anyway.
# PATH: python and alembic of the virtual environment.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# The user the app runs as owns nothing in the image. The virtual
# environment (with the app) and the migrations belong to root: a process
# taken over cannot change them, and a container that restarts runs the
# code of the image, not a changed copy.
RUN useradd --no-create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /app/.venv /app/.venv
COPY alembic ./alembic
COPY alembic.ini ./

USER appuser

EXPOSE 8000

# Docker's probe: python -m fastapi_starter.healthcheck (urllib, since the
# slim image has no curl or wget). It sends the first SERVER_TRUSTED_HOSTS
# entry as Host, which TrustedHostMiddleware accepts, to SERVER_PORT, the
# port fastapi_starter.serve listens on. The start period covers the startup:
# connecting to the database and fetching Keycloak's signing keys.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "-m", "fastapi_starter.healthcheck"]

# uvicorn with the SERVER_* settings: host, port, keep-alive, the proxies
# trusted with X-Forwarded-For, and the seconds open requests get when
# docker stop arrives (SERVER_TIMEOUT_GRACEFUL_SHUTDOWN, below the 10 that
# docker stop waits before it kills the process). Another command replaces
# this one whole, as the migrations do:
#   docker run <image> alembic upgrade head
CMD ["python", "-m", "fastapi_starter.serve"]
