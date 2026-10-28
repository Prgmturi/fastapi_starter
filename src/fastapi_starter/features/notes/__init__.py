"""Notes: the example feature, each user's own notes.

Three layers, each importing only the ones below it (import contracts in
pyproject.toml):

- api/: HTTP, the only part that knows FastAPI. The request and response
  schemas, the routes, and the wiring of the service.
- persistence/: SQLAlchemy. The notes table, and the repository that
  implements the port of the domain.
- domain/: the business rules, in plain Python. No FastAPI, no SQLAlchemy,
  no pydantic: they can be tested with a repository kept in memory.
"""
