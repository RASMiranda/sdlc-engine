"""D-004: the stage workflow is callable from another repository. Engine code comes from the called workflow's own
repository and commit (job.workflow_repository, job.workflow_sha), verified at run time; the project config comes from the
caller's trigger commit. Nothing reads config from the workspace root or the agent's branch. Parses the workflow; the verify
step is run for real against throwaway local git repositories. No network."""
import os
import re
import shutil
import subprocess

import pytest
import yaml

from engine_paths import STAGE_WORKFLOW

TEXT = STAGE_WORKFLOW.read_text(encoding="utf-8")
WF = yaml.safe_load(TEXT)
STEPS = WF["jobs"]["stage"]["steps"]
for _s in STEPS:
    _s.setdefault("name", _s.get("uses", ""))
NAMES = [s["name"] for s in STEPS]


def engine_checkouts():
    return [i for i, s in enumerate(STEPS) if str(s.get("uses", "")).startswith("actions/checkout@")
            and (s.get("with") or {}).get("path") == "engine"]


# ------------------------------------------------------------------------------------------------ permissions
def test_no_workflow_level_permissions_and_exactly_the_five_job_permissions():
    assert WF["permissions"] == {}
    assert WF["jobs"]["stage"]["permissions"] == {"contents": "write", "issues": "write", "pull-requests": "write",
                                                  "actions": "write", "id-token": "write"}
    assert TEXT.count("id-token") == 1                       # job level, claude-code-action, as before; nowhere else
    assert [k for k in WF["jobs"] if k != "stage"] == []     # one job: no other job could gain a permission


def test_there_is_no_engine_sha_input_anywhere():
    assert "engine_sha" not in TEXT and "engine-sha" not in TEXT.lower()
    assert set(WF[True]["workflow_call"]) == {"secrets"}      # PyYAML reads `on` as True; no inputs at all, one secret by name


# ------------------------------------------------------------------------------------------------- the engine checkouts
def test_every_engine_checkout_uses_the_called_workflows_repository_and_commit():
    found = engine_checkouts()
    assert len(found) == 4
    for i in found:
        s = STEPS[i]
        assert s["uses"] == "actions/checkout@v7"
        assert s["with"] == {"repository": "${{ job.workflow_repository }}", "ref": "${{ job.workflow_sha }}", "path": "engine",
                             "sparse-checkout": "src", "persist-credentials": False}, s["name"]


def test_the_first_engine_checkout_comes_before_decide_and_nothing_imports_the_engine_before_it():
    first = engine_checkouts()[0]
    assert first < NAMES.index("Decide what to run")
    for s in STEPS[:first]:
        assert "sdlc_engine" not in s.get("run", ""), s["name"]


def test_each_engine_checkout_is_followed_by_a_verify_step_that_takes_both_values_through_env():
    for i in engine_checkouts():
        verify = STEPS[i + 1]
        assert "verify the engine commit" in verify["name"], verify["name"]
        assert verify.get("if") == STEPS[i].get("if")
        assert verify["env"] == {"WORKFLOW_REPOSITORY": "${{ job.workflow_repository }}", "WORKFLOW_SHA": "${{ job.workflow_sha }}"}
        run = verify["run"]
        assert "${{" not in run and "job." not in run                     # nothing from the context in the script text
        assert 'git -C engine rev-parse HEAD' in run and '"$ENGINE_HEAD" != "$WORKFLOW_SHA"' in run and "exit 1" in run
        assert '>> "$GITHUB_STEP_SUMMARY"' in run and "$ENGINE_HEAD" in run.split("GITHUB_STEP_SUMMARY")[0].splitlines()[-1]


