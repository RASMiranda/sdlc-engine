# Changelog

All notable changes to this project are recorded here. The format follows Keep a Changelog; versions follow Semantic
Versioning. A released tag is never moved: a fix is a new version.

## [Unreleased]

## [0.2.0] - 2026-11-27

The stage workflow is callable from another repository (D-004). **BREAKING**: read the two notes below before bumping a pin.

### BREAKING
- `config_version` is required in `.github/sdlc-config.json` and must be `1`. A file without it, or with another value, now
  stops the run. The config change and the pin bump must be in the SAME pull request: an engine without `config_version` support rejects
  the key as unknown, and this engine rejects a file without it.
- The stage workflow is no longer callable from a repository that carries its own `src/`: it now loads the engine from its own
  repository and commit (`job.workflow_repository` at `job.workflow_sha`) into `engine/`, and the project config from the
  caller's trigger commit into `project-config/`, instead of reading `src` and `.github/sdlc-config.json` from the caller's
  workspace. The folders `engine/` and `project-config/` are now reserved in the caller's workspace (D-004).

### Added
- `python -m sdlc_engine check-project --root DIR`: checks the config, the roles, the caller workflow, the pin and the secrets
  of a consumer project (see `docs/CONFIG.md`). Standard library only, no network.
- A verify step after every engine checkout fails the job unless the checkout is exactly `job.workflow_sha`, and writes that
  commit to the job summary. There is no `engine_sha` input. On a failed verification the step removes `engine/`, so later
  steps cannot run an unverified checkout.
- `check-project` rule `reserved`: fails when `engine` or `project-config` exists in the project root.

### Changed
- `decide` and the budget gate run `PYTHONPATH="$TRUSTED_SRC" python -P` on the engine checkout, with `--config "$SDLC_CONFIG"`.
  Every engine call reads the config from `$SDLC_CONFIG`; the `$TRUSTED_SRC/../.github/sdlc-config.json` form is gone.
- Each trusted load is five steps (clear, engine checkout, verify, config checkout, use it) and there are four loads: one before
  `decide`, one before the agent, and one after each agent run. Permissions, triggers, tools, model and token handling are as before.

## [0.1.0] - 2026-11-27

Initial extraction from career-ai@a2422d8b2512b3065c3f68a7bddc470006a7d22c.

### Added
- The `sdlc_engine` package (standard library only), copied from career-ai at that commit, with `--version` read from
  `pyproject.toml`. No project name appears in the code or its strings.
- `.github/workflows/sdlc-stage.yml`, the reusable stage workflow, copied as it was. The only change is the committer name,
  now `sdlc-engine-bot` (see D-003). Making it callable from another repository is a later step.
- The engine's tests and golden files. Tests that read a project's files now read `tests/fixture-project/`.
- `template/`, the files a new project copies: caller workflow, config skeleton, labels, issue forms, pull request template,
  CODEOWNERS, agents, settings, review rules.
- A guard test that fails when a tracked file holds a project name, a maintainer handle, an email address or a phone number
  outside an explicit allow-list.
- `tests.yml` with read-only permissions and every third-party action pinned by full commit SHA.
- `README.md`, `SECURITY.md`, `docs/CONFIG.md`, `docs/SECURITY-MODEL.md`, `docs/DECISIONS.md`.
