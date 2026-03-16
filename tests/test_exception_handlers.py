"""Tests for exception handlers — global error handling.

Module under test: src/fastapi_starter/exception_handlers.py
Layer: Application integration (TestClient)

WHY these tests exist: Exception handlers are the last line of defense.
They convert domain exceptions to HTTP responses. If they break, the API
returns unparseable errors or leaks internal details.

STRATEGY: Create a temporary test endpoint that raises each exception type,
then call it via TestClient and verify the HTTP response.
"""

import pytest


class TestAppExceptionHandler:
    """Handler for AppExceptionError and subclasses.

    WHY: This handler converts every AppExceptionError subclass into
    a JSON response with {message, details}. We must verify each
    subclass produces the correct HTTP status code and response body.
    """

    async def test_not_found_returns_404_with_message(self):
        """[HP] NotFoundError -> 404 + JSON body."""
        pytest.skip("Not implemented yet")

    async def test_conflict_returns_409_with_message(self):
        """[HP] ConflictError -> 409 + JSON body."""
        pytest.skip("Not implemented yet")

    async def test_validation_error_returns_422_with_message(self):
        """[HP] ValidationError -> 422 + JSON body."""
        pytest.skip("Not implemented yet")

    async def test_unauthorized_returns_401_with_headers(self):
        """[HP] UnauthorizedError -> 401 + WWW-Authenticate header.

        WHY: RFC 7235 requires WWW-Authenticate header on 401 responses.
        """
        pytest.skip("Not implemented yet")

    async def test_forbidden_returns_403_with_message(self):
        """[HP] ForbiddenError -> 403 + JSON body."""
        pytest.skip("Not implemented yet")

    async def test_external_service_returns_502_with_service_name(self):
        """[HP] ExternalServiceError -> 502 + JSON with service name."""
        pytest.skip("Not implemented yet")

    async def test_response_body_structure(self):
        """[HP] Response always has {message: str, details: dict}.

        WHY: Frontend relies on this structure for error display.
        """
        pytest.skip("Not implemented yet")


class TestUnhandledExceptionHandler:
    """Catch-all handler for unexpected exceptions.

    WHY: Security requirement. Unhandled exceptions must not leak
    stack traces or internal details. The response must always be
    a generic 500 with 'Internal server error'.
    """

    async def test_returns_500(self):
        """[HP] Unknown Exception -> 500."""
        pytest.skip("Not implemented yet")

    async def test_response_hides_internal_details(self):
        """[HP] Response body is generic, no stack trace.

        WHY: Leaking internal details (file paths, variable names,
        database schemas) is a security vulnerability.
        """
        pytest.skip("Not implemented yet")

    async def test_http_exception_re_raised(self):
        """[EC] FastAPI HTTPException is re-raised, not caught.

        WHY: The unhandled handler explicitly checks for HTTPException
        and re-raises it so FastAPI's built-in handler processes it.
        This preserves correct 401/403/404 behavior for Depends() errors.
        """
        pytest.skip("Not implemented yet")
