from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fastapi_starter.core.auth import TokenValidator, get_auth_service
from fastapi_starter.core.config import get_settings
from fastapi_starter.core.database.dependencies import get_db_manager
from fastapi_starter.core.protocols import HealthCheckable

health_router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness check response schema."""

    status: str
    checks: dict[str, Any]


@health_router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Check if the application is running.",
)
async def liveness() -> HealthResponse:
    """Liveness probe - returns OK if the application is running."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.app.version,
        environment=settings.app.environment,
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
    """Readiness probe - checks database and auth backend connectivity."""
    checks: dict[str, Any] = {}

    # Check database
    try:
        await db_manager.health_check()
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # Check auth backend (provider-agnostic)
    try:
        await auth_service.health_check()
        checks["auth"] = {"status": "healthy"}
    except Exception as e:
        checks["auth"] = {"status": "unhealthy", "error": str(e)}

    all_healthy = all(check.get("status") == "healthy" for check in checks.values())

    response = ReadinessResponse(
        status="healthy" if all_healthy else "unhealthy",
        checks=checks,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )
