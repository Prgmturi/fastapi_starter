import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fastapi_starter.core.auth import TokenValidator, get_auth_service
from fastapi_starter.core.config import AppSettings
from fastapi_starter.core.database.dependencies import get_db_manager
from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.protocols import HealthCheckable

logger = get_logger(__name__)

health_router = APIRouter(prefix="/health", tags=["health"])

# A check slower than this counts as failed. SELECT 1 answers in
# milliseconds: a database that takes seconds cannot serve requests either,
# and the probe must answer before the orchestrator gives up on it.
CHECK_TIMEOUT_SECONDS = 2.0

CheckStatus = Literal["healthy", "unhealthy"]


def get_app_settings(request: Request) -> AppSettings:
    """Get AppSettings from app state (the ones create_app received)."""
    settings: AppSettings = request.app.state.settings.app
    return settings


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    version: str
    environment: str


class CheckResult(BaseModel):
    """Outcome of one readiness check. The cause of a failure is only logged."""

    status: CheckStatus


class ReadinessResponse(BaseModel):
    """Readiness check response schema."""

    status: CheckStatus
    checks: dict[str, CheckResult]


async def run_check(name: str, check: Callable[[], Awaitable[bool]]) -> CheckResult:
    """Run one readiness check, within CHECK_TIMEOUT_SECONDS.

    The endpoint needs no token, and error texts carry internal hosts and
    user names: the cause goes to the logs, the body gets only the status.
    """
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            ready = await check()
    except TimeoutError:
        error = f"timed out after {CHECK_TIMEOUT_SECONDS} s"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    else:
        if ready:
            return CheckResult(status="healthy")
        error = "reported not ready"

    logger.warning("readiness_check_failed", check=name, error=error)
    return CheckResult(status="unhealthy")


@health_router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Check if the application is running.",
)
async def liveness(
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> HealthResponse:
    """Liveness probe - returns OK if the application is running."""
    return HealthResponse(
        status="healthy",
        version=settings.version,
        environment=settings.environment,
    )


@health_router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Check if the application is ready to accept requests.",
    responses={
        200: {"description": "All services healthy"},
        503: {"description": "One or more services unhealthy"},
    },
)
async def readiness(
    db_manager: Annotated[HealthCheckable, Depends(get_db_manager)],
    auth_service: Annotated[TokenValidator, Depends(get_auth_service)],
) -> JSONResponse:
    """Readiness probe - can this instance serve requests now?

    A failed check answers 503. The auth check does not call the identity
    provider: while its signing keys are cached, tokens can be verified.
    """
    checks = {
        "database": await run_check("database", db_manager.health_check),
        "auth": await run_check("auth", auth_service.health_check),
    }

    all_healthy = all(check.status == "healthy" for check in checks.values())

    response = ReadinessResponse(
        status="healthy" if all_healthy else "unhealthy",
        checks=checks,
    )

    http_status = (
        status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(
        status_code=http_status,
        content=response.model_dump(),
    )
