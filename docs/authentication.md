# Authentication

How a user logs in, how the API knows who is calling, and how a route asks for a role. The frontend's side of the login is in [frontend.md](frontend.md).

## The idea

Users do not log in on the API. They log in on **Keycloak**, a separate server that keeps the users, their passwords and their roles. The API never sees a password.

After a login, Keycloak hands out two **tokens**, long strings that the frontend keeps:

- The **access token** says who the user is and which roles they have, and carries Keycloak's signature. It is valid for a few minutes, five unless the realm says otherwise, and the frontend sends it with every call.
- The **refresh token** lasts longer. It serves only to get a new access token when the old one expires.

The API checks the signature of the access token by itself, with Keycloak's public keys. Only Keycloak holds the private key that makes a signature, so no one else can write a token that passes. A normal request never calls Keycloak.

## A login, step by step

| Step | What happens | Route |
|---|---|---|
| 1 | The frontend asks the API for the address of Keycloak's login page, and sends the user there | `GET /auth/login` |
| 2 | The user types the password on Keycloak's page, never in the frontend. Keycloak sends the browser back to the frontend with a code, which works once and only for a short time | |
| 3 | The frontend gives the code to the API, which trades it with Keycloak for the two tokens. The API returns the access token, and puts the refresh token in a cookie | `POST /auth/token` |
| 4 | The frontend calls the API with the access token, in the header `Authorization: Bearer <token>`. The API checks it by itself | Every route that asks for a user |
| 5 | The access token expires, and the frontend asks for a new one. The browser sends the cookie by itself, and the API gets new tokens from Keycloak | `POST /auth/refresh` |
| 6 | The user logs out: the API asks Keycloak to end the session, and clears the cookie | `POST /auth/logout` |

`GET /auth/me` returns the user of the access token it receives.

Why the API stands between the frontend and Keycloak:

- **The secret stays on the server.** Keycloak trades a code for tokens only with the secret of the client, `KEYCLOAK_CLIENT_SECRET`, and only the API has it.
- **JavaScript never sees the refresh token.** It lives in an `HttpOnly` cookie, which scripts cannot read: a script injected into the page cannot steal it.
- **A stolen code is useless.** Before step 1 the frontend makes a random secret, the *code verifier*, and sends only its hash, the *code challenge*. At step 3 it sends the verifier, and Keycloak checks that the two match. This is PKCE. How the frontend makes the two values: [frontend.md](frontend.md#1-start-the-login).

## Words

| Word | What it means |
|---|---|
| Realm | A space in Keycloak with its own users, roles and clients. The stack's realm is `fastapi-starter` |
| Client | An app registered in the realm, which may ask Keycloak for logins. Here it is `fastapi-backend`, the API |
| JWT | The format of the access token: a small JSON object and its signature, encoded as text |
| Claim | A field of the token: `sub` is the user's id, `exp` the expiry, `iss` who issued it, `azp` the client it was issued to |
| JWKS | The public keys of the realm, which Keycloak publishes so that anyone can check its signatures |

## Where the code is

| Where | What it does | Does it know Keycloak? |
|---|---|---|
| `features/auth/router.py` | The routes of `/auth` | Only one of its settings: the allowed redirect URIs |
| `core/auth/` | The ports, `AuthService`, `CurrentUser` and the role checks, the refresh cookie, the check of `Origin` | No |
| `adapters/keycloak/` | `KeycloakClient`: the address of the login page, the tokens, the logout. `JWKSManager`: the public keys. `JWKSTokenDecoder`: the check of a token. `KeycloakClaimExtractor`: from the claims to a `User` | Yes: all the code that talks to it is here |
| `bootstrap.py` | Builds the adapters, and hands them to the app behind their ports | Yes, to build the adapters |

What runs before a route that asks for `CurrentUser`:

```
CurrentUser                     core/auth/dependencies.py   takes the token from "Authorization: Bearer"
└─ AuthService.validate_token   core/auth/service.py        knows only its two ports
   ├─ port TokenDecoder         the adapter JWKSTokenDecoder (adapters/keycloak/jwks.py):
   │                            checks the signature and the claims
   └─ port ClaimExtractor       the adapter KeycloakClaimExtractor (adapters/keycloak/extractors.py):
                                turns the claims into a User, with its roles
```

So `core/auth/` stays the same with another identity provider: it takes new adapters ([architecture.md](architecture.md#another-identity-provider)).

## How a token is checked

When the API starts, it downloads the public keys of the realm, and keeps them for an hour (`KEYCLOAK_JWKS_CACHE_TTL`, in seconds). Then it checks every access token:

| The API checks | So that |
|---|---|
| The signature, with the key named in the token (`kid`) | A token changed by someone, or made by another server, gets 401 |
| That `exp`, `iat`, `iss` and `sub` are there, and that `exp` has not passed | An expired token gets 401. Up to 30 seconds of difference between the clocks of the API and Keycloak are tolerated |
| That `iss` is the realm, at Keycloak's public address | A token of another realm, or of another Keycloak, gets 401 |
| That `typ` is `Bearer`, the type of an access token | ID tokens and refresh tokens get 401, though Keycloak signs them with the same keys |
| That `azp` is `KEYCLOAK_CLIENT_ID`, or one of `KEYCLOAK_ALLOWED_CLIENTS` | The tokens of the other clients of the realm get 401 |
| `aud`, only when `KEYCLOAK_AUDIENCE` is set | [Checking the audience](#checking-the-audience), below |

The 401 tells the client little: `Token expired`, or `Invalid token` for most other failures. The exact reason goes to the logs.

When the keys change, or Keycloak stops:

- **New keys.** Keycloak can change its keys. A token signed with a key the API has not seen makes it download them again: one download at a time, and at most one every `KEYCLOAK_JWKS_MIN_REFRESH_INTERVAL` seconds (30 by default), so tokens with invented keys cannot flood Keycloak with calls.
- **Keycloak down.** The keys already downloaded keep working, so users stay logged in. A token signed with a key the API does not have gets 503, and the frontend tries again later instead of logging the user out. A login or a refresh needs Keycloak, so those fail until it is back.
- **At startup.** The API downloads the keys before it accepts requests, so it does not start while Keycloak is down.

## Two addresses for Keycloak

The API and the browser may reach Keycloak at different addresses, so the settings name two:

| Settings | Used for | In `compose.yaml` |
|---|---|---|
| `KEYCLOAK_SCHEME`, `KEYCLOAK_HOST`, `KEYCLOAK_PORT` | The calls of the API to Keycloak: keys, tokens, logout | `http://keycloak:8080`: inside Docker, the API finds Keycloak by the name of its service |
| `KEYCLOAK_PUBLIC_URL` | The login page the browser is sent to, and the check of `iss` | `http://localhost:8080`, the address the browser reaches |

Keycloak writes its public address, `KC_HOSTNAME`, in every token as `iss`. So `KEYCLOAK_PUBLIC_URL` must be that same address, or every token gets 401. Unset, it is the first address: right when the app runs on the machine, with the values of `.env.example`. In production it is the https address of Keycloak ([production.md](production.md)).

## The routes, in detail

- `/auth/token` and `/auth/refresh` answer with `Cache-Control: no-store`, so no browser or proxy keeps a copy of the access token.
- `/auth/refresh` and `/auth/logout` work with the cookie, and the browser sends it by itself, even when a page of another site makes the request. So they answer 403 to a request whose `Origin` is not in `SERVER_CORS_ORIGINS`, before Keycloak is called. The frontend belongs on that list, even when a proxy serves it on the same origin as the API. A request without `Origin`, such as one from curl or a mobile app, passes.
- `/auth/logout` clears the cookie even when Keycloak does not answer.

## The redirect URIs

At the end of the login, Keycloak sends the browser, with the code, to the `redirect_uri` that the frontend named at step 1. So a login link made by someone else, with an address of theirs, would send them the user's code.

`KEYCLOAK_ALLOWED_REDIRECT_URIS` takes the callback addresses of the frontend, as a JSON list: `/auth/login` and `/auth/token` then refuse any other with 422. The comparison is exact: `http://localhost:3000/callback/`, with a final slash, is another address.

Keycloak checks its own list too, the *Valid redirect URIs* of the client, but a pattern there, such as `http://localhost:*`, lets every port through. Unset, only Keycloak checks. Staging and production refuse to start without the list.

## The refresh cookie

The refresh token never travels in a body, only in an `HttpOnly` cookie, which JavaScript cannot read. The `AUTH_COOKIE_*` settings shape it:

| Setting | Default | |
|---|---|---|
| `AUTH_COOKIE_NAME` | `__Host-rt` | With the `__Host-` prefix the browser accepts the cookie only with `Secure` and `Path=/` |
| `AUTH_COOKIE_SECURE` | `true` | The cookie travels only over https. Staging and production refuse `false` |
| `AUTH_COOKIE_SAMESITE` | `lax` | `none` for a frontend on another site ([frontend.md](frontend.md#cookies-and-origins)) |
| `AUTH_COOKIE_PATH` | `/` | |

- The app refuses to start with a `__Host-` name and `AUTH_COOKIE_SECURE=false`, or a path other than `/`: the browser would drop the cookie, and every refresh would answer 401.
- Over plain http, in development, use a name without the prefix and `AUTH_COOKIE_SECURE=false`, as `.env.example` does.
- Before 0.8.0 these settings were `KEYCLOAK_COOKIE_*`. The app refuses to start while one of those names is set, and names the new one.

## Keycloak in development

On its first start, the `keycloak` service of `compose.yaml` imports the realm of `docker/keycloak/realm-dev.json`:

- the realm `fastapi-starter`, with the roles `superadmin`, `admin`, `collaborator` and `user`;
- the client `fastapi-backend`, with the secret `fastapi-backend-dev-secret`. It is *confidential*: Keycloak gives tokens for a code only with that secret. Users log in only on Keycloak's page, and the redirect URIs it allows are `http://localhost:*`;
- the user `testuser`, password `testuser-dev-password`, role `user`.

These values are public, so the realm is for development only: staging and production refuse that secret.

The console of Keycloak is at http://localhost:8080, user `admin`, password `admin`. Changes made there stay in Keycloak's volume, and a realm that already exists is not imported again. To start again from the file, remove Keycloak's volume: `docker compose down`, then `docker volume rm <project>_keycloak_db_data`, where `<project>` is the name of the folder. The data of the app is in another volume.

### Checking the audience

A token can name the apps it is meant for, in its `aud` claim, the audience. In the realm of the stack Keycloak does not name the API there, so the API does not check `aud` by default: the check on `azp` already refuses the tokens of the other clients. It matters once `KEYCLOAK_ALLOWED_CLIENTS` lists other clients, whose tokens may be meant for other APIs too, and would pass here ([decision record 0002](adr/0002-keycloak.md)).

To check it as well: in the console, open the client `fastapi-backend`, tab *Client scopes*, then `fastapi-backend-dedicated`, and add a mapper of type *Audience*, with *Included Client Audience* `fastapi-backend` and *Add to access token* on. Then set `KEYCLOAK_AUDIENCE=fastapi-backend`. From then on, a token without the API in `aud` gets 401.

## Roles

Keycloak writes the user's roles in the access token: those of the realm, and those of the client `fastapi-backend`. The API reads them into `user.roles`, and a route asks for them:

```python
from typing import Annotated

from fastapi import Depends, status

from fastapi_starter.core.auth.dependencies import (
    AdminUser,
    CollabUser,
    CurrentUser,
    require_roles,
)
from fastapi_starter.core.auth.schemas import RoleEnum, User


# Any user who is logged in
@router.get("/profile")
async def profile(user: CurrentUser) -> ProfileResponse:
    return ProfileResponse(username=user.username)


# Admin or superadmin
@router.get("/admin/profile")
async def admin_profile(user: AdminUser) -> ProfileResponse:
    return ProfileResponse(username=user.username)


# Collaborator, admin or superadmin
@router.get("/staff/profile")
async def staff_profile(user: CollabUser) -> ProfileResponse:
    return ProfileResponse(username=user.username)


# Only the roles listed
@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    user: Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))],
) -> None: ...
```

`ProfileResponse` is the schema of the answer.

- Roles form a hierarchy: superadmin > admin > collaborator. `SuperAdminUser`, `AdminUser` and `CollabUser` let through their role and every role above it. `user` is not part of the hierarchy.
- `require_roles` lets through only the roles it lists. A role that does not exist stops the app at startup.
- A user without the role gets 403 with `"detail": "Permission denied"`. The response does not say which roles were needed.
- To give a user a role: in the console, *Users*, the user, tab *Role mapping*, *Assign role*. The user gets it with the next access token, so after the next refresh.
- A role in the token that `RoleEnum` does not know is skipped. The first time it shows up, the app logs the warning `unknown_role_skipped` with its name, so a role written wrong in Keycloak shows up in the logs, not only as a 403. The roles Keycloak gives every user, `offline_access`, `uma_authorization` and `default-roles-<realm>`, are skipped without a line.
