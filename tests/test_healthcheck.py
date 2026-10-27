"""Tests for healthcheck.py — the probe Docker runs in the container.

Module under test: src/fastapi_starter/healthcheck.py
Layer: Entry point (python -m fastapi_starter.healthcheck)

WHY these tests exist: Docker's HEALTHCHECK called /health/live with
Host: localhost:8000. With production trusted hosts TrustedHostMiddleware
answered 400, so a working container was marked unhealthy and taken out
of rotation.
"""

import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from fastapi_starter import healthcheck
from fastapi_starter.core.config import ServerSettings, Settings
from fastapi_starter.main import create_app

DOCKERFILE = Path(__file__).parent.parent / "docker" / "Dockerfile"
PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

# Prints every module that importing the probe loads, one per line
LIST_LOADED = "import sys, fastapi_starter.healthcheck; print(*sys.modules, sep='\\n')"


def probe_contract() -> dict:
    """The import-linter contract of the probe, in pyproject.toml."""
    importlinter = tomllib.loads(PYPROJECT.read_text())["tool"]["importlinter"]
    for contract in importlinter["contracts"]:
        if contract.get("source_modules") == ["fastapi_starter.healthcheck"]:
            return contract
    raise AssertionError("pyproject.toml has no import contract for healthcheck.py")


class TestLivenessRequest:
    @pytest.mark.parametrize(
        "trusted_hosts",
        [
            ["api.example.com"],
            ["api.example.com", "admin.example.com"],
            ["*.example.com"],
            ["localhost", "127.0.0.1"],
        ],
    )
    async def test_app_answers_200(self, trusted_hosts):
        """[HP] The probe's Host passes the app's TrustedHostMiddleware."""
        server = ServerSettings(trusted_hosts=trusted_hosts)
        request = healthcheck.liveness_request(server)
        app = create_app(Settings(server=server))

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            response = await client.get(
                request.full_url, headers={"Host": request.get_header("Host")}
            )

        assert response.status_code == 200

    def test_port_from_settings(self):
        """[HP] SERVER_PORT, 8000 by default like the image's CMD."""
        assert healthcheck.liveness_request(ServerSettings()).full_url == (
            "http://127.0.0.1:8000/health/live"
        )
        assert (
            ":9000/" in healthcheck.liveness_request(ServerSettings(port=9000)).full_url
        )


class TestMain:
    """The exit status Docker reads: 0 healthy, 1 unhealthy."""

    def test_200_is_healthy(self, monkeypatch):
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: response)

        assert healthcheck.main() == 0

    def test_error_status_is_unhealthy(self, monkeypatch):
        """[EC] 400 from TrustedHostMiddleware, 500, ... -> urlopen raises."""

        def answer_400(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", answer_400)

        assert healthcheck.main() == 1

    def test_nothing_listening_is_unhealthy(self, monkeypatch):
        """[EC] Port 1 is closed: connection refused -> 1, no traceback."""
        monkeypatch.setenv("SERVER_PORT", "1")

        assert healthcheck.main() == 1


class TestWhatTheProbeLoads:
    """What importing healthcheck.py loads.

    WHY: Docker runs the probe every 30 seconds, each time in a new Python
    process. In the image importing it takes about 350 ms, the health
    router about 580 ms, the app about 640 ms. Its import-linter contract
    reads import statements, but not what the __init__.py of a package
    pulls in: with fastapi imported in core/config/__init__.py the
    contract stayed kept, and the probe loaded FastAPI.
    """

    def test_loads_none_of_the_forbidden_modules(self, tmp_path):
        """[EC] The modules the contract forbids are not loaded at all.

        In a subprocess, because in this one conftest.py has already
        imported the whole app.
        """
        forbidden = probe_contract()["forbidden_modules"]

        result = subprocess.run(
            [sys.executable, "-c", LIST_LOADED],
            cwd=tmp_path,  # no .env in this directory
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert [
            name
            for name in result.stdout.split()
            if any(
                name == module or name.startswith(f"{module}.") for module in forbidden
            )
        ] == []


class TestDockerfile:
    def test_healthcheck_runs_the_module(self):
        """[HP] The image probes with this module, not with a fixed Host."""
        instruction = re.search(
            r"^HEALTHCHECK .*?CMD (.+)$",
            DOCKERFILE.read_text().replace("\\\n", " "),
            re.MULTILINE,
        )

        assert instruction is not None
        assert instruction.group(1).strip() == (
            '["python", "-m", "fastapi_starter.healthcheck"]'
        )
