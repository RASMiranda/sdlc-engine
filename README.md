# sdlc-engine

The deterministic half of an agentic software lifecycle. Agents write files in a checkout; this engine decides what runs,
checks what the agents changed, frames the issue as untrusted text, and builds what the workflow posts. The workflow only
calls it. A human merges.

- **Standard library only.** No dependency to install to run the engine. (The tests use PyYAML and pytest.)
- **Python 3.12 or later.** The version is in `pyproject.toml`, the single source of truth; `python -m sdlc_engine --version`
  reads it.
- **Public, MIT licensed.** It holds no secret, no project name and no personal data (a test enforces this).

## What is here

| Path | What |
|---|---|
| `src/sdlc_engine/` | The engine: decide, issue, prompt, check, scan, pr-body, review, rounds, budget. |
| `.github/workflows/sdlc-stage.yml` | The reusable stage workflow that calls the engine. |
| `template/` | The files a new project copies and edits. |
| `docs/CONFIG.md` | Every key of `.github/sdlc-config.json`, and the repository variables. |
| `docs/SECURITY-MODEL.md` | Who is trusted, which code runs with a token, and what an agent can change. |
| `docs/DECISIONS.md` | Decisions about this repository. |
| `tests/` | The engine's tests, golden files, and `fixture-project/`, a minimal stand-in for a consumer. |

## Status

This is the first extraction, `0.1.0`. The stage workflow was copied unchanged apart from the committer name. As copied it
still expects the engine source at `src/sdlc_engine/` and the config at `.github/sdlc-config.json` **in the calling
repository**, and the caller in `template/` refers to the stage workflow of this repository by a placeholder. Making the
stage workflow fetch the pinned engine from this repository is the next step and is not done here. Until it is, treat
`template/` as the target layout, not as something that already runs.

## How a project adopts it

1. Copy `template/` into the project's repository root. Replace every `<placeholder>` and every `your-github-handle`.
2. Edit `.github/sdlc-config.json` for the project. `docs/CONFIG.md` documents each key.
3. Write the project's `CLAUDE.md`, `docs/SDLC.md` and `REVIEW.md`, or change `prompt.read_first` to the documents you have.
4. In the caller workflow, replace the stage workflow reference with this repository pinned by commit (below).
5. Add the repository secret `CLAUDE_CODE_OAUTH_TOKEN`. The caller passes it to the stage workflow by name.
6. Settings, Actions, General: allow GitHub Actions to create pull requests.
7. Protect the default branch with a ruleset that requires a pull request, the `pytest` check, and review from Code Owners,
   so the `CODEOWNERS` file in the project does something.
8. Run the `labels` workflow once to create the issue labels.

## The pinning rule

Reference the engine only by a **full 40-hex commit SHA, with the version in a comment**:

```yaml
uses: RASMiranda/sdlc-engine/.github/workflows/sdlc-stage.yml@<full-40-hex-commit-sha> # v0.1.0
```

Never `@main`, never a branch, and never a floating tag such as `@v0`. A branch or a floating tag can change under you
without a pull request in your repository; a commit SHA cannot. The same rule applies to every third-party action in your
own workflows. To upgrade, change the SHA and the comment in a pull request and read the engine's `CHANGELOG.md` first.
To check a project against the engine it pins (config, roles, caller workflow, pin, secrets), run
`python -m sdlc_engine check-project --root .`; see `docs/CONFIG.md`.

## Develop

```bash
pip install pytest PyYAML
python -m pytest -q
```

Tests that need a project's files read `tests/fixture-project/`. `tests/test_guard_engine.py` fails if a tracked file holds
a project name, a maintainer handle, an email address or a phone number outside its allow-list.

## Security

See `SECURITY.md` for how to report a vulnerability, and `docs/SECURITY-MODEL.md` for the trust model.
