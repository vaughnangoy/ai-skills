---
name: feature-creator
description: "Structured feature development workflow for any git repository, built on the worktree-strategy POLICY (PR-first, per-change push cadence, sibling worktrees, never check out feature branches in the main worktree). Activated by /feature-creator or automatically when the session involves creating new features, modifying existing behavior, or non-trivial refactoring. Manages: feature worktree creation in <repo>-worktrees/, pre-change confirmation gates, test-driven development with visible subprocess test runs, per-commit CHANGELOG.md updates (one changelog per repo), commit + push + draft-PR offers after each verified working task, and post-merge worktree pruning via git prune-worktrees. In multi-repo sessions, independently tracks worktree state and changelog for every active repository. Offers to engage the superpowers approach (writing-plans, executing-plans, test-driven-development) when feature scope warrants it. Use for /feature-creator, 'start a feature', 'build a feature', 'add feature', 'refactor X', 'change behavior of X', or any session where the user is making non-trivial code changes."
argument-hint: "[<feature-name>] — optional short name for the feature worktree/branch (e.g. add-dark-mode, refactor-auth)"
---

# Feature Creator Skill

Wraps every feature development session in a consistent worktree-based workflow: **sync main → create worktree → confirm → test-first → run → commit → push → draft PR → changelog**. Works across any number of git repos in the session, giving each its own dedicated worktree, branch, and `CHANGELOG.md`.

