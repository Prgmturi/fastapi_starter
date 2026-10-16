"""Error responses as RFC 9457 problem details (application/problem+json).

Every error the API sends has the same members, so a client reads all of
them with the same code:

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "Product with id '3' not found"}

``type`` stays "about:blank": the status code alone says what kind of
problem it is, and ``title`` is that code's standard phrase. ``detail``
explains this occurrence. Any other member is an extension, such as
``errors`` for an invalid request.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

PROBLEM_JSON = "application/problem+json"

# Defined by the RFC: an extension never replaces them, or status and
# title could disagree with the response.
_STANDARD_MEMBERS = frozenset({"type", "title", "status", "detail", "instance"})


class ProblemDetails(BaseModel):
    """Body of every error response (RFC 9457)."""

    # Extension members, such as "resource" for a 404 or "service" for a 503.
    model_config = ConfigDict(extra="allow")

    type: str = Field(
        default="about:blank",
        description="Problem type. about:blank: the status code says it all",
    )
    title: str = Field(
        description="Standard phrase of the status code", examples=["Not Found"]
    )
    status: int = Field(description="HTTP status code", examples=[404])
    detail: str = Field(
        description="What went wrong in this request",
        examples=["Product with id '3' not found"],
    )
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Invalid request (422) only: one entry per invalid field, "
            "with loc, msg and type"
        ),
    )


def problem_response(
    status_code: int,
    detail: str | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> JSONResponse:
    """Build the error response for ``status_code``.

    Args:
        status_code: HTTP status of the response.
        detail: Explanation for the client. Defaults to the status phrase.
        headers: Extra response headers, such as WWW-Authenticate.
        extensions: Extra members. Members set to None are left out.
    """
    title = _status_phrase(status_code)
    members = {
        name: value
        for name, value in (extensions or {}).items()
        if name not in _STANDARD_MEMBERS
    }
    problem = ProblemDetails(
        title=title, status=status_code, detail=detail or title, **members
    )
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=status_code,
        headers=dict(headers) if headers else None,
        media_type=PROBLEM_JSON,
    )


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


# For OpenAPI. Passed to FastAPI(responses=...), so every route has it.
# "default" covers every status a route does not document itself, and
# FastAPI then skips its own 422 schema, which describes {"detail": [...]}.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {
        "description": "Error (RFC 9457 problem details)",
        "content": {
            PROBLEM_JSON: {
                "schema": ProblemDetails.model_json_schema(mode="serialization")
            }
        },
    }
}
