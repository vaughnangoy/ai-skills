# E2E test plan: feature-creator-skill

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`feature-creator-skill/SKILL.md`](../../feature-creator-skill/SKILL.md) and the [`worktree-strategy` POLICY](https://github.com/vaughnangoy/worktree-strategy/blob/main/POLICY.md)
**Test status:** spec (no executable e2e harness yet — the skill drives an interactive AI session and would need an agent harness to fully exercise)

---

## Scenario 1 (happy) — Create a feature worktree from a clean main worktree

**Setup**
- A scratch git repo cloned to `/tmp/fc-e2e-repo/` with at least one commit on `main`
- Repo has a working `origin` remote (a local bare repo at `/tmp/fc-e2e-origin.git` is enough)
- Current working directory is `/tmp/fc-e2e-repo/`
- `/tmp/fc-e2e-repo-worktrees/` does not yet exist
- An AI session active with the feature-creator-skill loaded

**Steps**
1. In the AI session say: "Add a feature called `dark-mode` to this repo"
2. The skill activates, builds the repo registry, and proposes the worktree path
3. Reply `yes` to the worktree creation prompt

**Expected**
- `/tmp/fc-e2e-repo-worktrees/feature/dark-mode/` exists and is a valid git worktree (`git worktree list` from the main repo lists it)
- The new worktree is on branch `feature/dark-mode` tracking `origin/main`
- `/tmp/fc-e2e-repo/` (the main worktree) remains on `main` — `git -C /tmp/fc-e2e-repo symbolic-ref --short HEAD` returns `main`
- The skill's confirmation summary lists the correct paths and branch
- Repo registry now records `feature_worktree_root=/tmp/fc-e2e-repo-worktrees/feature/dark-mode/`

---

## Scenario 2 (happy) — Per-change commit + push opens a draft PR on first push

**Setup**
- A repo prepared as in Scenario 1, with the `feature/dark-mode` worktree created
- A working task completed: one source file added under `feature/dark-mode`, with passing unit + integration + e2e tests, README updated, and `CHANGELOG.md` `[Unreleased]` bullet added
- `gh` CLI authenticated and able to create PRs against the origin
- `pr_state` in registry is `none`

**Steps**
1. Trigger the Step 6 commit + push flow (e.g. say: "commit and push this change")
2. Reply `yes` to the commit + push confirmation

**Expected**
- `git -C <feature_worktree_root> log -1 --pretty=%s` returns a conventional commit subject (e.g. `feat(...): ...`)
- The commit includes only the files in the task plus the updated `CHANGELOG.md` (verified by `git show --stat HEAD`)
- `git push -u origin feature/dark-mode` succeeded — `git ls-remote origin feature/dark-mode` returns a SHA
- `gh pr list --state open --head feature/dark-mode --json url,isDraft` returns exactly one PR with `isDraft: true`
- Repo registry now records `pr_url=https://github.com/.../pull/N` and `pr_state=draft`

---

## Scenario 3 (sad) — Refuse to edit a file inside the main worktree

**Setup**
- A repo with both main worktree (`/tmp/fc-e2e-repo/`) and feature worktree (`/tmp/fc-e2e-repo-worktrees/feature/dark-mode/`)
- The current AI session has the feature-creator-skill active with `feature_worktree_root` pointing at the feature worktree

**Steps**
1. Ask the skill to "edit `/tmp/fc-e2e-repo/src/index.ts` and add a function `foo()`"
2. Observe how the skill handles the request

**Expected**
- The skill detects that the target path resolves under the main worktree, **not** the feature worktree
- The skill refuses the change and re-routes the edit to `/tmp/fc-e2e-repo-worktrees/feature/dark-mode/src/index.ts`
- `/tmp/fc-e2e-repo/src/index.ts` is **not** modified (verify via mtime or content hash before/after)
- The skill explicitly tells the user the safety check fired and why

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Build a harness that drives an AI session non-interactively (Claude Code CLI `--print` mode, or the Copilot Chat agent API once available)
2. Stand up disposable git repos per scenario:
   ```bash
   git init --bare /tmp/fc-e2e-origin.git
   git clone /tmp/fc-e2e-origin.git /tmp/fc-e2e-repo
   ```
3. For Scenario 2's PR assertion, point the origin at a real GitHub test repo and clean up afterwards with `gh pr close --delete-branch`
4. Capture the AI agent's tool calls (file writes, `git` commands, `gh` commands) and assert on the path arguments — Scenario 3 should show zero writes targeting paths under the main worktree
5. Tear down: `git worktree remove --force` then `rm -rf` the worktrees root, and close + delete any PRs created
