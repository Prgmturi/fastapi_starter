# The frontend

How a single-page app logs a user in through the API, calls it, and keeps the user logged in. The API runs the authorization code flow of OAuth 2.0 with PKCE against Keycloak: the browser never sees the client secret, and JavaScript never sees the refresh token.

```
Frontend (browser)                          API                         Keycloak
1. make code_verifier and state
2. GET /auth/login?redirect_uri&code_challenge&state ─▶ builds the URL
   ◀── {"authorization_url": ...}
3. go to authorization_url ──────────────────────────────────────────▶ login page
   ◀──────────────── redirect_uri?code=...&state=... ────────────────────
4. check state, then POST /auth/token ─────▶ exchanges the code ─────▶
   ◀── {"access_token", "expires_in"}, and the refresh token in an HttpOnly cookie
5. GET /notes  Authorization: Bearer <access token>
6. on 401: POST /auth/refresh (the cookie) ─▶ a new access token and a new cookie; repeat the call
7. POST /auth/logout (the cookie) ─▶ Keycloak ends the session, the cookie is cleared
```

## 1. Start the login

- `code_verifier`: 43 to 128 random characters from `A-Z`, `a-z`, `0-9` and `-._~`, from `crypto.getRandomValues`. `code_challenge`: the SHA-256 of the verifier, in base64url without `=` padding; the API asks Keycloak for the `S256` method.
- `state`: another random string. The API hands it to Keycloak, which sends it back with the code: comparing the two refuses a login the frontend did not start.
- Keep both in `sessionStorage` until the callback.
- `GET /auth/login?redirect_uri=...&code_challenge=...&state=...` answers `{"authorization_url": "..."}`: send the browser there.
- `redirect_uri` is the frontend's callback. It must be one of `KEYCLOAK_ALLOWED_REDIRECT_URIS`, compared exactly (when the list is set, any other gets 422), and one of the *Valid redirect URIs* of the client in Keycloak.

## 2. The callback

- Keycloak sends the browser to `redirect_uri?code=...&state=...`. Compare `state` with the one kept, and stop if they differ.
- `POST /auth/token` with the JSON body `{"code", "code_verifier", "redirect_uri"}`, the same `redirect_uri` as in step 1, and `credentials: "include"`, so that the browser keeps the cookie.
- The answer is `{"access_token", "token_type": "Bearer", "expires_in"}`, with the refresh token in an HttpOnly cookie and `Cache-Control: no-store`. Delete `code_verifier` and `state`.

## 3. Call the API

- Keep the access token in memory, in a variable of the app, not in `localStorage` or `sessionStorage`: a script injected into the page could read those.
- Send it as `Authorization: Bearer <access token>`.
- A reload of the page loses it: call `/auth/refresh` when the app starts. A 401 there means that the user is not logged in.

## 4. Keep the user logged in

| Answer | What it means | What the frontend does |
|---|---|---|
| 401 from a route | The access token expired, or is not valid | `POST /auth/refresh` once, then repeat the call. If the refresh answers 401 too, log in again |
| 503 | Keycloak is unreachable, and the API cannot check the key of this token | Keep the user logged in, and try again after a few seconds |
| 403 `Permission denied` | The token is valid, the role is missing | Say so: a refresh does not help |
| 403 `Origin not allowed`, from `/auth/refresh` or `/auth/logout` | The origin of the page is not in `SERVER_CORS_ORIGINS` | A setting of the server to fix |

- `POST /auth/refresh` takes no body, only `credentials: "include"`. It answers with a new access token, and sets a new refresh token in the cookie.
- Send one refresh at a time: when several calls get 401 together, let them wait for the same refresh. If the realm has *Revoke Refresh Token* on, a refresh token works only once: a second refresh with the same token gets 401, and a frontend that reads it as "logged out" sends the user back to the login. The development realm leaves the option off.
- `expires_in` gives the lifetime of the access token in seconds: a refresh shortly before it saves the failed call.

## 5. Log out

`POST /auth/logout` with `credentials: "include"`. The API asks Keycloak to end the session and clears the cookie, even when Keycloak does not answer. Then drop the access token from memory.

## Cookies and origins

- **CORS.** `SERVER_CORS_ORIGINS` lists the origins of the frontend exactly: scheme, host and port. Credentials are allowed (`SERVER_CORS_ALLOW_CREDENTIALS`, true by default). `/auth/refresh` and `/auth/logout` refuse with 403 a request whose `Origin` is not listed, before they read the cookie. List the frontend even when a proxy serves it on the same origin as the API.
- **The cookie** (`AUTH_COOKIE_*`) is by default `__Host-rt`, `Secure`, `SameSite=lax` and `Path=/`.
  - Frontend and API on one site: `app.example.com` and `api.example.com` share the site `example.com`, and so do `localhost:5173` and `localhost:8000`, since the port does not count. `lax` works.
  - On two sites, such as `app.example.com` and `api.example.net`, the browser does not send a `lax` cookie with `fetch`. That takes `AUTH_COOKIE_SAMESITE=none`, which browsers accept only with `Secure`, so over https. Such a cookie is a third-party cookie, which some browsers block (Safari by default): keep the frontend and the API on one site when you can.
  - Over plain http, in development, use the values of `.env.example`: a name without `__Host-` (`rt`) and `AUTH_COOKIE_SECURE=false`. The app refuses to start with a `__Host-` name and no `Secure`.
- **`X-Request-ID`.** Every response has it, and CORS lets JavaScript read it. Show it or log it with an error: the log lines of that request on the server carry the same id.
- **Errors** are problem documents (`application/problem+json`) with `status`, `title` and `detail`. A 422 adds `errors`, one entry for each invalid field (README, Errors).

`tests/e2e/test_login.py` runs this whole flow against the stack, in Python: `pkce_pair` in `tests/e2e/browser.py` makes the two PKCE values.
