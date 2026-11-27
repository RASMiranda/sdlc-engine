"""``python -m sdlc_engine check-project --root DIR``: does a consumer project fit this engine? (D-004). Stdlib only.

It reads files under ``--root`` and nothing else: no network, no git, no engine input (the stage workflow has none). One
plain message per failure, each starting with the rule that failed (reserved, config, roles, caller, triggers, pin, secrets); exit 1 on any
failure, 0 otherwise.

PyYAML is a test dependency only, so the caller workflow is read by a small reader for the subset of YAML a caller
workflow uses (block mappings, block lists of scalars, one-line flow lists and maps, quoted and plain scalars,
comments). Anything outside that subset is a failure ("cannot read"), never a guess. ``tests/test_project_check.py``
keeps the reader equal to PyYAML on the fixture and the template callers.
"""
import json
import os
import re
import sys
from pathlib import Path

from . import config

# This repository's own path: the only repository a consumer may call (D-001 c, D-004). The stage workflow is pinned by a
# full commit SHA of this repository, never a tag, a branch or a local path.
ENGINE_REPO = "RASMiranda/sdlc-engine"
STAGE_WORKFLOW_PATH = ".github/workflows/sdlc-stage.yml"
PIN = re.compile(re.escape(f"{ENGINE_REPO}/{STAGE_WORKFLOW_PATH}") + r"@[0-9a-f]{40}")
# The issue event types `decide` starts a stage on: `opened` (a trusted author's new issue) and `labeled` (an agent:*
# label). tests/test_project_check.py keeps this equal to what `decide` does with each action.
ISSUE_EVENT_TYPES = {"opened", "labeled"}
SECRET_NAME = "CLAUDE_CODE_OAUTH_TOKEN"
SECRET_VALUE = re.compile(r"\$\{\{\s*secrets\." + SECRET_NAME + r"\s*\}\}")
CALLER = ".github/workflows/sdlc.yml"
CONFIG_FILE = ".github/sdlc-config.json"
STAGE_JOB = "stage"
# The stage workflow deletes and re-creates these two folders in the caller's workspace (D-004).
RESERVED = ("engine", "project-config")


# ------------------------------------------------------------------------------------------ shared expression helpers
def inner_expression(text):
    """The text inside ``${{ ... }}`` when ``text`` is exactly one expression, else None."""
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", text, re.S) if isinstance(text, str) else None
    return m.group(1).strip() if m else None


def json_lists(expression):
    """The JSON lists written as ``fromJSON('[...]')`` in a workflow expression, in order. Raises ``ValueError`` on one
    that is not a list of text."""
    out = []
    for raw in re.findall(r"fromJSON\('([^']*)'\)", expression or ""):
        value = json.loads(raw)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{raw!r} is not a list of text")
        out.append(value)
    return out


# --------------------------------------------------------------------------------------- the small YAML subset reader
class YamlError(ValueError):
    """The text is not in the YAML subset this reader understands."""


_KEY = re.compile(r"""^(?P<k>"[^"]*"|'[^']*'|[^\s'"\[\]{}#&*!|>%@`,-][^:]*?)\s*:(?:\s+(?P<v>.*))?$""")
_OPEN = " \t([{,:"


def _strip_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or line[i - 1] in _OPEN):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(text):
    text = text.strip()
    if text[:1] in "&*!":
        raise YamlError(f"anchors, aliases and tags are not supported: {text[:20]!r}")
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return text


def _split_flow(body):
    parts, depth, quote, cur = [], 0, None, ""
    for i, ch in enumerate(body):
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or body[i - 1] in _OPEN):
            quote = ch
            cur += ch
        elif ch in "[{":
            depth += 1
            cur += ch
        elif ch in "]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if quote or depth:
        raise YamlError("an unbalanced flow list or map")
    if cur.strip():
        parts.append(cur)
    return parts


