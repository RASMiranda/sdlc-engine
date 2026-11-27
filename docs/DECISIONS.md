# Decisions

Decisions about this repository, newest last. A decision is never edited after it is merged; a later one supersedes it.

## D-001: Engine extraction from career-ai

TODO: paste text of the career-ai extraction ADR, to be provided by the maintainer

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
