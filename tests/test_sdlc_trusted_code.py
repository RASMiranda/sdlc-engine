"""ADR-036, D-004: every sdlc_engine step uses the engine code from the called workflow's own repository and commit
(the `engine` checkout), and the project config from the trigger commit (the `project-config` checkout), never code or
config from the agent's branch or from the caller's workspace. Parses the workflow file; no network, no git."""
import json
from pathlib import Path

import yaml
from engine_paths import ENGINE, FIXTURE, STAGE_WORKFLOW, sdlc_config_for, trusted_tree  # noqa: F401

WORKFLOW = STAGE_WORKFLOW  # S2: the stage job lives here
SECRETS = ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC", "CLAUDE_CODE_OAUTH_TOKEN")
STAGE_AGENTS = "Run the stage agents"
REVIEW_AGENTS = "Run the review agents"
LOAD = "Trusted engine code"
ALWAYS = "always() && steps.d.outputs.run == 'true'"
ENGINE_WITH = {"repository": "${{ job.workflow_repository }}", "ref": "${{ job.workflow_sha }}", "path": "engine",
               "sparse-checkout": "src", "persist-credentials": False}
CONFIG_WITH = {"repository": "${{ github.repository }}", "ref": "${{ github.sha }}", "path": "project-config",
               "sparse-checkout": ".github/sdlc-config.json", "sparse-checkout-cone-mode": False,
               "persist-credentials": False}
PRE_DECIDE, PRE_AGENT, POST_AGENT, POST_REVIEW = ("Trusted engine code, before decide", "Trusted engine code, before the agent",
                                                  "Trusted engine code, after the stage agents",
                                                  "Trusted engine code, again after the reviewers")


def steps():
    sts = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return sts


def names():
    return [s["name"] for s in steps()]


def idx(prefix):
    return [i for i, n in enumerate(names()) if n.startswith(prefix)]


def after(agent_name):
    return steps()[names().index(agent_name) + 1:]


def test_every_sdlc_engine_call_after_the_stage_agents_uses_the_trusted_copy_without_the_cwd():
    calls = [s for s in after(STAGE_AGENTS) if "sdlc_engine" in s.get("run", "") and "python" in s["run"]]
    assert calls
    for s in calls:
        assert 'PYTHONPATH="$TRUSTED_SRC"' in s["run"] and "python -P" in s["run"], s["name"]
        assert "PYTHONPATH=src" not in s["run"], s["name"]
    for s in after(STAGE_AGENTS):
        assert "PYTHONPATH=src" not in s.get("run", ""), s["name"]


BRANCH_CHECKOUT = "Check out the issue's branch"
SKIP_STEP = "Skip a stage whose output is already on the branch (ADR-057)"
FRAME_STEP = "Frame the issue as untrusted input and write the stage prompt"


def test_the_decide_and_budget_steps_use_the_engine_checkout_not_the_workspace_src():
    # Before: they ran `PYTHONPATH=src python` from the caller's workspace, trusted only because it was the trigger commit,
    # and a consumer has no src. Now they run the engine checkout, loaded by the group before them, with `python -P`.
    n = names()
    decide, budget = n.index("Decide what to run"), idx("Budget gate")[0]
    load_use = n.index(f"{PRE_DECIDE} (5 of 5) use it (ADR-036, D-004)")
    assert load_use < decide < budget < n.index(BRANCH_CHECKOUT)
    for i in (decide, budget):
        run = steps()[i]["run"]
        assert 'PYTHONPATH="$TRUSTED_SRC" python -P -m sdlc_engine' in run, n[i]
        assert "PYTHONPATH=src" not in run and "PYTHONPATH=src" not in str(steps()[i].get("env", "")), n[i]
    assert not [s["name"] for s in steps() if "PYTHONPATH=src" in s.get("run", "")]      # nowhere in the workflow


def test_no_helper_between_the_branch_checkout_and_the_agent_imports_the_branch_src():
    # ADR-036 (i.F9): after `git checkout` the working tree is the issue's branch, which an agent wrote. A `run:` step
    # there must import from the trusted copy, never from `src` in the working tree.
    n = names()
    window = steps()[n.index(BRANCH_CHECKOUT) + 1:n.index(STAGE_AGENTS)]
    assert window, "the checkout and the agent step are not in the expected order"
    for s in window:
        assert "PYTHONPATH=src" not in s.get("run", ""), s["name"]
        assert "PYTHONPATH=src" not in str(s.get("env", "")), s["name"]
    assert any(s["name"] in (SKIP_STEP, FRAME_STEP) for s in window)     # the helpers are still there, just trusted


def group(prefix):
    """The five steps of one load, in order: clear, engine checkout, verify, config checkout, use it."""
    found = [steps()[i] for i in range(len(steps())) if names()[i].startswith(prefix + " (")]
    assert [s["name"][len(prefix) + 2:len(prefix) + 8] for s in found] == [f"{k} of 5" for k in range(1, 6)], prefix
    first = names().index(found[0]["name"])
    assert names()[first:first + 5] == [s["name"] for s in found]            # nothing sits between the five
    return found


