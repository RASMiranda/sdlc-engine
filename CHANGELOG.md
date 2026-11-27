# Changelog

All notable changes to this project are recorded here. The format follows Keep a Changelog; versions follow Semantic
Versioning. A released tag is never moved: a fix is a new version.

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
