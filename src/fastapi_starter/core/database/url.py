"""The database URL, built from the settings.

It lives here and not in DatabaseSettings: core.config is imported by
core.auth, and a SQLAlchemy import there would load SQLAlchemy with it.
"""

from sqlalchemy.engine import URL

from fastapi_starter.core.config.database import DatabaseSettings


def database_url(settings: DatabaseSettings) -> URL:
    """URL for SQLAlchemy, built part by part.

    No string is parsed, so characters such as @, : or % in the password
    stay part of the password. str() and repr() of the URL hide it; for
    logs use ``render_as_string(hide_password=True)``.
    """
    return URL.create(
        drivername=settings.driver,
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )
