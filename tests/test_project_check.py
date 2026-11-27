"""D-004: `python -m sdlc_engine check-project --root DIR`. Fixtures only: tmp_path copies of tests/fixture-project, no
network. The checked-in fixture caller uses `./`, so it must fail the pin rule and nothing else; the positive cases
rewrite its `uses:` line in the copy."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml

import sdlc_engine as sdlc
from sdlc_engine import config, project_check
from sdlc_engine.project_check import ENGINE_REPO, ISSUE_EVENT_TYPES, YamlError, check_project, read_yaml
from engine_paths import ENGINE, FIXTURE

SHA = "0123456789abcdef0123456789abcdef01234567"
GOOD = f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@{SHA}"
CALLER = ".github/workflows/sdlc.yml"
CONFIG = ".github/sdlc-config.json"


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    return root


def set_uses(root, uses):
    path = root / CALLER
    text, n = re.subn(r"^(\s*uses:) .*$", lambda m: f"{m.group(1)} {uses}", path.read_text(), flags=re.M)
    assert n == 1
    path.write_text(text)


def edit(root, rel, old, new, count=1):
    path = root / rel
    text = path.read_text()
    assert old in text, (rel, old)
    path.write_text(text.replace(old, new, count))


def edit_config(root, fn):
    path = root / CONFIG
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data, indent=2))


@pytest.fixture
def ok(proj):
    set_uses(proj, GOOD)
    return proj


# ------------------------------------------------------------------------------------------------ the whole command
def test_the_checked_in_fixture_fails_the_pin_rule_and_only_that_rule():
    problems = check_project(FIXTURE)
    assert len(problems) == 1 and problems[0].startswith("pin: "), problems
    assert "'./.github/workflows/sdlc-stage.yml'" in problems[0]


def test_a_pinned_copy_of_the_fixture_has_no_problem(ok):
    assert check_project(ok) == []


def cli(root):
    env = {**os.environ, "PYTHONPATH": str(ENGINE / "src")}
    return subprocess.run([sys.executable, "-m", "sdlc_engine", "check-project", "--root", str(root)], capture_output=True,
                          text=True, env=env, cwd=ENGINE)


def test_the_command_exits_1_with_exactly_the_pin_message_on_the_fixture():
    run = cli(FIXTURE)
    assert run.returncode == 1 and run.stdout == ""
    assert run.stderr.splitlines() == check_project(FIXTURE) and len(run.stderr.splitlines()) == 1


def test_the_command_exits_0_on_a_pinned_copy(ok):
    run = cli(ok)
    assert run.returncode == 0 and run.stderr == "" and run.stdout.startswith("ok: ")


def test_the_command_exits_1_for_a_root_that_is_not_a_folder(tmp_path):
    run = cli(tmp_path / "nope")
    assert run.returncode == 1 and "is not a directory" in run.stderr


def test_one_message_per_failure_each_naming_its_rule(ok):
    edit_config(ok, lambda d: d.update(config_version=9))
    set_uses(ok, "./.github/workflows/sdlc-stage.yml")
    edit(ok, CALLER, "secrets:\n      CLAUDE_CODE_OAUTH_TOKEN", "secrets:\n      OTHER", 1)
    assert [m.split(":")[0] for m in check_project(ok)] == ["config", "pin", "secrets", "secrets"]


# --------------------------------------------------------------------------------------------------------- reserved
@pytest.mark.parametrize("name", ["engine", "project-config"])
@pytest.mark.parametrize("kind", ["folder", "file", "empty folder"])
def test_a_reserved_name_in_the_project_root_is_one_failure(ok, name, kind):
    if kind == "file":
        (ok / name).write_text("x")
    else:
        (ok / name).mkdir()
        if kind == "folder":
            (ok / name / "f").write_text("x")
    assert check_project(ok) == [f"reserved: {name}/ exists in the project root; the stage workflow deletes and re-creates it (D-004)"]


def test_both_reserved_names_are_two_failures_and_neither_is_none(ok):
    assert [m for m in check_project(ok) if m.startswith("reserved")] == []
    (ok / "engine").mkdir()
    (ok / "project-config").write_text("x")
    assert [m.split("/")[0] for m in check_project(ok)] == ["reserved: engine", "reserved: project-config"]


def test_a_dangling_link_with_a_reserved_name_is_a_failure(ok):
    (ok / "engine").symlink_to(ok / "nowhere")
    assert len(check_project(ok)) == 1 and check_project(ok)[0].startswith("reserved: engine/")


def test_the_fixture_and_the_template_hold_no_reserved_name():
    for root in (FIXTURE, ENGINE / "template"):
        assert not [m for m in check_project(root) if m.startswith("reserved")], root


# ------------------------------------------------------------------------------------------------------------ config
def test_a_missing_config_file_is_one_failure(ok):
    (ok / CONFIG).unlink()
    assert check_project(ok) == [f"config: {CONFIG} is missing"]


def test_a_config_that_is_not_json_is_one_failure(ok):
    (ok / CONFIG).write_text("{ nope")
    problems = check_project(ok)
    assert len(problems) == 1 and problems[0].startswith(f"config: {CONFIG} cannot be read as JSON")


@pytest.mark.parametrize("version", [0, 2, "1", 1.0, True, None, [1]])
def test_an_unknown_config_version_is_named_clearly(ok, version):
    edit_config(ok, lambda d: d.update(config_version=version))
    problems = check_project(ok)
    assert len(problems) == 1 and "config_version" in problems[0] and "is not supported" in problems[0], problems
    assert "reads version 1 only" in problems[0]


def test_a_missing_config_version_is_named_clearly(ok):
    edit_config(ok, lambda d: d.pop("config_version"))
    problems = check_project(ok)
    assert len(problems) == 1 and "config_version is missing" in problems[0] and '"config_version": 1' in problems[0]


def test_a_missing_required_key_is_a_failure(ok):
    edit_config(ok, lambda d: d.pop("model"))
    problems = check_project(ok)
    assert problems == [f"config: {CONFIG}: the file lacks model"]


@pytest.mark.parametrize("name,change,expected", [
    ("limits not whole numbers", lambda d: d["limits"].update(max_files="ten"), "limits must hold whole numbers"),
    ("model not text", lambda d: d.update(model=3), "model must be a non-empty string"),
    ("stages not an object", lambda d: d.update(stages=[]), "stages must be a non-empty object"),
    ("turns zero", lambda d: d["stages"]["build"].update(turns=0), "turns must be a whole number of at least 1"),
    ("trusted_associations text", lambda d: d.update(trusted_associations="OWNER"), "trusted_associations must be a list"),
])
def test_a_wrong_type_is_a_failure(ok, name, change, expected):
    edit_config(ok, change)
    problems = check_project(ok)
    assert any(expected in p for p in problems) and all(p.startswith(f"config: {CONFIG}: ") for p in problems), problems


def test_the_checker_reuses_the_engines_own_validator_not_a_second_key_list(ok):
    assert project_check.config is config
    data = json.loads((ok / CONFIG).read_text())
    assert config.problems_in(data) == []
    edit_config(ok, lambda d: d.update(surprise=1))
    assert check_project(ok) == [f"config: {CONFIG}: the file has unknown key(s) surprise"]


def test_a_config_failure_does_not_hide_the_pin_and_secrets_rules(proj):
    (proj / CONFIG).unlink()
    assert [m.split(":")[0] for m in check_project(proj)] == ["config", "pin"]


# ------------------------------------------------------------------------------------------------------------- roles
def test_a_stage_role_without_its_agent_file_is_a_failure(ok):
    (ok / ".claude" / "agents" / "tester.md").unlink()
    problems = check_project(ok)
    assert problems and all(p.startswith("roles: ") and "'tester'" in p and ".claude/agents/tester.md is missing" in p for p in problems)
    cfg = json.loads((ok / CONFIG).read_text())
    assert len(problems) == sum("tester" in spec["roles"] for spec in cfg["stages"].values())


def test_a_role_that_is_a_path_is_a_failure(ok):
    edit_config(ok, lambda d: d["stages"]["intent"].update(roles=["../x"]))
    assert check_project(ok) == ["roles: stage 'intent' names the role '../x', which is not a file name"]


# ------------------------------------------------------------------------------------------------------------ caller
def test_a_missing_caller_is_one_failure(ok):
    (ok / CALLER).unlink()
    assert check_project(ok) == [f"caller: {CALLER} is missing"]


def test_a_label_list_that_differs_from_the_config_is_a_failure(ok):
    edit(ok, CALLER, '"agent:build",', "", count=1)             # the first of the two copies: the concurrency group
    problems = check_project(ok)
    assert len(problems) == 1 and "concurrency.group lists the labels" in problems[0] and "'agent:build'" in problems[0]
    edit(ok, CALLER, '"agent:build",', "", count=1)             # now the job `if` too
    assert len(check_project(ok)) == 2


def test_a_config_label_the_caller_lacks_is_a_failure(ok):
    edit_config(ok, lambda d: (d["label_to_stage"].update({"agent:extra": "build"})))
    problems = check_project(ok)
    assert len(problems) == 2 and all("lists the labels" in p and "agent:extra" in p for p in problems)


def test_an_author_association_list_that_differs_is_a_failure(ok):
    edit(ok, CALLER, '"COLLABORATOR",', "", count=2)
    problems = check_project(ok)
    assert len(problems) == 2 and all("lists the author associations" in p and "COLLABORATOR" in p for p in problems)


@pytest.mark.parametrize("types", ["[opened]", "[opened, labeled, edited]", "[labeled]", "[opened, reopened]"])
def test_event_types_that_differ_from_the_engines_constant_are_a_failure(ok, types):
    edit(ok, CALLER, "types: [opened, labeled]", f"types: {types}")
    problems = check_project(ok)
    assert len(problems) == 1 and "on.issues.types" in problems[0] and "['labeled', 'opened']" in problems[0]


def test_event_types_may_be_written_as_a_block_list(ok):
    edit(ok, CALLER, "types: [opened, labeled]", "types:\n      - labeled\n      - opened")
    assert check_project(ok) == []


def test_a_caller_without_a_stage_job_is_a_failure(ok):
    edit(ok, CALLER, "  stage:\n", "  other:\n")
    assert check_project(ok) == [f"caller: {CALLER} has no job named 'stage'"]


def test_a_caller_outside_the_readable_subset_is_a_failure_not_a_guess(ok):
    edit(ok, CALLER, f"    uses: {GOOD}", f"    uses: &pin {GOOD}")
    problems = check_project(ok)
    assert len(problems) == 1 and problems[0].startswith(f"caller: {CALLER} cannot be read: ")


def test_the_event_types_constant_is_exactly_the_actions_decide_starts_a_stage_on():
    assert ISSUE_EVENT_TYPES == {"opened", "labeled"}

    def runs(action):
        issue = {"number": 1, "title": "t", "state": "open", "locked": False, "author_association": "OWNER", "labels": []}
        ev = {"action": action, "issue": issue, "sender": {"type": "User", "login": "o"}, "label": {"name": "agent:intent"}}
        return sdlc.decide(ev, [])["run"]
    every = ["opened", "labeled", "edited", "reopened", "closed", "assigned", "unlabeled", "deleted", "transferred", "pinned"]
    assert {a for a in every if runs(a)} == ISSUE_EVENT_TYPES


# ---------------------------------------------------------------------------------------------------------- triggers
OTHER_EVENTS = {
    "workflow_dispatch": "  workflow_dispatch:\n",
    "pull_request": "  pull_request:\n    types: [opened]\n",
    "pull_request_target": "  pull_request_target:\n    types: [opened]\n",
    "pull_request_review": "  pull_request_review:\n",
    "pull_request_review_comment": "  pull_request_review_comment:\n",
    "push": "  push:\n    branches: [main]\n",
    "schedule": "  schedule:\n    - cron: '0 0 * * *'\n",
    "workflow_run": "  workflow_run:\n    workflows: [tests]\n",
    "workflow_call": "  workflow_call:\n",
    "repository_dispatch": "  repository_dispatch:\n",
    "issue_comment": "  issue_comment:\n    types: [created]\n",
    "release": "  release:\n    types: [published]\n",
    "merge_group": "  merge_group:\n",
    "discussion": "  discussion:\n",
}


def test_issues_alone_passes_the_triggers_rule(ok):
    assert check_project(ok) == []
    assert read_yaml((ok / CALLER).read_text())["on"].keys() == {"issues"}


@pytest.mark.parametrize("event", sorted(OTHER_EVENTS))
def test_any_other_event_next_to_issues_is_one_triggers_failure(ok, event):
    edit(ok, CALLER, "on:\n", "on:\n" + OTHER_EVENTS[event])
    assert check_project(ok) == [f"triggers: {CALLER} on: has {event!r}; the caller must be triggered by issues only"]


@pytest.mark.parametrize("event", sorted(OTHER_EVENTS))
def test_any_other_event_after_issues_is_caught_too(ok, event):
    edit(ok, CALLER, "    types: [opened, labeled]\n", "    types: [opened, labeled]\n" + OTHER_EVENTS[event])
    assert check_project(ok) == [f"triggers: {CALLER} on: has {event!r}; the caller must be triggered by issues only"]


def test_two_other_events_are_two_failures(ok):
    edit(ok, CALLER, "on:\n", "on:\n" + OTHER_EVENTS["push"] + OTHER_EVENTS["workflow_dispatch"])
    assert [m for m in check_project(ok) if m.startswith("triggers")] == [
        f"triggers: {CALLER} on: has 'push'; the caller must be triggered by issues only",
        f"triggers: {CALLER} on: has 'workflow_dispatch'; the caller must be triggered by issues only"]


def test_a_caller_without_issues_fails_the_triggers_rule(ok):
    edit(ok, CALLER, "  issues:\n    types: [opened, labeled]\n", "  workflow_dispatch:\n")
    problems = check_project(ok)
    assert f"triggers: {CALLER} on: has no issues key; the caller must be triggered by issues only" in problems
    assert f"triggers: {CALLER} on: has 'workflow_dispatch'; the caller must be triggered by issues only" in problems


@pytest.mark.parametrize("on", ["on: issues\n", "on: [issues, push]\n", "on: [issues]\n"])
def test_on_that_is_not_a_mapping_fails_the_triggers_rule(ok, on):
    edit(ok, CALLER, "on:\n  issues:\n    types: [opened, labeled]\n", on)
    problems = [m for m in check_project(ok) if m.startswith("triggers")]
    assert len(problems) == 1 and "it must be a mapping whose only key is issues" in problems[0]


def test_the_fixture_and_the_template_callers_pass_the_triggers_rule():
    for root in (FIXTURE, ENGINE / "template"):
        assert not [m for m in check_project(root) if m.startswith("triggers")], root


# --------------------------------------------------------------------------------------------------------------- pin
@pytest.mark.parametrize("name,uses", [
    ("a tag", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@v1"),
    ("a branch", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@main"),
    ("a short sha", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@{SHA[:7]}"),
    ("39 hex", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@{SHA[:39]}"),
    ("41 hex", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@{SHA}a"),
    ("upper case hex", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml@{SHA.upper()}"),
    ("no ref", f"{ENGINE_REPO}/.github/workflows/sdlc-stage.yml"),
    ("a local path", "./.github/workflows/sdlc-stage.yml"),
    ("another repository", f"someone/else/.github/workflows/sdlc-stage.yml@{SHA}"),
    ("another workflow file", f"{ENGINE_REPO}/.github/workflows/other.yml@{SHA}"),
    ("a lookalike repository", f"{ENGINE_REPO}-fork/.github/workflows/sdlc-stage.yml@{SHA}"),
    ("the placeholder", f"<ENGINE_OWNER>/sdlc-engine/.github/workflows/sdlc-stage.yml@<FULL_40_HEX_COMMIT_SHA>"),
])
def test_anything_but_the_engine_workflow_at_a_full_lowercase_sha_fails_the_pin_rule(ok, name, uses):
    set_uses(ok, uses)
    problems = check_project(ok)
    assert len(problems) == 1 and problems[0].startswith("pin: "), (name, problems)


def test_a_pin_with_a_version_comment_passes(ok):
    set_uses(ok, f"{GOOD} # v0.2.0")
    assert check_project(ok) == []


def test_a_quoted_pin_passes(ok):
    set_uses(ok, f'"{GOOD}"')
    assert check_project(ok) == []


def test_the_template_caller_fails_the_pin_rule_until_the_placeholder_is_filled_in(tmp_path):
    root = tmp_path / "t"
    shutil.copytree(ENGINE / "template", root)
    problems = check_project(root)
    assert len(problems) == 1 and problems[0].startswith("pin: ") and "<ENGINE_OWNER>" in problems[0]
    set_uses(root, GOOD)
    assert check_project(root) == []


# ----------------------------------------------------------------------------------------------------------- secrets
def test_secrets_inherit_is_a_failure(ok):
    edit(ok, CALLER, "    secrets:\n      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", "    secrets: inherit")
    problems = check_project(ok)
    assert len(problems) == 1 and problems[0].startswith("secrets: ") and "secrets: inherit is not allowed" in problems[0]


def test_a_renamed_secret_is_a_failure(ok):
    edit(ok, CALLER, "      CLAUDE_CODE_OAUTH_TOKEN: ${{", "      OTHER_TOKEN: ${{")
    problems = check_project(ok)
    assert len(problems) == 2 and "passes 'OTHER_TOKEN'" in problems[0] and "does not pass CLAUDE_CODE_OAUTH_TOKEN" in problems[1]


def test_the_right_name_with_another_secrets_value_is_a_failure(ok):
    edit(ok, CALLER, "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", "${{ secrets.OTHER }}")
    problems = check_project(ok)
    assert len(problems) == 1 and "passes CLAUDE_CODE_OAUTH_TOKEN as '${{ secrets.OTHER }}'" in problems[0]


def test_a_literal_value_is_a_failure(ok):
    edit(ok, CALLER, "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", "not-a-real-value")
    problems = check_project(ok)
    assert len(problems) == 1 and "as 'not-a-real-value'" in problems[0]


def test_an_extra_secret_next_to_the_right_one_is_a_failure(ok):
    edit(ok, CALLER, "      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}",
         "      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n      EXTRA: ${{ secrets.EXTRA }}")
    problems = check_project(ok)
    assert len(problems) == 1 and "passes 'EXTRA'" in problems[0] and "only CLAUDE_CODE_OAUTH_TOKEN may be passed" in problems[0]


def test_no_secrets_at_all_is_a_failure(ok):
    edit(ok, CALLER, "    secrets:\n      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n", "")
    problems = check_project(ok)
    assert len(problems) == 1 and problems[0].startswith("secrets: ") and "passes no secrets" in problems[0]


def test_the_secret_value_may_have_other_spacing_inside_the_braces(ok):
    edit(ok, CALLER, "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}", "${{secrets.CLAUDE_CODE_OAUTH_TOKEN}}")
    assert check_project(ok) == []


# ----------------------------------------------------------- the small YAML reader agrees with PyYAML where it is used
def normal(value):
    """PyYAML's value with scalars as text and `on` as "on", the way the small reader gives it."""
    if isinstance(value, dict):
        return {("on" if k is True else str(k)): normal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normal(v) for v in value]
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@pytest.mark.parametrize("path", [FIXTURE / CALLER, ENGINE / "template" / CALLER, FIXTURE / ".github/workflows/tests.yml",
                                  ENGINE / ".github/workflows/tests.yml"],
                         ids=lambda p: str(p.relative_to(ENGINE)))
