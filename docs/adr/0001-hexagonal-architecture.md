# 0001. Ports in core, adapters in adapters/, wired in bootstrap.py

Status: accepted. Recorded on 27 October 2026.

## Context

The project is a template that teaches: whoever starts from it should find the business rules apart from the libraries and services they use, and be able to test the rules without them.

## Decision

- **Ports** are `Protocol` classes: `core/auth/protocols.py` (`TokenDecoder`, `ClaimExtractor`, `TokenValidator`, `OAuthProvider`), `core/protocols.py` (`KeyProvider`, `HealthCheckable`), `core/database/protocols.py` (`DatabaseProvider`), and the ports of a feature's own domain, such as `features/notes/domain/protocols.py`.
- **Adapters** implement them, one folder per external service: `adapters/keycloak/` holds the client of the login flow, the key manager, the token decoder and the claim extractor.
- **`bootstrap.py`** is the only module that builds the adapters and hands them to the app. It stores each one in `app.state` through a variable typed as its port, so mypy checks that an adapter still matches its port.
- **The rules are checked on every push:** import contracts in `pyproject.toml` (layers, ports that import no adapter, a domain that imports no framework), plus tests that import modules in a new process, to see what an `__init__.py` pulls in.

## Consequences

- `AuthService` and the domain of a feature are tested with fakes, in milliseconds.
- Another identity provider means another folder next to `adapters/keycloak/`, its settings in `core/config/` and its wiring in `bootstrap.py`. Two places still name Keycloak outside the adapters: the auth router reads the allowed redirect URIs from `KeycloakSettings`, and `core/config/production.py` names the `KEYCLOAK_*` variables.
- `KeycloakSettings` stays in `core/config/`: `Settings` gathers every section there, and `core` never imports an adapter.
- More files than a flat project, and a rule to learn: a module imports only from the layers below its own.
