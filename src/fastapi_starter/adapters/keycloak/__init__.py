"""The Keycloak adapters.

- client.py: login, token exchange, refresh and logout (OAuthProvider)
- jwks_manager.py: the realm's signing keys, fetched and cached (KeyProvider)
- jwks.py: the checks on an access token, with PyJWT (TokenDecoder)
- extractors.py: the claims of a token mapped to User (ClaimExtractor)

Their settings, KeycloakSettings, stay in core/config: Settings gathers
every section there, and core never imports an adapter.
"""
