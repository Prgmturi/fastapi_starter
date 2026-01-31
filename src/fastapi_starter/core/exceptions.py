from typing import Any

from fastapi import HTTPException, status


class AppExceptionError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail={"message": self.message, **self.details},
        )


class NotFoundError(AppExceptionError):
    def __init__(self, resource: str, identifier: str | int | None = None) -> None:
        message = f"{resource} not found"
        if identifier is not None:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(AppExceptionError):
    def __init__(self, message: str, resource: str | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details={"resource": resource} if resource else {},
        )


class ValidationError(AppExceptionError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"field": field} if field else {},
        )


class UnauthorizedError(AppExceptionError):
    def __init__(
        self,
        message: str = "Authentication required",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message=message, status_code=status.HTTP_401_UNAUTHORIZED)
        self.headers = headers or {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppExceptionError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN)


class ExternalServiceError(AppExceptionError):
    """External service communication error."""

    def __init__(
        self,
        service: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Error communicating with {service}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service},
        )
