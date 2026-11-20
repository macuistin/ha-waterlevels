# Docs, writing and workflow

## Writing

- UK English everywhere: code comments, docs, strings, commits (behaviour, colour, licence).
  The Irish translation follows `ga.json` conventions.
- Short sentences, action verbs, concrete names (files, fields, entities). A paragraph over three
  sentences is usually overwritten.
- No em dash to bolt on an afterthought. Use a comma or a full stop, or reword.
- A comment says why, never what the next line does. Delete commented-out code.

## Docs are generic

`README.md`, `docs/` and every user-facing string are written for any user at any station. They
never mention the maintainer, a household, a personal device, a home location, people's names or
avatars. Describe a setting by its meaning and unit, with a labelled round-number example.

## Unofficial

The integration is not made or endorsed by the OPW (waterlevel.ie), the Environment Agency or
SEPA. Say so wherever a source is named in a README, a string or the repository description, and
never copy their logos.

## Commits and pull requests

- Conventional Commits for commit messages and PR titles: `feat(sensor): ...`, `fix(config): ...`.
- PR body: `.github/PULL_REQUEST_TEMPLATE.md`. List what was not verified under Testing. Keep any
  attribution lines the session or project asks for; they are the one thing added to the template.
- Related PRs are stacked: each is based on the branch below it. Merge commits, not squash.
- Never rebase, amend or force-push a branch that has an open PR. Address review feedback with
  new commits.
- When a lower PR merges, retarget the next one to `main` and merge `main` into it.
- Nothing merges unless CI is green on the exact head commit. Never merge a PR, run the Release
  workflow or push a tag unless the maintainer asks.
