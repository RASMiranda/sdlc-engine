# Security policy

## Reporting a vulnerability

Report it privately through GitHub: open this repository's **Security** tab and choose **Report a vulnerability**
(GitHub private vulnerability reporting). That is the only channel. Please do not open a public issue or pull request for a
vulnerability, and do not send details anywhere else.

Include what you found, the version or commit, and the smallest way to reproduce it. A realistic path from an input to a
harm helps most.

## What is in scope

This engine runs inside its consumers' workflows next to their tokens, so these matter most:

- a way for text an agent or an issue controls to reach a step that holds a token;
- a way for an agent to write a protected path, to push, or to widen a permission;
- a way for a credential, an email address or a phone number to reach a posted text unscanned;
- a way for a consumer to run engine code or config that was not pinned or not from the default branch;
- a weakened control in the stage workflow or in the engine's checks.

## Supported versions

Only the latest release is supported. A bad release is fixed by a new version, never by moving a tag.

## What the engine holds

The engine holds no secrets, and none are needed to run its tests. Consumers pass their own secrets to the stage workflow by
name.
