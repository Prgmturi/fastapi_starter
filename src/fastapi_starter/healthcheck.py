"""Docker's HEALTHCHECK: GET /health/live on this container.

Run as ``python -m fastapi_starter.healthcheck``. TrustedHostMiddleware
answers 400 to a Host missing from SERVER_TRUSTED_HOSTS, so the probe
sends the first trusted host instead of localhost. It reads the settings
the way the app does (environment, then .env), so the two cannot disagree.

Exit status 0: healthy. 1: no answer, or an answer other than 200.
"""

import sys
import urllib.request

from fastapi_starter.core.config.server import ServerSettings


def host_header(trusted_hosts: list[str]) -> str:
    """The first trusted host, made concrete if it is a wildcard.

    "*.example.com" accepts "healthcheck.example.com"; "*" accepts anything.
    """
    host = trusted_hosts[0] if trusted_hosts else "localhost"
    return host.replace("*", "healthcheck", 1)


def liveness_request(settings: ServerSettings) -> urllib.request.Request:
    return urllib.request.Request(
        f"http://127.0.0.1:{settings.port}/health/live",
        headers={"Host": host_header(settings.trusted_hosts)},
    )


def main() -> int:
    request = liveness_request(ServerSettings())
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return 0 if response.status == 200 else 1
    except OSError:
        # Connection refused, timeout, and HTTPError for 4xx and 5xx
        return 1


if __name__ == "__main__":
    sys.exit(main())
