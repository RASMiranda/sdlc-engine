"""Non-negotiable 1: the engine holds no project name, no personal data and no secret.

This test fails when any tracked file contains one of the banned strings:

* the name of the project the engine was extracted from, the name of its first product, or the maintainer's handle
  (case-insensitive: see ``WORDS``);
* an email address;
* a phone number.

Where each string may appear is an explicit allow-list (``allowed_for``), not a pattern that quietly grows.

How this file avoids tripping on itself. Every banned word is written in two parts and joined at import time
(``"car" + "eer"``), so no line of this file contains one whole, and ``git grep`` for the banned words does not list it.
The sample emails below are built the same way. The file is also exempt by path (``GUARD``), as the rules ask, because
its tests must hold deliberately bad samples. Those samples are written to a temporary directory at run time and are
never committed.
"""
import re
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1]
GUARD = "tests/test_guard_engine.py"

# The banned words, each written in two parts (see the module docstring).
NAME_A = "car" + "eer"
NAME_B = "job" + "scan"
HANDLE = "RAS" + "Miranda"
WORDS = {"name_a": NAME_A, "name_b": NAME_B, "handle": HANDLE}
WORD_RE = re.compile("|".join(re.escape(w) for w in WORDS.values()), re.I)

# Allowed literals. They are removed from the text before the banned words are looked for, and only where listed.
SOURCE_REPO = NAME_A + "-ai"                    # the source repository's name, in ADR citations (CHANGELOG.md, docs/*.md)
ENGINE_REPO = HANDLE + "/sdlc-engine"         # this repository's own path: clone and project URLs
CODEOWNERS_HANDLE = re.compile("@" + HANDLE + r"\b", re.I)    # the real handle, in .github/CODEOWNERS only

# Emails. Exactly two literals are allowed anywhere, compared whole, never by prefix or by domain:
# the Co-Authored-By trailer and the public GitHub Actions bot committer address (decision D-003).
EXACT_EMAILS = {"noreply@anthropic.com", "41898282+github-actions[bot]@users.noreply.github.com"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-\[\]]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
RESERVED_DOMAINS = {"example.com", "example.org", "example.net"}     # RFC 2606, and any name beneath them; tests/ only

# Phone numbers. A candidate is a run of digits and the usual separators that starts and ends on a digit, is not part
# of a longer word, and holds 8 to 15 digits. Then the shapes that are not phone numbers are set aside.
PHONE_RE = re.compile(r"(?<![\w+.\-])\+?\(?\d[\d ().\-]{6,}\d(?![\w])")
NOT_PHONE = [
    re.compile(r"\d{4}-\d{2}-\d{2}"),              # an ISO date, alone or at the start of a timestamp
    re.compile(r"\d{4}-\d{4}$"),                   # a year range
    re.compile(r"\d+(?:\.\d+){1,3}$"),             # a version, or an IPv4 address (dots only)
]
DOTTED_PHONE = re.compile(r"\d{3}\.\d{3}\.\d{4}$")           # 555.123.4567: dots only, but a phone number


def is_phone(candidate):
    digits = re.sub(r"\D", "", candidate)
    if not 8 <= len(digits) <= 15:
        return False
    if not re.search(r"[ ()\-.]", candidate) and not candidate.startswith("+"):
        return False                               # a bare digit run: an id, a size, a timestamp
    core = candidate.lstrip("+(")                  # "(2026-11-27, ..." is a date in brackets, not a number
    if DOTTED_PHONE.match(core):
        return True
    return not any(p.match(core) for p in NOT_PHONE)


def allowed_for(rel):
    """What a file may hold: ``exempt``, the whole-literal allowances, and whether sample example domains are allowed."""
    if rel == "LICENSE" or rel == GUARD:
        return {"exempt": True}
    rules = {"exempt": False, "literals": [], "handle": False, "sample_domains": rel.startswith("tests/")}
    if rel == ".github/CODEOWNERS":
        rules["handle"] = True                                   # the engine's own code owner, the real handle
    elif rel == "CHANGELOG.md" or re.fullmatch(r"docs/[^/]+\.md", rel):
        rules["literals"] = [SOURCE_REPO, ENGINE_REPO]             # ADR citations and the repository URL
    elif rel in ("README.md", "pyproject.toml"):
        rules["literals"] = [ENGINE_REPO]                        # clone and project URLs only
    elif rel == "src/sdlc_engine/project_check.py":
        rules["literals"] = [ENGINE_REPO]                        # the one repository `check-project` accepts in a pin (D-004)
    # template/ and tests/fixture-project/ get no allowance: a placeholder handle is not a banned word.
    return rules