def test_the_reader_gives_what_pyyaml_gives_for_the_workflow_files_a_project_has(path):
    text = path.read_text()
    assert read_yaml(text) == normal(yaml.safe_load(text))


def test_the_reader_handles_the_shapes_a_caller_uses():
    doc = read_yaml("on:\n  issues:\n    types: [opened, 'labeled']  # c\nx: {a: 1, b: \"two\"}\nlist:\n- a\n- b: c\n  d: e\nempty:\n"
                    "note: it's # a comment\nblock: |\n  not # read\n  a: b\nafter: 1\n")
    assert doc == {"on": {"issues": {"types": ["opened", "labeled"]}}, "x": {"a": "1", "b": "two"},
                   "list": ["a", {"b": "c", "d": "e"}], "empty": None, "note": "it's", "block": "<text block>", "after": "1"}


@pytest.mark.parametrize("text", ["a: 1\na: 2\n", "a: &x 1\n", "a: *x\n", "a: !tag 1\n", "a:\n\tb: 1\n", "a: [1,\n  2]\n",
                                  "a: one\n  two\n", "a: 1\n b: 2\n", "", "just text\n"])
def test_the_reader_refuses_what_it_does_not_understand(text):
    with pytest.raises(YamlError):
        read_yaml(text)


# ------------------------------------------------------------------------------------------------- config_version
def test_the_template_and_the_fixture_carry_config_version_1_and_load():
    for root in (ENGINE / "template", FIXTURE):
        data = json.loads((root / CONFIG).read_text())
        assert data["config_version"] == config.CONFIG_VERSION == 1
        assert config.load(root / CONFIG) is not None


@pytest.mark.parametrize("version,message", [(None, "config_version is missing"), (2, "config_version 2 is not supported"),
                                             ("1", "config_version '1' is not supported"), (True, "config_version True is not supported")])
def test_config_load_fails_with_a_clear_message_on_a_missing_or_unknown_version(tmp_path, version, message):
    data = json.loads((FIXTURE / CONFIG).read_text())
    data.pop("config_version")
    if version is not None:
        data["config_version"] = version
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data))
    with pytest.raises(config.ConfigError) as err:
        config.load(path)
    assert message in str(err.value) and "reads version 1 only" in str(err.value)


def test_the_engine_stops_on_a_config_without_a_version_instead_of_running(tmp_path):
    data = json.loads((FIXTURE / CONFIG).read_text())
    data.pop("config_version")
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data))
    with pytest.raises(config.ConfigError):
        sdlc.main(["--config", str(path), "scan"])
