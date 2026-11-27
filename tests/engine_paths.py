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
    """A copy of the layout the workflow's two trusted checkouts make (D-004): ``<root>/engine/src`` holds the engine
    (the called workflow's own repository) and ``<root>/project-config/.github/sdlc-config.json`` the project's config.
    Returns the ``src`` directory (the value of TRUSTED_SRC); ``sdlc_config_for`` gives the matching SDLC_CONFIG."""
    root = Path(tmp_path) / name
    if (root / "engine" / "src").is_dir():
        return root / "engine" / "src"
    shutil.copytree(ENGINE / "src", root / "engine" / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "project-config" / ".github").mkdir(parents=True)
    shutil.copy(FIXTURE / ".github" / "sdlc-config.json", root / "project-config" / ".github" / "sdlc-config.json")
    return root / "engine" / "src"


def sdlc_config_for(trusted_src):
    """The SDLC_CONFIG value that goes with a ``trusted_tree`` (the value the workflow's use-it step exports)."""
    return Path(trusted_src).parent.parent / "project-config" / ".github" / "sdlc-config.json"
