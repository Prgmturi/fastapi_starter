# 0002. Keycloak as the identity provider, its tokens checked locally

Status: accepted. Recorded on 27 October 2026.

## Context

The API needs logins, roles and tokens without storing passwords itself, and the template must run whole on one machine.

## Decision

- Keycloak runs in the stack (`compose.yaml`). In development it imports the realm of `docker/keycloak/realm-dev.json`; in production the realm is created by hand (`docs/production.md`).
- The API is a confidential client, `fastapi-backend`: it exchanges the authorization code with its secret, which never reaches the browser (ADR 0003, `docs/frontend.md`).
- The API checks every access token itself, with the public keys of the realm: no call to Keycloak per request. `JWKSManager` keeps the keys for `KEYCLOAK_JWKS_CACHE_TTL` seconds, fetches them again for an unknown key id (a key rotation), at most every `KEYCLOAK_JWKS_MIN_REFRESH_INTERVAL` seconds and one fetch at a time.
- `JWKSTokenDecoder` checks the signature, the expiry, the issuer (the public address, `KEYCLOAK_PUBLIC_URL`), `typ: Bearer` and `azp` (`KEYCLOAK_ALLOWED_CLIENTS`). `aud` only with `KEYCLOAK_AUDIENCE`, which needs an audience mapper in Keycloak: decision 5 of the roadmap, left for later.
- The roles of the realm map to `RoleEnum`, with a hierarchy: superadmin > admin > collaborator.

## Consequences

- The API fetches the keys when it starts, so it does not start while Keycloak is down; in compose it waits for Keycloak to be healthy.
- While Keycloak is unreachable, tokens signed with a key in the cache keep working, and a token whose key is not cached gets 503: the frontend retries instead of logging the user out.
- The API reaches Keycloak at an internal address (`KEYCLOAK_SCHEME://KEYCLOAK_HOST:KEYCLOAK_PORT`), and the browser at the public one: two settings, both checked in production.
