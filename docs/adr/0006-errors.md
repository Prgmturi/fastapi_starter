# 0006. One format for errors, and adapters translate the errors of their libraries

Status: accepted. Recorded on 5 November 2026, in place since 0.4.0, and since 0.9.1 for the difference between 502 and 503.

## Context

The API answered errors in three shapes: `{"detail": "..."}` from FastAPI and Starlette, `{"detail": [...]}` for invalid requests, and `{"message", "details"}` for its own exceptions, so a client needed three ways to read an error. A service out of reach had no answer of its own either: a Postgres that refused the connection answered 500, with a traceback of about 190 lines in the log, and a Keycloak that did not answer gave a 502, which the frontend guide did not list.

## Decision

- Every error the app raises leaves as an RFC 9457 problem document (`core/problem_details.py`), with `type`, `title`, `status` and `detail`. OpenAPI documents it as the default response of every route.
- Code raises the exceptions of `core/exceptions.py`, subclasses of `AppExceptionError`. `exception_handlers.py` turns them into the response, and their `details` become extra members.
- An adapter turns every error of its library into one of those exceptions, and a port says which ones it raises: `OAuthProvider` promises `UnauthorizedError`, `ServiceUnavailableError` and `ExternalServiceError`. A route never sees an error of httpx or PyJWT.
- 503, with `Retry-After`, means that a service cannot be reached, and the same request can succeed once it is back. 502 means that the service answered in a way the API cannot use: an unexpected status, or a refusal of the API's own client. A bug is a 500, whose body says only `An unexpected error occurred.`
- `UnhandledExceptionMiddleware` answers that 500 inside the middleware stack, so it keeps the CORS and security headers and `X-Request-ID`.
- A service out of reach writes one log line, with the type of the error and no traceback. An invalid request (422) does not send back the rejected value: a password that is too short would return in the response.

## Consequences

- A client reads every error with the same code, and can tell "try later" from "log in again".
- An adapter has to translate every error of its library. No tool checks it: one it forgets becomes a 500.
- Two answers stay in plain text, because they come from middleware the app does not write: the 400 of `TrustedHostMiddleware` and the 400 of a CORS preflight refused.
- A bug in a middleware is answered outside every middleware, so that 500 has none of their headers.
