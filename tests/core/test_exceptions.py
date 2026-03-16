"""Tests for custom exceptions — status codes, messages, and hierarchy.

Module under test: src/fastapi_starter/core/exceptions.py
Layer: Pure domain (no I/O, no mocks needed)

WHY these tests exist: Exception classes carry status codes and structured
details that the exception handler converts to HTTP responses. Wrong status
code = wrong HTTP response. Wrong hierarchy = exception handler misses it.
"""

import pytest


class TestAppExceptionError:
    """Base exception — status code, message, details.

    WHY: All domain exceptions inherit from this. The exception handler
    reads .status_code, .message, .details to build the JSON response.
    """

    def test_default_status_code_is_500(self):
        """[HP] Without explicit status_code, defaults to 500."""
        pytest.skip("Not implemented yet")

    def test_custom_status_code(self):
        """[HP] Custom status_code is stored correctly."""
        pytest.skip("Not implemented yet")

    def test_details_default_to_empty_dict(self):
        """[HP] details=None -> stored as {}."""
        pytest.skip("Not implemented yet")

    def test_message_stored_and_in_str(self):
        """[HP] message accessible as .message and via str(exc)."""
        pytest.skip("Not implemented yet")


class TestNotFoundError:
    """NotFoundError — 404 with resource identification.

    WHY: Structured details (resource, identifier) help API consumers
    understand what was not found.
    """

    def test_status_code_is_404(self):
        """[HP] status_code == 404."""
        pytest.skip("Not implemented yet")

    def test_message_without_identifier(self):
        """[HP] message = '{resource} not found'."""
        pytest.skip("Not implemented yet")

    def test_message_with_identifier(self):
        """[HP] message = '{resource} with id '{id}' not found'."""
        pytest.skip("Not implemented yet")

    def test_details_include_resource_and_identifier(self):
        """[HP] details dict contains resource and identifier."""
        pytest.skip("Not implemented yet")


class TestConflictError:
    """ConflictError — 409."""

    def test_status_code_is_409(self):
        """[HP] status_code == 409."""
        pytest.skip("Not implemented yet")


class TestValidationError:
    """ValidationError — 422."""

    def test_status_code_is_422(self):
        """[HP] status_code == 422."""
        pytest.skip("Not implemented yet")


class TestUnauthorizedError:
    """UnauthorizedError — 401 with WWW-Authenticate header.

    WHY: The headers attribute is read by the exception handler
    to set HTTP response headers (required by RFC 7235).
    """

    def test_status_code_is_401(self):
        """[HP] status_code == 401."""
        pytest.skip("Not implemented yet")

    def test_default_message(self):
        """[HP] Default message is 'Authentication required'."""
        pytest.skip("Not implemented yet")

    def test_default_headers_include_www_authenticate(self):
        """[HP] headers['WWW-Authenticate'] == 'Bearer'."""
        pytest.skip("Not implemented yet")


class TestForbiddenError:
    """ForbiddenError — 403."""

    def test_status_code_is_403(self):
        """[HP] status_code == 403."""
        pytest.skip("Not implemented yet")

    def test_default_message(self):
        """[HP] Default message is 'Permission denied'."""
        pytest.skip("Not implemented yet")


class TestExternalServiceError:
    """ExternalServiceError — 502 with service identification.

    WHY: When Keycloak or DB is unreachable, the error response
    must include which service failed (for debugging).
    """

    def test_status_code_is_502(self):
        """[HP] status_code == 502."""
        pytest.skip("Not implemented yet")

    def test_default_message_includes_service_name(self):
        """[HP] message = 'Error communicating with {service}'."""
        pytest.skip("Not implemented yet")

    def test_details_include_service(self):
        """[HP] details['service'] == service name."""
        pytest.skip("Not implemented yet")


class TestExceptionHierarchy:
    """All exceptions inherit from AppExceptionError.

    WHY: The global exception handler catches AppExceptionError.
    If a subclass does not inherit from it, the handler misses it
    and the unhandled handler returns a generic 500.
    """

    def test_all_subclasses_inherit_from_app_exception_error(self):
        """[CT] NotFound, Conflict, Validation, Unauthorized, Forbidden,
        ExternalService are all subclasses of AppExceptionError."""
        pytest.skip("Not implemented yet")