def make_engine(tmp_path, commits=2):
    """A throwaway repository at tmp_path/engine and the shas of its commits, oldest first."""
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    repo = tmp_path / "engine"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    g = lambda *a: subprocess.run(["git", *a], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    g("init", "-q")
    shas = []
    for n in range(commits):
        (repo / "f").write_text(str(n))
        g("add", "f")
        g("commit", "-q", "-m", str(n))
        shas.append(g("rev-parse", "HEAD"))
    return shas, env


def run_verify(tmp_path, sha, repo="owner/engine-repo"):
    verify = STEPS[engine_checkouts()[0] + 1]
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "WORKFLOW_REPOSITORY": repo,
           "WORKFLOW_SHA": sha, "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", verify["run"]], cwd=tmp_path, env=env, capture_output=True, text=True)


def test_the_verify_step_passes_on_the_called_commit_and_writes_the_sha_to_the_summary(tmp_path):
    shas, _ = make_engine(tmp_path)
    run = run_verify(tmp_path, shas[-1])
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "summary.md").read_text() == f"Engine: owner/engine-repo at {shas[-1]} (the called workflow's own repository and commit)\n"


@pytest.mark.parametrize("which", ["older commit", "empty", "short sha", "uppercase sha", "not a sha"])
def test_the_verify_step_fails_unless_the_checkout_is_exactly_the_called_commit(tmp_path, which):
    shas, _ = make_engine(tmp_path)
    value = {"older commit": shas[0], "empty": "", "short sha": shas[-1][:7], "uppercase sha": shas[-1].upper(),
             "not a sha": "main"}[which]
    run = run_verify(tmp_path, value)
    assert run.returncode == 1 and "::error title=Engine commit::" in run.stdout, (run.stdout, run.stderr)
    assert not (tmp_path / "summary.md").exists()


# ------------------------------------------------------------------------------------------ the config checkouts
def test_no_step_reads_config_from_the_workspace_or_the_agents_branch():
    runs = [(s["name"], s["run"]) for s in STEPS if "run" in s]
    config_args = [(name, m) for name, run in runs for m in re.findall(r"--config\s+(\S+)", run)]
    assert len(config_args) >= 15
    assert all(arg == '"$SDLC_CONFIG"' for _, arg in config_args), config_args
    assigned = [(name, line.strip()) for name, run in runs for line in run.splitlines() if "SDLC_CONFIG=" in line]
    assert len(assigned) == 4
    for name, line in assigned:
        assert line == 'echo "SDLC_CONFIG=$GITHUB_WORKSPACE/project-config/.github/sdlc-config.json" >> "$GITHUB_ENV"', name
    for name, run in runs:                                     # the path appears in run text only inside that assignment
        assert ".github/sdlc-config.json" not in run.replace(assigned[0][1], ""), name
    assert not [n for n, run in runs if "../.github" in run or "PYTHONPATH=src" in run]
    assert not [s["name"] for s in STEPS if "SDLC_CONFIG" in str(s.get("env", ""))]    # never set from a step's own env


def test_the_config_checkout_is_of_the_caller_at_the_trigger_commit_with_one_sparse_file():
    found = [s for s in STEPS if (s.get("with") or {}).get("path") == "project-config"]
    assert len(found) == 4
    for s in found:
        assert s["with"] == {"repository": "${{ github.repository }}", "ref": "${{ github.sha }}", "path": "project-config",
                             "sparse-checkout": ".github/sdlc-config.json", "sparse-checkout-cone-mode": False,
                             "persist-credentials": False}


def test_the_clear_steps_cover_engine_and_project_config_and_nothing_still_names_trusted():
    clears = [s for s in STEPS if s["name"].startswith("Trusted engine code") and "(1 of 5)" in s["name"]]
    assert len(clears) == 4
    for s in clears:
        assert "rm -rf engine project-config" in s["run"]
        assert "grep -qxF '/engine/' .git/info/exclude" in s["run"] and "echo '/engine/' >> .git/info/exclude" in s["run"]
        assert "grep -qxF '/project-config/' .git/info/exclude" in s["run"]
    assert not re.search(r"\btrusted/|rm -rf trusted|'/trusted/'", TEXT)


def test_the_checkout_of_the_callers_own_workspace_is_unchanged():
    first = STEPS[0]
    assert first["uses"] == "actions/checkout@v7" and first["with"] == {"fetch-depth": 0, "persist-credentials": False}
