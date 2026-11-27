"""The packaging of the engine: one version, standard library only, URLs that point at the engine repository."""
import ast
import re
import subprocess
import sys
import tomllib

from engine_paths import ENGINE
from test_guard_engine import ENGINE_REPO, HANDLE

PYPROJECT = tomllib.loads((ENGINE / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_package_is_sdlc_engine_version_0_2_1_for_python_3_12_and_up():
    project = PYPROJECT["project"]
    assert project["name"] == "sdlc-engine" and project["version"] == "0.2.1"
    assert project["requires-python"] == ">=3.12"


def test_there_is_no_runtime_dependency():
    assert PYPROJECT["project"]["dependencies"] == []
    assert "optional-dependencies" not in PYPROJECT["project"]


def test_the_engine_imports_only_the_standard_library_and_itself():
    seen = set()
    for path in (ENGINE / "src" / "sdlc_engine").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                seen |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                seen.add(node.module.split(".")[0])
    assert seen - set(sys.stdlib_module_names) - {"sdlc_engine"} == set(), sorted(seen)


def test_the_project_urls_point_at_the_engine_repository():
    urls = PYPROJECT["project"]["urls"]
    assert urls and all(ENGINE_REPO in url for url in urls.values()), urls


def test_the_cli_version_is_the_pyproject_version_and_nothing_else_holds_it():
    run = subprocess.run([sys.executable, "-P", "-m", "sdlc_engine", "--version"], cwd=ENGINE, capture_output=True, text=True,
                         env={"PYTHONPATH": str(ENGINE / "src"), "PATH": ""})
    assert run.returncode == 0 and run.stdout.strip() == "sdlc-engine " + PYPROJECT["project"]["version"], run.stderr
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (ENGINE / "src" / "sdlc_engine").glob("*.py"))
    assert not re.search(r"\b0\.1\.0\b", sources)               # the version is never written in the code


def test_the_engine_codeowners_name_the_maintainer_for_every_path():
    lines = [l for l in (ENGINE / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    assert lines[0].split() == ["*", "@" + HANDLE]                 # the catch-all comes first, so everything is covered
    assert all(l.split()[1:] == ["@" + HANDLE] for l in lines)
