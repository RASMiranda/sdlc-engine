# Security model

The engine is the part of an agentic SDLC that decides, checks and frames what agents do. Agents write files in a checkout.
They cannot push, merge, label, close an issue, call GitHub or reach the web. This engine decides what is kept, and only
then does the workflow commit, push to an `agent/*` branch, open a **draft** pull request and post. A human merges.

## The rule that governs everything

**Engine code and project config come from a pinned commit or from the default branch, never from an agent branch.**

An agent can write any file in its checkout, so any code or config it can influence must not run in a step that holds a
token. Concretely:

- The **engine** runs from a checkout of the repository and the commit the called workflow itself comes from
  (`job.workflow_repository` at `job.workflow_sha`), into `engine/`, with only `src` fetched. It is taken before anything
  else runs (so `decide` and the budget gate run the engine's code too, never the caller's workspace) and again after each
  agent run, with `python -P` so the working directory is not on `sys.path`. Every one of those four checkouts is followed by a step that
  fails the job unless `git -C engine rev-parse HEAD` equals `job.workflow_sha`, and writes that commit to the job summary.
  Both values reach the step through `env`, never the script text. The workflow has no `engine_sha` input: the only way to
  choose the engine's version is the consumer's pinned `uses:` line (D-004).
- The **project config** (`.github/sdlc-config.json`) comes from a sparse checkout of the caller's trigger commit
  (`github.sha`, which for an issue event is the default branch's commit) into `project-config/`, passed to every engine call
  as `--config "$SDLC_CONFIG"`. A config change therefore reaches a run only through a merged pull request. It is a protected
  path, so an agent cannot write it. Nothing reads config from the workspace root or from the agent's branch.
- A consumer reaches the engine only by a **full 40-hex commit SHA** with the version in a comment. A branch or a floating
  tag can move under a consumer without any review in the consumer's repository; a SHA cannot. A released `v*` tag of this
  repository can never be moved (see D-002).
- A change to the engine or to the stage workflow made on an agent branch is not used by that branch's own run. That is
  intended. In a consumer the engine is not in the workspace at all; the engine's package is also a protected path in a
  consumer's config.

## Where the token is, and where it is not

Summarised from career-ai ADR-035, ADR-036 and ADR-037, which the engine was extracted with.

**Token scope (ADR-035).** The repository token is not set on the job. It is set per step, and only on the steps that call
`gh` or `git push`: the budget gate, the fetch of issue comments, the commit-and-push step and the post step. The agent
steps and the safety check run without it and without any `ANTHROPIC*` or OAuth variable. The agent action writes its
token into the `origin` URL in `.git/config`, so a step after each action run resets `origin` before anything an agent
wrote can run. `tests/test_sdlc_token_scope.py` pins this by parsing the workflow.

**Trusted code and git hygiene (ADR-036).** Every step that holds a token and imports the engine does so from the trusted
checkout. Git in those steps runs with hooks and fsmonitor off and ignores the global and system git config. After each
agent run a reset step removes every `.git/config` key the checkout did not write (`include.*`, `core.fsmonitor`,
`core.hooksPath`, `url.*`, `credential.*`, `filter.*`, `diff.external`, `core.worktree`), deletes `.git/config.worktree` and
empties `.git/hooks`. An agent's own write into `.git/` is refused by the project's hook where one is installed (the engine's check reads
`git status`, which never lists `.git/`, so it does not see such a write); the reset steps strip what is left.
`tests/test_sdlc_trusted_code.py` and `tests/test_sdlc_git_hygiene.py` cover it, the latter against a poisoned throwaway
repository.

**No repository test code in the privileged job (ADR-037).** The agent process holds the tokens, and job permissions do not
limit the app token. A test or `conftest.py` the build agent wrote would run in that process. So no stage allows `pytest`,
`pip` or any `python -m` of repository code. Tests run only in the project's own workflow, with a read-only token and no
secrets, which the push step dispatches. The build agent writes tests and does not run them; the report says so in a line
written by the workflow, and the `pytest` check on the pull request is the evidence. The review reads the check results from
a file written by a step the agent cannot influence.

## What an agent can change

`python -m sdlc_engine check` rejects a run that changes anything outside the stage's `writes`, any protected path, more
than `limits.max_files` files or `limits.max_added_bytes` bytes, or that adds a credential, an email address or a phone
number. Text the workflow posts to the issue (reports, reviews) is scanned for credentials and, in prose, for personal data
before it is posted. A forged review-round marker in agent text is withheld.

## Review and merge

A reviewer and a security reviewer read the diff, read only. Their answer has a fixed shape that the engine parses; a
malformed answer fails closed as one IMPORTANT finding. A finding whose line is not in the diff is dropped. Findings never
approve and never block by themselves; branch protection, a green check and a code owner's review do.

## Residual risks, as recorded

- The agent process still holds the repository token and the app token (the action sets them). Splitting the agent and the
  publish step into two jobs is the remaining step and is not done.
- `.git/HEAD`, refs and objects are not reset between steps.
- A deny rule in the agent settings is a pattern match, not a sandbox.
- A person with write access can delete the bot's review marker comments, which lowers the round count.
- Several of the controls above were checked by tests of the workflow's text and by fixtures, not by a real run on a
  consumer. A consumer should watch its first runs.
- Not verified: that `job.workflow_repository` and `job.workflow_sha` hold the called workflow's own repository and commit
  inside a real cross-repository call. A spike measured them in a step's `with:` (no `id-token` permission needed); the
  first canary run in a consumer covers the rest (D-004). If they were wrong, the verify step would fail the job rather than
  run other code.
- The folders `engine/` and `project-config/` are the workflow's own, in the caller's workspace. Each load deletes them
  before it checks them out, so a consumer must keep those two names free. `check-project` fails (rule `reserved`) when
  either exists in the project root, tracked or not. A failed engine verification also removes `engine/`, so a later step
  cannot run an unverified checkout.

## This repository

The engine repository is protected more strictly than its consumers, because a compromised engine reaches every consumer's
token. The settings are recorded in D-002 (`docs/DECISIONS.md`): a branch ruleset that requires a pull request and a code
owner's review, an immutable `v*` tag ruleset, read-only workflow permissions, secret scanning with push protection, immutable
releases, and no secrets or variables at all. The engine holds no secret; consumers pass theirs by name.

**Who can cut a release (D-005).** Only a merge into `main`, which the branch ruleset limits to a pull request with a code
owner's approval. A release PR moves the `[Unreleased]` notes under a new `## [X.Y.Z] - YYYY-MM-DD` heading and bumps the
version; merging it starts `.github/workflows/release.yml`, which checks that the changelog, `pyproject.toml` and the engine
agree, then creates the annotated `vX.Y.Z` tag on the merged commit and the release. That job holds `contents: write` and
nothing else, and only its tag and release steps see the token. It never touches an existing tag. No person and no agent
pushes a release tag by hand; the agent session cannot push tags at all.

The engine also holds no project name, no personal data and no secret. `tests/test_guard_engine.py` fails the build if a
tracked file contains a project name, a maintainer handle, an email address or a phone number outside a short, explicit
allow-list.
