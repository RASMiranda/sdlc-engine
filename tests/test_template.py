"""The template is what a new project copies. These tests keep it valid, in step with the fixture and the docs, and pinned."""
import json
import re
from pathlib import Path

import pytest
import yaml

import sdlc_engine as sdlc
from sdlc_engine import budget, config
from engine_paths import ENGINE, FIXTURE
from test_guard_engine import SOURCE_REPO

TEMPLATE = ENGINE / "template"
SHA_USE = re.compile(r"^\s*-?\s*uses:\s*(\S+)@([0-9a-f]{40})\s+#\s*v\d+\.\d+\.\d+\s*$")
ENGINE_WORKFLOWS = [ENGINE / ".github" / "workflows" / "tests.yml"]
TEMPLATE_WORKFLOWS = sorted((TEMPLATE / ".github" / "workflows").glob("*.yml"))


def template_config():
    return json.loads((TEMPLATE / ".github" / "sdlc-config.json").read_text(encoding="utf-8"))


def test_the_template_has_every_file_the_adoption_steps_name():
    expected = {".github/sdlc-config.json", ".github/labels.json", ".github/CODEOWNERS", ".github/pull_request_template.md",
                ".github/ISSUE_TEMPLATE/bug.yml", ".github/ISSUE_TEMPLATE/feature.yml", ".github/ISSUE_TEMPLATE/support.yml",
                ".github/ISSUE_TEMPLATE/config.yml", ".github/workflows/sdlc.yml", ".github/workflows/labels.yml",
                ".github/workflows/tests.yml", ".claude/settings.json", "REVIEW.md", ".gitignore"}
    expected |= {f".claude/agents/{n}.md" for n in ("stakeholder", "product-owner", "scrum-master", "tech-lead", "developer",
                                                    "tester", "devops", "reviewer", "security-reviewer", "release-manager",
                                                    "l1-support", "l2-support", "l3-support")}
    have = {str(p.relative_to(TEMPLATE)) for p in TEMPLATE.rglob("*") if p.is_file()}
    assert expected <= have, sorted(expected - have)


def test_the_template_config_is_valid_and_holds_the_built_in_values_except_the_project_text():
    cfg = template_config()
    assert config.load(TEMPLATE / ".github" / "sdlc-config.json") is not None
    built_in = {"agent_branch_prefix": sdlc.AGENT_BRANCH_PREFIX, "artifact_dir": sdlc.WORK, "label_to_stage": sdlc.LABEL_TO_STAGE,
                "stages": sdlc.STAGES, "protected_paths": sdlc.PROTECTED}
    for key, value in built_in.items():
        assert cfg[key] == value, key
    assert set(cfg["requestable_labels"]) == sdlc.REQUESTABLE_LABELS and set(cfg["trusted_associations"]) == sdlc.TRUSTED
    assert cfg["budget"]["mention"].startswith("@your-")         # a placeholder, never a real handle
    assert cfg["git_identity"]["name"] == "sdlc-engine-bot"


def test_the_template_config_and_the_fixture_config_differ_only_where_a_project_chooses():
    a, b = template_config(), json.loads((FIXTURE / ".github" / "sdlc-config.json").read_text(encoding="utf-8"))
    differing = {k for k in a if a[k] != b[k]}
    assert differing == {"secret_patterns_extra", "prompt", "budget"}, differing
    assert {k: v for k, v in a["budget"].items() if k != "mention"} == {k: v for k, v in b["budget"].items() if k != "mention"}


def test_the_template_agents_and_settings_are_the_fixtures():
    for path in (TEMPLATE / ".claude").rglob("*"):
        if path.is_file():
            assert path.read_text() == (FIXTURE / path.relative_to(TEMPLATE)).read_text(), path.name
    for name in ("labels.json", "pull_request_template.md"):
        assert (TEMPLATE / ".github" / name).read_text() == (FIXTURE / ".github" / name).read_text(), name
    for form in (TEMPLATE / ".github" / "ISSUE_TEMPLATE").glob("*.yml"):
        assert form.read_text() == (FIXTURE / ".github" / "ISSUE_TEMPLATE" / form.name).read_text(), form.name


