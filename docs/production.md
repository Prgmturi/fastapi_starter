# Production

The stack of `compose.yaml` on one server, with `compose.prod.yaml` over it:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

What you need:

- a server with Docker and Docker Compose 2.24 or later (`compose.prod.yaml` uses the `!reset` and `!override` tags);
- two DNS names pointing at it, one for the API and one for Keycloak (here `api.example.com` and `auth.example.com`), and their certificates, for example from certbot;
- Nginx on the server, with `docs/nginx.conf`;
- the image of a release, `ghcr.io/prgmturi/fastapi_starter:<version>`: the version is the one in `compose.prod.yaml`. The release workflow creates the package with the visibility of the repository, so a public repository gives a public image. From a private repository, log the server in to `ghcr.io` with a token that can read packages.

`compose.prod.yaml` changes what a server needs, and nothing else:

| | `compose.yaml` (development) | with `compose.prod.yaml` |
|---|---|---|
| API and migrations | built from `docker/Dockerfile` | the image of the release |
| Passwords and secrets | development values in the file | from the server's `.env`; compose stops while one is missing |
| Keycloak | `start-dev`, the realm of `docker/keycloak/realm-dev.json` | `start`, HTTP behind the TLS proxy, no realm imported |
| Ports | open on every interface | API and Keycloak on `127.0.0.1`, for the proxy; the databases on none |
| Console of Keycloak | on the public address | on `127.0.0.1` only (`KC_HOSTNAME_ADMIN`) |
| Logs | Docker's default, never rotated | 5 files of 10 MB per container |

## The server's .env

In the folder of the repository, next to `compose.yaml`. Compose reads it, and passes to the containers only what the compose files name.

```bash
# Required: compose refuses to start without them
DATABASE_PASSWORD=...              # the app's Postgres, set when its volume is created
KEYCLOAK_DB_PASSWORD=...           # Keycloak's Postgres
KEYCLOAK_ADMIN_USER=...            # Keycloak's temporary administrator, for the first start
KEYCLOAK_ADMIN_PASSWORD=...
KEYCLOAK_PUBLIC_URL=https://auth.example.com
KEYCLOAK_CLIENT_SECRET=...         # from Keycloak, after the first start (below)
KEYCLOAK_ALLOWED_REDIRECT_URIS=["https://app.example.com/callback"]
SERVER_TRUSTED_HOSTS=["api.example.com"]
SERVER_CORS_ORIGINS=["https://app.example.com"]

# Optional
APP_LOG_LEVEL=INFO
KEYCLOAK_AUDIENCE=                 # README, Keycloak
KEYCLOAK_ALLOWED_CLIENTS=[]        # .env.example
STACK_SUBNET=172.30.0.0/24         # change it if the server has a network there
APP_IMAGE=                         # another image than the release in compose.prod.yaml
```

The API also checks its own settings: with `APP_ENVIRONMENT=production`, which `compose.prod.yaml` sets, it refuses to start on a development or example value, and names every variable to change (README, Configuration reference).

Keep the file readable by its owner only: `chmod 600 .env`.

## First start

Keycloak first, because the API fetches the realm's signing keys when it starts:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --wait keycloak
```

The console answers on the server only. From your machine, open a tunnel and log in at http://127.0.0.1:8080/admin/ with `KEYCLOAK_ADMIN_USER` and `KEYCLOAK_ADMIN_PASSWORD`:

```bash
ssh -L 8080:127.0.0.1:8080 you@your-server
```

1. In the realm `master`, create your own administrator (*Users*, *Add user*, then *Credentials* and *Role mapping*: `admin`). Log in with it, and delete the temporary one.
2. Create the realm `fastapi-starter`, and in it the roles `superadmin`, `admin`, `collaborator` and `user`.
3. Create the client `fastapi-backend`: *Client authentication* on, *Standard flow* only, *Valid redirect URIs* the frontend's callback URLs, exactly as in `KEYCLOAK_ALLOWED_REDIRECT_URIS`.
4. In *Realm settings*, *Security defenses*, turn on *Brute force detection*.
5. Copy the client's secret (*Clients*, `fastapi-backend`, *Credentials*) into `.env` as `KEYCLOAK_CLIENT_SECRET`.
6. Create the users, with their roles.

Do not import `docker/keycloak/realm-dev.json`: its user, password and secret are public.

Then the rest of the stack: the migrations run, and the API starts after them.

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --wait
curl -H "Host: api.example.com" http://127.0.0.1:8000/health/ready
```

## The proxy

`docs/nginx.conf` goes in `/etc/nginx/conf.d/`, with your names and certificate paths. It:

- redirects HTTP to HTTPS, and ends TLS for both names;
- sends the API `X-Request-ID` (Nginx's `$request_id`, so its log and the app's share the id) and `X-Forwarded-For`, which uvicorn trusts only from the stack's network;
- serves only `/realms/` and `/resources/` of Keycloak, as Keycloak advises: not the realm `master`, the console, nor the management port;
- limits requests per address on `/auth/` of the API (30 a minute, bursts of 30) and on Keycloak's login form (10 a minute), with 429 for the excess;
- refuses bodies over 64 KiB, as the API does (`SERVER_MAX_BODY_SIZE`).

## A new release

Change the version in the two `image:` lines of `compose.prod.yaml` (the release's own `compose.prod.yaml` already names it), then:

```bash
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d --wait
```

The migrations run before the new API starts. The old API gets `SERVER_TIMEOUT_GRACEFUL_SHUTDOWN` seconds (5) to finish its open requests.

## Backups

The data lives in two volumes, `<project>_db_data` and `<project>_keycloak_db_data`. Dump both databases on a schedule, and keep the dumps off the server:

```bash
docker compose -f compose.yaml -f compose.prod.yaml exec -T db pg_dump -U appbase appbase > app.sql
docker compose -f compose.yaml -f compose.prod.yaml exec -T keycloak-db pg_dump -U keycloak keycloak > keycloak.sql
```

`docker compose down -v` deletes both volumes: never on the server.