This skill is the agent-facing companion to the [`worktree-strategy`](https://github.com/vaughnangoy/worktree-strategy) toolkit. The full rules live in that repo's [`POLICY.md`](https://github.com/vaughnangoy/worktree-strategy/blob/main/POLICY.md); this skill encodes them as a step-by-step procedure.

## Core rules (from POLICY.md)

- **Main worktree stays on `main` permanently.** Never `git checkout <branch>` inside it.
- **Every feature, fix, or refactor → a new sibling worktree** at `<repo-root>-worktrees/<type>/<name>/`.
- **Integration is always via Pull Request** — never a local `git merge` into main.
- **Push cadence is per-change**, not end-of-feature: every E2E-green change pushes to the open PR.
- **First push opens the PR as `--draft`**, kept open and updated by every subsequent push.
- **Cleanup uses `git prune-worktrees`** (from worktree-strategy) — never `--force`.

---

## Definitions

| Term | Meaning |
|---|---|
| **Feature** | New capability, new endpoint, new UI component, new script |
| **Behaviour modification** | Change to existing logic that alters observable output |
| **Refactor** | Structural change with no observable behaviour change |
| **Working task** | A discrete unit of work where all tests pass and the feature behaves correctly |
| **Active repo** | Any git repo the session reads from or writes to |
| **Main worktree** | The original clone at `<repo-root>/`, permanently on the default branch |
| **Feature worktree** | A sibling dir at `<repo-root>-worktrees/<type>/<name>/` where work happens |
| **Worktrees root** | The sibling parent dir `<repo-root>-worktrees/` that contains all feature worktrees for one repo |
| **Push trigger** | The 5 conditions (unit + integration + e2e green, docs + e2e doc updated, CHANGELOG entry added) that gate every push |
| **E2E doc** | The per-feature spec at `<feature_worktree_root>/docs/e2e/<feature-name>-YYYY-MM-DD.md` capturing every e2e scenario (2 happy + 1 sad minimum) — one file per feature, dated at first creation, appended-to as scenarios grow |

---

## Procedure

Follow these steps **exactly** when `/feature-creator` is invoked **or** when the session is recognised as feature development (see Step 0).

---

### Step 0 — Recognise the session

Before the first code change in any session, assess the work being requested.

**Triggers for automatic activation:**

- User says "add", "create", "build", "implement", "write", or "introduce" + a feature name
- User says "refactor", "rework", "redesign", "restructure", or "clean up" existing code
- User says "change the behaviour / logic / output of" something
- User modifies a function signature, changes a return type, renames a public API
- User adds a new file that contains business logic, a handler, a route, or a script
- The session involves changes across more than one file

**Not a trigger (skip this skill):**

- Fixing a typo, updating a comment, changing a config value with no logic change
- One-line hotfix where the cause is already known and the fix is trivial

**On activation**, announce to the user:

> **Feature Creator activated** (worktree workflow).
> I'll manage worktree setup, pre-change confirmation, tests, per-change commit + push, draft PR creation, and changelogs for this session — following the [`worktree-strategy`](https://github.com/vaughnangoy/worktree-strategy) POLICY.
> Type `/feature-creator off` at any time to disable for the remainder of the session.

If the user types `/feature-creator off`, stop enforcing the workflow silently and confirm:

> **Feature Creator paused.** I'll stop gating changes for this session.

---

### Step 1 — Superpowers check

Evaluate the scope of work:

- **Non-trivial** = more than ~3 files touched, or a new subsystem, or a behaviour change with unknown ripple effects
- **Trivial** = contained change, well-understood scope, 1–2 files

If the scope is **non-trivial**, offer the superpowers approach before proceeding:

> **This looks like a non-trivial task. Would you like to use the superpowers approach?**
>
> The superpowers approach means:
> - **writing-plans** — drafting a step-by-step implementation plan before touching any code
> - **executing-plans** — working through the plan task by task with explicit checkboxes
> - **test-driven-development** — writing failing tests before writing implementation code
>
> This is recommended for features that touch multiple systems, have unclear scope, or carry risk of regressions.
>
> **Reply with:**
> — **yes / superpowers** to activate the full approach
> — **plan only** to just write a plan first, then proceed normally
> — **tdd only** to use test-first development without a formal plan
> — **skip** to proceed without superpowers

**If yes / superpowers:**
1. Write a full implementation plan (numbered tasks, files affected, test strategy per task) before any code changes
2. Present it to the user for approval
3. Wait for explicit "looks good" or "proceed" before starting Step 2
4. Work through tasks one at a time using the plan as the source of truth

**If plan only:** Draft the plan and wait for approval, then proceed to Step 2.

**If tdd only:** Enforce test-first on every task (Step 5a), skip formal plan.

**If skip / trivial scope:** Proceed directly to Step 2.

---

### Step 2 — Build the repo registry

Identify every git repo that will be touched this session.

For each repo, inspect both the current working directory and the existing worktrees:

```bash
git -C <repo-path> rev-parse --show-toplevel 2>/dev/null
git -C <repo-path> symbolic-ref --short HEAD 2>/dev/null
git -C <repo-path> remote get-url origin 2>/dev/null
git -C <repo-path> worktree list --porcelain 2>/dev/null
```

The **main worktree** is the entry whose branch matches the default branch (`main` or `master`). Record for each repo:

| Field | Value |
|---|---|
| `main_worktree_root` | Absolute path of the main worktree (default-branch checkout) |
| `worktrees_root` | `<main_worktree_root>-worktrees/` (sibling dir; created lazily in Step 3) |
| `origin` | Remote URL (or "local" if none) |
| `main_branch` | `main` if it exists, else `master`, else ask |
| `feature_branch` | Set in Step 3 (e.g. `feature/<name>`) |
| `feature_worktree_root` | Set in Step 3 (`<worktrees_root><type>/<name>/`) |
| `pr_url` | Set in Step 6 after the first push |
| `pr_state` | `none` → `draft` → `ready` → `merged` (tracked across Steps 6/8) |
| `changelog_path` | `<feature_worktree_root>/CHANGELOG.md` |

**Finding the main branch:**

```bash
git -C <repo-path> branch --list main master
```

- If both exist → use `main`
- If neither exists → ask the user: "Which branch should I branch from in `<repo-name>`?"

**Detecting where you are:** parse `git worktree list --porcelain`. If the user's current working directory matches the main worktree root, Step 3 must move work to a feature worktree before any code changes. If it matches an existing feature worktree, capture it as `feature_worktree_root` and skip ahead to Step 4.

Repeat for every repo in the session. If a new repo is added mid-session (user opens a second project or installs a dependency repo), automatically add it to the registry and run Step 3 for it.

---

### Step 3 — Feature worktree setup (per repo)

**Hard rule:** never `git checkout <branch>` inside the main worktree. Every feature, fix, or refactor goes into its own sibling worktree.

Classify the change first to pick the prefix:

| User intent | Prefix |
|---|---|
| Add capability / new file / new endpoint | `feature/` |
| Fix incorrect behaviour | `fix/` |
| Restructure with no observable change | `refactor/` |

For each repo in the registry:

> **Set up a worktree in `<repo-name>`?**
>
> | | |
> |---|---|
> | **Main worktree** | `<main_worktree_root>` (stays on `<main-branch>`) |
> | **New worktree path** | `<main_worktree_root>-worktrees/<type>/<feature-name>/` |
> | **New branch** | `<type>/<feature-name>` (created from `origin/<main-branch>`) |
>
> **Options:**
> — **yes** to create the worktree + branch
> — **name** to use a different feature name
> — **type** to switch prefix (feature / fix / refactor)
> — **existing** to reuse an existing worktree (provide path)
> — **skip** to work directly in current dir (⚠️ violates POLICY; require explicit override)

**If yes** — sync main, then create the worktree (all output captured to a temp file to avoid terminal stalls):

```bash
{
  echo "=== sync main ==="
  git -C <main_worktree_root> fetch --prune origin
  git -C <main_worktree_root> pull --ff-only origin <main-branch>
  echo "=== create worktree ==="
  mkdir -p <main_worktree_root>-worktrees/<type>
  git -C <main_worktree_root> worktree add \
      <main_worktree_root>-worktrees/<type>/<feature-name> \
      -b <type>/<feature-name> origin/<main-branch>
  echo "=== verify ==="
  git -C <main_worktree_root> worktree list
  echo "---DONE---"
} > /tmp/.fc_worktree_out 2>&1
```

Then read `/tmp/.fc_worktree_out` for the result.

**All subsequent shell commands for this repo MUST use the feature worktree path**, either via `cd <feature_worktree_root>` or `git -C <feature_worktree_root> …`. Never run feature-work commands against `<main_worktree_root>`.

**Confirm worktree creation:**

> ✅ **Worktree created**
>
> | | |
> |---|---|
> | **Repo** | `<repo-name>` |
> | **Worktree** | `<feature_worktree_root>` |
> | **Branch** | `<type>/<feature-name>` (tracking `origin/<main-branch>`) |

Update `feature_branch` and `feature_worktree_root` in the repo registry.

**If the user is already inside a feature worktree** when the session starts: skip creation, register the existing path as `feature_worktree_root`, and continue to Step 4.

**If the user picks `skip` (work in current dir):** require an explicit acknowledgement:

> ⚠️ This bypasses the worktree POLICY. Type `confirm bypass` to proceed; otherwise pick **yes** / **existing**.

---

### Step 4 — Pre-change confirmation gate

**This step applies before EVERY code change for the rest of the session.**

Before writing, editing, or deleting any file, present a confirmation:

> **Proposed change — confirm before proceeding**
>
> | | |
> |---|---|
> | **Repo** | `<repo-name>` |
> | **Worktree** | `<feature_worktree_root>` |
> | **Action** | Create / Edit / Delete |
> | **File(s)** | `path/to/file.ext` (resolved inside the feature worktree) |
> | **What changes** | `<one-sentence description of what will change and why>` |
>
> **yes** to proceed · **no** to cancel · **adjust** to change the approach first

**Safety check before every change:** assert the target file path resolves under `<feature_worktree_root>` and **not** under `<main_worktree_root>`. If a path resolves under the main worktree, refuse and re-route the change to the feature worktree.

Do not make changes until the user replies **yes** or an affirmative.

**Exception:** If the user has already approved a plan (Step 1) and the current change is an explicit step in that plan, a brief inline prompt is sufficient:

> Proceeding with step 3: create `src/auth/token.ts`. OK?

Still wait for confirmation.

---

### Step 5 — Test-driven development loop

For every working task:

#### Step 5a — Write the test first

Before implementing any new function, class, endpoint, or behaviour change:

1. Identify the test file (create it if it doesn't exist)
2. Write the test that describes the expected behaviour
3. Present the test to the user and confirm before creating it (Step 4 gate)
4. Create the test file

The test must be **specific** — it must fail for a well-defined reason (the function doesn't exist yet, or it returns the wrong thing).

#### Step 5b — Run the test and confirm it fails

Run the test suite in a **subprocess with full visible output** so the user can see what's happening:

```bash
<test-runner-command> 2>&1 | tee /tmp/.fc_test_out; echo "---DONE---"
```

Common test runners by ecosystem (always `cd` into the **feature worktree**, never the main worktree):

| Ecosystem | Command |
|---|---|
| Python (pytest) | `cd <feature_worktree_root> && uv run python -m pytest <test-file> -v` |
| Node.js (jest) | `cd <feature_worktree_root> && npx jest <test-file> --verbose` |
| Node.js (vitest) | `cd <feature_worktree_root> && npx vitest run <test-file>` |
| Go | `cd <feature_worktree_root> && go test ./... -v -run <TestName>` |
| Rust | `cd <feature_worktree_root> && cargo test <test_name> -- --nocapture` |
| Ruby | `cd <feature_worktree_root> && bundle exec rspec <test-file>` |
| Swift | `cd <feature_worktree_root> && swift test --filter <TestName>` |

**End-to-end runners** — pick the one that matches the layer under test:

| Layer | Runner |
|---|---|
| Web UI | `npx playwright test <spec>` or `npx cypress run --spec <spec>` |
| HTTP API (Node) | `npx jest tests/e2e/` (with `supertest`) against a running app |
| HTTP API (Python) | `uv run python -m pytest tests/e2e/ -v` (with `requests` / `httpx`) against a running app |
| CLI / shell tool | `bats tests/e2e/*.bats` or a shell script that exercises the binary end-to-end |
| Background job / pipeline | a script that submits a job and asserts the side effects (files written, DB rows, queue messages) |

Do **not** use `run_in_background`. Tests must run in the foreground so output is visible to the user.

Confirm the test fails with the expected error (import error, attribute error, assertion error, etc.) before continuing.

If the test unexpectedly passes, stop and investigate — the test may not be testing the right thing.

#### Step 5c — Implement to make the test pass

Apply the change gate (Step 4). Implement the minimum code required to make the test pass. Do not add logic beyond what the test requires.

#### Step 5d — Run the full test suite

After the implementation, run the **full test suite** for the repo (not just the new test):

```bash
<full-test-command> 2>&1 | tee /tmp/.fc_fulltest_out; echo "---DONE---"
```

Read `/tmp/.fc_fulltest_out`. Check for:

- All new tests pass
- No previously passing tests now fail (regression)

**If a regression is detected:**

> ⚠️ **Regression detected in `<repo-name>`**
>
> The following tests that previously passed are now failing:
> `<test-names>`
>
> I'll pause here and investigate before continuing.

Diagnose and fix the regression before proceeding to Step 5e.

#### Step 5e — End-to-end coverage and documentation

If the change is **user-observable** (new endpoint, new CLI command, new UI flow, new file output, new pipeline behaviour), you must add e2e coverage **before** moving to the push gate.

**When e2e is NOT required**:
- Pure internal refactor with no observable behaviour change
- Docs-only change
- Test-only change
- Config tweak with no runtime effect

In those cases, note in the commit body why e2e was skipped and continue to Step 5f.

##### Coverage pattern (minimum)

- **2 happy-path scenarios** — different valid inputs that exercise the main flow end-to-end
- **1 sad-path scenario** — invalid input, missing dependency, or expected failure mode

Run them with the appropriate e2e runner (see Step 5b's end-to-end runners table). All three must pass.

##### Document the scenarios in `docs/e2e/<feature-name>-YYYY-MM-DD.md`

Every feature gets a dedicated e2e spec at:

```
<feature_worktree_root>/docs/e2e/<feature-name>-YYYY-MM-DD.md
```

Rules:
- `<feature-name>` = the feature branch slug, kebab-case (e.g. `add-dark-mode`, `auth-refresh-rotation`)
- `YYYY-MM-DD` = the date the doc was **first created** — this date does not change as the file grows
- **One file per feature.** Append new scenarios to the existing file as the feature grows; do not create a new file per task
- The file is committed in the **same commit** as the e2e test code it describes

##### File template

```markdown
# E2E test plan: <feature title>

**Created:** YYYY-MM-DD
**Feature branch:** `feature/<name>`
**Source of truth:** link to the spec, PRD, SKILL.md, or design doc that drives this feature
**Test status:** spec / partial / executable

---

## Scenario 1 (happy) — <short descriptive name>

**Setup**
- preconditions, fixtures, env vars, services that must be running

**Steps**
1. concrete user-observable action
2. concrete user-observable action

**Expected**
- observable outcome 1
- observable outcome 2

---

## Scenario 2 (happy) — <short descriptive name>

…

---

## Scenario 3 (sad) — <short descriptive name>

…

---

## How to execute

- `<command to spin up any required services>`
- `<command to run these scenarios>`
- `<command to tear down>`
```

If the scenarios are not yet runnable as automated tests (spec-only), mark `**Test status:** spec` and note what's blocking execution in the **How to execute** section.

#### Step 5f — Confirm the task is working

Once all tests pass (unit + integration + e2e, where applicable) and the e2e doc has been updated, verify the feature behaves correctly if there's a way to check beyond tests (e.g., a script output, a CLI invocation, a UI check). Report to the user:

> ✅ **Task complete — all tests pass, no regressions, e2e doc updated.**

---

### Step 6 — Commit + push + PR flow (per change)

After each **working task** (Step 5f confirmed), apply the **push trigger** before doing anything. Per POLICY, a commit + push happens **if and only if all five** are true for the change just made:

1. Unit tests pass
2. The relevant integration test passes
3. End-to-end scenarios pass (2 happy + 1 sad minimum) AND documented in `docs/e2e/<feature-name>-YYYY-MM-DD.md` — OR explicitly skipped per Step 5e with the reason recorded in the commit body
4. README / docs updated in the same change (including `docs/e2e/<feature-name>-YYYY-MM-DD.md` when the task added or modified an e2e scenario)
5. CHANGELOG `## [Unreleased]` bullet added

If any fail → **do not commit, do not push.** Root-cause and fix first, then re-evaluate.

Once all five are true, offer the commit + push:

> **Commit + push this change?**
>
> | | |
> |---|---|
> | **Repo** | `<repo-name>` |
> | **Worktree** | `<feature_worktree_root>` |
> | **Branch** | `<feature-branch>` |
> | **Files changed** | `<file list>` |
> | **Suggested message** | `<type>(<scope>): <what changed and why>` |
> | **PR state** | `<pr_state>` (first push will open as `--draft`) |
>
> **yes** to commit + push with the suggested message · **edit** to write a custom message · **skip** to defer (⚠️ only if the push trigger isn't actually met)

#### Step 6a — Stage specific files

Never use `git add .` or `git add -A`. Stage only the files that are part of this working task (paths relative to the **feature worktree**):

```bash
git -C <feature_worktree_root> add <file1> <file2> ...
```

#### Step 6b — Commit message format

Use conventional commits. Scope = sub-feature or module:

```
<type>(<scope>): <imperative short description>

<body — what + why + tests added>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

Example:
```
feat(auth): add JWT refresh token rotation

Tokens now expire after 15 min and are rotated on each request.
Refresh tokens are stored hashed in Redis with a 7-day TTL.
Covered by tests/auth/test_refresh_rotation.py.
```

#### Step 6c — Update CHANGELOG.md before committing

Before running `git commit`, update `<feature_worktree_root>/CHANGELOG.md` (Step 7), then stage it as part of the same commit.

#### Step 6d — Run git commit

```bash
git -C <feature_worktree_root> commit -m "$(cat <<'EOF'
<commit-message>
EOF
)"
```

#### Step 6e — Push and open / update the PR

**If this is the first push for this feature branch (`pr_state == none`):**

```bash
{
  git -C <feature_worktree_root> push -u origin <feature-branch>
  gh --repo <origin-owner>/<origin-repo> pr create \
    --base <main-branch> \
    --head <feature-branch> \
    --title "<conventional-commit subject>" \
    --body "<short body: links to plan / first commit subject>" \
    --draft
  echo "---DONE---"
} > /tmp/.fc_push_out 2>&1
```

Read `/tmp/.fc_push_out`, parse the PR URL, store it in the registry as `pr_url`, and set `pr_state = draft`. Confirm to the user:

> ✅ **Draft PR opened:** `<pr_url>`

**If the PR already exists (`pr_state in {draft, ready}`):**

```bash
git -C <feature_worktree_root> push origin <feature-branch> > /tmp/.fc_push_out 2>&1
echo "---DONE---" >> /tmp/.fc_push_out
```

The push automatically updates the PR — no extra command needed. Confirm:

> ✅ **PR updated:** `<pr_url>` (CI re-running)

#### Hard rules for this cadence

- ❌ No commits without all 5 push-trigger conditions met.
- ❌ No `--no-verify`. No force-push to a PR branch that has prior pushes.
- ❌ No local squashing before push (squash happens at PR-merge time on the remote).
- ❌ No local `git merge` into `main` — ever. PR-only.
- ✅ Commit + push is the only way to checkpoint work.
- ✅ If CI goes red, fix in the feature worktree and push again — do **not** close + reopen the PR.

---

### Step 7 — CHANGELOG.md management

Every active repo must have a `CHANGELOG.md` at its root. Every commit must update it.

#### Step 7a — Initialise CHANGELOG.md (if missing)

If `<feature_worktree_root>/CHANGELOG.md` does not exist, create it:

```markdown
# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

```

Then stage and include it in the first feature commit.

#### Step 7b — Update the Unreleased section

Before each commit, insert an entry under `## [Unreleased]` in the appropriate category:

| Category | When to use |
|---|---|
| `### Added` | New feature, new file, new endpoint, new command |
| `### Changed` | Modified behaviour, updated API, changed config |
| `### Fixed` | Bug fix, incorrect behaviour corrected |
| `### Removed` | Deleted code, removed command, dropped support |
| `### Refactored` | Internal restructure with no behaviour change |
| `### Security` | Security fix or hardening |

Format for each entry:

```markdown
## [Unreleased]

### Added
- `feature-name`: short description of what was added and why it matters

### Changed
- `module-name`: what changed and the motivation
```

Rules:
- Entries are written in plain English, from the user's perspective (not the implementer's)
- One bullet per logical change (not per file)
- Keep the section sorted: Added → Changed → Fixed → Removed → Refactored → Security
- Do not duplicate entries — check existing bullets before adding
- Do not record test-only changes in the changelog unless the tests themselves are the deliverable

#### Step 7c — Multi-repo sessions

In sessions with more than one repo, maintain independent changelogs:

- Each repo's `CHANGELOG.md` records only changes made **to that repo**
- Cross-repo relationships are noted with a reference: `(see also: <other-repo-name>)`
- Commit changelogs independently — one commit per repo, not a cross-repo mega-commit

Present a session summary when asked or at session end:

> **Session changelog summary**
>
> | Repo | Worktree | Branch | PR | Commits | Changelog entries |
> |---|---|---|---|---|---|
> | `repo-a` | `…-worktrees/feature/add-auth/` | `feature/add-auth` | `#42 draft` | 3 | 2 Added, 1 Changed |
> | `repo-b` | `…-worktrees/feature/update-api/` | `feature/update-api` | `#17 ready` | 1 | 1 Changed |

---

### Step 8 — Session completion

When the user signals the session is done (or uses `finishing-a-development-branch`), run a final check per repo. **At no point is a local `git merge` into `main` performed.**

#### Step 8a — Uncommitted changes check

```bash
git -C <feature_worktree_root> status --short
git -C <feature_worktree_root> diff --stat
```

If uncommitted changes exist:

> ⚠️ **`<repo-name>` has uncommitted changes in `<feature_worktree_root>`.**
> Would you like to commit + push them (Step 6), or discard?

#### Step 8b — Full test suite run

Run the complete test suite one final time in each **feature worktree**.

#### Step 8c — CHANGELOG.md final check

Verify the `## [Unreleased]` section in `<feature_worktree_root>/CHANGELOG.md` accurately reflects all changes made this session. If any commits were made without a changelog entry, add them now (and push again per Step 6e).

#### Step 8d — Mark the PR ready for review

For each repo whose feature is complete and `pr_state == draft`, offer:

> **Mark `<pr_url>` ready for review?**
>
> — **yes** to run `gh pr ready` (flips draft → ready)
> — **leave draft** to keep iterating later

If yes:

```bash
gh --repo <origin-owner>/<origin-repo> pr ready <pr-number>
```

Set `pr_state = ready` in the registry.

#### Step 8e — Post-merge cleanup (only after the user merges the PR on GitHub)

Merging is done by the user in the GitHub UI (or via `gh pr merge` if they prefer). The skill **never** merges and **never** force-pushes. Once a PR is reported as merged:

```bash
# Inside the MAIN worktree (not the feature worktree)
git -C <main_worktree_root> fetch --prune origin
git -C <main_worktree_root> pull --ff-only origin <main-branch>
git -C <main_worktree_root> prune-worktrees   # from worktree-strategy
```

The `git prune-worktrees` step is conservative and will only remove worktrees whose PR is MERGED on origin, are clean, and have no unpushed commits. Anything still in flight is left untouched.

If `git prune-worktrees` is not installed, fall back to the install guide at <https://github.com/vaughnangoy/worktree-strategy#install> and surface this to the user once — do **not** substitute `git worktree remove --force`.

#### Step 8f — Session summary

> **Session complete**
>
> | Repo | Worktree | Branch | PR | Commits | Tests | Status |
> |---|---|---|---|---|---|---|
> | `<repo-name>` | `<feature_worktree_root>` | `<feature-branch>` | `<pr_url>` (`<pr_state>`) | `<n>` | ✅ all passing | Awaiting merge → then `git prune-worktrees` |

---

## Flags

| Flag | Behaviour |
|---|---|
| `/feature-creator off` | Pause the workflow for the session |
| `/feature-creator on` | Resume if paused |
| `/feature-creator status` | Show the repo registry: main worktree, feature worktree, branch, PR state |
| `/feature-creator changelog` | Print the current `[Unreleased]` section for every active feature worktree |
| `/feature-creator commit` | Trigger the commit + push + draft-PR flow (Step 6) manually |
| `/feature-creator ready` | Run `gh pr ready` for the active repo's PR (Step 8d) |
| `/feature-creator prune` | Run `git prune-worktrees` from the main worktree (Step 8e) |

---

## Examples of valid invocations

| Invocation | Behaviour |
|---|---|
| `/feature-creator` | Activates with no feature name — prompts for scope and worktree name in Step 0/3 |
| `/feature-creator add-dark-mode` | Suggests worktree `<repo>-worktrees/feature/add-dark-mode/` on branch `feature/add-dark-mode` |
| `/feature-creator refactor-auth` | Infers refactor type, suggests `<repo>-worktrees/refactor/refactor-auth/` on `refactor/refactor-auth` |
| `/feature-creator status` | Shows registry: main worktree, feature worktree, branch, PR state, uncommitted changes |
| `/feature-creator changelog` | Prints current Unreleased section for each active feature worktree |

---

## See also

- [`worktree-strategy` repo](https://github.com/vaughnangoy/worktree-strategy) — source of POLICY.md and the `git prune-worktrees` binary that this skill orchestrates.
- [`using-git-worktrees` superpower skill](https://github.com/anthropics/superpowers-marketplace) — lower-level worktree creation helper, used when isolating exploratory work outside of a feature PR.

---

## CHANGELOG.md example

```markdown
# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `auth`: JWT refresh token rotation — tokens now rotate on each request with a 15-min expiry
- `auth`: Redis-backed refresh token storage with 7-day TTL

### Changed
- `config`: `AUTH_SECRET` env var renamed to `JWT_SECRET` for clarity

---

## [1.2.0] — 2026-04-10

### Added
- `users`: bulk invite endpoint `POST /users/invite`
```