def test_the_template_caller_is_the_fixture_caller_except_for_the_pinned_stage_workflow_reference():
    template = (TEMPLATE / ".github/workflows/sdlc.yml").read_text().splitlines()
    fixture = (FIXTURE / ".github/workflows/sdlc.yml").read_text().splitlines()
    assert len(template) == len(fixture)
    changed = [(t, f) for t, f in zip(template, fixture) if t != f]
    assert len(changed) == 1
    t, f = changed[0]
    assert f.strip() == "uses: ./.github/workflows/sdlc-stage.yml"
    assert re.fullmatch(r"\s*uses: <ENGINE_OWNER>/sdlc-engine/\.github/workflows/sdlc-stage\.yml@<FULL_40_HEX_COMMIT_SHA> # <ENGINE_VERSION>", t)


def test_the_template_never_inherits_secrets_or_uses_a_floating_reference():
    for path in TEMPLATE_WORKFLOWS:
        text = path.read_text()
        assert "secrets: inherit" not in text, path.name
        assert not re.search(r"uses:\s*\S+@(main|master|v\d+)\s*$", text, re.M), path.name


# ------------------------------------------------------------------------------------------- the pinning rule
@pytest.mark.parametrize("path", ENGINE_WORKFLOWS + [p for p in TEMPLATE_WORKFLOWS if p.name != "sdlc.yml"],
                         ids=lambda p: f"{p.parent.parent.parent.name}/{p.name}")
def test_every_third_party_action_is_pinned_by_a_full_commit_sha_with_a_version_comment(path):
    uses = [l for l in path.read_text().splitlines() if re.match(r"^\s*-?\s*uses:", l)]
    assert uses
    for line in uses:
        assert SHA_USE.match(line), line


def test_the_engine_tests_workflow_is_read_only_runs_on_push_and_pull_request_and_holds_no_secret():
    path = ENGINE / ".github" / "workflows" / "tests.yml"
    wf = yaml.safe_load(path.read_text())
    triggers = wf.get("on", wf.get(True))
    assert {"push", "pull_request"} <= set(triggers)
    assert wf["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in wf["jobs"].values())          # no job widens it
    text = path.read_text()
    assert not re.search(r"secrets[.:]|secrets\s*\[", text) and "GITHUB_TOKEN" not in text and "pull_request_target" not in text
    assert "python -m pytest -q" in text


# ------------------------------------------------------------------------------------------------- the docs
def all_keys(cfg):
    keys = set(cfg)
    for name in ("limits", "budget", "test", "git_identity", "prompt"):
        keys |= set(cfg[name])
    for stage in cfg["stages"].values():
        keys |= set(stage)
    return keys


def test_docs_config_names_every_key_of_the_config_and_every_stage_name():
    doc = (ENGINE / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    cfg = json.loads((FIXTURE / ".github" / "sdlc-config.json").read_text(encoding="utf-8"))
    missing = [k for k in sorted(all_keys(cfg) | config.KEYS | config.PROMPT_KEYS | config.STAGE_KEYS | config.OPTIONAL_STAGE_KEYS)
               if f"`{k}`" not in doc]
    assert missing == []
    for stage in cfg["stages"]:
        assert f"`{stage}`" in doc, stage


def test_docs_config_names_every_repository_variable_the_stage_workflow_reads():
    doc = (ENGINE / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    text = (ENGINE / ".github" / "workflows" / "sdlc-stage.yml").read_text()
    for name in set(re.findall(r"vars\.([A-Z0-9_]+)", text)):
        assert f"`{name}`" in doc, name


def test_decisions_holds_d001_with_its_source_d002_verbatim_and_d003():
    text = (ENGINE / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert f"## D-001: Engine extraction from {SOURCE_REPO} (2026-11-27, Bangkok)\n\nSource: {SOURCE_REPO} ADR-082," in text
    assert "TODO" not in text                                  # D-001 is no longer an open item
    assert "## D-002: Engine repo lock-down (2026-11-27, Bangkok)\n" in text and "## D-003: " in text
    assert "Six settings applied and confirmed on the settings pages:" in text
    assert text.index("## D-001") < text.index("## D-002") < text.index("## D-003")
