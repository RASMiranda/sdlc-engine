"""D-005: `python -m sdlc_engine release-notes`. Fixtures only, written to tmp_path; no network, no git."""
import os
import subprocess
import sys

import pytest

import sdlc_engine as sdlc
from sdlc_engine import release
from engine_paths import ENGINE

GOOD = """# Changelog

Intro text.

## [Unreleased]

### Added
- something not released yet

## [1.4.0] - 2026-12-01

### Added
- the thing

### Fixed
- the other thing

## [1.3.2] - 2026-11-01

- older
"""


def write(tmp_path, changelog=GOOD, version="1.4.0"):
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "sdlc-engine"\nversion = "{version}"\n', encoding="utf-8")
    return tmp_path / "CHANGELOG.md", tmp_path / "pyproject.toml"


class Args:
    def __init__(self, changelog, pyproject, out):
        self.changelog, self.pyproject, self.out = str(changelog), str(pyproject), str(out)


def run(tmp_path, capsys, engine="1.4.0", **kw):
    changelog, pyproject = write(tmp_path, **kw)
    out = tmp_path / "notes.md"
    rc = release.command(Args(changelog, pyproject, out), engine)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err, out


# ------------------------------------------------------------------------------------------------------------ success
def test_the_top_versioned_section_is_released_and_unreleased_is_skipped(tmp_path, capsys):
    rc, out, err, notes = run(tmp_path, capsys)
    assert rc == 0 and out == "1.4.0\n" and err == ""
    assert notes.read_text() == "### Added\n- the thing\n\n### Fixed\n- the other thing\n"
    assert "not released yet" not in notes.read_text() and "older" not in notes.read_text()


def test_the_last_section_runs_to_the_end_of_the_file(tmp_path, capsys):
    rc, out, _, notes = run(tmp_path, capsys, changelog="# C\n\n## [2.0.0-rc.1+b.7] - 2026-12-01\n\n- only\n",
                            version="2.0.0-rc.1+b.7", engine="2.0.0-rc.1+b.7")
    assert rc == 0 and out == "2.0.0-rc.1+b.7\n" and notes.read_text() == "- only\n"


def test_the_real_changelog_and_pyproject_agree_with_the_engine(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ENGINE / "src")}
    run_ = subprocess.run([sys.executable, "-P", "-m", "sdlc_engine", "release-notes", "--changelog", "CHANGELOG.md",
                           "--pyproject", "pyproject.toml", "--out", str(tmp_path / "n.md")],
                          cwd=ENGINE, env=env, capture_output=True, text=True)
    assert run_.returncode == 0, run_.stderr
    assert run_.stdout.strip() == sdlc.engine_version() and (tmp_path / "n.md").read_text().strip()


# ----------------------------------------------------------------------------------------------------------- failures
def fails(tmp_path, capsys, expected, **kw):
    rc, out, err, notes = run(tmp_path, capsys, **kw)
    assert rc == 1 and out == "" and not notes.exists(), (rc, out, err)
    assert err.startswith("release-notes: ") and expected in err and len(err.splitlines()) == 1, err


def test_no_versioned_section(tmp_path, capsys):
    fails(tmp_path, capsys, "no versioned section", changelog="# C\n\n## [Unreleased]\n\n- x\n")


def test_a_heading_without_a_date_is_not_a_versioned_section(tmp_path, capsys):
    fails(tmp_path, capsys, "no versioned section", changelog="# C\n\n## [1.4.0]\n\n- x\n")


@pytest.mark.parametrize("version", ["1.4", "v1.4.0", "01.4.0", "1.4.0.0", "1.4.x", "latest", ""])
def test_a_version_that_is_not_semver(tmp_path, capsys, version):
    fails(tmp_path, capsys, "is not SemVer", changelog=f"## [{version}] - 2026-12-01\n\n- x\n", version=version, engine=version)


def test_a_date_that_does_not_exist(tmp_path, capsys):
    fails(tmp_path, capsys, "is not a real date", changelog="## [1.4.0] - 2026-02-30\n\n- x\n")


def test_a_version_that_differs_from_pyproject(tmp_path, capsys):
    fails(tmp_path, capsys, "but", version="1.3.2")


def test_a_version_that_differs_from_the_engine(tmp_path, capsys):
    fails(tmp_path, capsys, "the engine reports 1.3.2", engine="1.3.2")


@pytest.mark.parametrize("changelog", ["## [1.4.0] - 2026-12-01\n", "## [1.4.0] - 2026-12-01\n\n   \n\n## [1.3.2] - 2026-11-01\n\n- x\n"])
def test_an_empty_body(tmp_path, capsys, changelog):
    fails(tmp_path, capsys, "is empty", changelog=changelog)


def test_an_unreadable_pyproject(tmp_path, capsys):
    changelog, pyproject = write(tmp_path)
    pyproject.write_text("[project]\nname = 'x'\n")
    rc = release.command(Args(changelog, pyproject, tmp_path / "notes.md"), "1.4.0")
    assert rc == 1 and "cannot read project.version" in capsys.readouterr().err


def test_a_missing_changelog(tmp_path, capsys):
    rc = release.command(Args(tmp_path / "nope.md", tmp_path / "p.toml", tmp_path / "notes.md"), "1.4.0")
    assert rc == 1 and "cannot read" in capsys.readouterr().err


def test_the_cli_exits_1_with_one_plain_line(tmp_path):
    changelog, pyproject = write(tmp_path, version="9.9.9")
    env = {**os.environ, "PYTHONPATH": str(ENGINE / "src")}
    run_ = subprocess.run([sys.executable, "-P", "-m", "sdlc_engine", "release-notes", "--changelog", str(changelog),
                           "--pyproject", str(pyproject), "--out", str(tmp_path / "n.md")], env=env, capture_output=True, text=True)
    assert run_.returncode == 1 and run_.stdout == "" and len(run_.stderr.splitlines()) == 1
