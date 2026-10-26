"""Tests for what the project takes from others, and how it is checked.

WHY these tests exist: on 19 March 2026 an attacker moved 76 of the 77
tags of aquasecurity/trivy-action to code that stole the secrets of the
workflows using them. Every action here was named by a tag. Dependabot
sent security updates only, with no dependabot.yml; nothing scanned the
image a release publishes; nothing stopped a secret before the commit
(all checked on 25 October 2026).
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
PRE_COMMIT = ROOT / ".pre-commit-config.yaml"
COMPOSE = ROOT / "compose.yaml"
# owner/repo[/path]@<commit SHA> # v<version>
PINNED = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+(\.\d+)*")


def uses() -> list[str]:
    """Every action the workflows run, with the comment after it."""
    return [
        match.group(1).strip()
        for path in WORKFLOWS
        for match in re.finditer(r"^\s*(?:- )?uses:\s*(.+)$", path.read_text(), re.M)
    ]


def updates() -> dict[str, dict]:
    """The entries of dependabot.yml, by ecosystem."""
    config = yaml.safe_load(DEPENDABOT.read_text())
    return {entry["package-ecosystem"]: entry for entry in config["updates"]}


def ignored(ecosystem: str) -> dict[str, list[str]]:
    """Dependency name -> the update types Dependabot must not propose."""
    return {
        rule["dependency-name"]: rule.get("update-types", ["all"])
        for rule in updates()[ecosystem].get("ignore", [])
    }


def ci_step(job: str, action: str) -> dict:
    steps = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"][job]["steps"]
    return next(step for step in steps if step.get("uses", "").startswith(action))


class TestActions:
    def test_every_action_is_pinned_to_a_commit(self):
        """[SEC] owner/repo@<commit SHA> # v<version>, never a tag alone.

        WHY: a tag can be moved to other code, a commit cannot. The comment
        keeps the version readable, and Dependabot updates both.
        """
        assert uses()
        assert [use for use in uses() if not PINNED.fullmatch(use)] == []


class TestDependabot:
    def test_every_ecosystem_is_updated_weekly(self):
        """[HP] Actions, the Dockerfile, the compose files, the Python lock."""
        directories = {name: entry["directory"] for name, entry in updates().items()}

        assert directories == {
            "github-actions": "/",
            "docker": "/docker",
            "docker-compose": "/",
            "uv": "/",
        }
        assert {entry["schedule"]["interval"] for entry in updates().values()} == {
            "weekly"
        }

    def test_what_the_image_runs_makes_a_release(self):
        """[HP] Runtime updates are fix(deps), the rest is not.

        WHY: release-please releases on fix. A new base image or a runtime
        library reaches the published image only with a release; a new
        test tool or action needs none.
        """
        prefixes = {name: entry["commit-message"] for name, entry in updates().items()}

        assert prefixes["uv"] == {
            "prefix": "fix(deps)",
            "prefix-development": "build(deps-dev)",
        }
        assert prefixes["docker"] == {"prefix": "fix(deps)"}
        assert prefixes["docker-compose"] == {"prefix": "fix(deps)"}
        assert prefixes["github-actions"] == {"prefix": "ci"}

    def test_no_upgrade_that_needs_more_than_a_review(self):
        """[EC] Python 3.14, Postgres 18 and Keycloak 27 are upgrades by hand.

        WHY: another Python in the image than in CI; a Postgres major does
        not start on the data of the previous one; a Keycloak major can
        need steps of its own. uv moves in three files at once
        (tests/test_lockfile.py), and our own image moves with releases.
        """
        majors = ["version-update:semver-major"]

        assert ignored("docker")["python"] == ["version-update:semver-minor", *majors]
        assert ignored("docker")["ghcr.io/astral-sh/uv"] == ["all"]
        assert ignored("docker-compose")["postgres"] == majors
        assert ignored("docker-compose")["quay.io/keycloak/keycloak"] == majors
        assert ignored("docker-compose")["ghcr.io/prgmturi/fastapi_starter"] == ["all"]


class TestImageScan:
    def test_the_built_image_is_scanned(self):
        """[SEC] Grype on the image CI builds: it fails on a fixable High.

        WHY only the fixable ones: on 25 October 2026 the image had 55 High
        in Debian packages with no fix. Failing on those would fail every
        build, with nothing to do about it.
        """
        scan = ci_step("docker", "anchore/scan-action@")["with"]

        assert scan["image"] == "fastapi-starter:ci"
        assert scan["only-fixed"] is True
        assert scan["severity-cutoff"] == "high"
        assert scan["fail-build"] is True
        assert scan["output-format"] == "sarif"

    def test_the_results_reach_code_scanning(self):
        """[HP] The report goes to the Security tab, also when the scan fails."""
        upload = ci_step("docker", "github/codeql-action/upload-sarif@")
        job = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["docker"]

        assert "!cancelled()" in upload["if"]
        assert job["permissions"] == {"contents": "read", "security-events": "write"}

    def test_no_upload_without_a_report(self):
        """[EC] Without a scan there is no report, and no upload.

        WHY: when the image did not build, the upload ran anyway and failed
        with "Input required and not supplied: sarif_file", an error next to
        the real one (PR #53, 26 October 2026). scan-action sets its sarif
        output also when it fails the build, so a failed scan still reaches
        the Security tab.
        """
        upload = ci_step("docker", "github/codeql-action/upload-sarif@")

        assert "steps.scan.outputs.sarif != ''" in upload["if"]


class TestSecretsHook:
    def test_gitleaks_runs_before_each_commit(self):
        """[SEC] gitleaks stops a secret before it leaves the machine.

        WHY: once pushed to a public repository a secret is public, even if
        the commit is removed later. Its revision is a commit, as for the
        actions.
        """
        config = yaml.safe_load(PRE_COMMIT.read_text())
        repo = next(
            r
            for r in config["repos"]
            if r["repo"] == "https://github.com/gitleaks/gitleaks"
        )

        assert re.fullmatch(r"[0-9a-f]{40}", repo["rev"])
        assert re.search(r"rev: [0-9a-f]{40}  # frozen: v\d+", PRE_COMMIT.read_text())
        assert [hook["id"] for hook in repo["hooks"]] == ["gitleaks"]

    def test_the_keycloak_database_url_is_not_taken_for_a_key(self):
        """[EC] A commit that moves or copies KC_DB_URL is not stopped.

        WHY: gitleaks' generic-api-key rule reads "keycloak-db" as the name
        of a key and "5432/keycloak" as its value, with an entropy of 3.55
        against a threshold of 3.5 (checked on 26 October 2026). The line
        says gitleaks:allow, which is safe while the URL holds no user name
        and no password: those stay in KC_DB_USERNAME and KC_DB_PASSWORD.
        """
        line = next(
            line for line in COMPOSE.read_text().splitlines() if "KC_DB_URL:" in line
        )

        assert line.endswith("  # gitleaks:allow")
        assert "@" not in line
