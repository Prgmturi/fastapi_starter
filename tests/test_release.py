"""Tests for what a release does: the image it publishes, the files it bumps.

WHY these tests exist: a release made a tag and a GitHub release, and no
image. release.yml already had the release_created output and no job used
it (checked on 25 October 2026). compose.prod.yaml names the image of a
release, so every release must bump it, as it bumps pyproject.toml.
tests/test_lockfile.py covers uv.lock.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
COMPOSE_PROD = ROOT / "compose.prod.yaml"
RELEASED_IMAGE = "ghcr.io/prgmturi/fastapi_starter"
# release-please's generic updater changes the version on lines with this
VERSION_MARKER = "# x-release-please-version"


def image_job() -> dict:
    """The job of release.yml that may write packages."""
    jobs = yaml.safe_load(RELEASE_WORKFLOW.read_text())["jobs"]
    publishing = [job for job in jobs.values() if "packages" in job["permissions"]]
    assert len(publishing) == 1
    return publishing[0]


def script() -> str:
    return "\n".join(step.get("run", "") for step in image_job()["steps"])


class TestImage:
    def test_published_only_for_a_release(self):
        """[HP] After release-please, and only when it made a release.

        WHY in release.yml: the tag that release-please pushes with
        GITHUB_TOKEN starts no workflow, so no "on: push: tags" would run.
        """
        job = image_job()

        assert job["needs"] == "release-please"
        assert job["if"] == "needs.release-please.outputs.release_created == 'true'"

    def test_only_the_permissions_it_needs(self):
        """[SEC] Read the code, write the package: nothing else."""
        assert image_job()["permissions"] == {"contents": "read", "packages": "write"}

    def test_built_from_the_tag(self):
        """[HP] The code of the release, the same the tag points at."""
        checkout = next(
            step
            for step in image_job()["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )

        assert checkout["with"]["ref"] == "${{ needs.release-please.outputs.tag_name }}"

    def test_pushes_the_version_and_latest(self):
        """[HP] ghcr.io/<owner>/<repository>, lower case, version and latest.

        WHY lower case: the registry refuses capitals, and the owner is
        Prgmturi.
        """
        assert 'image="$REGISTRY/${GITHUB_REPOSITORY,,}"' in script()
        assert 'docker push "$image:$version"' in script()
        assert 'docker push "$image:latest"' in script()
        assert "-f docker/Dockerfile" in script()

    def test_the_package_names_its_repository(self):
        """[HP] The OCI source label links the package to the repository."""
        assert "org.opencontainers.image.source=" in script()


class TestOneRunAtATime:
    def test_release_runs_wait_for_each_other(self):
        """[EC] Merges close together run release-please one after the other.

        WHY: #50 and #51, merged 20 seconds apart, started two runs at once.
        Both found no release PR, both opened it, and one failed with "A pull
        request already exists" (26 October 2026). Two image jobs at once
        could also push latest out of order.
        """
        workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())

        assert workflow["concurrency"] == {
            "group": "release",
            "cancel-in-progress": False,
        }

    def test_the_image_names_the_commit_it_was_built_from(self):
        """[EC] The revision label is the commit of the tag, not of the run.

        WHY: a newer run takes the place of one still waiting, and then makes
        the release of the merge before it: its GITHUB_SHA is a later commit
        than the tag it builds.
        """
        assert 'revision="$(git rev-parse HEAD)"' in script()
        assert "org.opencontainers.image.revision=$revision" in script()


class TestVersionBump:
    def test_release_bumps_compose_prod(self):
        """[HP] release-please writes the new version into compose.prod.yaml."""
        config = json.loads((ROOT / "release-please-config.json").read_text())

        assert {"type": "generic", "path": "compose.prod.yaml"} in config["packages"][
            "."
        ]["extra-files"]

    def test_every_image_line_carries_the_marker(self):
        """[EC] Each line naming the released image ends with the marker.

        WHY: the generic updater changes only those lines; one without it
        would keep the old version, and the server would run it.
        """
        lines = COMPOSE_PROD.read_text().splitlines()
        image_lines = [line.rstrip() for line in lines if RELEASED_IMAGE in line]

        assert image_lines
        assert [line for line in image_lines if not line.endswith(VERSION_MARKER)] == []
