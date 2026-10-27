"""Tests for auth schemas — User model, RoleEnum, and TokenResponse.

Module under test: src/fastapi_starter/core/auth/schemas.py
Layer: Pure domain (no I/O, no mocks needed)

WHY these tests exist: User and RoleEnum are the core domain models.
Every other module depends on them. We verify our Pydantic configuration
(patterns, constraints), computed properties (full_name), and role-checking
logic so that changes are deliberate and visible.
"""

import pytest
from pydantic import ValidationError

from fastapi_starter.core.auth.schemas import RoleEnum, TokenResponse, User


def _make_user(**overrides) -> User:
    """Build a User with sensible defaults. Override any field via kwargs."""
    defaults: dict = {
        "id": "e37e9825-ac1c-4bd3-8380-579af43eac48",
        "username": "test_user",
        "roles": [RoleEnum.USER],
    }
    return User(**(defaults | overrides))


# ---------------------------------------------------------------------------
# RoleEnum
# ---------------------------------------------------------------------------


class TestRoleEnum:
    """RoleEnum values and helper methods.

    WHY: RoleEnum is referenced in authorization decisions throughout the app.
    These tests lock down the enum membership and convenience methods so that
    adding/removing a role is a deliberate, visible change.
    """

    def test_all_roles_returns_complete_list(self):
        """[HP] all_roles() returns all four defined roles."""
        result = RoleEnum.all_roles()

        expected = {RoleEnum.SUPERADMIN, RoleEnum.ADMIN, RoleEnum.COLLAB, RoleEnum.USER}
        assert set(result) == expected
        assert len(result) == 4

    def test_staff_roles_returns_admin_and_superadmin(self):
        """[HP] staff_roles() returns only SUPERADMIN and ADMIN."""
        result = RoleEnum.staff_roles()

        assert result == [RoleEnum.SUPERADMIN, RoleEnum.ADMIN]

    def test_role_values_match_expected_strings(self):
        """[CT] Each RoleEnum member has the expected string value.

        WHY: Keycloak sends role names as strings. If someone renames
        an enum value, claim extraction silently breaks. This locks
        the string<->enum mapping.
        """
        assert RoleEnum.SUPERADMIN.value == "superadmin"
        assert RoleEnum.ADMIN.value == "admin"
        assert RoleEnum.COLLAB.value == "collaborator"
        assert RoleEnum.USER.value == "user"


# ---------------------------------------------------------------------------
# TokenResponse
# ---------------------------------------------------------------------------