def _flow(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [_flow(p) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        out = {}
        for part in _split_flow(text[1:-1]):
            m = _KEY.match(part.strip())
            if not m or m.group("k") in out:
                raise YamlError(f"cannot read the flow map entry {part.strip()!r}")
            out[_scalar(m.group("k"))] = _flow(m.group("v") or "")
        return out
    if text.startswith(("[", "{")):
        raise YamlError("a flow list or map that does not close on the same line")
    return _scalar(text)


def read_yaml(text):
    """The document as nested dicts, lists and text. Every scalar stays text (``false`` is ``"false"``), and ``on`` is
    the key ``"on"``. Raises ``YamlError`` outside the supported subset."""
    entries = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).rstrip()
        if not line.strip() or line.strip() in ("---", "..."):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if line[indent:indent + 1] == "\t":
            raise YamlError(f"line {number}: a tab used as indentation")
        entries.append([indent, line.strip(), number])
    if not entries:
        raise YamlError("the file is empty")
    value, i = _block(entries, 0, entries[0][0])
    if i != len(entries):
        raise YamlError(f"line {entries[i][2]}: unexpected indentation")
    return value


def _is_item(text):
    return text == "-" or text.startswith("- ")


def _block(entries, i, indent):
    return _sequence(entries, i, indent) if _is_item(entries[i][1]) else _mapping(entries, i, indent)


def _sequence(entries, i, indent):
    out = []
    while i < len(entries) and entries[i][0] == indent and _is_item(entries[i][1]):
        rest = entries[i][1][1:].strip()
        number = entries[i][2]
        if not rest:
            if i + 1 < len(entries) and entries[i + 1][0] > indent:
                value, i = _block(entries, i + 1, entries[i + 1][0])
            else:
                value, i = None, i + 1
            out.append(value)
        elif _KEY.match(rest) and not rest.startswith(("[", "{", "'", '"')):
            entries[i] = [indent + 2, rest, number]      # "- key: value": a mapping that starts on the dash's line
            value, i = _mapping(entries, i, indent + 2)
            out.append(value)
        else:
            out.append(_flow(rest))
            i += 1
    return out, i


def _mapping(entries, i, indent):
    out = {}
    while i < len(entries) and entries[i][0] == indent and not _is_item(entries[i][1]):
        _, text, number = entries[i]
        m = _KEY.match(text)
        if not m:
            raise YamlError(f"line {number}: cannot read {text[:40]!r} as a key")
        key, value = _scalar(m.group("k")), (m.group("v") or "").strip()
        if key in out:
            raise YamlError(f"line {number}: the key {key!r} appears twice")
        i += 1
        if value[:1] in ("|", ">"):
            while i < len(entries) and entries[i][0] > indent:       # a block of text: its content is not read
                i += 1
            out[key] = "<text block>"
        elif not value:
            if i < len(entries) and (entries[i][0] > indent or (entries[i][0] == indent and _is_item(entries[i][1]))):
                out[key], i = _block(entries, i, entries[i][0])
            else:
                out[key] = None
        else:
            out[key] = _flow(value)
            if i < len(entries) and entries[i][0] > indent:
                raise YamlError(f"line {entries[i][2]}: a value that continues on the next line is not supported")
    if i < len(entries) and entries[i][0] > indent:
        raise YamlError(f"line {entries[i][2]}: unexpected indentation")
    return out, i


# ----------------------------------------------------------------------------------------------------------- the rules
def _read_config(root, out):
    """The parsed config when it is valid, else None (with the reasons in ``out``)."""
    path = root / CONFIG_FILE
    if not path.is_file():
        out.append(f"config: {CONFIG_FILE} is missing")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        out.append(f"config: {CONFIG_FILE} cannot be read as JSON: {exc}")
        return None
    problems = config.problems_in(data)
    out.extend(f"config: {CONFIG_FILE}: {p}" for p in problems)
    return None if problems else data


def _check_roles(root, cfg, out):
    for stage, spec in cfg["stages"].items():
        for role in spec["roles"]:
            if "/" in role or "\\" in role or role in (".", ".."):
                out.append(f"roles: stage {stage!r} names the role {role!r}, which is not a file name")
            elif not (root / ".claude" / "agents" / f"{role}.md").is_file():
                out.append(f"roles: stage {stage!r} uses the role {role!r}, but .claude/agents/{role}.md is missing")


def _get(node, *path):
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node


def _check_caller_lists(where, text, cfg, out):
    expression = inner_expression(text)
    if expression is None:
        out.append(f"caller: {CALLER} {where} must be one ${{{{ ... }}}} expression")
        return
    try:
        lists = json_lists(expression)
    except ValueError as exc:
        out.append(f"caller: {CALLER} {where} holds a fromJSON list that is not valid: {exc}")
        return
    if len(lists) != 2:
        out.append(f"caller: {CALLER} {where} must hold exactly two fromJSON lists (author associations, then labels); "
                   f"it holds {len(lists)}")
        return
    for what, got, want in (("author associations", lists[0], cfg["trusted_associations"]),
                            ("labels", lists[1], list(cfg["label_to_stage"]))):
        if set(got) != set(want):
            out.append(f"caller: {CALLER} {where} lists the {what} {sorted(got)}, but {CONFIG_FILE} has {sorted(want)}")


def _check_triggers(doc, out):
    """The caller starts only on issue events (D-006). Its job `if` and `decide` are written for those alone; any other
    event would start a job that holds write permissions and the OAuth secret on input nothing here vets."""
    on = doc.get("on")
    if not isinstance(on, dict):
        out.append(f"triggers: {CALLER} on: is {on!r}; it must be a mapping whose only key is issues")
        return
    if "issues" not in on:
        out.append(f"triggers: {CALLER} on: has no issues key; the caller must be triggered by issues only")
    for event in on:
        if event != "issues":
            out.append(f"triggers: {CALLER} on: has {event!r}; the caller must be triggered by issues only")


def _check_caller(root, cfg, out):
    """Returns the caller's stage job (a dict) for the pin and secrets rules, or None."""
    path = root / CALLER
    if not path.is_file():
        out.append(f"caller: {CALLER} is missing")
        return None
    try:
        doc = read_yaml(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, YamlError) as exc:
        out.append(f"caller: {CALLER} cannot be read: {exc}")
        return None
    _check_triggers(doc, out)
    job = _get(doc, "jobs", STAGE_JOB)
    if not isinstance(job, dict):
        out.append(f"caller: {CALLER} has no job named {STAGE_JOB!r}")
        return None
    if cfg is None:
        return job
    types = _get(doc, "on", "issues", "types")
    if not isinstance(types, list) or set(types) != ISSUE_EVENT_TYPES or len(types) != len(set(types)):
        out.append(f"caller: {CALLER} on.issues.types is {types!r}, but it must be exactly {sorted(ISSUE_EVENT_TYPES)}")
    _check_caller_lists(f"jobs.{STAGE_JOB}.if", job.get("if"), cfg, out)
    _check_caller_lists("concurrency.group", _get(doc, "concurrency", "group"), cfg, out)
    return job


def _check_pin(job, out):
    uses = job.get("uses")
    if not isinstance(uses, str) or not PIN.fullmatch(uses.strip()):
        out.append(f"pin: {CALLER} job {STAGE_JOB!r} uses {uses!r}; it must be "
                   f"{ENGINE_REPO}/{STAGE_WORKFLOW_PATH}@<40 lowercase hex commit sha> (no tag, branch, short sha, "
                   f"local path or other repository)")


def _check_secrets(job, out):
    secrets = job.get("secrets")
    if secrets is None:
        out.append(f"secrets: {CALLER} job {STAGE_JOB!r} passes no secrets; it must pass {SECRET_NAME}: "
                   f"${{{{ secrets.{SECRET_NAME} }}}}")
    elif not isinstance(secrets, dict):
        out.append(f"secrets: {CALLER} job {STAGE_JOB!r} has secrets: {secrets!r}; pass {SECRET_NAME} by name "
                   f"(secrets: inherit is not allowed)")
    else:
        for name, value in secrets.items():
            if name != SECRET_NAME:
                out.append(f"secrets: {CALLER} job {STAGE_JOB!r} passes {name!r}; only {SECRET_NAME} may be passed")
            elif not isinstance(value, str) or not SECRET_VALUE.fullmatch(value.strip()):
                out.append(f"secrets: {CALLER} job {STAGE_JOB!r} passes {SECRET_NAME} as {value!r}; it must be "
                           f"${{{{ secrets.{SECRET_NAME} }}}}")
        if SECRET_NAME not in secrets:
            out.append(f"secrets: {CALLER} job {STAGE_JOB!r} does not pass {SECRET_NAME}")


def _check_reserved(root, out):
    for name in RESERVED:
        if os.path.lexists(root / name):                   # a file, a folder or a dangling link: all are in the way
            out.append(f"reserved: {name}/ exists in the project root; the stage workflow deletes and re-creates it (D-004)")


def check_project(root):
    """Every failure found under ``root``, as plain messages. Empty when the project fits this engine."""
    root, out = Path(root), []
    _check_reserved(root, out)
    cfg = _read_config(root, out)
    if cfg is not None:
        _check_roles(root, cfg, out)
    job = _check_caller(root, cfg, out)
    if job is not None:
        _check_pin(job, out)
        _check_secrets(job, out)
    return out


def command(args):
    root = Path(args.root)
    if not root.is_dir():
        print(f"check-project: {args.root} is not a directory", file=sys.stderr)
        return 1
    problems = check_project(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"ok: {args.root} fits this engine")
    return 1 if problems else 0
