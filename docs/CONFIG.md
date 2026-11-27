# Configuration

A project gives the engine its values in one file, `.github/sdlc-config.json`. The skeleton is
`template/.github/sdlc-config.json`; a worked, minimal project is `tests/fixture-project/`.

How the file is read:

- The workflow passes it with `--config "$SDLC_CONFIG"`, a sparse checkout of the **trigger commit** of the caller (the
  default branch's commit for an issue event) into `project-config/`, never the agent's branch and never the workspace
  root. A change to it takes effect only once a human has merged it.
- It must carry `"config_version": 1`. A file with no version, or a version this engine does not read, stops the run with a
  message that says so. A change to the shape of the file will bump the version and say BREAKING in `CHANGELOG.md`.
- A malformed file stops the run. A `--config` path that names no file stops the run. Nothing falls back silently,
  because a wrong value could let a stage write where it must not.
- With no `--config` at all, the engine's built-in values apply. They are generic: they name no project.
- `.github/sdlc-config.json` is itself a protected path, so no agent can write it.
- YAML cannot read JSON, so a few values are also written in the workflow text (the runner, the model, the Python
  version, the titles, the committer). The engine's tests keep the file and the workflow equal.

Every key below is required unless it says optional. An unknown key is an error.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `config_version` | whole number | The shape of this file. Must be `1`; any other value, or none, stops the run. |
| `default_branch` | text | The branch pull requests target and the diff base (`origin/<branch>...HEAD`). |
| `agent_branch_prefix` | text | Prefix of the branch an agent works on: `<prefix><issue number>-<slug>`. |
| `artifact_dir` | text | Folder each issue's stage documents live in. Only `{n}` (issue number) and `{slug}` may appear. |
| `trusted_associations` | list of text | The issue author associations (`OWNER`, `MEMBER`, `COLLABORATOR`) whose newly opened issue starts a stage. |
| `label_to_stage` | object | Maps each `agent:*` label to a stage name from `stages`. Applying the label (by a person with write access) starts that stage. |
| `requestable_labels` | list of text | The only labels an agent may ask the workflow to apply, for example `needs-info`. |
| `stages` | object | One entry per stage; see below. |
| `protected_paths` | list of text | Path patterns no agent may ever write. Always include `.github/**`, `.claude/**` and the engine's own source. |
| `limits` | object | See below. |
| `secret_patterns_extra` | list of text | Extra regular expressions for a credential shape of your own. They are added to the built-in list and matched case-insensitively. May be empty. |
| `budget` | object | See below. |
| `model` | text | The model name the agent steps pass. |
| `test` | object | See below. |
| `git_identity` | object | See below. |
| `commit_title` | text | The commit message of an agent commit. It may use `$NUMBER` and `$STAGE`. |
| `pr_title` | text | The title of the draft pull request. It may use `$NUMBER` and `$ISSUE_TITLE`. |
| `runner` | text | The `runs-on` label of every job, for example `ubuntu-24.04`. |
| `prompt` | object, optional | Your own text for the stage prompts; see below. |

## `stages`

Each entry is named by a stage: `intent`, `spec`, `plan`, `build`, `review`, `release`, `support-l1`, `support-l2`,
`support-l3`. Every key is required, except `checkout`.

| Key | Type | Meaning |
|---|---|---|
| `roles` | list of text | The agents the stage uses, by file name in `.claude/agents/` (without `.md`). |
| `needs` | text or `null` | A file that must already be on the branch (for example `intent.md`), else the stage stops. `null` for none. |
| `writes` | list of text | The path patterns the stage may write. `{n}` and `{slug}` are replaced. Anything else it changes is rejected. |
| `repo` | true or false | Whether the stage changes files that are committed to the issue's branch and a draft pull request. |
| `tools` | text | The tools the agent may use, as the agent action's allow-list. Only read-only `git` commands may be allowed under `Bash`. |
| `turns` | whole number, at least 1 | The turn cap. The action enforces it after the run, so leave margin. |
| `checkout` | true or false, optional | Whether the stage checks out the issue's branch. Defaults to the value of `repo`. |

## `limits`

| Key | Meaning |
|---|---|
| `max_files` | The most files one agent run may change. |
| `max_added_bytes` | The most bytes it may add. |

## `budget`

The agents run on a subscription with usage limits, so a cap on agent time protects it. The gate adds up the minutes of
earlier runs of the caller workflow.

| Key | Meaning |
|---|---|
| `cap_24h` | Agent minutes allowed in a rolling 24 hours. |
| `cap_7d` | Agent minutes allowed in a rolling 7 days. |
| `min_run_seconds` | Runs shorter than this do not count. |
| `mention` | Optional. The handle that starts the comment when the gate or the review cap blocks a run, for example `@your-github-handle`. Empty means no handle. |

## `test`

The engine never runs your tests in the privileged job. It starts the project's own workflow on the agent branch and reads
its check.

| Key | Meaning |
|---|---|
| `command` | The command the project's tests workflow runs. |
| `check_name` | The name of the job, and so of the check, the reviewers look for. |
| `workflow` | The file name of the project's tests workflow, which must accept `workflow_dispatch`. |
| `python` | The Python version of that workflow. |

## `git_identity`

| Key | Meaning |
|---|---|
| `name` | The committer name of an agent commit. The stage workflow sets `sdlc-engine-bot`; keep this equal to it. |
| `email` | The committer email: the public GitHub Actions bot address. Keep it equal to the workflow. |

## `prompt` (optional)

Every key is optional. Without them the engine's generic text applies.

| Key | Meaning |
|---|---|
| `never_touch` | A sentence naming the files a stage must never read or write. Empty leaves the sentence out. |
| `read_first` | The documents every stage reads first. A non-empty list. Default: `CLAUDE.md`, `docs/SDLC.md`. |
| `support_sources` | Where first-line support answers from. Default: `README.md and docs/`. |
| `support_bundle` | A command whose output is safe to paste into an issue. Empty leaves the clause out. |

## Repository variables

Set these under Settings, Secrets and variables, Actions, Variables. All are optional. An unset or non-numeric value means
the default, never unlimited.

| Repository variable | Meaning | Default |
|---|---|---|
| `SDLC_MAX_AGENT_MIN_24H` | Agent minutes allowed in a rolling 24 hours. | 60 |
| `SDLC_MAX_AGENT_MIN_7D` | Agent minutes allowed in a rolling 7 days. | 240 |
| `SDLC_MAX_REVIEW_ROUNDS` | How many reviews may run on one issue. | 3 |
| `SDLC_REVIEW_VERIFY` | Set it to exactly `true` to turn the optional verifier on. | off |

- **To stop everything**, set either agent-minute variable to `0`: every stage is refused until you raise it. Exactly at a
  cap is allowed.
- **Review rounds.** Each posted review carries a hidden marker. The round is one more than the markers in the issue's
  comments written by the workflow's own bot; a marker from anyone else is ignored. A review runs while its round is at
  most the cap; with the default, rounds 1 to 3 run and round 4 is blocked. If the issue's comments cannot be read, the
  review is blocked too (fail closed). A blocked round runs no review agent and posts one short comment that starts with
  `budget.mention`.
- **Diff only from round 3.** The review reads only the change since the commit in the latest marker, while that commit is
  still an ancestor of the branch; otherwise it reads the full diff.
- **The verifier** is a second read-only agent that checks each IMPORTANT finding against the code. Only a confirmed
  finding is posted. It is off by default because it is one more model call on every review that has an IMPORTANT finding.
- **To stop reviews entirely**, set `SDLC_MAX_REVIEW_ROUNDS` to `0`: every review is blocked and the build still runs and
  posts its report. Remove the variable to go back to 3.

## Secrets

| Secret | Meaning |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | The token the agent steps authenticate with. The caller workflow passes it to the stage workflow **by name**; it never uses `secrets: inherit`. The engine repository holds no secret of its own. |

## Checking a project: `check-project`

```bash
git clone https://github.com/RASMiranda/sdlc-engine /tmp/sdlc-engine
git -C /tmp/sdlc-engine checkout <the full 40-hex sha your sdlc.yml pins>
PYTHONPATH=/tmp/sdlc-engine/src python -P -m sdlc_engine check-project --root .
```

It reads files under `--root` only (standard library, no network, no git) and prints one plain message per failure to
standard error, each starting with the rule that failed. **Exit 1** on any failure, **0** when there is none (it then prints one
`ok:` line). Run it from the project root before a bump pull request is merged.

| Rule | Fails when |
|---|---|
| `config` | `.github/sdlc-config.json` is missing or not JSON, `config_version` is missing or not `1`, a required key is missing or unknown, or a value has the wrong type. The keys and types are the ones the engine itself enforces. |
| `roles` | A role named in `stages` has no `.claude/agents/<role>.md`. |
| `caller` | `.github/workflows/sdlc.yml` has no job `stage`, cannot be read, or differs from the config: the two `fromJSON` lists (author associations, then labels) in the job `if` and in the concurrency group must equal `trusted_associations` and the keys of `label_to_stage`, and `on.issues.types` must be exactly `opened` and `labeled`. |
| `pin` | The `stage` job's `uses:` is not `RASMiranda/sdlc-engine/.github/workflows/sdlc-stage.yml@` followed by 40 lowercase hex characters. A tag, a branch, a short sha, `./` or another repository fails. A trailing `# v0.2.0` comment is fine. |
| `secrets` | The call does not pass `CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`, uses `secrets: inherit`, passes any other secret, or passes a literal value. |

The stage workflow has no inputs, so there is no engine input to compare. The caller file is read by a small reader for
the YAML a caller uses; a file outside that subset (anchors, multi-line values) fails with "cannot be read" instead of being
guessed at. `check-project` does not say whether the pinned sha is the newest engine release.
