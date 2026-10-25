"""What a browser does on Keycloak's login page, with httpx.

Keycloak marks its cookies Secure even on http, and httpx never sends a
Secure cookie over http, so this keeps the cookies itself and sends them
by hand. Redirects are followed by hand too: the last one goes to the
frontend's redirect_uri, which nothing serves in a test.
"""

import base64
import hashlib
import secrets
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

LOGIN_FORM_ID = "kc-form-login"


def pkce_pair() -> tuple[str, str]:
    """A code_verifier and its S256 code_challenge (RFC 7636)."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class LoginFormParser(HTMLParser):
    """The action of Keycloak's login form."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == LOGIN_FORM_ID:
            self.action = values.get("action")


class Browser:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}
        self.client = httpx.Client(timeout=10, follow_redirects=False)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self.cookies:
            pairs = [f"{name}={value}" for name, value in self.cookies.items()]
            kwargs.setdefault("headers", {})["Cookie"] = "; ".join(pairs)
        response = self.client.request(method, url, **kwargs)
        for header in response.headers.get_list("set-cookie"):
            name, _, rest = header.partition("=")
            self.cookies[name.strip()] = rest.split(";", 1)[0]
        return response

    def log_in(self, authorization_url: str, username: str, password: str) -> str:
        """Log in on Keycloak; the URL Keycloak sends the browser back to."""
        page = self.request("GET", authorization_url)
        while page.is_redirect:
            page = self.request("GET", urljoin(str(page.url), page.headers["location"]))
        assert page.status_code == 200, page.text[:500]

        form = LoginFormParser()
        form.feed(page.text)
        assert form.action is not None, "no login form on Keycloak's page"

        answer = self.request(
            "POST",
            form.action,
            data={"username": username, "password": password, "credentialId": ""},
        )
        assert answer.is_redirect, f"login refused: {answer.status_code}"
        return answer.headers["location"]


def query(url: str) -> dict[str, str]:
    """The query parameters of a URL, one value each."""
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}
