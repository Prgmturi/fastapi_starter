"""Tests for KeycloakClaimExtractor — claim parsing and role mapping.

Module under test: src/fastapi_starter/core/auth/extractors.py
Layer: Core logic (no mocks needed — pure transformation from dict to User)

WHY these tests exist: KeycloakClaimExtractor is the Keycloak-specific adapter
for the ClaimExtractor protocol. It translates Keycloak's JWT claim structure
into our domain User. If this breaks, authentication silently fails or grants
wrong roles.
"""

import pytest


class TestExtractUser:
    """KeycloakClaimExtractor.extract_user() — claim-to-User mapping.

    WHY: This is the single point where provider-specific JWT structure
    is translated into domain objects. Every claim field mapping must
    be verified because Keycloak's JWT structure is an external contract
    we cannot control.
    """

    def test_full_claims_maps_all_fields(self):
        """[HP] All Keycloak claims are correctly mapped to User fields."""
        pytest.skip("Not implemented yet")

    def test_minimal_claims_uses_defaults(self):
        """[HP] Only sub/exp/iat/iss required — optional fields get defaults."""
        pytest.skip("Not implemented yet")

    def test_missing_username_falls_back_to_sub(self):
        """[EC] When preferred_username is None, User.username = sub."""
        pytest.skip("Not implemented yet")

    def test_invalid_claims_missing_sub_raises_unauthorized(self):
        """[EC] Claims without 'sub' raise UnauthorizedError.

        WHY: We must verify that Pydantic validation of TokenPayload
        is caught and re-raised as UnauthorizedError (domain exception),
        not leaked as PydanticValidationError.
        """
        pytest.skip("Not implemented yet")

    def test_empty_claims_raises_unauthorized(self):
        """[EC] Empty dict raises UnauthorizedError."""
        pytest.skip("Not implemented yet")

    def test_claims_with_wrong_types_raises_unauthorized(self):
        """[EC] Claims with wrong types (e.g., sub=123) raises UnauthorizedError."""
        pytest.skip("Not implemented yet")


class TestCollectRoles:
    """Role collection from realm_access and resource_access.

    WHY: Keycloak stores roles in two places (realm-level and client-level).
    We must verify both sources are merged, duplicates removed, and
    unknown roles (from Keycloak defaults like 'uma_authorization') are
    silently skipped.
    """

    def test_realm_roles_collected(self):
        """[HP] Roles from realm_access.roles are included."""
        pytest.skip("Not implemented yet")

    def test_client_roles_collected(self):
        """[HP] Roles from resource_access[client_id].roles are included."""
        pytest.skip("Not implemented yet")

    def test_roles_deduped_across_realm_and_client(self):
        """[EC] Same role in both realm and client appears once."""
        pytest.skip("Not implemented yet")

    def test_unknown_roles_silently_skipped(self):
        """[EC] Keycloak default roles (e.g., 'uma_authorization') are ignored.

        WHY: Keycloak adds roles we do not define in RoleEnum. The extractor
        must skip them without raising, so new Keycloak roles do not break auth.
        """
        pytest.skip("Not implemented yet")

    def test_no_roles_returns_empty_list(self):
        """[EC] No realm_access, no resource_access -> empty roles list."""
        pytest.skip("Not implemented yet")

    def test_no_realm_access_key(self):
        """[EC] realm_access is None — only client roles collected."""
        pytest.skip("Not implemented yet")

    def test_no_resource_access_key(self):
        """[EC] resource_access is None — only realm roles collected."""
        pytest.skip("Not implemented yet")

    def test_wrong_client_id_skips_client_roles(self):
        """[EC] resource_access has different client_id — those roles ignored."""
        pytest.skip("Not implemented yet")


class TestClaimExtractorProtocol:
    """Contract test: KeycloakClaimExtractor satisfies ClaimExtractor.

    WHY: The hexagonal architecture depends on structural typing.
    If someone renames extract_user or changes its signature,
    AuthService breaks at runtime. This test catches it at test time.
    """

    def test_implements_claim_extractor_protocol(self):
        """[CT] isinstance(extractor, ClaimExtractor) is True."""
        pytest.skip("Not implemented yet")
