# Operations

What the API says when something goes wrong, how a container shows that it is healthy, what the logs look like, and every setting.

## Errors

Every error response is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document, sent as `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Product with id '3' not found",
  "resource": "Product",
  "identifier": 3
}
```

- `status`, `title` and `detail` are always there. `title` is the standard phrase of the status code; `detail` explains what went wrong in this request.
- An invalid request (422) adds `errors`, one entry for each invalid field: `{"loc": ["query", "limit"], "msg": "Input should be a valid integer, …", "type": "int_parsing"}`. The rejected value is not sent back.
- To return an error from your code, raise a subclass of `AppExceptionError` from `core/exceptions.py`: `NotFoundError`, `ConflictError`, `ForbiddenError`, `UnauthorizedError`, and the others. Its `details` become extra members, like `resource` and `identifier` above.
- OpenAPI documents this format as the `default` response of every route.
- An unexpected error answers only `"An unexpected error occurred."`. The cause and the traceback go to the logs, also with `APP_DEBUG=true`.
- Every response has an `X-Request-ID` header, a 500 from a route included, and the log lines of that request carry the same id. The exception is a 500 caused by a bug in a middleware: Starlette answers it outside every middleware, so it has none of their headers, and only its log lines carry the id.

## Health checks

- `GET /health/live` answers 200 while the process runs. Docker's `HEALTHCHECK` calls it with `python -m fastapi_starter.healthcheck`, which sends the first entry of `SERVER_TRUSTED_HOSTS` as `Host`, on the port `SERVER_PORT`. So the probe passes the same host check as the real requests, on the port the image's command listens on.
- `GET /health/ready` answers 200 when the instance can serve requests, and 503 when a check fails. The body is a status report, not a problem document, and gives only the status of each check: `{"status": "unhealthy", "checks": {"database": {"status": "unhealthy"}, "auth": {"status": "healthy"}}}`. The route needs no token, so the cause goes to the logs only, as `readiness_check_failed`. A check that takes more than 2 seconds counts as failed.
- The auth check does not call Keycloak: it passes while the signing keys are cached. If Keycloak goes down, the instances keep checking tokens with those keys, and stay ready.

## Logs

Every line the process writes has one format: JSON outside development, with the timestamp, the level and the fields of the service (`service`, `version`, `environment`), and colored columns in development. The lines of uvicorn, SQLAlchemy and httpx go through the same formatter, with the name of their logger in `logger`. A traceback stays inside its line, in `exception`. `APP_LOG_LEVEL` applies to all of them.

- **Request id.** Every request has an id, in all its log lines (`request_id`) and in the `X-Request-ID` response header. A request that arrives with an `X-Request-ID` of up to 64 letters, digits, `.`, `_` or `-` keeps it, so the log of the proxy and the log of the app share the id. Any other value is replaced with a new one.
- **The proxy sets the id.** It must write the header itself, over the client's, or the client picks the id. With Nginx: `proxy_set_header X-Request-ID $request_id;`, and `$request_id` in its `log_format`. CORS exposes the header, so a frontend on another origin can read it, for example to show it with an error.
- **Who made the request.** `request_started` names the client, with `client_ip` and `user_agent`. The query string is not logged, because it can hold personal data or tokens.
- **Health probes are quiet.** The lines of the requests to `/health/...` are DEBUG, since Docker's `HEALTHCHECK` alone would write two lines every 30 seconds.
- **Behind a proxy.** uvicorn takes the client's address from `X-Forwarded-For` only on connections from an address in `SERVER_FORWARDED_ALLOW_IPS`, by default `["127.0.0.1"]`. In a container the proxy has another address: set it to that address, or to its network (`["172.18.0.0/16"]`), or `client_ip` is always the proxy's. Never `*` while the port can be reached without the proxy: anyone could choose the address the logs show, and production refuses it. The image's command passes the setting to uvicorn; the uvicorn command of development reads uvicorn's own `FORWARDED_ALLOW_IPS` variable instead.
- **No access line.** uvicorn's access line is off: `request_completed` says the same, with the request id and the duration, and the access line also carries the query string. To have it back, delete the line that sets `uvicorn.access` to `WARNING` in `core/logging/config.py`.
- **More processes.** With `--workers` or `--reload`, the parent process of uvicorn never calls the app factory, so its few lines, at start and stop, keep uvicorn's format. The image runs one process unless `SERVER_WORKERS` says otherwise: to scale, run more containers.

## Settings

The app reads its settings from environment variables, and from `.env` in the root of the repository. `.env.example` lists them all, each with a comment. In the code they are split by subject, in `core/config/`: `AppSettings` (`APP_*`), `DatabaseSettings` (`DATABASE_*`), `KeycloakSettings` (`KEYCLOAK_*`), `AuthCookieSettings` (`AUTH_COOKIE_*`) and `ServerSettings` (`SERVER_*`), gathered in `Settings`. `compose.yaml` reads from `.env` only the ports and the credentials of the database; the `api` service gets the rest of its settings in `compose.yaml` itself.

There are two Postgres in `compose.yaml`: `db`, the app's, on `DATABASE_PORT` (5433), and `keycloak-db`, reachable only inside the stack.

The variables you are most likely to change:

```bash
APP_ENVIRONMENT=development        # development | staging | production
APP_LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR | CRITICAL, any case
DATABASE_PORT=5433
DATABASE_COMMAND_TIMEOUT=30        # seconds for each query; a slower one answers 500
KEYCLOAK_CLIENT_SECRET=...         # required
KEYCLOAK_PUBLIC_URL=               # production: the address the browser sees, = KC_HOSTNAME
SERVER_CORS_ORIGINS=["http://localhost:3000"]
SERVER_MAX_BODY_SIZE=65536         # bytes; a larger request body gets 413
SERVER_PORT=8000                   # the image listens and probes here
SERVER_TIMEOUT_GRACEFUL_SHUTDOWN=5 # seconds open requests get at shutdown, below docker stop's 10
SERVER_FORWARDED_ALLOW_IPS=["127.0.0.1"]  # the proxy, behind one: see Logs
```

- **The image's command.** It is `python -m fastapi_starter.serve`, which runs uvicorn with the `SERVER_*` settings: host, port, workers, keep-alive, the shutdown time and the trusted proxies. Another command replaces it whole, as for the migrations: `docker run <image> alembic upgrade head`.
- **The documentation pages.** `/docs`, `/redoc` and `/openapi.json` exist only with `APP_ENVIRONMENT=development`.
- **Production refuses development values.** With `APP_ENVIRONMENT=production` the app refuses to start while one of these is left: `APP_DEBUG=true`, the public address of Keycloak on http, an empty or example `KEYCLOAK_CLIENT_SECRET`, `AUTH_COOKIE_SECURE=false`, no `KEYCLOAK_ALLOWED_REDIRECT_URIS`, the default or example `DATABASE_PASSWORD`, `DATABASE_ECHO=true`, `*` in `SERVER_CORS_ORIGINS`, `SERVER_TRUSTED_HOSTS` or `SERVER_FORWARDED_ALLOW_IPS`, or only localhost in `SERVER_TRUSTED_HOSTS`. The error lists every variable to change at once, without their values. The checks are in `core/config/production.py`.
- **Bounds in every environment.** The pool settings and the database timeouts have bounds, and a value out of range stops the startup ([the database guide](database.md#the-connection-pool)).
- **Errors show no values.** A setting that fails its check stops the startup with an error that names the field and the reason, without printing the values of `.env`.
