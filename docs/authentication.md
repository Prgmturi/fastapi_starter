# Authentication

How a user logs in, how the API checks a token, and how a route asks for a role. The frontend's side of the login is in [frontend.md](frontend.md).

## The routes

```
GET  /auth/login    → the address of Keycloak's login page, for PKCE
POST /auth/token    → exchanges the code for tokens; the refresh token goes into an HttpOnly cookie
POST /auth/refresh  → a new access token, from the cookie
POST /auth/logout   → ends the session in Keycloak and clears the cookie
GET  /auth/me       → the user of the bearer token
```

- `/auth/token` and `/auth/refresh` answer with `Cache-Control: no-store`, so no browser or proxy keeps the access token.
- `/auth/refresh` and `/auth/logout` use the cookie, which the browser sends by itself. So a request whose `Origin` is not in `SERVER_CORS_ORIGINS` gets 403 before Keycloak is called. List your frontend there even when a proxy serves it on the same origin as the API. A request without `Origin`, such as one from curl or a mobile app, passes.

## How a token is checked

The API checks every access token itself, with the public keys of the realm: no call to Keycloak for each request.

- `JWKSManager` keeps the keys in a cache for `KEYCLOAK_JWKS_CACHE_TTL` seconds. A token signed with a key it does not know, as after a key rotation, makes it fetch them again: one request at a time, and at most once every `KEYCLOAK_JWKS_MIN_REFRESH_INTERVAL` seconds (30 by default).
- If Keycloak is unreachable, the keys in the cache keep working. A token whose key is not cached gets 503, so the frontend retries instead of logging the user out.
- The API accepts only access tokens (`typ: Bearer`) issued to `KEYCLOAK_CLIENT_ID`, or to a client listed in `KEYCLOAK_ALLOWED_CLIENTS` (`azp`). ID tokens, refresh tokens and the tokens of other clients of the realm get 401, even though Keycloak signs them with the same keys.
- Up to 30 seconds of difference between the clocks of the API and Keycloak are tolerated.
- The API fetches the keys when it starts, so it does not start while Keycloak is down.

## The redirect URIs

Set `KEYCLOAK_ALLOWED_REDIRECT_URIS` to the callback URLs of the frontend, as a JSON list. `/auth/login` and `/auth/token` then refuse any other `redirect_uri` with 422.

Why: Keycloak sends the authorization code to that address, and a pattern in Keycloak's *Valid redirect URIs*, such as `http://localhost:*`, lets any port through. The comparison is exact, so `http://localhost:3000/callback/` is another URI. Unset, only Keycloak checks.

## The refresh cookie

The refresh token travels only in its HttpOnly cookie, which JavaScript cannot read. The cookie is set by the `AUTH_COOKIE_*` settings:

| Setting | Default | |
|---|---|---|
| `AUTH_COOKIE_NAME` | `__Host-rt` | The `__Host-` prefix makes the browser accept the cookie only with `Secure` and `Path=/` |
| `AUTH_COOKIE_SECURE` | `true` | Production refuses `false` |
| `AUTH_COOKIE_SAMESITE` | `lax` | `none` for a frontend on another site ([frontend.md](frontend.md)) |
| `AUTH_COOKIE_PATH` | `/` | |

- The app refuses to start with a `__Host-` name that breaks its rules.
- Over plain http, in development, use another name and `AUTH_COOKIE_SECURE=false`, as `.env.example` does.
- Before 0.8.0 these settings were `KEYCLOAK_COOKIE_*`. The app refuses to start while one of those names is set, and names the new one.

## Keycloak in development

On its first start, the `keycloak` service of `compose.yaml` imports the realm of `docker/keycloak/realm-dev.json`:

- the realm `fastapi-starter`, with the roles `superadmin`, `admin`, `collaborator` and `user`;
- the client `fastapi-backend`: confidential, standard flow only, redirect URIs `http://localhost:*`, secret `fastapi-backend-dev-secret`;
- the user `testuser`, password `testuser-dev-password`, role `user`.

These values are public, so the realm is for development only: with `APP_ENVIRONMENT=production` the app refuses that secret.

The console is at http://localhost:8080, user `admin`, password `admin`. Changes made there stay in Keycloak's volume, and a realm that already exists is not imported again. To start again from the file, remove Keycloak's volume: `docker compose down`, then `docker volume rm <project>_keycloak_db_data`, where `<project>` is the name of the folder. The data of the app is in another volume.

### Checking the audience

To have the API check `aud`: in the *Client scopes* tab of the client, open `fastapi-backend-dedicated` and add a mapper of type *Audience*, with *Included Client Audience* `fastapi-backend` and *Add to access token* on. Then set `KEYCLOAK_AUDIENCE=fastapi-backend`.

## Roles

```python
from typing import Annotated

from fastapi import Depends

from fastapi_starter.core.auth.dependencies import (
    AdminUser,
    CollabUser,
    CurrentUser,
    require_roles,
)
from fastapi_starter.core.auth.schemas import RoleEnum, User


# Any user who is logged in
@router.get("/profile")
async def profile(user: CurrentUser): ...


# Admin or superadmin
@router.get("/stats")
async def stats(user: AdminUser): ...


# Collaborator, admin or superadmin
@router.get("/drafts")
async def drafts(user: CollabUser): ...


# Only the roles listed
@router.delete("/users/{id}")
async def delete_user(
    user: Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))],
): ...
```

- Roles form a hierarchy: superadmin > admin > collaborator. `SuperAdminUser`, `AdminUser` and `CollabUser` let through their role and every role above it. `user` is not part of the hierarchy.
- `require_roles` lets through only the roles it lists, and a role that does not exist stops the app at startup.
- A user without the role gets 403 with `"detail": "Permission denied"`. The response does not say which roles were needed.
- A role in the token that `RoleEnum` does not know is skipped. The first time it shows up, the app logs the warning `unknown_role_skipped` with its name, so a role written wrong in Keycloak shows up in the logs, not only as a 403. The roles Keycloak gives every user, `offline_access`, `uma_authorization` and `default-roles-<realm>`, are skipped without a line.
