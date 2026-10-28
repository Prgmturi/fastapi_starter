from http import HTTPStatus
from typing import Any


class AppExceptionError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppExceptionError):
    def __init__(self, resource: str, identifier: str | int | None = None) -> None:
        message = f"{resource} not found"
        if identifier is not None:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(
            message=message,
            status_code=HTTPStatus.NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(AppExceptionError):
    def __init__(self, message: str, resource: str | None = None) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.CONFLICT,
            details={"resource": resource} if resource else {},
        )


class ValidationError(AppExceptionError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
            details={"field": field} if field else {},
        )


class UnauthorizedError(AppExceptionError):
    def __init__(
        self,
        message: str = "Authentication required",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message=message, status_code=HTTPStatus.UNAUTHORIZED)
        self.headers = headers or {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppExceptionError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message=message, status_code=HTTPStatus.FORBIDDEN)


class ExternalServiceError(AppExceptionError):
    """External service communication error."""

    def __init__(
        self,
        service: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Error communicating with {service}",
            status_code=HTTPStatus.BAD_GATEWAY,
            details={"service": service},
        )


class ServiceUnavailableError(AppExceptionError):
    """A service the request needs is unreachable: retry later (503).

    Unlike ExternalServiceError (502), the same request can succeed once
    the service is back.
    """

    def __init__(self, service: str) -> None:
        super().__init__(
            message="Service temporarily unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            details={"service": service},
        )