def test_the_pre_agent_trusted_load_sits_right_after_the_branch_checkout_and_before_the_skip_step():
    n = names()
    clear, engine, verify, conf, use = group(PRE_AGENT)
    c, u = n.index(clear["name"]), n.index(use["name"])
    assert n.index(BRANCH_CHECKOUT) < c < u < n.index(SKIP_STEP)
    assert n[c - 1] == BRANCH_CHECKOUT and n[u + 1] == "Check the stage's input exists (the gate before it)"
    assert n.index(SKIP_STEP) < n.index(FRAME_STEP) < n.index(STAGE_AGENTS)
    assert "rm -rf engine project-config" in clear["run"] and "/engine/" in clear["run"] and "/project-config/" in clear["run"]
    assert ".git/info/exclude" in clear["run"] and "trusted" not in clear["run"]
    assert "test -f engine/src/sdlc_engine/__init__.py" in use["run"]
    assert 'echo "TRUSTED_SRC=$GITHUB_WORKSPACE/engine/src" >> "$GITHUB_ENV"' in use["run"]


def test_the_pre_agent_checkouts_have_the_same_parameters_as_the_other_loads():
    for prefix in (PRE_DECIDE, PRE_AGENT, POST_AGENT, POST_REVIEW):
        _, engine, _, conf, _ = group(prefix)
        assert engine["uses"] == conf["uses"] == "actions/checkout@v7", prefix
        assert engine["with"] == ENGINE_WITH and conf["with"] == CONFIG_WITH, prefix


def test_the_helpers_before_the_agent_use_the_trusted_src_with_python_dash_p():
    # The helpers import only src/ (stdlib otherwise); -P keeps the working directory off sys.path, so a file the agent
    # planted in the workspace cannot shadow the package.
    for s in steps()[names().index(BRANCH_CHECKOUT) + 1:names().index(STAGE_AGENTS)]:
        for line in s.get("run", "").splitlines():
            if "-m sdlc_engine" in line:
                assert 'PYTHONPATH="$TRUSTED_SRC" python -P -m sdlc_engine' in line, (s["name"], line)


def test_the_engine_and_config_are_checkouts_of_pinned_commits_and_never_git_archive():
    text = WORKFLOW.read_text()
    assert "git archive" not in text
    checkouts = [s for s in steps() if s["name"].startswith(LOAD) and "uses" in s]
    assert len(checkouts) == 8              # four loads: before decide, before the agent, after each of the two agent runs
    for s in checkouts:
        assert s["uses"] == "actions/checkout@v7"   # bumped to Node 24 (ADR-057 item i.F5e)
        assert s["with"] in (ENGINE_WITH, CONFIG_WITH), s["name"]
        assert not s.get("env")
        # every load runs always() once the decision says the run goes on; the first has no decision yet and no condition
        assert s.get("if") == (None if s["name"].startswith(PRE_DECIDE) else ALWAYS), s["name"]
    assert sum(s["with"]["path"] == "engine" for s in checkouts) == sum(s["with"]["path"] == "project-config" for s in checkouts) == 4


def test_each_trusted_load_follows_its_agent_run_and_precedes_the_steps_that_import_sdlc_engine():
    n = names()
    c1, u1 = n.index(group(POST_AGENT)[0]["name"]), n.index(group(POST_AGENT)[4]["name"])
    c2, u2 = n.index(group(POST_REVIEW)[0]["name"]), n.index(group(POST_REVIEW)[4]["name"])
    assert n.index(STAGE_AGENTS) < c1 < u1 < n.index("Check what the agent changed")
    assert u1 < idx("Commit and push")[0] < n.index(REVIEW_AGENTS)
    # the second load comes after both agent runs, before the reviewer check and the post step
    assert n.index(REVIEW_AGENTS) < c2 < u2 < n.index("Reject any change the reviewers made") < idx("Post the report")[0]
    # a clear step runs right before its checkout, and the folders are hidden from git status
    assert n[c1 + 1].startswith(f"{POST_AGENT} (2 of 5)") and n[c2 + 1].startswith(f"{POST_REVIEW} (2 of 5)")
    for i in (c1, c2):
        assert "rm -rf engine project-config" in steps()[i]["run"] and ".git/info/exclude" in steps()[i]["run"]
        assert "trusted" not in steps()[i]["run"]


def test_the_load_steps_have_no_token():
    for s in steps():
        if s["name"].startswith(LOAD):
            assert not [k for k in (s.get("env") or {}) if any(x in k for x in SECRETS)], s["name"]
            assert "GH_TOKEN" not in str(s) and "secrets." not in str(s) and "github.token" not in str(s)