def tracked_files(root):
    """Tracked files, plus new files not yet ignored, so a file is checked before it is committed."""
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                         capture_output=True, check=True).stdout
    return sorted(p for p in out.decode().split("\0") if p)


def violations(root, files):
    """Every banned string in ``files`` (paths relative to ``root``) as ``path:line: kind``."""
    found = []
    for rel in files:
        rules = allowed_for(rel)
        if rules["exempt"]:
            continue
        data = (Path(root) / rel).read_bytes()
        if b"\0" in data:
            continue                                         # a binary file
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            text = line
            for literal in rules["literals"]:
                text = text.replace(literal, "")
            if rules["handle"]:
                text = CODEOWNERS_HANDLE.sub("", text)
            for word in WORD_RE.findall(text):
                found.append(f"{rel}:{number}: banned word {word.lower()!r}")
            for match in EMAIL_RE.finditer(line):
                email = match.group(0)
                domain = email.rsplit("@", 1)[1].lower()
                if email in EXACT_EMAILS:
                    continue
                if rules["sample_domains"] and any(domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS):
                    continue
                found.append(f"{rel}:{number}: email address {email!r}")
            for match in PHONE_RE.finditer(line):
                if is_phone(match.group(0)):
                    found.append(f"{rel}:{number}: phone number {match.group(0)!r}")
    return found


# --------------------------------------------------------------------------------------------- the real repository
def test_no_tracked_file_holds_a_project_name_the_maintainers_handle_an_email_or_a_phone_number():
    assert violations(ENGINE, tracked_files(ENGINE)) == []


# ------------------------------------------------------------------------------------------- each ban fires on a sample
def write(tmp_path, rel, text):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


def check(tmp_path, rel, text):
    write(tmp_path, rel, text)
    return violations(tmp_path, [rel])


@pytest.mark.parametrize("word", [NAME_A, NAME_B, HANDLE, NAME_A.upper(), NAME_B.title(), HANDLE.lower()])
def test_each_banned_word_fires_in_code_whatever_its_case(tmp_path, word):
    found = check(tmp_path, "src/x.py", f"name = '{word}'\n")
    assert found and "banned word" in found[0] and found[0].startswith("src/x.py:1")


def test_a_word_that_merely_contains_a_banned_one_still_fires(tmp_path):
    assert check(tmp_path, "src/x.py", f"x = '{NAME_A}-data'\n") and check(tmp_path, "src/y.py", f"x = 'my{NAME_B}s'\n")


def test_the_line_number_is_reported(tmp_path):
    found = check(tmp_path, "src/x.py", f"a = 1\nb = 2\nc = '{NAME_B}'\n")
    assert found == ["src/x.py:3: banned word " + repr(NAME_B)]


@pytest.mark.parametrize("email", ["someone" + "@" + "gmail.com", "a.b+c" + "@" + "outlook.com",
                                   "security" + "@" + "anthropic.com", "noreply" + "@" + "anthropic.com.example.io",
                                   "x" + "@" + "users.noreply.github.com", "noreply" + "@" + "github.com"])
def test_an_email_address_fires(tmp_path, email):
    found = check(tmp_path, "src/x.py", f"contact = '{email}'\n")
    assert found and "email address" in found[0]


def test_a_different_anthropic_address_and_a_gmail_address_both_still_fail(tmp_path):
    """Decision D-003: the exception is the whole literal noreply@anthropic.com, nothing near it."""
    for email in ("support" + "@" + "anthropic.com", "Noreply" + "@" + "anthropic.com", "noreply2" + "@" + "anthropic.com",
                  "me" + "@" + "gmail.com"):
        found = check(tmp_path, "docs/a.md", f"mail {email} now\n")
        assert found and "email address" in found[0], email


