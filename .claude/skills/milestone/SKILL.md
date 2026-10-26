---
name: milestone
description: Start the next work package from the roadmap in project_spec.md, state its success criteria, and cut a task branch before any code changes. Use when the user says "start the next milestone", "start M2", "next work package", or runs /milestone.
---

Begin one milestone or work package from `project_spec.md`. Do not edit code until steps 1 to 3 are done and the user has confirmed the plan.

## 1. Find the milestone

Read the roadmap table in `project_spec.md` under **B8. Roadmap**. Take the milestone the user named (for example `M2`). If they named none, take the first row whose status is not `Done`. Report which one you chose.

If the milestone's status is `Not started`, continue. If it is `Done`, stop and say so. If the user asks for a sub-task, use the matching row in the spec's requirement sections (A6 and B3).

## 2. State the success criteria

Read the milestone's **Exit criteria** cell and the requirement section it points to (for example `FR-M2-*` in A6 and the calculation in B3.1). Then write out:

- The requirement IDs that must have passing tests.
- The concrete checks: the pytest targets (`tests/unit/...`, `tests/contract/...`), and any golden outputs or sign-off the milestone needs.
- What is out of scope, taken from the milestone's Tasks cell and the decision log.

Do this before any edit, as CLAUDE.md asks. If the spec is ambiguous or two approaches differ materially, list the trade-off and ask the user to choose.

## 3. Get the go-ahead

Stop and wait for the user to approve the plan. Do not start implementing in the same reply. The user may change model or effort first.

## 4. Cut the branch

After approval:

1. Run `git status --short`. If there are uncommitted changes, stop and ask the user what to do with them. Do not stash or discard them.
2. Run `git switch main` and `git pull --ff-only`.
3. Run `git switch -c <type>/<milestone-slug>`, for example `feat/m2-suspended`, where `type` is `feat`, `fix`, `refactor` or `chore`.

## 5. Work the Definition of Done

Follow project_spec.md B7 in order:

1. Write failing tests that reference the requirement IDs.
2. Implement the smallest change that passes.
3. Run `python -m pytest` and `/validate-calc-engine`. Both must pass.
4. Run `/code-review` and resolve its findings.
5. Commit with `/commit-msg`. Do not add a `Co-Authored-By` trailer.
6. Open the pull request with `/pr`.

Keep the change to the milestone's scope. Record any new design decision in the spec's Appendix decision log, and tell the user about it.

## 6. Update the roadmap

When the PR is merged and the exit criteria are met, change the milestone's Status cell in `project_spec.md` to `Done` on the same branch. If the hydrologist sign-off is still pending, write `Done (sign-off pending)` instead.

## 7. Report

Summarise: the milestone, the criteria and whether each passed, the branch name, the PR URL, and what is still open.
