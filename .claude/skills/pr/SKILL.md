---
name: pr
description: Push the current task branch, open a pull request against main, wait for CI, and report the result. Use when the user says "open a PR", "make a pull request", "push this for review", or runs /pr.
---

Open a pull request for the current branch. Follow these steps in order and stop at the first failure.

## 1. Check the branch and the tree

- Run `git branch --show-current`. If it prints `main`, stop and tell the user to create a task branch first (`git switch -c <type>/<short-name>`). Never open a PR from `main`.
- Run `git status --short`. If there are uncommitted changes, stop and tell the user to commit them with `/commit-msg` first. Do not commit anything yourself.
- Run `git log origin/main..HEAD --oneline`. If it is empty, stop: there is nothing to review.

## 2. Run the local checks

Run these and stop if any fails. Report the output, do not work around it:

1. `python -m ruff check .`
2. `python -m ruff format --check .`
3. `python -m pytest`

If the change touches `src/core/`, also run `/validate-calc-engine`. A change to a calculated number also needs hydrologist sign-off (docs/project_spec.md B7, step 7), so mention that in the PR body.

## 3. Push

`git push -u origin HEAD`. This asks the user for approval because `git push` is set to ask in `.claude/settings.json`. Do not use `--force`.

## 4. Write the PR

Title: the first commit's subject, or the branch's conventional subject if it summarises the work better. Under 70 characters.

Body, in this order:

```
## Summary
- what changed
- why (link the requirement ID, e.g. FR-M2-*, or the spec section)

## Test plan
- [ ] pytest passes locally
- [ ] ruff check and ruff format --check pass
- [ ] (only if numeric) goldens regenerated, hydrologist sign-off pending

## Review
- Findings from /code-review, each marked fixed or declined with the reason
```

The Review section is required by docs/project_spec.md D44: every review finding is fixed or declined here before merge. If no review ran, write "No review run yet" and say so to the user.

End the body with this line, exactly:

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Write the body to a file in `$CLAUDE_JOB_DIR/tmp` (or the scratchpad) and create the PR with `gh pr create --base main --title "<title>" --body-file <file>`. Do not add any other attribution line.

## 5. Watch CI

Run `gh pr checks --watch` and wait for the `ci` check. Report the result.

- **Green:** tell the user the PR URL. Merge only if they have asked to, or if the standing rule applies: squash-merge with `gh pr merge --squash --delete-branch`. That command asks for approval, so it will not run silently.
- **Red:** run `gh run view --log-failed`, summarise the failing step and the first error, and stop. Do not retry the push or skip checks.

## 6. Report

Show the PR URL, the CI status, and the next step: either "merge when ready" or the failing step to fix.
