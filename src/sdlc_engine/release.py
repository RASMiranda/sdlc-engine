"""``python -m sdlc_engine release-notes``: the version and notes of the newest release in ``CHANGELOG.md`` (D-005).

Stdlib only, no network, no git. It reads the top ``## [X.Y.Z] - YYYY-MM-DD`` section (``[Unreleased]`` is skipped),
prints ``X.Y.Z`` to standard output and writes the section's body to ``--out``. It exits 1 with one plain message, and
writes nothing, when there is no versioned section, the version is not SemVer, the date is not a real date, the version
differs from ``pyproject.toml`` or from ``engine_version()``, or the body is empty. The release workflow runs it before it
tags, so a release PR that forgot one of the version bumps fails red instead of tagging the wrong thing.
"""
import datetime
import re
import sys
import tomllib
from pathlib import Path

# semver.org's own pattern: MAJOR.MINOR.PATCH, no leading zeros, optional pre-release and build metadata.
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
                    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
                    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?")
HEADING = re.compile(r"^## \[(?!Unreleased\])(?P<version>[^\]\n]*)\] - (?P<date>\d{4}-\d{2}-\d{2})[ \t]*$", re.M)
NEXT_SECTION = re.compile(r"^## ", re.M)


class ReleaseError(ValueError):
    """The changelog or the version is not ready to release."""


def top_release(changelog_text):
    """``(version, body)`` of the first versioned section. Raises ``ReleaseError``."""
    m = HEADING.search(changelog_text)
    if not m:
        raise ReleaseError("no versioned section: the changelog has no '## [X.Y.Z] - YYYY-MM-DD' heading")
    version, date = m.group("version"), m.group("date")
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"the top versioned section's version {version!r} is not SemVer (X.Y.Z)")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise ReleaseError(f"the top versioned section's date {date!r} is not a real date") from None
    rest = changelog_text[m.end():]
    nxt = NEXT_SECTION.search(rest)
    body = (rest[:nxt.start()] if nxt else rest).strip()
    if not body:
        raise ReleaseError(f"the section for {version} is empty: write its notes first")
    return version, body + "\n"


def pyproject_version(path):
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise ReleaseError(f"cannot read project.version from {path}: {exc}") from None


def release_notes(changelog, pyproject, engine):
    """``(version, body)`` when the changelog, ``pyproject.toml`` and the engine agree. Raises ``ReleaseError``."""
    try:
        text = Path(changelog).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseError(f"cannot read {changelog}: {exc}") from None
    version, body = top_release(text)
    declared = pyproject_version(pyproject)
    if declared != version:
        raise ReleaseError(f"{changelog} says {version} but {pyproject} says {declared}")
    if engine != version:
        raise ReleaseError(f"{changelog} says {version} but the engine reports {engine}")
    return version, body


def command(args, engine):
    try:
        version, body = release_notes(args.changelog, args.pyproject, engine)
    except ReleaseError as exc:
        print(f"release-notes: {exc}", file=sys.stderr)
        return 1
    Path(args.out).write_text(body, encoding="utf-8")
    print(version)
    return 0