class TestTokenResponse:
    """TokenResponse model — OAuth token structure.

    WHY: This model is the contract between our backend and the frontend.
    We verify the token_type default and required fields.
    """

    def test_valid_token_response_creation(self):
        """[HP] TokenResponse accepts valid access/refresh tokens."""
        token = TokenResponse(
            access_token="abc",
            refresh_token="def",
            expires_in=300,
        )

        assert token.access_token == "abc"
        assert token.refresh_token == "def"
        assert token.expires_in == 300

    def test_default_token_type_is_bearer(self):
        """[HP] token_type defaults to 'Bearer' when not specified."""
        token = TokenResponse(
            access_token="abc",
            refresh_token="def",
            expires_in=300,
        )

        assert token.token_type == "Bearer"

    def test_missing_access_token_raises_validation_error(self):
        """[EC] access_token is required — omitting it fails validation."""
        with pytest.raises(ValidationError):
            TokenResponse(refresh_token="def", expires_in=300)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUser:
    """User model validation, computed properties, and role methods.

    WHY: User is the domain identity object. All authorization decisions
    flow through has_role/has_any_role/is_staff. We must verify:
    1. Pydantic constraints are correctly configured (not that Pydantic works)
    2. Computed properties behave correctly at boundaries
    3. Role-checking methods handle both enum and string inputs
    """

    # --- Construction / Validation ---

    def test_valid_user_creation(self):
        """[HP] User with all valid fields is created successfully."""
        user = _make_user(
            email="a@b.com",
            email_verified=True,
            first_name="Test",
            last_name="User",
        )

        assert user.id == "e37e9825-ac1c-4bd3-8380-579af43eac48"
        assert user.username == "test_user"
        assert user.email == "a@b.com"
        assert user.email_verified is True
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.roles == [RoleEnum.USER]

    def test_username_rejects_whitespace(self):
        """[EC] Whitespace is rejected: it breaks log parsing and headers."""
        for bad in ("bad name", "leading ", " trailing"):
            with pytest.raises(ValidationError):
                _make_user(username=bad)

    def test_username_rejects_control_characters(self):
        r"""[SEC] Newline, tab, NUL, CR and DEL are rejected.

        WHY: username ends up in the output of structlog and in API responses.
        A preferred_username such as "evil\nlevel=error" would forge a log
        line, and a \r\n in a header is response splitting.
        """
        for bad in ("evil\nadmin", "a\tb", "cr\rlf", "nul\x00byte", "del\x7f"):
            with pytest.raises(ValidationError):
                _make_user(username=bad)

    def test_username_accepts_email_form(self):
        """[HP] An email as username is accepted.

        WHY: a regression. Keycloak issues the email as preferred_username as
        soon as "Email as username" is on. The previous pattern
        (^[a-zA-Z0-9_-]+$) turned every login of those realms into a 500.
        """
        user = _make_user(username="mario.rossi@example.com")

        assert user.username == "mario.rossi@example.com"

    def test_username_accepts_non_ascii(self):
        """[EC] Non-ASCII usernames are valid: Keycloak allows them."""
        user = _make_user(username="José")

        assert user.username == "José"

    def test_username_length_boundaries(self):
        """[EC] Empty refused, 1 character accepted, 255 accepted, 256 refused.

        WHY: the limit is 255, as for id: the most Keycloak itself allows. The
        old limit of 50 was arbitrary.
        """
        with pytest.raises(ValidationError):
            _make_user(username="")

        assert _make_user(username="a").username == "a"
        assert _make_user(username="u" * 255).username == "u" * 255

        with pytest.raises(ValidationError):
            _make_user(username="u" * 256)

    def test_email_optional_accepts_none(self):
        """[HP] email=None is valid (field is optional)."""
        user = _make_user(email=None)

        assert user.email is None

    def test_email_accepts_addresses_a_strict_validator_refuses(self):
        """[HP] Reserved domains pass: Keycloak already validated the address.

        WHY: EmailStr refused special-use domains such as .local, so
        mario@azienda.local could never log in (measured 16 October 2026).
        """
        for address in ("mario@azienda.local", "ops@intranet.test"):
            assert _make_user(email=address).email == address

    def test_email_format_is_not_checked(self):
        """[EC] No format check: the IdP owns what an email address is.

        WHY: deliberate. Here only what can harm logs and responses is
        refused, as for username.
        """
        assert _make_user(email="not-an-email").email == "not-an-email"

    def test_email_rejects_control_characters(self):
        """[SEC] Newline, tab, CR, NUL and DEL in the email are rejected."""
        for bad in (
            "a@b.com\nlevel=error",
            "a\t@b.com",
            "a@b.com\r",
            "a\x00@b.com",
            "a\x7f@b.com",
        ):
            with pytest.raises(ValidationError):
                _make_user(email=bad)

    def test_email_length_boundaries(self):
        """[EC] Empty rejected, 320 accepted, 321 rejected (64 + '@' + 255)."""
        with pytest.raises(ValidationError):
            _make_user(email="")

        longest = "a" * 310 + "@example.c"
        assert len(longest) == 320
        assert _make_user(email=longest).email == longest

        with pytest.raises(ValidationError):
            _make_user(email="a" + longest)

    def test_names_up_to_255_characters_accepted(self):
        """[EC] 255 accepted, 256 rejected — the limit Keycloak itself applies.

        WHY: the old limit was 100. A given_name of 120 characters, accepted
        by Keycloak, made every login of that user fail with 401.
        """
        for field in ("first_name", "last_name"):
            assert getattr(_make_user(**{field: "n" * 255}), field) == "n" * 255

            with pytest.raises(ValidationError):
                _make_user(**{field: "n" * 256})

    def test_names_reject_control_characters(self):
        """[SEC] Control characters in names are rejected, as in username."""
        for field in ("first_name", "last_name"):
            for bad in ("Mario\nRossi", "Ma\x00rio", "Mario\x7f"):
                with pytest.raises(ValidationError):
                    _make_user(**{field: bad})

    def test_names_accept_spaces_and_non_ascii(self):
        """[HP] Spaces, apostrophes and accents are part of real names."""
        user = _make_user(first_name="Maria Grazia", last_name="D'Angelo Žák")

        assert user.full_name == "Maria Grazia D'Angelo Žák"

    def test_id_min_length_rejects_empty(self):
        """[EC] Empty string for id is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            _make_user(id="")

    # --- Computed properties ---

    def test_full_name_both_names(self):
        """[HP] full_name returns 'First Last' when both present."""
        user = _make_user(first_name="Alice", last_name="Smith")

        assert user.full_name == "Alice Smith"

    def test_full_name_first_only(self):
        """[EC] full_name returns first_name when last_name is None."""
        user = _make_user(first_name="Alice", last_name=None)

        assert user.full_name == "Alice"

    def test_full_name_last_only(self):
        """[EC] full_name returns last_name when first_name is None."""
        user = _make_user(first_name=None, last_name="Smith")

        assert user.full_name == "Smith"

    def test_full_name_none_when_no_names(self):
        """[EC] full_name returns None when both names are None."""
        user = _make_user(first_name=None, last_name=None)

        assert user.full_name is None

    # --- Role methods ---

    def test_has_role_with_enum_true(self):
        """[HP] has_role(RoleEnum.USER) returns True when user has role."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_role(RoleEnum.USER) is True

    def test_has_role_with_enum_false(self):
        """[EC] has_role(RoleEnum.ADMIN) returns False when user lacks role."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_role(RoleEnum.ADMIN) is False

    def test_has_role_with_string(self):
        """[HP] has_role('user') works with string value."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_role("user") is True

    def test_has_role_unknown_string_is_false(self):
        """[EC] has_role("manager") -> False, not ValueError.

        WHY: a role that does not exist is a role the user does not have.
        Before, RoleEnum("manager") raised ValueError: a 500 inside a route.
        """
        user = _make_user(roles=[RoleEnum.ADMIN])

        assert user.has_role("manager") is False

    def test_has_any_role_skips_unknown_strings(self):
        """[EC] has_any_role(["manager", "admin"]) -> True for an admin."""
        user = _make_user(roles=[RoleEnum.ADMIN])

        assert user.has_any_role(["manager", "admin"]) is True

    def test_has_all_roles_unknown_string_is_false(self):
        """[EC] has_all_roles(["admin", "manager"]) -> False, not ValueError."""
        user = _make_user(roles=[RoleEnum.ADMIN])

        assert user.has_all_roles(["admin", "manager"]) is False

    def test_has_any_role_true_partial_match(self):
        """[HP] has_any_role returns True if user has at least one."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_any_role([RoleEnum.ADMIN, RoleEnum.USER]) is True

    def test_has_any_role_false_no_match(self):
        """[EC] has_any_role returns False if user has none."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_any_role([RoleEnum.ADMIN, RoleEnum.SUPERADMIN]) is False

    def test_has_all_roles_true(self):
        """[HP] has_all_roles returns True when user has all requested."""
        user = _make_user(roles=[RoleEnum.ADMIN, RoleEnum.USER])

        assert user.has_all_roles([RoleEnum.ADMIN, RoleEnum.USER]) is True

    def test_has_all_roles_false_partial(self):
        """[EC] has_all_roles returns False when user has only some."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.has_all_roles([RoleEnum.ADMIN, RoleEnum.USER]) is False

    def test_is_staff_true_for_admin(self):
        """[HP] is_staff returns True for ADMIN role."""
        user = _make_user(roles=[RoleEnum.ADMIN])

        assert user.is_staff() is True

    def test_is_staff_true_for_superadmin(self):
        """[HP] is_staff returns True for SUPERADMIN role."""
        user = _make_user(roles=[RoleEnum.SUPERADMIN])

        assert user.is_staff() is True

    def test_is_staff_false_for_user(self):
        """[EC] is_staff returns False for USER-only role."""
        user = _make_user(roles=[RoleEnum.USER])

        assert user.is_staff() is False

    def test_is_staff_false_for_collaborator(self):
        """[EC] is_staff returns False for COLLAB-only role."""
        user = _make_user(roles=[RoleEnum.COLLAB])

        assert user.is_staff() is False
