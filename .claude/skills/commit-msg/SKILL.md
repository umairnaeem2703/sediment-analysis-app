---
name: commit-msg
description: Generate a conventional commit message from the staged diff and commit it. Use when the user says "write a commit message", "generate a commit", "commit my changes", or runs /commit-msg.
---

Write a commit for the currently staged changes only. Follow these steps in order.

## 1. Check for staged changes

Run `git diff --staged --stat`. If the output is empty, stop and tell the user to stage their changes first (`git add <files>`). Do not stage anything yourself and do not commit.

## 2. Read the staged diff

Run `git diff --staged` and read the full output. If the diff is very large, also run `git diff --staged --stat` and read the relevant hunks in more detail so the message describes what actually changed.

## 3. Write the message

Use this exact format:

```
type(scope): short subject

- bullet of what changed
- bullet of why
```

Rules:

- **type** is one of: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`. Pick the one that matches the primary intent of the change.
- **scope** is the area of the codebase the change touches, in lowercase, such as `rusle`, `wilcock`, `reservoir`, `services`, `ui`, `inputs`, or `tests`. Omit the parentheses entirely if no single scope fits.
- **subject** is imperative, lowercase after the colon, with no trailing period, and **under 60 characters** total for the whole first line.
- **body bullets** are optional but encouraged. Use one bullet for what changed and one for why. Keep each bullet to one line where possible. Describe the change from the diff, not from guesses.
- **Never** add a `Co-Authored-By` trailer or any other attribution line. The message ends with the last body bullet, or the subject if there are no bullets.

Before committing, check the subject length (the first line must be under 60 characters). If it is too long, shorten it.

## 4. Commit

Write the message to a file in the scratchpad directory and commit with `-F` so quoting and multi-line text are handled correctly:

```
git commit -F <scratchpad-file>
```

Do not use `--no-verify` or any flag that skips hooks. If a hook fails, report the failure output to the user and do not retry with bypass flags.

After the commit succeeds, run `git log -1 --format=%B` and show the user the committed message and the short hash.
