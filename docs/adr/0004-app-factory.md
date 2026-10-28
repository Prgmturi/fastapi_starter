# 0004. The app is built by a factory, create_app()

Status: accepted. Recorded on 27 October 2026, in place since 0.3.0.

## Context

`main.py` built the app when it was imported, from the settings of the environment. One invalid variable broke every tool that imported the package, pytest included, and a test could not build an app with settings of its own.

## Decision

- `create_app(settings=None)` builds and returns the app; with no argument it reads the settings of the environment. No module holds an app at import time.
- uvicorn calls it: `uvicorn fastapi_starter.main:create_app --factory` in development, and `serve.py` in the image, which runs uvicorn with the `SERVER_*` settings.
- Tests build their own app with their own settings, isolated from the `.env` of the machine (`tests/conftest.py`).

## Consequences

- Importing `fastapi_starter.main` reads no setting and starts nothing (a test checks it, in a new process).
- `uvicorn fastapi_starter.main:app` does not work: `app` does not exist. That was the breaking change of 0.3.0.
