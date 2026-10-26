"""The Docker image's command: uvicorn with the SERVER_* settings.

Run as ``python -m fastapi_starter.serve``. Host, port and the other server
options come from ServerSettings, read the way the app reads them
(environment, then .env), so uvicorn listens on the port the healthcheck
probes. In development, ``uvicorn ... --reload`` (README) is still the way
to start the app.
"""

from typing import Any

import uvicorn

from fastapi_starter.core.config.server import ServerSettings

APP_FACTORY = "fastapi_starter.main:create_app"


def uvicorn_options(settings: ServerSettings) -> dict[str, Any]:
    """The keyword arguments of uvicorn.run for these settings."""
    return {
        "host": settings.host,
        "port": settings.port,
        "workers": settings.workers,
        "timeout_keep_alive": settings.timeout_keep_alive,
        "timeout_graceful_shutdown": settings.timeout_graceful_shutdown,
        # Passed here, uvicorn ignores the FORWARDED_ALLOW_IPS variable
        "forwarded_allow_ips": settings.forwarded_allow_ips,
    }


def main() -> None:
    # factory=True: uvicorn calls create_app() in the server process, so
    # the settings of the app are read there, not when this module loads
    uvicorn.run(APP_FACTORY, factory=True, **uvicorn_options(ServerSettings()))


if __name__ == "__main__":
    main()
