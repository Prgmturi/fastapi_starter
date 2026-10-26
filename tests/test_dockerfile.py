"""Tests for docker/Dockerfile: what the image starts from, as whom, and how.

WHY these tests exist: measured on 25 October 2026 on the image of
master. The base image was a tag that moves (python:3.13-slim moved on
24 October), so the same commit built twice could differ. The app user
owned its code and could rewrite it, and a restarted container keeps
what was written. The package was installed in editable mode, pointing
at a copy of src/ found through PYTHONPATH. tests/test_serve.py covers
the command the image starts.
"""

import re
from pathlib import Path

DOCKERFILE = Path(__file__).parent.parent / "docker" / "Dockerfile"


def instructions() -> list[str]:
    """The instructions, one per line: comments out, continuations joined."""
    joined = re.sub(r"\\\n\s*", " ", DOCKERFILE.read_text())
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def base_images() -> list[str]:
    return [i.split()[1] for i in instructions() if i.startswith("FROM ")]


class TestBaseImage:
    def test_every_stage_starts_from_a_digest(self):
        """[HP] Each FROM names the image by tag and by digest."""
        assert len(base_images()) == 2
        assert [
            image
            for image in base_images()
            if not re.fullmatch(r"python:[\w.-]+@sha256:[0-9a-f]{64}", image)
        ] == []

    def test_both_stages_start_from_the_same_image(self):
        """[EC] The builder compiles for the Python the runtime has."""
        assert len(set(base_images())) == 1


class TestRuntimeStage:
    def runtime(self) -> list[str]:
        steps = instructions()
        start = next(i for i, step in enumerate(steps) if " AS runtime" in step)
        return steps[start:]

    def test_the_app_user_owns_nothing(self):
        """[SEC] Code, virtual environment and migrations belong to root.

        WHY: as the owner, the process could change its own code, and with
        restart: unless-stopped a container comes back with the change.
        """
        steps = self.runtime()

        assert [step for step in steps if "chown" in step] == []
        assert "USER appuser" in steps

    def test_the_package_is_installed_not_linked(self):
        """[HP] The app lives in the virtual environment, not in src/."""
        steps = instructions()

        assert any(
            step.startswith("RUN uv sync") and "--no-editable" in step for step in steps
        )
        assert [step for step in self.runtime() if "src" in step] == []
        assert [step for step in steps if "PYTHONPATH" in step] == []

    def test_starts_through_serve(self):
        """[HP] The image starts python -m fastapi_starter.serve.

        WHY a CMD and no ENTRYPOINT: another command replaces it whole, as
        the migrations do (docker run <image> alembic upgrade head).
        """
        steps = self.runtime()

        assert steps[-1] == 'CMD ["python", "-m", "fastapi_starter.serve"]'
        assert [step for step in steps if step.startswith("ENTRYPOINT")] == []
