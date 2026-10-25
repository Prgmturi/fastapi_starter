"""Tests that keep uv.lock in step with pyproject.toml.

WHY these tests exist: release-please bumps the version in pyproject.toml
but not in uv.lock, so after every release the lock named the previous
version. CI installed with --frozen, which never compares the two: the
release PR of 0.6.1 passed with a lock that said 0.6.0. Three uv versions
(CI, the Dockerfile, a developer's machine) also wrote the lock in
different formats.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
UV_IMAGE = re.compile(r"COPY --from=ghcr\.io/astral-sh/uv:(\S+) ")


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def project_name() -> str:
    """The name uv.lock gives the project: fastapi_starter -> fastapi-starter."""
    return normalized(pyproject()["project"]["name"])


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def ci_uv_version() -> str:
    match = re.search(r'^\s*UV_VERSION: "([^"]+)"$', CI_WORKFLOW.read_text(), re.M)
    assert match is not None, "ci.yml sets no UV_VERSION"
    return match.group(1)


def image_uv_version() -> str:
    match = UV_IMAGE.search(DOCKERFILE.read_text())
    assert match is not None, "the Dockerfile copies no uv binary"
    return match.group(1)


class TestLockfile:
    """uv.lock names the version that pyproject.toml declares."""

    def test_lock_has_the_project_version(self):
        """[HP] The project's own entry in uv.lock has the current version."""
        lock = tomllib.loads((ROOT / "uv.lock").read_text())
        locked = [p["version"] for p in lock["package"] if p["name"] == project_name()]

        assert locked == [pyproject()["project"]["version"]]

    def test_release_bumps_the_lock_too(self):
        """[HP] release-please writes the new version into uv.lock as well.

        WHY ".value": release-please reads the TOML into values wrapped with
        their position in the file, so the name sits in name.value. With
        @.name the filter matches nothing, and release-please only logs a
        warning (tried with release-please 17.6.0, the one in
        release-please-action v5, on 25 October 2026).
        """
        config = json.loads((ROOT / "release-please-config.json").read_text())

        assert {
            "type": "toml",
            "path": "uv.lock",
            "jsonpath": f"$.package[?(@.name.value=='{project_name()}')].version",
        } in config["packages"]["."].get("extra-files", [])


class TestUvVersion:
    """One uv version in CI and in the image, and no older one anywhere."""

    def test_ci_and_image_use_the_same_uv(self):
        """[HP] The uv that checks the lock in CI is the one the image uses."""
        assert ci_uv_version() == image_uv_version()

    def test_every_setup_uv_step_uses_the_pinned_version(self):
        """[EC] Without a version, setup-uv installs the newest uv."""
        workflow = CI_WORKFLOW.read_text()

        assert workflow.count("astral-sh/setup-uv@") == workflow.count(
            "version: ${{ env.UV_VERSION }}"
        )

    def test_pinned_uv_meets_the_required_version(self):
        """[EC] The pinned uv is allowed by required-version in pyproject.toml.

        WHY a minimum: uv 0.12 and older rewrite the lock in an older format
        (revision 3 instead of 5) as soon as anything in it changes, as uv
        0.9.15 did on a developer's machine (measured on 25 October 2026).
        """
        required = pyproject()["tool"]["uv"]["required-version"]
        match = re.fullmatch(r">=(\d+\.\d+\.\d+)", required)
        assert match is not None, required

        assert version_tuple(ci_uv_version()) >= version_tuple(match.group(1))

    def test_every_install_checks_the_lock(self):
        """[EC] uv sync fails, in CI and in the image, on a lock out of date.

        WHY: --frozen installs what the lock says without comparing it with
        pyproject.toml; --locked stops with an error.
        """
        installs = [
            line.strip()
            for path in (CI_WORKFLOW, DOCKERFILE)
            for line in path.read_text().splitlines()
            if re.search(r"\buv sync\b", line) and not line.lstrip().startswith("#")
        ]

        assert installs
        assert [line for line in installs if "--locked" not in line] == []
