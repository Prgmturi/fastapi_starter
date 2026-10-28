"""Tests for custom exceptions — status codes, messages, and hierarchy.

Module under test: src/fastapi_starter/core/exceptions.py
Layer: Pure domain (no I/O, no mocks needed)

WHY these tests exist: Exception classes carry status codes and structured
details that the exception handler converts to HTTP responses. Wrong status
code = wrong HTTP response. Wrong hierarchy = exception handler misses it.
"""

import subprocess
import sys

from fastapi_starter.core.exceptions import (
    AppExceptionError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
)


class TestAppExceptionError:
    """Base exception — status code, message, details.

    WHY: All domain exceptions inherit from this. The exception handler
    reads .status_code, .message, .details to build the JSON response.
    """

    def test_default_status_code_is_500(self):
        """[HP] Without explicit status_code, defaults to 500."""
        exc = AppExceptionError("something broke")

        assert exc.status_code == 500

    def test_custom_status_code(self):
        """[HP] Custom status_code is stored correctly."""
        exc = AppExceptionError("bad request", status_code=400)

        assert exc.status_code == 400

    def test_details_default_to_empty_dict(self):
        """[HP] details=None -> stored as {}."""
        exc = AppExceptionError("error")

        assert exc.details == {}

    def test_message_stored_and_in_str(self):
        """[HP] message accessible as .message and via str(exc)."""
        exc = AppExceptionError("test message")

        assert exc.message == "test message"
        assert str(exc) == "test message"


class TestNotFoundError:
    """NotFoundError — 404 with resource identification.

    WHY: Structured details (resource, identifier) help API consumers
    understand what was not found.
    """

    def test_status_code_is_404(self):
        """[HP] status_code == 404."""
        exc = NotFoundError("User")

        assert exc.status_code == 404

    def test_message_without_identifier(self):
        """[HP] message = '{resource} not found'."""
        exc = NotFoundError("User")

        assert exc.message == "User not found"

    def test_message_with_identifier(self):
        """[HP] message = '{resource} with id '{id}' not found'."""
        exc = NotFoundError("User", identifier="abc-123")

        assert exc.message == "User with id 'abc-123' not found"

    def test_details_include_resource_and_identifier(self):
        """[HP] details dict contains resource and identifier."""
        exc = NotFoundError("User", identifier=42)

        assert exc.details == {"resource": "User", "identifier": 42}


class TestConflictError:
    """ConflictError — 409."""

    def test_status_code_is_409(self):
        """[HP] status_code == 409."""
        exc = ConflictError("already exists")

        assert exc.status_code == 409


class TestValidationError:
    """ValidationError — 422."""

    def test_status_code_is_422(self):
        """[HP] status_code == 422."""
        exc = ValidationError("invalid input")

        assert exc.status_code == 422


class TestUnauthorizedError:
    """UnauthorizedError — 401 with WWW-Authenticate header.

    WHY: The headers attribute is read by the exception handler
    to set HTTP response headers (required by RFC 7235).
    """

    def test_status_code_is_401(self):
        """[HP] status_code == 401."""
        exc = UnauthorizedError()

        assert exc.status_code == 401

    def test_default_message(self):
        """[HP] Default message is 'Authentication required'."""
        exc = UnauthorizedError()

        assert exc.message == "Authentication required"

    def test_default_headers_include_www_authenticate(self):
        """[HP] headers['WWW-Authenticate'] == 'Bearer'."""
        exc = UnauthorizedError()

        assert exc.headers == {"WWW-Authenticate": "Bearer"}


class TestForbiddenError:
    """ForbiddenError — 403."""

    def test_status_code_is_403(self):
        """[HP] status_code == 403."""
        exc = ForbiddenError()

        assert exc.status_code == 403

    def test_default_message(self):
        """[HP] Default message is 'Permission denied'."""
        exc = ForbiddenError()

        assert exc.message == "Permission denied"


class TestExternalServiceError:
    """ExternalServiceError — 502 with service identification.

    WHY: When Keycloak or DB is unreachable, the error response
    must include which service failed (for debugging).
    """

    def test_status_code_is_502(self):
        """[HP] status_code == 502."""
        exc = ExternalServiceError("Keycloak")

        assert exc.status_code == 502

    def test_default_message_includes_service_name(self):
        """[HP] message = 'Error communicating with {service}'."""
        exc = ExternalServiceError("Keycloak")

        assert exc.message == "Error communicating with Keycloak"

    def test_details_include_service(self):
        """[HP] details['service'] == service name."""
        exc = ExternalServiceError("Keycloak")

        assert exc.details == {"service": "Keycloak"}


class TestServiceUnavailableError:
    """ServiceUnavailableError — 503, the request can be retried.

    WHY: with Keycloak down a valid token cannot always be checked. A 401
    would send the user back to the login; 503 says "retry later".
    """

    def test_status_code_is_503(self):
        """[HP] status_code == 503."""
        exc = ServiceUnavailableError("auth")

        assert exc.status_code == 503

    def test_message_is_generic(self):
        """[HP] Same message for every service: no internal names."""
        exc = ServiceUnavailableError("auth")

        assert exc.message == "Service temporarily unavailable"

    def test_details_include_service(self):
        """[HP] details['service'] == the label passed in."""
        exc = ServiceUnavailableError("auth")

        assert exc.details == {"service": "auth"}


class TestExceptionHierarchy:
    """All exceptions inherit from AppExceptionError.

    WHY: The global exception handler catches AppExceptionError.
    If a subclass does not inherit from it, the handler misses it
    and the unhandled handler returns a generic 500.
    """

    def test_all_subclasses_inherit_from_app_exception_error(self):
        """[CT] NotFound, Conflict, Validation, Unauthorized, Forbidden,
        ExternalService, ServiceUnavailable are all subclasses of
        AppExceptionError."""
        subclasses = [
            NotFoundError,
            ConflictError,
            ValidationError,
            UnauthorizedError,
            ForbiddenError,
            ExternalServiceError,
            ServiceUnavailableError,
        ]

        for cls in subclasses:
            assert issubclass(cls, AppExceptionError), (
                f"{cls.__name__} must inherit from AppExceptionError"
            )


class TestNoWebFramework:
    """What importing the exceptions loads.

    WHY: the business layer of a feature raises them (NotFoundError), and
    that layer must not depend on FastAPI. The status codes came from
    fastapi.status, so importing the exceptions loaded FastAPI and Starlette.
    """

    def test_import_loads_neither_fastapi_nor_starlette(self, tmp_path):
        """[EC] The codes come from the standard library, http.HTTPStatus.

        In a subprocess, because in this one conftest.py has already
        imported the whole app.
        """
        code = (
            "import sys, fastapi_starter.core.exceptions; "
            "print(sorted({name.split('.')[0] for name in sys.modules} "
            "& {'fastapi', 'starlette'}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp_path,  # no .env in this directory
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]"
