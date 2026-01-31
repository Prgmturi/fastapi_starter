from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from fastapi_starter.core.auth.dependencies import get_auth_service
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.config import get_settings
from fastapi_starter.core.database.dependencies import get_db_manager
from fastapi_starter.core.database.manager import DatabaseManager

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
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Check if the application is ready to accept requests.",
)
async def readiness(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    ) -> ReadinessResponse:
    """Readiness probe - checks database connectivity."""
    checks: dict[str, Any] = {}

    # Check database
    try:
        await db_manager.health_check()
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # Check Keycloak
    try:
        await auth_service.health_check()
        checks["keycloak"] = {"status": "healthy"}
    except Exception as e:
        checks["keycloak"] = {"status": "unhealthy", "error": str(e)}

    # Determine overall status
    all_healthy = all(
        check.get("status") == "healthy" for check in checks.values()
    )

    return ReadinessResponse(
        status="healthy" if all_healthy else "unhealthy",
        checks=checks,
    )
