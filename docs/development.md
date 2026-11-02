# Development

The tools, the tests, the checks of CI, the releases, and the care taken with what the project takes from others.

## Tools

- **Docker**, for the stack of `compose.yaml`.
- **[uv](https://docs.astral.sh/uv/) 0.13 or later.** An older uv stops with an error in this project: run `uv self update`. uv installs the Python of `.python-version`, 3.13, when the machine does not have it.

## Run the app on your machine

With Postgres and Keycloak from the stack:

```bash
uv sync
uv run pre-commit install         # ruff, gitleaks and commitlint on every commit, as CI runs them
cp .env.example .env              # the values of the stack, as the host sees them
docker compose up --wait db keycloak
uv run alembic upgrade head
uv run uvicorn fastapi_starter.main:create_app --factory --reload
```

Then open http://localhost:8000/docs.

## Tests

```bash
uv run pytest                              # every test but the integration and end-to-end ones
uv run pytest tests/core/auth/             # one folder
uv run pytest tests/core/auth/test_service.py::TestValidateToken  # one class
uv run pytest --cov                        # with coverage, as CI runs it
uv run pytest -m integration               # only the integration tests, on a real Postgres
uv run pytest -m e2e                       # a login through the running stack
```

- **Unit tests** are async, and outside `tests/integration/` they use stubs (`AsyncMock`): no database and no Keycloak. The root `conftest.py` provides the app, an HTTP client, mock services, and users with different roles.
- **They ignore your machine.** Tests never read your local `.env`, nor the `APP_*`, `KEYCLOAK_*` and other variables you export: an autouse fixture in `tests/conftest.py` switches both off. A test that needs some settings builds them and passes them to `create_app(settings)`.
- **CI runs the suite twice**, the second time with a `.env` and variables of a production server, and fails when coverage drops below `fail_under` in `pyproject.toml`.

### Integration tests

The tests in `tests/integration/` run on a real Postgres, for what a mock cannot show, such as a commit that the database refuses.

- `uv run pytest` leaves them out, even when you name their file; `-m integration` runs only them.
- They read `TEST_DATABASE_*`, exported or in `.env` (see `.env.example`), and no other setting.
- They refuse a database whose name does not end in `_test`, because they create and drop tables in it. Create it once, in the `db` service of the stack:

  ```bash
  docker compose exec db createdb -U appbase appbase_test   # -U: DATABASE_USER
  ```

- Before the first test, a fixture brings that database to the last migration (`alembic upgrade head`), as CI does: no command is needed.
- CI runs them in a job of its own, with its own Postgres. They do not count towards the coverage threshold.

### End-to-end test

`uv run pytest -m e2e` logs the test user in through Keycloak, then calls the API with the token, as a frontend would. CI does it on every push, on the stack it starts.

The stack takes its ports from `SERVER_PORT`, `KEYCLOAK_PORT` and `DATABASE_PORT`, exported or in `.env`. The test calls the API at `E2E_API_URL`, `http://localhost:8000` by default: with the stack on another port, export it too (`E2E_API_URL=http://localhost:18000`), or the test calls whatever answers on 8000.

## What CI runs

| Job | What it does |
|---|---|
| `ci` | ruff, the format, mypy, the import contracts ([architecture.md](architecture.md)), the unit tests with coverage, then the tests again in a production-like environment |
| Integration tests | The migrations up, checked against the models, down and up again; then the integration tests, on a Postgres of their own |
| Build container image | The image of `docker/Dockerfile`, a smoke test of the app inside it, the check that the app cannot change its own code, and the Grype scan |
| Log in through the whole stack | `docker compose up` of the stack, then the end-to-end test |
| Lint commit messages | Every commit of a pull request, and its title, through commitlint |

## Releases

Commits follow [Conventional Commits](https://www.conventionalcommits.org/). commitlint checks every commit of a pull request, and its title, which becomes the commit on `master` when the pull request is squashed.

[release-please](https://github.com/googleapis/release-please) keeps a release pull request open, with the next version and the changelog. Merging it:

- tags `vX.Y.Z` and publishes the GitHub release;
- publishes the image `ghcr.io/prgmturi/fastapi_starter:X.Y.Z`, and `:latest`;
- has already raised the version in `pyproject.toml`, `uv.lock` and the `image:` lines of `compose.prod.yaml`.

Under 1.0, `feat` and `fix` raise the patch number, and a breaking change (`!`) the minor one.

## Supply chain

What the project takes from others, and how it is checked:

- **Actions pinned to a commit.** Every GitHub Action is pinned to a commit, with its version in a comment. A tag can be moved to other code: it happened to `aquasecurity/trivy-action` in March 2026.
- **Dependabot** proposes updates once a week (`.github/dependabot.yml`): the actions, the base image of `docker/Dockerfile`, Postgres and Keycloak in the compose files, and `uv.lock`. What the image runs comes as `fix(deps)`, so it leads to a release; the tools of development come as `build(deps-dev)` or `ci`. New majors of Python, Postgres and Keycloak, and new versions of uv, are upgrades done by hand.
- **Grype** scans the image in CI ([Grype](https://github.com/anchore/grype)), and fails on a High or Critical vulnerability that has a fix. The report goes to the Security tab of the repository.
- **gitleaks** runs in the pre-commit hook ([gitleaks](https://github.com/gitleaks/gitleaks)) on the staged changes, and stops a commit that holds a secret. When it takes for a secret a value that is not one, end that line with `# gitleaks:allow`, as `KC_DB_URL` does in `compose.yaml`.
- **On GitHub**, turn on secret scanning and push protection (*Settings*, *Advanced Security*): they check every push.
