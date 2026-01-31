"""Tests for KeycloakClaimExtractor — claim parsing and role mapping.

Module under test: src/fastapi_starter/core/auth/extractors.py
Layer: Core logic (no mocks needed — pure transformation from dict to User)

WHY these tests exist: KeycloakClaimExtractor is the Keycloak-specific adapter
for the ClaimExtractor protocol. It translates Keycloak's JWT claim structure
into our domain User. If this breaks, authentication silently fails or grants
wrong roles.
"""

import pytest

from fastapi_starter.core.auth.extractors import KeycloakClaimExtractor
from fastapi_starter.core.auth.protocols import ClaimExtractor
from fastapi_starter.core.auth.schemas import RoleEnum
from fastapi_starter.core.exceptions import UnauthorizedError

CLIENT_ID = "test-client"


@pytest.fixture
def extractor() -> KeycloakClaimExtractor:
    return KeycloakClaimExtractor(client_id=CLIENT_ID)


class TestExtractUser:
    """KeycloakClaimExtractor.extract_user() — claim-to-User mapping.

    WHY: This is the single point where provider-specific JWT structure
    is translated into domain objects. Every claim field mapping must
    be verified because Keycloak's JWT structure is an external contract
    we cannot control.
    """

    def test_full_claims_maps_all_fields(self, extractor, sample_claims):
        """[HP] All Keycloak claims are correctly mapped to User fields."""
        user = extractor.extract_user(sample_claims)

        assert user.id == sample_claims["sub"]
        assert user.username == sample_claims["preferred_username"]
        assert user.email == sample_claims["email"]
        assert user.email_verified is True
        assert user.first_name == sample_claims["given_name"]
        assert user.last_name == sample_claims["family_name"]

    def test_minimal_claims_uses_defaults(self, extractor, sample_claims_minimal):
        """[HP] Only sub/exp/iat/iss required — optional fields get defaults."""
        user = extractor.extract_user(sample_claims_minimal)

        assert user.id == "minimal-user"
        assert user.username == "minimal-user"  # fallback to sub
        assert user.email is None
        assert user.email_verified is False
        assert user.first_name is None
        assert user.last_name is None
        assert user.roles == []

    def test_missing_username_falls_back_to_sub(self, extractor, sample_claims):
        """[EC] When preferred_username is None, User.username = sub."""
        sample_claims["preferred_username"] = None

        user = extractor.extract_user(sample_claims)

        assert user.username == sample_claims["sub"]

    def test_invalid_claims_missing_sub_raises_unauthorized(self, extractor):
        """[EC] Claims without 'sub' raise UnauthorizedError.

        WHY: We must verify that Pydantic validation of TokenPayload
        is caught and re-raised as UnauthorizedError (domain exception),
        not leaked as PydanticValidationError.
        """
        claims = {"exp": 9999999999, "iat": 1700000000, "iss": "http://test"}

        with pytest.raises(UnauthorizedError):
            extractor.extract_user(claims)

    def test_empty_claims_raises_unauthorized(self, extractor):
        """[EC] Empty dict raises UnauthorizedError."""
        with pytest.raises(UnauthorizedError):
            extractor.extract_user({})

    def test_claims_with_wrong_types_raises_unauthorized(self, extractor):
        """[EC] Claims with wrong types (e.g., sub=123) raises UnauthorizedError."""
        claims = {"sub": 123, "exp": "not-a-number", "iat": 1700000000, "iss": "test"}

        with pytest.raises(UnauthorizedError):
            extractor.extract_user(claims)


class TestCollectRoles:
    """Role collection from realm_access and resource_access.

    WHY: Keycloak stores roles in two places (realm-level and client-level).
    We must verify both sources are merged, duplicates removed, and
    unknown roles (from Keycloak defaults like 'uma_authorization') are
    silently skipped.
    """

    def test_realm_roles_collected(self, extractor, sample_claims):
        """[HP] Roles from realm_access.roles are included."""
        sample_claims["realm_access"] = {"roles": ["admin"]}
        sample_claims["resource_access"] = {}

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.ADMIN in user.roles

    def test_client_roles_collected(self, extractor, sample_claims):
        """[HP] Roles from resource_access[client_id].roles are included."""
        sample_claims["realm_access"] = None
        sample_claims["resource_access"] = {
            CLIENT_ID: {"roles": ["user"]},
        }

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.USER in user.roles

    def test_roles_deduped_across_realm_and_client(self, extractor, sample_claims):
        """[EC] Same role in both realm and client appears once."""
        sample_claims["realm_access"] = {"roles": ["admin", "user"]}
        sample_claims["resource_access"] = {
            CLIENT_ID: {"roles": ["admin"]},
        }

        user = extractor.extract_user(sample_claims)

        admin_count = user.roles.count(RoleEnum.ADMIN)
        assert admin_count == 1

    def test_unknown_roles_silently_skipped(self, extractor, sample_claims):
        """[EC] Keycloak default roles (e.g., 'uma_authorization') are ignored.

        WHY: Keycloak adds roles we do not define in RoleEnum. The extractor
        must skip them without raising, so new Keycloak roles do not break auth.
        """
        sample_claims["realm_access"] = {"roles": ["uma_authorization", "user"]}
        sample_claims["resource_access"] = {}

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.USER in user.roles
        assert len(user.roles) == 1

    def test_no_roles_returns_empty_list(self, extractor, sample_claims_minimal):
        """[EC] No realm_access, no resource_access -> empty roles list."""
        user = extractor.extract_user(sample_claims_minimal)

        assert user.roles == []

    def test_no_realm_access_key(self, extractor, sample_claims):
        """[EC] realm_access is None — only client roles collected."""
        sample_claims["realm_access"] = None
        sample_claims["resource_access"] = {
            CLIENT_ID: {"roles": ["admin"]},
        }

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.ADMIN in user.roles

    def test_no_resource_access_key(self, extractor, sample_claims):
        """[EC] resource_access is None — only realm roles collected."""
        sample_claims["realm_access"] = {"roles": ["user"]}
        sample_claims["resource_access"] = None

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.USER in user.roles

    def test_wrong_client_id_skips_client_roles(self, extractor, sample_claims):
        """[EC] resource_access has different client_id — those roles ignored."""
        sample_claims["realm_access"] = {"roles": ["user"]}
        sample_claims["resource_access"] = {
            "other-client": {"roles": ["admin"]},
        }

        user = extractor.extract_user(sample_claims)

        assert RoleEnum.ADMIN not in user.roles
        assert RoleEnum.USER in user.roles


class TestClaimExtractorProtocol:
    """Contract test: KeycloakClaimExtractor satisfies ClaimExtractor.

    WHY: The hexagonal architecture depends on structural typing.
    If someone renames extract_user or changes its signature,
    AuthService breaks at runtime. This test catches it at test time.
    """

    def test_implements_claim_extractor_protocol(self, extractor):
        """[CT] isinstance(extractor, ClaimExtractor) is True."""
        assert isinstance(extractor, ClaimExtractor)