def test_the_two_exact_emails_are_allowed_everywhere_and_only_whole(tmp_path):
    trailer = "Co-Authored-By: Claude <noreply@anthropic.com>"
    bot = "git config user.email \"41898282+github-actions[bot]@users.noreply.github.com\""
    for rel in ("src/x.py", "docs/a.md", "README.md", ".github/workflows/w.yml", "tests/t.py"):
        assert check(tmp_path, rel, trailer + "\n" + bot + "\n") == [], rel
    assert check(tmp_path, "src/x.py", "xnoreply" + "@" + "anthropic.com\n")           # a longer local part is another address
    assert check(tmp_path, "src/y.py", "41898282+github-actions[bot]" + "@" + "users.noreply.github.com.example.io\n")


def test_reserved_example_domains_are_allowed_in_tests_only(tmp_path):
    for domain in ("example.com", "example.org", "example.net"):
        sample = "me" + "@" + domain
        assert check(tmp_path, "tests/t.py", f"x = '{sample}'\n") == [], domain
        assert check(tmp_path, "docs/a.md", f"x {sample}\n"), domain
        assert check(tmp_path, "template/a.md", f"x {sample}\n"), domain
        assert check(tmp_path, "src/x.py", f"x = '{sample}'\n"), domain
    assert check(tmp_path, "tests/t.py", "a" + "@" + "example.io\n")                   # only the three reserved domains
    assert check(tmp_path, "tests/t.py", "a" + "@" + "notexample.com\n")               # a longer name is not beneath them
    assert check(tmp_path, "tests/t.py", "a" + "@" + "example.com.evil.io\n")          # nor is a name that merely contains one
    assert check(tmp_path, "docs/a.md", "a" + "@" + "corp.example.org\n")              # beneath them, but outside tests/
    assert check(tmp_path, "tests/t.py", "person.real" + "@" + "corp.example.org\n") == []   # beneath example.org, in tests/
    assert check(tmp_path, "tests/t.py", "a" + "@" + "b.test\n")


@pytest.mark.parametrize("number", ["+44 20 7946 0958", "+1 (555) 123-4567", "(555) 123-4567", "555-123-4567",
                                    "555.123.4567", "+351 912 345 678", "+66812345678", "020 7946 0958", "06 12 34 56 78"])
def test_a_phone_number_fires(tmp_path, number):
    found = check(tmp_path, "src/x.py", f"call {number} now\n")
    assert found and "phone number" in found[0], number


SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
ALL_DIGIT_SHA = "1234567890123456789012345678901234567890"     # 40 hex characters that happen to be digits


@pytest.mark.parametrize("text", [
    f"uses: actions/checkout@{SHA} # v7.0.1",                   # a 40-hex commit SHA
    f"commit {SHA}",
    f"commit 10a663cd81e9cbb88029419a0df2cfe71b6d87e6",         # starts with digits
    f"sha: {ALL_DIGIT_SHA}",                                    # all digits, no separators
    "version = \"0.1.0\"", "python 3.12.1", "v7.0.1", "1.2.3", "10.20.30.40", "127.0.0.1",   # semver and dotted quads
    "2026-11-27", "dated 2026-11-27 (Bangkok)", "## D-002 (2026-11-27, Bangkok)", "(2026-11-27)", "[2026-11-27]", "2026-11-27T12:00:00Z", "2026-11-27 12:00:00",   # ISO dates
    "run 41410127118 took 3 s", "max_added_bytes: 400000", "1732700000",                    # ids, sizes, timestamps
    "2026-2027", "ADR-064 and ADR-065", "lines 10-20", "| 60 | 240 |",
])
def test_the_phone_pattern_does_not_fire_on_shas_semver_dates_and_other_numbers(tmp_path, text):
    assert check(tmp_path, "docs/a.md", text + "\n") == [], text


# ------------------------------------------------------------------------------------------------ the allow-list
def test_license_is_exempt_and_the_guard_file_is_exempt_by_path(tmp_path):
    bad = f"{NAME_A} {NAME_B} {HANDLE} " + "me" + "@" + "gmail.com +44 20 7946 0958\n"
    assert check(tmp_path, "LICENSE", bad) == []
    assert check(tmp_path, GUARD, bad) == []
    assert check(tmp_path, "tests/other.py", bad)


