"""Tests that the checks run on the machine and with the tools we chose.

WHY these tests exist: every CI job ran on ubuntu-latest, which GitHub
moves to Ubuntu 26.04 one repository at a time between 19 October and
19 November 2026, so any run could land on a new image. And the
pre-commit hooks and CI checked the same things with different tools:
a file or a commit message the hook accepted could fail CI. And no file
named the version of Python: on a machine without 3.13, uv took the newest
it could download, 3.15.1, and the install stopped on a package with no
wheel for it (tried on 27 October 2026).
"""

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
COMMITS_WORKFLOW = ROOT / ".github" / "workflows" / "commits.yml"
PRE_COMMIT = ROOT / ".pre-commit-config.yaml"
PYTHON_VERSION = ROOT / ".python-version"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
RUNNER = "ubuntu-24.04"
PR_TITLE = "${{ github.event.pull_request.title }}"


def runners() -> list[str]:
    """Each runs-on of every workflow, as "file: value"."""
    return [
        f"{path.name}: {match.group(1)}"
        for path in WORKFLOWS
        for match in re.finditer(r"^\s*runs-on:\s*(\S+)", path.read_text(), re.M)
    ]


def imported_by_src() -> set[str]:
    """Top-level modules imported in src/, the code mypy checks."""
    modules = set()
    for path in ROOT.glob("src/**/*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules.add(node.module.split(".")[0])
    return modules


class TestRunner:
    def test_every_job_runs_on_the_pinned_image(self):
        """[HP] Each job names its Ubuntu, so the image changes when we choose."""
        assert runners()
        assert [r for r in runners() if not r.endswith(f": {RUNNER}")] == []


class TestRuffHook:
    def test_hook_runs_the_ruff_of_the_lock(self):
        """[HP] pre-commit runs ruff through uv, so the version CI runs."""
        config = PRE_COMMIT.read_text()
        entries = re.findall(r"^\s*entry:\s*(.+)$", config, re.M)
        ruff = [entry for entry in entries if "ruff" in entry]

        assert "astral-sh/ruff-pre-commit" not in config
        assert len(ruff) == 2
        assert [entry for entry in ruff if not entry.startswith("uv run")] == []


class TestCommitMessages:
    """The hook and CI check commit messages with the same commitlint.

    WHY: the hook ran conventional-pre-commit, CI commitlint, which also
    refuses a capital letter, a final full stop and body lines over 100
    characters. Three messages the hook accepted failed CI (25 October
    2026), and the list of types was written in both.
    """

    def test_hook_runs_commitlint(self):
        """[HP] The commit-msg hook is commitlint, with commitlint.config.js."""
        config = PRE_COMMIT.read_text()

        assert "conventional-pre-commit" not in config
        assert re.search(r"^\s*entry:\s*commitlint --edit\s*$", config, re.M)

    def test_ci_runs_the_hook_itself(self):
        """[HP] CI runs the hook on each commit, not a copy of commitlint."""
        workflows = "".join(path.read_text() for path in WORKFLOWS)

        assert "pre-commit run commitlint --hook-stage commit-msg" in (
            COMMITS_WORKFLOW.read_text()
        )
        assert "npx commitlint" not in workflows

    def test_ci_checks_the_pr_title(self):
        """[HP] The PR title is checked, and again whenever it is edited.

        WHY: with more than one commit the squash merge takes the PR title
        as the commit on master (COMMIT_OR_PR_TITLE in the repository
        settings), and release-please reads that commit.
        """
        workflow = COMMITS_WORKFLOW.read_text()

        assert PR_TITLE in workflow
        assert re.search(r"^\s*types:\s*\[.*\bedited\b.*\]", workflow, re.M)

    def test_pr_title_never_becomes_shell_code(self):
        """[SEC] The title reaches the script as an environment variable.

        WHY: whoever opens the PR writes the title. Written inside run:,
        GitHub would paste it into the script before the shell reads it.
        """
        lines = [
            line.strip()
            for path in WORKFLOWS
            for line in path.read_text().splitlines()
            if "github.event.pull_request.title" in line
        ]

        as_variable = re.compile(r"\w+: " + re.escape(PR_TITLE))

        assert lines
        assert [line for line in lines if not as_variable.fullmatch(line)] == []


class TestMypy:
    def test_every_override_names_a_module_the_code_imports(self):
        """[EC] An override for a module that src/ never imports is dead config.

        WHY: the override for asyncpg.* outlived the last import of asyncpg,
        and mypy 2.4 reports it as an unused section (26 October 2026).
        """
        mypy = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mypy"]
        modules = [
            module
            for override in mypy.get("overrides", [])
            for module in (
                [override["module"]]
                if isinstance(override["module"], str)
                else override["module"]
            )
        ]
        imported = imported_by_src()

        assert [m for m in modules if m.split(".")[0] not in imported] == []


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class TestPythonVersion:
    """.python-version: the Python of development, of CI and of the image.

    uv reads the file, and downloads that version when the machine has
    none: without it, uv took the newest Python it could get.
    """

    def test_the_image_runs_the_version_of_the_file(self):
        """[HP] Both FROM of the Dockerfile use python:<the file's version>.

        The FROM lines cannot read the file: the image is pinned by digest.
        """
        versions = re.findall(
            r"^FROM python:(\d+\.\d+)-slim@", DOCKERFILE.read_text(), re.M
        )

        assert versions == [PYTHON_VERSION.read_text().strip()] * 2

    def test_ci_takes_the_version_from_the_file(self):
        """[EC] No workflow names a Python of its own: the file is the only one."""
        assert [
            path.name
            for path in WORKFLOWS
            if re.search(r"^\s*python-version:", path.read_text(), re.M)
        ] == []

    def test_the_version_meets_requires_python(self):
        """[HP] The version of the file is one that pyproject.toml accepts."""
        requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
            "requires-python"
        ]
        lowest = re.fullmatch(r">=(\d+\.\d+)", requires)

        assert lowest is not None, requires
        assert version_tuple(PYTHON_VERSION.read_text().strip()) >= version_tuple(
            lowest.group(1)
        )
