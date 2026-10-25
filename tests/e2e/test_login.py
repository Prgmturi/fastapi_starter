"""A user of the dev realm logs in, calls the API, refreshes and logs out.

WHY this test exists: the phase 8 goal is that a clean clone plus
docker compose up gives a working login. It runs against the real stack
(Keycloak, Postgres, the image of the API), in CI after
docker compose up --wait, and replaces the login_flow.py script of the
check on 20 October 2026.
"""

import json
import secrets
from pathlib import Path

from tests.e2e.browser import Browser, pkce_pair, query

DEV_REALM = Path(__file__).parents[2] / "docker" / "keycloak" / "realm-dev.json"
# A frontend address: nothing listens there, the test reads the redirect
REDIRECT_URI = "http://localhost:3000/callback"


def dev_user() -> tuple[str, str]:
    """Username and password of the realm's test user."""
    user = json.loads(DEV_REALM.read_text())["users"][0]
    return user["username"], user["credentials"][0]["value"]


def refresh_cookie(response) -> str:
    """The refresh token cookie the API set, as a Cookie header."""
    header = response.headers["set-cookie"]
    return header.split(";", 1)[0]


def test_log_in_call_refresh_and_log_out(api):
    """[HP] The whole flow of a frontend, through Keycloak and the API."""
    username, password = dev_user()
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)

    login = api.get(
        "/auth/login",
        params={
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge,
            "state": state,
        },
    )
    assert login.status_code == 200

    back = Browser().log_in(login.json()["authorization_url"], username, password)
    assert back.startswith(REDIRECT_URI + "?")
    assert query(back)["state"] == state

    tokens = api.post(
        "/auth/token",
        json={
            "code": query(back)["code"],
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert tokens.status_code == 200, tokens.text
    access_token = tokens.json()["access_token"]

    me = api.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == username
    assert me.json()["roles"] == ["user"]

    refreshed = api.post("/auth/refresh", headers={"Cookie": refresh_cookie(tokens)})
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"] != access_token

    logout = api.post("/auth/logout", headers={"Cookie": refresh_cookie(refreshed)})
    assert logout.status_code == 200, logout.text
