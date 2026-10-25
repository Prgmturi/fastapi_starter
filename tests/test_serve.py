"""Tests for serve.py — the command the Docker image starts.

Module under test: src/fastapi_starter/serve.py
Layer: Entry point (python -m fastapi_starter.serve)

WHY these tests exist: the image started uvicorn with --host and --port
written in its CMD and no limit on shutdown. Measured on 25 October 2026:
with SERVER_PORT=9001 the container was unhealthy while the app answered
on 8000, since the healthcheck read the setting and the CMD did not; and
docker stop with a request in flight waited 10.1 s for it, then killed
the process (exit 137) before the lifespan closed anything.
"""

import runpy
import sys

import pytest
import uvicorn

from fastapi_starter import serve
from fastapi_starter.core.config import ServerSettings
from fastapi_starter.healthcheck import liveness_request

# docker stop sends SIGTERM, then SIGKILL after this many seconds
DOCKER_STOP_TIMEOUT = 10


class TestUvicornOptions:
    def test_options_come_from_the_settings(self):
        """[HP] Every option uvicorn gets is a SERVER_* setting."""
        settings = ServerSettings(
            host="127.0.0.1",
            port=9001,
            workers=2,
            timeout_keep_alive=7,
            timeout_graceful_shutdown=3,
            forwarded_allow_ips=["172.18.0.0/16"],
        )

        assert serve.uvicorn_options(settings) == {
            "host": "127.0.0.1",
            "port": 9001,
            "workers": 2,
            "timeout_keep_alive": 7,
            "timeout_graceful_shutdown": 3,
            "forwarded_allow_ips": ["172.18.0.0/16"],
        }

    def test_listens_where_the_healthcheck_probes(self):
        """[HP] One SERVER_PORT for uvicorn and for Docker's probe."""
        settings = ServerSettings(port=9001)

        assert serve.uvicorn_options(settings)["port"] == 9001
        assert ":9001/" in liveness_request(settings).full_url

    def test_open_requests_get_less_than_docker_stop(self):
        """[HP] By default uvicorn stops waiting before Docker kills it.

        WHY: the lifespan closes the database pool and the HTTP client only
        after uvicorn has stopped waiting for open requests.
        """
        timeout = serve.uvicorn_options(ServerSettings())["timeout_graceful_shutdown"]

        assert 0 < timeout < DOCKER_STOP_TIMEOUT

    def test_never_reloads(self):
        """[EC] No --reload in the image: it is for development only."""
        assert "reload" not in serve.uvicorn_options(ServerSettings())


class TestMain:
    @pytest.fixture
    def uvicorn_calls(self, monkeypatch) -> list[tuple[str, dict]]:
        """uvicorn.run replaced: the calls, without starting a server."""
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            uvicorn, "run", lambda app, **options: calls.append((app, options))
        )
        return calls

    def test_runs_the_factory_with_the_settings(self, uvicorn_calls, monkeypatch):
        """[HP] uvicorn calls create_app, with the options of SERVER_*."""
        monkeypatch.setenv("SERVER_PORT", "9001")

        serve.main()

        assert uvicorn_calls == [
            (
                "fastapi_starter.main:create_app",
                {"factory": True, **serve.uvicorn_options(ServerSettings(port=9001))},
            )
        ]

    def test_runs_as_a_module(self, uvicorn_calls, monkeypatch):
        """[HP] python -m fastapi_starter.serve, the image's CMD, starts uvicorn."""
        # Run it fresh, as python -m does, not the copy imported above
        monkeypatch.delitem(sys.modules, "fastapi_starter.serve")

        runpy.run_module("fastapi_starter.serve", run_name="__main__")

        assert len(uvicorn_calls) == 1
