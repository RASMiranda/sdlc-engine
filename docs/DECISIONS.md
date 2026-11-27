# Decisions

Decisions about this repository, newest last. A decision is never edited after it is merged; a later one supersedes it.

## D-001: Engine extraction from career-ai (2026-11-27, Bangkok)

Source: career-ai ADR-082, "The SDLC engine moves to a shared public repo, sdlc-engine (S3)". Extracted at career-ai@a2422d8b2512b3065c3f68a7bddc470006a7d22c.

Context. The agentic SDLC (engine, reusable stage workflow, goldens; career-ai ADR-064 to ADR-068 and ADR-073 to ADR-077) lived inside career-ai. A second project, motion-blueprint-app (a public JavaScript PWA with npm tests), will use the same workflow. A third repository that holds personal data stays out on purpose: the agents can read a whole repository they run in (non-negotiables 1 and 2).

Decision.

* (a) A public repository, RASMiranda/sdlc-engine, holds the stdlib-only engine, the reusable workflow `sdlc-stage.yml`, `template/` for new projects and the docs.
* (b) Each project keeps a thin caller `sdlc.yml`, `.github/sdlc-config.json` (with `config_version`), its agents, labels, `REVIEW.md` and CODEOWNERS.
* (c) A project pins the engine by the full 40-hex commit SHA of a release, with a `# vX.Y.Z` comment; never `@main`, never a tag.
* (d) Releases follow SemVer, 0.y.z until 1.0. A breaking change bumps the minor and says BREAKING in `CHANGELOG.md`. Tags `vX.Y.Z` are annotated and protected by a tag ruleset.
* (e) Licence: MIT, matching motion-blueprint-app.
* (f) One `CLAUDE_CODE_OAUTH_TOKEN` per project repository. The Pro quota is shared and each budget gate counts only its own repository.
* (g) A bump is a PR in the project (Dependabot or by hand), a protected-path PR merged by a human, followed by a canary intent run. Rollback is a revert.
* (h) The engine repository is locked down harder than the projects: rulesets on main and on tags, read-only Actions permissions, no secrets, immutable releases (see D-002).
* (i) A `check-project` command compares the pin and the `config_version`; the running workflow verifies its own commit.

Consequences.

* An engine fix reaches a project only through a bump PR, so a fix is two merges per project. Every project can lag; `check-project` reports it.
* A compromised engine repository reaches every consumer's token, which is why (c) and (h) exist.
* Not verified when decided: whether Dependabot bumps a SHA-pinned reusable-workflow reference, and how a called workflow learns its own commit (a spike measures it before the cross-repo step). Immutable releases were available on this plan (D-002).

## D-002: Engine repo lock-down (2026-11-27, Bangkok)

Context. A compromised sdlc-engine reaches every consumer's token (career-ai, motion-blueprint-app), so the engine repo is protected more strictly than the consumers. Repo: RASMiranda/sdlc-engine, public, MIT licence (s3a). It was created with only a LICENSE commit, with no README, so the first PR adds the rest.
Decision. Six settings applied and confirmed on the settings pages:

1. Branch ruleset `protect-main`: PR required, 1 approval, Code Owners review, stale approvals dismissed, no force push, no deletion. Bypass is Repository admin, for pull requests only. The required CI check is added after the first CI run.
2. Tag ruleset on `v*`: restrict updates and deletions, with an empty bypass list, so a released tag can never move.
3. Actions: workflow permissions read-only, approval required for all external contributors' fork PRs, Actions cannot create or approve PRs.
4. Code security: secret scanning, push protection, Dependabot alerts and security updates, private vulnerability reporting.
5. Immutable releases: enabled.
6. No secrets and no variables at repo, environment, Dependabot or Codespaces level; no org-level secret or variable is shared with this repo.

Consequences.

* Releases are cut only via human-merged PRs plus a new `v*` tag; fixing a bad release means a new version, never a moved tag (non-negotiable 3).
* Admin bypass is PR-only, so there is no direct push to main.
* The tag ruleset itself is still editable by admins; this is a residual risk, mitigated by the ruleset-change audit trail.
* The engine holds no secrets, and consumers pass theirs by name (non-negotiable 4).
* Follow-ups: add CODEOWNERS in the first PR, add the required check after the first CI run, and add the guard test for non-negotiable 1.

## D-003: Neutral committer name and two exact-match email exceptions (2026-11-27, Bangkok)

Context. Before the first build, a scan of the copied `sdlc-stage.yml` and the engine's tests found strings the guard test
bans: the committer name `career-ai-sdlc` (a project name), the Co-Authored-By trailer address `noreply@anthropic.com`, and
the GitHub Actions bot committer address `41898282+github-actions[bot]@users.noreply.github.com`. The tests also held
sample paths, sample email addresses and one sample phone number, used to exercise the engine's own scanner. The first scan
named the first two; the third was found while the guard was written, because the guard's email pattern counts a bracketed
local part such as `[bot]`.

Decision.

1. The committer name in the engine's copy of `sdlc-stage.yml` is `sdlc-engine-bot`. `tests/golden/sdlc-steps.txt` is
   regenerated; it differs from its source only on that line. The fixture config carries the same name, so the test that
   keeps the config equal to the workflow text still holds. The source repository and its config are untouched.
2. The guard allows exactly two email literals, in any file, compared whole: `noreply@anthropic.com` and the bot committer
   address above. Every other email stays banned, including any other `anthropic.com` address and any gmail address; tests
   prove it. The maintainer approved the second literal on 2026-11-27 after the first scan.
3. Under `tests/` only, the RFC 2606 domains `example.com`, `example.org` and `example.net`, and any name beneath them, are
   allowed in sample addresses. The engine's scanner treats an address on a name that starts with `example.` as a placeholder,
   so a sample that it must flag as real has to sit beneath a reserved domain, not on it.
4. No exception is made for phone numbers. The one sample number the engine's scanner tests need, and the one `.test`
   placeholder address, are built from two string parts in `tests/test_sdlc.py`. They are fictional.
5. Test data that named the source project (`src/<project>/...` sample paths, a handle in a comment-author sample, the
   project's credential shape, its prompt text in the goldens) now uses neutral values. Assertions are unchanged.

Consequences.

* Step f (making the stage workflow callable from a consumer) must handle the committer-name change. A consumer's
  `git_identity.name` must equal the workflow's name, so each consumer's config and its own tests change from the old name
  to `sdlc-engine-bot`, and the authorship of agent commits in that consumer changes at the same time.
* The two email literals are a standing exception. A third needs a new decision.
* The goldens are rendered from the fixture project, not from a real project's config. A consumer that wants its own prompt
  text pinned byte for byte keeps its own golden files.
