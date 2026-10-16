"""Tests for exception handlers — every error as an RFC 9457 problem.

Module under test: src/fastapi_starter/exception_handlers.py
Layer: Application integration (HTTP client against the real app)

WHY these tests exist: exception handlers are the last line of defense.
They turn exceptions into HTTP responses. If they break, the API returns
errors a client cannot parse, or leaks internal details.

STRATEGY: Create a temporary endpoint that raises each exception type,
then call it through the app and verify the whole HTTP response.
"""

from http import HTTPStatus

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field

from fastapi_starter.core.auth.dependencies import AdminUser, CurrentUser
from fastapi_starter.core.exceptions import (
    AppExceptionError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

# The media type RFC 9457 defines; written here, not imported, so the
# test checks the code against the standard.
PROBLEM_JSON = "application/problem+json"


def assert_problem(response, status: int) -> dict:
    """The response is an RFC 9457 problem document for this status.

    Returns the body, for the checks specific to each test.
    """
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == HTTPStatus(status).phrase
    assert body["status"] == status
    assert isinstance(body["detail"], str)
    assert body["detail"]
    return body


class TestSameShapeForEveryError:
    """401, 403, 404, 405, 422 and 500 answer with the same members.

    WHY: a client reads every error with one piece of code. Before this
    there were three shapes: {"detail": "..."}, {"detail": [...]} and
    {"message", "details"}.
    """

    @pytest.fixture(autouse=True)
    def routes(self, app, mock_auth_service, sample_user):
        async def validate(token: str):
            if token == "user-token":
                return sample_user
            raise UnauthorizedError("Invalid token")

        mock_auth_service.validate_token.side_effect = validate

        @app.get("/shape/me")
        async def me(user: CurrentUser) -> dict[str, str]:
            return {"id": user.id}

        @app.get("/shape/admin")
        async def admin(user: AdminUser) -> dict[str, str]:
            return {"id": user.id}

        @app.get("/shape/items")
        async def items(limit: int) -> dict[str, int]:
            return {"limit": limit}

        @app.get("/shape/crash")
        async def crash() -> None:
            raise RuntimeError("bug")

    @pytest.mark.parametrize(
        ("method", "path", "headers", "status"),
        [
            pytest.param("GET", "/shape/me", {}, 401, id="401-no-token"),
            pytest.param(
                "GET",
                "/shape/me",
                {"Authorization": "Bearer bad"},
                401,
                id="401-invalid-token",
            ),
            pytest.param(
                "GET",
                "/shape/admin",
                {"Authorization": "Bearer user-token"},
                403,
                id="403-missing-role",
            ),
            pytest.param("GET", "/shape/nowhere", {}, 404, id="404-unknown-path"),
            pytest.param("POST", "/shape/me", {}, 405, id="405-wrong-method"),
            pytest.param("GET", "/shape/items?limit=many", {}, 422, id="422-bad-query"),
            pytest.param("GET", "/shape/crash", {}, 500, id="500-unexpected"),
        ],
    )
    async def test_answers_with_a_problem_document(
        self, client, method, path, headers, status
    ):
        """[HP] Same media type and members, whatever produced the error."""
        response = await client.request(method, path, headers=headers)

        assert_problem(response, status)

    async def test_401_without_token_asks_for_a_bearer_token(self, client):
        """[HP] RFC 9110: a 401 says which scheme to use (WWW-Authenticate)."""
        response = await client.get("/shape/me")

        body = assert_problem(response, 401)
        assert body["detail"] == "Not authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_405_lists_the_allowed_methods(self, client):
        """[HP] RFC 9110: a 405 lists the methods the path accepts (Allow)."""
        response = await client.post("/shape/me")

        assert_problem(response, 405)
        assert response.headers["Allow"] == "GET"


class TestAppExceptionHandler:
    """Handler for AppExceptionError and subclasses.

    WHY: every AppExceptionError subclass must produce its status code,
    its message as detail, and its details as extension members.
    """

    async def test_not_found_returns_404(self, app, client):
        """[HP] NotFoundError -> 404, resource and identifier as members."""

        @app.get("/exc/not-found")
        async def _():
            raise NotFoundError("User", identifier="abc-123")

        response = await client.get("/exc/not-found")

        body = assert_problem(response, 404)
        assert body["detail"] == "User with id 'abc-123' not found"
        assert body["resource"] == "User"
        assert body["identifier"] == "abc-123"

    async def test_conflict_returns_409(self, app, client):
        """[HP] ConflictError -> 409."""

        @app.get("/exc/conflict")
        async def _():
            raise ConflictError("already exists", resource="User")

        response = await client.get("/exc/conflict")

        body = assert_problem(response, 409)
        assert body["detail"] == "already exists"
        assert body["resource"] == "User"

    async def test_validation_error_returns_422(self, app, client):
        """[HP] ValidationError -> 422 with the field as a member."""

        @app.get("/exc/validation")
        async def _():
            raise ValidationError("invalid input", field="email")

        response = await client.get("/exc/validation")

        body = assert_problem(response, 422)
        assert body["detail"] == "invalid input"
        assert body["field"] == "email"

    async def test_unauthorized_returns_401_with_headers(self, app, client):
        """[HP] UnauthorizedError -> 401 + WWW-Authenticate header.

        WHY: RFC 9110 requires WWW-Authenticate header on 401 responses.
        """

        @app.get("/exc/unauthorized")
        async def _():
            raise UnauthorizedError()

        response = await client.get("/exc/unauthorized")

        assert_problem(response, 401)
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_forbidden_returns_403(self, app, client):
        """[HP] ForbiddenError -> 403."""

        @app.get("/exc/forbidden")
        async def _():
            raise ForbiddenError()

        response = await client.get("/exc/forbidden")

        body = assert_problem(response, 403)
        assert body["detail"] == "Permission denied"

    async def test_external_service_returns_502_with_service_name(
        self,
        app,
        client,
    ):
        """[HP] ExternalServiceError -> 502 with the service as a member."""

        @app.get("/exc/external")
        async def _():
            raise ExternalServiceError("Keycloak")

        response = await client.get("/exc/external")

        body = assert_problem(response, 502)
        assert body["detail"] == "Error communicating with Keycloak"
        assert body["service"] == "Keycloak"

    async def test_details_cannot_replace_standard_members(self, app, client):
        """[EC] A details key named like an RFC member is dropped.

        WHY: status and title must match the response. A subclass that
        put "status" in its details would otherwise lie to the client.
        """

        @app.get("/exc/clash")
        async def _():
            raise AppExceptionError(
                "clash",
                status_code=400,
                details={"status": 999, "title": "Fine", "hint": "kept"},
            )

        response = await client.get("/exc/clash")

        body = assert_problem(response, 400)
        assert body["hint"] == "kept"

    async def test_status_without_standard_phrase_gets_generic_title(self, app, client):
        """[EC] A status with no standard phrase (499) still gets a problem.

        WHY: building the error response must never fail, or the client
        gets a bare 500 instead of the error the code meant to send.
        """

        @app.get("/exc/unregistered")
        async def _():
            raise AppExceptionError("client closed request", status_code=499)

        response = await client.get("/exc/unregistered")

        assert response.status_code == 499
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.json() == {
            "type": "about:blank",
            "title": "Error",
            "status": 499,
            "detail": "client closed request",
        }


class TestHTTPExceptionHandler:
    """Starlette and FastAPI HTTPException.

    WHY: routing raises them for unknown paths (404) and wrong methods
    (405), and FastAPI code often raises them directly.
    """

    async def test_detail_text_becomes_detail(self, app, client):
        """[HP] HTTPException(418, "I'm a teapot") -> problem with that detail."""

        @app.get("/exc/http-exception")
        async def _():
            raise HTTPException(status_code=418, detail="I'm a teapot")

        response = await client.get("/exc/http-exception")

        body = assert_problem(response, 418)
        assert body["detail"] == "I'm a teapot"

    async def test_structured_detail_is_not_rendered(self, app, client):
        """[EC] A non-text detail is replaced by the status phrase.

        WHY: str() of a dict or an enum shows Python reprs to the client.
        Structured data goes in an AppExceptionError subclass instead.
        """

        @app.get("/exc/structured")
        async def _():
            raise HTTPException(status_code=400, detail={"field": "x"})

        response = await client.get("/exc/structured")

        body = assert_problem(response, 400)
        assert body["detail"] == "Bad Request"

    async def test_status_without_body_sends_no_body(self, app, client):
        """[EC] 304 must not carry a body (RFC 9110), so no problem document."""

        @app.get("/exc/not-modified")
        async def _():
            raise HTTPException(status_code=304)

        response = await client.get("/exc/not-modified")

        assert response.status_code == 304
        assert response.content == b""


class Credentials(BaseModel):
    username: str
    password: str = Field(min_length=12)


class TestRequestValidationHandler:
    """Invalid query, path or body -> 422 with one entry per field.

    WHY: the client needs to know which field to fix and why. FastAPI's
    own format put the list under "detail", where RFC 9457 wants text.
    """

    async def test_lists_each_invalid_field(self, app, client):
        """[HP] errors has loc, msg and type for every invalid field."""

        @app.get("/v/items")
        async def _(limit: int, offset: int) -> dict[str, int]:
            return {"limit": limit, "offset": offset}

        response = await client.get("/v/items?limit=many")

        body = assert_problem(response, 422)
        assert body["detail"] == "Request validation failed"
        assert [(e["loc"], e["type"]) for e in body["errors"]] == [
            (["query", "limit"], "int_parsing"),
            (["query", "offset"], "missing"),
        ]
        for error in body["errors"]:
            assert set(error) == {"loc", "msg", "type"}
            assert error["msg"]

    async def test_does_not_echo_what_the_client_sent(self, app, client):
        """[SEC] The rejected value is not copied into the response.

        WHY: FastAPI's default echoed the input. For a password that is
        too short, the password itself came back and reached any log or
        tool that records responses.
        """

        @app.post("/v/login")
        async def _(credentials: Credentials) -> dict[str, str]:
            return {"username": credentials.username}

        response = await client.post(
            "/v/login", json={"username": "mario", "password": "hunter2"}
        )

        assert_problem(response, 422)
        assert "hunter2" not in response.text


class TestUnhandledExceptionHandler:
    """Catch-all handler for unexpected exceptions.

    WHY: Security requirement. Unhandled exceptions must not leak
    stack traces or internal details. The response must always be
    a generic 500.
    """

    async def test_returns_500(self, app, client):
        """[HP] Unknown Exception -> 500 problem document."""

        @app.get("/exc/unhandled")
        async def _():
            raise RuntimeError("unexpected crash")

        response = await client.get("/exc/unhandled")

        assert_problem(response, 500)

    async def test_response_hides_internal_details(self, app, client):
        """[HP] Response body is generic, no stack trace.

        WHY: Leaking internal details (file paths, variable names,
        database schemas) is a security vulnerability.
        """

        @app.get("/exc/hidden")
        async def _():
            raise RuntimeError("secret database password exposed")

        response = await client.get("/exc/hidden")

        body = assert_problem(response, 500)
        assert body["detail"] == "An unexpected error occurred."
        assert "secret" not in response.text
        assert "password" not in response.text
