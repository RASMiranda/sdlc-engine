# Review rules (read by the review agent and by `tech-lead`)

Scope: every PR to this repository. The agent that wrote the code never approves it. The review never approves or blocks
by itself: a human merges. Its output shape is fixed by the engine: one line per finding, `IMPORTANT`, `NIT` or
`PRE-EXISTING`, then `path:line`.

## What failure looks like, per area
Look for the failure that would reach the owner, not for style. Replace or extend these for your project.
- **Docs**: a statement that is false about the code or the diff.
- **Workflow and config** (`.github/`): a change that misroutes a run: the wrong stage runs, a gate is skipped, a label or
  a protected path is missing or wrong.
- **Code** (`src/`): <what a real failure looks like here, for example a leak or a skipped check>.
- **Tests**: a test that passes without checking anything: no assertion, an assertion that cannot fail, a test edited to
  match a fix, a skipped test with no reason.

## Evidence
- Every IMPORTANT and NIT cites `path:line` (or a range such as `10-20`) on a line the diff adds or shows as context.
- A finding without a line from the diff is not reported. The workflow drops such a finding and says so.
- Name the realistic failure: the input and the wrong result. "Could be wrong" is not a finding.

## Severity
- **IMPORTANT**: blocks the next gate. Contract, secrets and personal data, correctness, missing tests.
- **NIT**: at most three per PR, something the author would plausibly change.
- **PRE-EXISTING**: a problem the diff did not introduce. It never blocks and is not checked against the diff.

## What is not reviewed
Lockfiles, generated files, and formatting the code already follows.

## Risk tier
The workflow computes the tier from the changed paths, never from the author: HIGH when a protected path changed
(`.github/sdlc-config.json` lists them), MEDIUM for code outside them, LOW for docs and tests only.

## Human approval
Squash-merge needs the `pytest` check green and a code owner's review.
