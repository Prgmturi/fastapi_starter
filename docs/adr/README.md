# Architecture decision records

Short notes on the decisions that shape the project: the context, the decision, and what follows from it. A record is not rewritten when a decision changes: a new one replaces it, and says which.

| Record | Decision |
|---|---|
| [0001](0001-hexagonal-architecture.md) | Ports in `core`, adapters in `adapters/`, wired in `bootstrap.py` |
| [0002](0002-keycloak.md) | Keycloak as the identity provider, its tokens checked locally |
| [0003](0003-refresh-token-in-a-cookie.md) | The refresh token travels only in an HttpOnly cookie |
| [0004](0004-app-factory.md) | The app is built by a factory, `create_app()` |
| [0005](0005-database.md) | SQLAlchemy is part of `core`; a feature with rules keeps it behind a port |
