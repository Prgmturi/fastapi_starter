# 0003. The refresh token travels only in an HttpOnly cookie

Status: accepted. Recorded on 27 October 2026.

## Context

A single-page app needs a token on every call, and a way to get a new one without asking the user to log in again. Whatever JavaScript can read, a script injected into the page can read too.

## Decision

- `/auth/token` and `/auth/refresh` return the access token in the body and set the refresh token in a cookie: `HttpOnly`, so JavaScript cannot read it, never in the body. The frontend keeps the access token in memory.
- The cookie is the app's, not Keycloak's: its settings are `AUTH_COOKIE_*` (`core/config/auth_cookie.py`). By default `__Host-rt`, `Secure`, `SameSite=lax`, `Path=/`; its lifetime is the one Keycloak gives the refresh token. The `__Host-` prefix makes the browser demand `Secure` and `Path=/`, and the app refuses to start with a `__Host-` name that breaks either.
- `/auth/refresh` and `/auth/logout`, which act on the cookie the browser sends by itself, refuse with 403 a request whose `Origin` is not in `SERVER_CORS_ORIGINS`, before reading it.
- `/auth/token` and `/auth/refresh` answer with `Cache-Control: no-store`.

## Consequences

- The frontend calls with `credentials: "include"`, and a reload of the page asks `/auth/refresh` for a new access token.
- `SameSite=lax` needs the frontend and the API on one site. On two sites the cookie needs `SameSite=none` and `Secure`, and it becomes a third-party cookie, which some browsers block (`docs/frontend.md`).
- In development over plain http the cookie needs another name and `AUTH_COOKIE_SECURE=false` (`.env.example`); production refuses `AUTH_COOKIE_SECURE=false`.
