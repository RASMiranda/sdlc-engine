"""Where the engine's tests find things.

ENGINE is this repository: the engine code, the stage workflow and the golden files.
FIXTURE is tests/fixture-project/: a minimal project (config, caller workflow, agents, labels, forms, CODEOWNERS,
REVIEW.md) that stands in for a consumer. No test reads a real project's files.
"""
import shutil
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
FIXTURE = ENGINE / "tests" / "fixture-project"
STAGE_WORKFLOW = ENGINE / ".github" / "workflows" / "sdlc-stage.yml"


def trusted_tree(tmp_path, name="trusted-tree"):
    """A copy of the layout the workflow's trusted checkout makes: ``<root>/src`` holds the engine and
    ``<root>/.github/sdlc-config.json`` the project's config, so ``$TRUSTED_SRC/../.github/sdlc-config.json`` resolves.
    Returns the ``src`` directory (the value of TRUSTED_SRC)."""
    root = Path(tmp_path) / name
    if (root / "src").is_dir():
        return root / "src"
    shutil.copytree(ENGINE / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (root / ".github").mkdir()
    shutil.copy(FIXTURE / ".github" / "sdlc-config.json", root / ".github" / "sdlc-config.json")
    return root / "src"
