"""What production refuses: values meant for development or examples.

Settings runs these checks when APP_ENVIRONMENT=production and lists every
problem in one error. Messages name the variable to change, never its
value.
"""

from fastapi_starter.core.config.app import AppSettings
from fastapi_starter.core.config.auth_cookie import AuthCookieSettings
from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.config.server import ServerSettings

# The code default and the value in .env.example
EXAMPLE_DATABASE_PASSWORDS = {"postgres", "appbase_secret_change_me"}
# Empty by default; the old placeholder of .env.example; the secret of the
# development realm (docker/keycloak/realm-dev.json), public in the repository
EXAMPLE_CLIENT_SECRETS = {"", "your-client-secret-here", "fastapi-backend-dev-secret"}
# The default SERVER_TRUSTED_HOSTS
LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def production_problems(
    app: AppSettings,
    auth_cookie: AuthCookieSettings,
    database: DatabaseSettings,
    keycloak: KeycloakSettings,
    server: ServerSettings,
) -> list[str]:
    """Every development or example value in the settings, one line each."""
    problems = []

    if app.debug:
        problems.append("APP_DEBUG is true")

    if not auth_cookie.secure:
        problems.append("AUTH_COOKIE_SECURE is false")

    if not keycloak.public_server_url.startswith("https://"):
        problems.append(
            "Keycloak's public address is not https: set KEYCLOAK_PUBLIC_URL "
            "(unset, it is KEYCLOAK_SCHEME://KEYCLOAK_HOST:KEYCLOAK_PORT)"
        )
    if keycloak.client_secret.get_secret_value() in EXAMPLE_CLIENT_SECRETS:
        problems.append("KEYCLOAK_CLIENT_SECRET is empty or the example value")
    if not keycloak.allowed_redirect_uris:
        problems.append(
            "KEYCLOAK_ALLOWED_REDIRECT_URIS is empty: list the frontend's callback URLs"
        )

    if database.password.get_secret_value() in EXAMPLE_DATABASE_PASSWORDS:
        problems.append("DATABASE_PASSWORD is the default or the example value")
    if database.echo:
        problems.append(
            "DATABASE_ECHO is true: every query goes to the logs with its values"
        )

    if "*" in server.cors_origins:
        problems.append('SERVER_CORS_ORIGINS contains "*"')
    if "*" in server.trusted_hosts:
        problems.append('SERVER_TRUSTED_HOSTS contains "*": any Host is accepted')
    elif set(server.trusted_hosts) <= LOCAL_HOSTS:
        problems.append(
            "SERVER_TRUSTED_HOSTS lists only localhost: add the API's domain"
        )
    if "*" in server.forwarded_allow_ips:
        problems.append(
            'SERVER_FORWARDED_ALLOW_IPS contains "*": any client can choose '
            "the address the logs show"
        )

    return problems
