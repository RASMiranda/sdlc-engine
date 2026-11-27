"""D-005: .github/workflows/release.yml. Parses the workflow; the tag-exists step runs for real against a fake `git`.
No network."""
import os
import re
import shutil
import subprocess

import pytest
import yaml

from engine_paths import ENGINE

PATH = ENGINE / ".github" / "workflows" / "release.yml"
TEXT = PATH.read_text(encoding="utf-8")
WF = yaml.safe_load(TEXT)
JOB = WF["jobs"]["release"]
STEPS = JOB["steps"]
NAME = {s.get("id"): s for s in STEPS if s.get("id")}
TAG = next(s for s in STEPS if s.get("name") == "Create and push the annotated tag")
RELEASE = next(s for s in STEPS if s.get("name") == "Create the release from the tag")
TOKEN = re.compile(r"GH_TOKEN|GITHUB_TOKEN|github\.token|secrets\.")


def test_the_trigger_is_exactly_a_push_to_main_that_changes_the_changelog():
    assert WF[True] == {"push": {"branches": ["main"], "paths": ["CHANGELOG.md"]}}     # PyYAML reads `on` as True
    for word in ("workflow_dispatch", "pull_request", "workflow_run", "schedule", "repository_dispatch", "merge_group"):
        assert word not in TEXT, word


def test_permissions_are_empty_at_workflow_level_and_contents_write_on_the_one_job():
    assert WF["permissions"] == {}
    assert list(WF["jobs"]) == ["release"]
    assert JOB["permissions"] == {"contents": "write"}
    assert TEXT.count("write") == 1 and "id-token" not in TEXT


def test_the_token_is_only_on_the_tag_step_and_the_release_step():
    assert not WF.get("env") and not JOB.get("env")
    holders = [s.get("name", s.get("uses")) for s in STEPS if TOKEN.search(str(s))]
    assert holders == [TAG["name"], RELEASE["name"]]
    for s in (TAG, RELEASE):
        assert s["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_every_action_is_pinned_by_full_sha_with_a_version_comment():
    uses = [s["uses"] for s in STEPS if "uses" in s]
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses
    for line in TEXT.splitlines():
        if "uses:" in line:
            assert re.search(r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), line


def test_the_checkout_is_the_pushed_commit_without_credentials():
    checkout = STEPS[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}


def test_no_run_text_holds_an_expression_and_version_and_sha_come_through_env():
    for s in STEPS:
        assert "${{" not in s.get("run", ""), s.get("name")
    for s in (NAME["exists"], TAG, RELEASE):
        assert s["env"]["VERSION"] == "${{ steps.notes.outputs.version }}"
    assert '"$GITHUB_SHA"' in TAG["run"]


def test_no_step_runs_pytest_or_pip():
    for s in STEPS:
        assert not re.search(r"\bpytest\b|\bpip3?\b|-m\s+pip\b|setup\.py|\bpoetry\b|\buv\s", s.get("run", "")), s.get("name")


def test_the_notes_step_runs_the_checkout_with_python_dash_p():
    run = NAME["notes"]["run"]
    assert "PYTHONPATH=src python -P -m sdlc_engine release-notes --changelog CHANGELOG.md --pyproject pyproject.toml --out notes.md" in run
    assert 'echo "version=$VERSION" >> "$GITHUB_OUTPUT"' in run


def test_the_steps_are_in_order_and_the_tag_and_release_only_run_when_the_tag_is_new():
    order = [s.get("id") or s.get("name") for s in STEPS]
    assert order.index("notes") < order.index("exists") < order.index(TAG["name"]) < order.index(RELEASE["name"])
    for s in (TAG, RELEASE):
        assert s["if"] == "steps.exists.outputs.exists == 'false'"
    assert "if" not in NAME["exists"] and "if" not in NAME["notes"]


def test_the_tag_step_pushes_only_that_annotated_tag_on_the_pushed_commit():
    run = TAG["run"]
    assert 'tag -a "v$VERSION" -m "v$VERSION" "$GITHUB_SHA"' in run
    pushes = [line for line in run.splitlines() if "git push" in line]
    assert len(pushes) == 1 and pushes[0].rstrip().endswith('"refs/tags/v$VERSION:refs/tags/v$VERSION"')
    assert "--force" not in run and " -f " not in run and "--tags" not in run and "--delete" not in run


def test_the_release_step_creates_the_release_from_the_verified_tag():
    assert 'gh release create "v$VERSION" --verify-tag --title "v$VERSION" --notes-file notes.md' in RELEASE["run"]


def run_exists(tmp_path, remote_output, fail=False):
    if not shutil.which("bash"):
        pytest.skip("needs bash")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "git").write_text("#!/bin/sh\n" + ("exit 2\n" if fail else f"printf '%s' '{remote_output}'\n"))
    (bin_ / "git").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "VERSION": "1.4.0",
           "GITHUB_OUTPUT": str(tmp_path / "out"), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    run = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", NAME["exists"]["run"]], env=env, capture_output=True, text=True)
    out = (tmp_path / "out").read_text() if (tmp_path / "out").exists() else ""
    return run, out


def test_an_existing_tag_stops_green_and_the_tag_and_release_steps_do_not_run(tmp_path):
    run, out = run_exists(tmp_path, "0123456789abcdef0123456789abcdef01234567\trefs/tags/v1.4.0")
    assert run.returncode == 0 and "already released" in run.stdout
    assert out == "exists=true\n"                    # so TAG and RELEASE, both `exists == 'false'`, are skipped
    assert "already released: v1.4.0" in (tmp_path / "summary").read_text()


def test_a_new_tag_goes_on_to_the_tag_and_release_steps(tmp_path):
    run, out = run_exists(tmp_path, "")
    assert run.returncode == 0 and out == "exists=false\n"


def test_a_failed_lookup_fails_the_job_and_never_tags_blind(tmp_path):
    run, out = run_exists(tmp_path, "", fail=True)
    assert run.returncode != 0 and "exists=" not in out


def test_one_release_job_at_a_time_and_none_is_cancelled():
    # D-006: two pushes to main that change the changelog close together queue in one group; a running release is
    # never cancelled halfway between its tag and its release.
    assert WF["concurrency"] == {"group": "release", "cancel-in-progress": False}
    assert "concurrency" not in JOB                         # workflow level: covers every run of this file