def test_codeowners_may_hold_the_real_handle_but_nothing_else_banned(tmp_path):
    assert check(tmp_path, ".github/CODEOWNERS", f"*   @{HANDLE}\n/.github/   @{HANDLE}\n") == []
    assert check(tmp_path, ".github/CODEOWNERS", f"*   @{HANDLE}  # {NAME_A}\n")
    assert check(tmp_path, ".github/CODEOWNERS", f"# owner: {HANDLE}\n")                  # the handle without its @ is not the owner line


def test_the_real_handle_is_banned_in_every_other_file_including_template_and_fixture(tmp_path):
    for rel in ("template/.github/CODEOWNERS", "tests/fixture-project/.github/CODEOWNERS", ".github/workflows/w.yml",
                "SECURITY.md", "src/x.py", "tests/t.py"):
        assert check(tmp_path, rel, f"*  @{HANDLE}\n"), rel


def test_template_and_fixture_may_hold_a_placeholder_handle_but_not_the_other_banned_words(tmp_path):
    for rel in ("template/.github/CODEOWNERS", "tests/fixture-project/.github/CODEOWNERS"):
        assert check(tmp_path, rel, "*  @your-github-handle\n*  @example-owner\n") == [], rel
        assert check(tmp_path, rel, f"# {NAME_A}\n"), rel
        assert check(tmp_path, rel, f"# {NAME_B}\n"), rel
        assert check(tmp_path, rel, f"# {SOURCE_REPO}\n"), rel


def test_docs_and_changelog_may_name_the_source_repo_and_the_engine_repo_and_nothing_else(tmp_path):
    ok = f"Extracted from {SOURCE_REPO}@abc (ADR-035). Clone https://github.com/{ENGINE_REPO}.\n"
    for rel in ("CHANGELOG.md", "docs/DECISIONS.md", "docs/CONFIG.md", "docs/SECURITY-MODEL.md"):
        assert check(tmp_path, rel, ok) == [], rel
        assert check(tmp_path, rel, f"see {NAME_A}-data\n"), rel                        # only the literal source name is allowed
        assert check(tmp_path, rel, f"{NAME_B} runs\n"), rel
        assert check(tmp_path, rel, f"owner {HANDLE}\n"), rel                           # the handle alone is not the repo path
        assert check(tmp_path, rel, "me" + "@" + "gmail.com\n"), rel
        assert check(tmp_path, rel, "+44 20 7946 0958\n"), rel
    assert check(tmp_path, "docs/sub/deep.md", ok)                                      # docs/*.md only, not a subfolder
    assert check(tmp_path, "docs/notes.txt", ok)


def test_readme_and_pyproject_may_name_only_the_engine_repo(tmp_path):
    url = f"https://github.com/{ENGINE_REPO}\n"
    for rel in ("README.md", "pyproject.toml"):
        assert check(tmp_path, rel, url) == [], rel
        assert check(tmp_path, rel, f"{SOURCE_REPO}\n"), rel                              # the source repo is not allowed here
        assert check(tmp_path, rel, f"{HANDLE}\n"), rel
    assert check(tmp_path, "SECURITY.md", url)                                          # SECURITY.md carries no repository path


def test_a_binary_file_is_skipped(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"\0\1\2" + NAME_A.encode())
    assert violations(tmp_path, ["x.bin"]) == []


def test_the_engines_own_repository_path_is_allowed_in_the_pin_rule_only(tmp_path):
    """D-004: `check-project` must name the one repository a consumer may call. That literal, whole, is allowed in that
    one module and nowhere else under src/ or tests/; a bare handle is still banned there."""
    line = f'ENGINE_REPO = "{ENGINE_REPO}"\n'
    assert check(tmp_path, "src/sdlc_engine/project_check.py", line) == []
    assert check(tmp_path, "src/sdlc_engine/project_check.py", f'X = "{HANDLE}"\n') != []
    assert check(tmp_path, "src/sdlc_engine/other.py", line) != []
    assert check(tmp_path, "tests/test_x.py", line) != []