def test_the_use_step_exports_the_src_of_the_engine_checkout_and_the_config_of_the_project_checkout():
    uses = [s for s in steps() if s["name"].startswith(LOAD) and "(5 of 5)" in s["name"]]
    assert len(uses) == 4
    for s in uses:
        assert 'echo "TRUSTED_SRC=$GITHUB_WORKSPACE/engine/src" >> "$GITHUB_ENV"' in s["run"]
        assert 'echo "SDLC_CONFIG=$GITHUB_WORKSPACE/project-config/.github/sdlc-config.json" >> "$GITHUB_ENV"' in s["run"]
        assert "test -f engine/src/sdlc_engine/__init__.py" in s["run"]


def test_every_token_step_after_the_stage_agents_that_imports_sdlc_engine_runs_after_a_trusted_load():
    start = names().index(STAGE_AGENTS)
    for i, s in enumerate(steps()):
        if i > start and "GH_TOKEN" in (s.get("env") or {}) and "sdlc_engine" in s.get("run", ""):
            assert any(n.startswith(LOAD) for n in names()[:i]), s["name"]
            assert 'PYTHONPATH="$TRUSTED_SRC"' in s["run"], s["name"]


# ------------------------------------------------ the pre-agent helpers, run through their real shell (i.F9)
def _shell(step_run, cwd, extra):
    import os
    import shutil
    import subprocess

    import pytest
    if not shutil.which("bash"):
        pytest.skip("needs bash")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}     # the step must not depend on a PYTHONPATH=src
    env.update({"TRUSTED_SRC": str(trusted_tree(cwd.parent, name=f"trusted-{cwd.name}")),
                "SDLC_CONFIG": str(sdlc_config_for(trusted_tree(cwd.parent, name=f"trusted-{cwd.name}"))), "GITHUB_ENV": str(cwd / "github.env"),
                "GITHUB_OUTPUT": str(cwd / "github.out"), "NUMBER": "7", **extra})
    return subprocess.run(["bash", "-e", "-c", step_run], cwd=cwd, env=env, capture_output=True, text=True)


def _decision_and_branch(cwd, stage_file=None):
    import sdlc_engine as sdlc
    event = {"action": "labeled", "sender": {"type": "User", "login": "o"}, "label": {"name": "agent:spec"},
             "issue": {"number": 7, "title": "Add a thing", "body": "", "state": "open", "locked": False,
                       "author_association": "OWNER", "labels": []}}
    (cwd / ".sdlc").mkdir(exist_ok=True)
    (cwd / ".sdlc" / "decision.json").write_text(json.dumps(sdlc.decide(event, ["agent/7-add-a-thing"])))
    if stage_file:
        (cwd / "docs/intents/7-add-a-thing").mkdir(parents=True, exist_ok=True)
        (cwd / "docs/intents/7-add-a-thing" / stage_file).write_text("x")
    return event


def test_the_skip_step_runs_for_real_from_the_trusted_src_and_stops_only_when_the_file_is_on_the_branch(tmp_path):
    import sdlc_engine as sdlc
    skip = next(s for s in steps() if s["name"] == SKIP_STEP)
    _decision_and_branch(tmp_path, stage_file="spec.md")
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert (tmp_path / ".sdlc" / "comment.md").read_text().splitlines() == [
        sdlc.skip_line("spec", "docs/intents/7-add-a-thing/spec.md")]
    assert "stop=true" in (tmp_path / "github.env").read_text() and "skipped=true" in (tmp_path / "github.env").read_text()
    (tmp_path / "docs/intents/7-add-a-thing/spec.md").unlink()
    (tmp_path / "github.env").unlink()
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert not (tmp_path / ".sdlc" / "comment.md").exists() and not (tmp_path / "github.env").exists()


def test_the_frame_step_writes_the_issue_and_the_prompt_for_real_from_the_trusted_src(tmp_path):
    frame = next(s for s in steps() if s["name"].startswith("Frame the issue"))
    event = _decision_and_branch(tmp_path)
    (tmp_path / "event.json").write_text(json.dumps(event))
    (tmp_path / ".sdlc" / "comments.json").write_text("[]")
    (tmp_path / ".sdlc" / "pr-comments.json").write_text("[]")
    run = _shell(frame["run"], tmp_path, {"GITHUB_EVENT_PATH": str(tmp_path / "event.json")})
    assert run.returncode == 0, run.stderr
    assert (tmp_path / ".sdlc" / "issue.md").is_file() and (tmp_path / ".sdlc" / "prompt.md").is_file()


def test_a_planted_sdlc_engine_package_in_the_workspace_is_not_imported_by_the_pre_agent_helpers(tmp_path):
    # `python -P` keeps the working directory off sys.path. Without it, this file would shadow the trusted package.
    skip = next(s for s in steps() if s["name"] == SKIP_STEP)
    (tmp_path / "sdlc_engine").mkdir()
    (tmp_path / "sdlc_engine" / "__init__.py").write_text("raise SystemExit('the workspace copy was imported')\n")
    _decision_and_branch(tmp_path, stage_file="spec.md")
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert "shadow" not in run.stderr and (tmp_path / ".sdlc" / "comment.md").exists()
