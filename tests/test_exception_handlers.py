"""Tests for exception handlers — global error handling.

Module under test: src/fastapi_starter/exception_handlers.py
Layer: Application integration (TestClient)

WHY these tests exist: Exception handlers are the last line of defense.
They convert domain exceptions to HTTP responses. If they break, the API
returns unparseable errors or leaks internal details.

STRATEGY: Create a temporary test endpoint that raises each exception type,
then call it via TestClient and verify the HTTP response.
"""

from fastapi import HTTPException

from fastapi_starter.core.exceptions import (
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class TestAppExceptionHandler:
    """Handler for AppExceptionError and subclasses.

    WHY: This handler converts every AppExceptionError subclass into
    a JSON response with {message, details}. We must verify each
    subclass produces the correct HTTP status code and response body.
    """

    async def test_not_found_returns_404_with_message(self, app, client):
        """[HP] NotFoundError -> 404 + JSON body."""

        @app.get("/exc/not-found")
        async def _():
            raise NotFoundError("User", identifier="abc-123")

        response = await client.get("/exc/not-found")

        assert response.status_code == 404
        body = response.json()
        assert body["message"] == "User with id 'abc-123' not found"

    async def test_conflict_returns_409_with_message(self, app, client):
        """[HP] ConflictError -> 409 + JSON body."""

        @app.get("/exc/conflict")
        async def _():
            raise ConflictError("already exists", resource="User")

        response = await client.get("/exc/conflict")

        assert response.status_code == 409
        body = response.json()
        assert body["message"] == "already exists"

    async def test_validation_error_returns_422_with_message(self, app, client):
        """[HP] ValidationError -> 422 + JSON body."""

        @app.get("/exc/validation")
        async def _():
            raise ValidationError("invalid input", field="email")

        response = await client.get("/exc/validation")

        assert response.status_code == 422
        body = response.json()
        assert body["message"] == "invalid input"

    async def test_unauthorized_returns_401_with_headers(self, app, client):
        """[HP] UnauthorizedError -> 401 + WWW-Authenticate header.

        WHY: RFC 7235 requires WWW-Authenticate header on 401 responses.
        """

        @app.get("/exc/unauthorized")
        async def _():
            raise UnauthorizedError()

        response = await client.get("/exc/unauthorized")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_forbidden_returns_403_with_message(self, app, client):
        """[HP] ForbiddenError -> 403 + JSON body."""

        @app.get("/exc/forbidden")
        async def _():
            raise ForbiddenError()

        response = await client.get("/exc/forbidden")

        assert response.status_code == 403
        body = response.json()
        assert body["message"] == "Permission denied"

    async def test_external_service_returns_502_with_service_name(
        self,
        app,
        client,
    ):
        """[HP] ExternalServiceError -> 502 + JSON with service name."""

        @app.get("/exc/external")
        async def _():
            raise ExternalServiceError("Keycloak")

        response = await client.get("/exc/external")

        assert response.status_code == 502
        body = response.json()
        assert body["message"] == "Error communicating with Keycloak"
        assert body["details"]["service"] == "Keycloak"

    async def test_response_body_structure(self, app, client):
        """[HP] Response always has {message: str, details: dict}.

        WHY: Frontend relies on this structure for error display.
        """

        @app.get("/exc/structure")
        async def _():
            raise NotFoundError("Item")

        response = await client.get("/exc/structure")
        body = response.json()

        assert "message" in body
        assert "details" in body
        assert isinstance(body["message"], str)
        assert isinstance(body["details"], dict)


class TestUnhandledExceptionHandler:
    """Catch-all handler for unexpected exceptions.

    WHY: Security requirement. Unhandled exceptions must not leak
    stack traces or internal details. The response must always be
    a generic 500 with 'Internal server error'.
    """

    async def test_returns_500(self, app, client):
        """[HP] Unknown Exception -> 500."""

        @app.get("/exc/unhandled")
        async def _():
            raise RuntimeError("unexpected crash")

        response = await client.get("/exc/unhandled")

        assert response.status_code == 500

    async def test_response_hides_internal_details(self, app, client):
        """[HP] Response body is generic, no stack trace.

        WHY: Leaking internal details (file paths, variable names,
        database schemas) is a security vulnerability.
        """

        @app.get("/exc/hidden")
        async def _():
            raise RuntimeError("secret database password exposed")

        response = await client.get("/exc/hidden")
        body = response.json()

        assert body["message"] == "Internal server error"
        assert body["details"] == {}
        assert "secret" not in str(body)
        assert "password" not in str(body)

    async def test_http_exception_re_raised(self, app, client):
        """[EC] FastAPI HTTPException is re-raised, not caught.

        WHY: The unhandled handler explicitly checks for HTTPException
        and re-raises it so FastAPI's built-in handler processes it.
        This preserves correct 401/403/404 behavior for Depends() errors.
        """

        @app.get("/exc/http-exception")
        async def _():
            raise HTTPException(status_code=418, detail="I'm a teapot")

        response = await client.get("/exc/http-exception")

        assert response.status_code == 418
        assert response.json()["detail"] == "I'm a teapot"
