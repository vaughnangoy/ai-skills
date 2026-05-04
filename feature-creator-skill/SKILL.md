---
name: feature-creator
description: "Structured feature development workflow for any git repository. Activated by /feature-creator or automatically when the session involves creating new features, modifying existing behavior, or non-trivial refactoring. Manages: feature branch creation from main/master, pre-change confirmation gates, test-driven development with visible subprocess test runs, per-commit CHANGELOG.md updates (one changelog per repo), and commit offers after each verified working task. In multi-repo sessions, independently tracks branch state and changelog for every active repository. Offers to engage the superpowers approach (writing-plans, executing-plans, test-driven-development) when feature scope warrants it. Use for /feature-creator, 'start a feature', 'build a feature', 'add feature', 'refactor X', 'change behavior of X', or any session where the user is making non-trivial code changes."
argument-hint: "[<feature-name>] — optional short name for the feature branch (e.g. add-dark-mode, refactor-auth)"
---

# Feature Creator Skill

Wraps every feature development session in a consistent workflow: **branch → confirm → test-first → run → commit → changelog**. Works across any number of git repos in the session, giving each its own branch and `CHANGELOG.md`.

---

## Definitions

| Term | Meaning |
|---|---|
| **Feature** | New capability, new endpoint, new UI component, new script |
| **Behaviour modification** | Change to existing logic that alters observable output |
| **Refactor** | Structural change with no observable behaviour change |
| **Working task** | A discrete unit of work where all tests pass and the feature behaves correctly |
| **Active repo** | Any git repo the session reads from or writes to |

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

> **Feature Creator activated.**
> I'll manage branch setup, pre-change confirmation, tests, commits, and changelogs for this session.
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

For each repo:

```bash
git -C <repo-path> rev-parse --show-toplevel 2>/dev/null
git -C <repo-path> symbolic-ref --short HEAD 2>/dev/null
git -C <repo-path> remote get-url origin 2>/dev/null
```

Record for each repo:

| Field | Value |
|---|---|
| `root` | Absolute path to repo root |
| `origin` | Remote URL (or "local" if none) |
| `current_branch` | Current branch name |
| `main_branch` | `main` if it exists, else `master`, else ask |
| `feature_branch` | Set in Step 3 |
| `changelog_path` | `<root>/CHANGELOG.md` |

**Finding the main branch:**

```bash
git -C <repo-path> branch --list main master
```

- If both exist → use `main`
- If neither exists → ask the user: "Which branch should I branch from in `<repo-name>`?"

Repeat for every repo in the session. If a new repo is added mid-session (user opens a second project or installs a dependency repo), automatically add it to the registry and run Step 3 for it.

---

### Step 3 — Feature branch setup (per repo)

For each repo in the registry where the current branch is `main` or `master`:

> **Set up a feature branch in `<repo-name>`?**
>
> | | |
> |---|---|
> | **Repo** | `<repo-root>` |
> | **Currently on** | `<current-branch>` |
> | **Branch from** | `<main-branch>` |
> | **Suggested branch** | `feature/<feature-name>` |
>
> **Options:**
> — **yes** to create `feature/<feature-name>` from `<main-branch>`
> — **name** to use a different branch name
> — **skip** to stay on the current branch (changes will be made directly)
> — **existing** to enter the name of an existing branch to switch to

**If yes:**

```bash
git -C <repo-path> checkout <main-branch>
git -C <repo-path> pull --ff-only
git -C <repo-path> checkout -b feature/<feature-name>
```

Read the output via file to avoid terminal stalls:

```bash
git -C <repo-path> checkout <main-branch> > /tmp/.fc_branch_out 2>&1
git -C <repo-path> pull --ff-only >> /tmp/.fc_branch_out 2>&1
git -C <repo-path> checkout -b feature/<feature-name> >> /tmp/.fc_branch_out 2>&1
echo "---DONE---" >> /tmp/.fc_branch_out
```

Then read `/tmp/.fc_branch_out` for the result.

**Confirm branch creation:**

> ✅ **Branch `feature/<feature-name>` created in `<repo-name>`.**

Update `feature_branch` in the repo registry.

**If the repo is already on a non-main branch:** Confirm with the user before continuing:

> ⚠️ `<repo-name>` is already on `<current-branch>`. Continue work here, or create a new branch?

---

### Step 4 — Pre-change confirmation gate

**This step applies before EVERY code change for the rest of the session.**

Before writing, editing, or deleting any file, present a confirmation:

> **Proposed change — confirm before proceeding**
>
> | | |
> |---|---|
> | **Repo** | `<repo-name>` |
> | **Action** | Create / Edit / Delete |
> | **File(s)** | `path/to/file.ext` |
> | **What changes** | `<one-sentence description of what will change and why>` |
>
> **yes** to proceed · **no** to cancel · **adjust** to change the approach first

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

Common test runners by ecosystem:

| Ecosystem | Command |
|---|---|
| Python (pytest) | `cd <repo-root> && uv run python -m pytest <test-file> -v` |
| Node.js (jest) | `cd <repo-root> && npx jest <test-file> --verbose` |
| Node.js (vitest) | `cd <repo-root> && npx vitest run <test-file>` |
| Go | `cd <repo-root> && go test ./... -v -run <TestName>` |
| Rust | `cd <repo-root> && cargo test <test_name> -- --nocapture` |
| Ruby | `cd <repo-root> && bundle exec rspec <test-file>` |
| Swift | `cd <repo-root> && swift test --filter <TestName>` |

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

Diagnose and fix the regression before proceeding to Step 6.

#### Step 5e — Confirm the task is working

Once all tests pass, verify the feature behaves correctly if there's a way to check beyond tests (e.g., a script output, a CLI invocation, a UI check). Report to the user:

> ✅ **Task complete — all tests pass, no regressions.**

---

### Step 6 — Commit flow

After each **working task** (Step 5e confirmed), offer to commit:

> **Commit this task?**
>
> | | |
> |---|---|
> | **Repo** | `<repo-name>` |
> | **Branch** | `<feature-branch>` |
> | **Files changed** | `<file list>` |
> | **Suggested message** | `<type>(<scope>): <what changed and why>` |
>
> **yes** to commit with the suggested message · **edit** to write a custom message · **skip** to defer

#### Step 6a — Stage specific files

Never use `git add .` or `git add -A`. Stage only the files that are part of this working task:

```bash
git -C <repo-path> add <file1> <file2> ...
```

#### Step 6b — Commit message format

Use conventional commits:

```
<type>(<scope>): <short description>

<optional body — what changed and why, if non-obvious>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

Example:
```
feat(auth): add JWT refresh token rotation

Tokens now expire after 15 min and are rotated on each request.
Refresh tokens are stored hashed in Redis with a 7-day TTL.
```

#### Step 6c — Update CHANGELOG.md before committing

Before running `git commit`, update the `CHANGELOG.md` for the affected repo (Step 6d), then include it in the same commit.

#### Step 6d — Run git commit

```bash
git -C <repo-path> commit -m "$(cat <<'EOF'
<commit-message>
EOF
)"
```

Confirm success by reading the output.

---

### Step 7 — CHANGELOG.md management

Every active repo must have a `CHANGELOG.md` at its root. Every commit must update it.

#### Step 7a — Initialise CHANGELOG.md (if missing)

If `<repo-root>/CHANGELOG.md` does not exist, create it:

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
> | Repo | Branch | Commits | Changelog entries |
> |---|---|---|---|
> | `repo-a` | `feature/add-auth` | 3 | 2 Added, 1 Changed |
> | `repo-b` | `feature/update-api` | 1 | 1 Changed |

---

### Step 8 — Session completion

When the user signals the session is done (or uses `finishing-a-development-branch`), run a final check:

#### Step 8a — Uncommitted changes check

```bash
git -C <repo-path> status --short
git -C <repo-path> diff --stat
```

If uncommitted changes exist:

> ⚠️ **`<repo-name>` has uncommitted changes.**
> Would you like to commit them before finishing, or discard them?

#### Step 8b — Full test suite run

Run the complete test suite one final time for each repo.

#### Step 8c — CHANGELOG.md final check

Verify the `## [Unreleased]` section accurately reflects all changes made this session. If any commits were made without a changelog entry, add them now.

#### Step 8d — Session summary

> **Session complete**
>
> | Repo | Branch | Commits | Tests | Status |
> |---|---|---|---|---|
> | `<repo-name>` | `feature/<name>` | `<n>` | ✅ all passing | Ready to PR |

---

## Flags

| Flag | Behaviour |
|---|---|
| `/feature-creator off` | Pause the workflow for the session |
| `/feature-creator on` | Resume if paused |
| `/feature-creator status` | Show the current repo registry and session state |
| `/feature-creator changelog` | Print the current `[Unreleased]` section for all active repos |
| `/feature-creator commit` | Trigger the commit flow (Step 6) manually |

---

## Examples of valid invocations

| Invocation | Behaviour |
|---|---|
| `/feature-creator` | Activates with no feature name — prompts for scope in Step 0 |
| `/feature-creator add-dark-mode` | Activates with `feature/add-dark-mode` as the suggested branch name |
| `/feature-creator refactor-auth` | Activates, infers refactor type, suggests `refactor/refactor-auth` as branch |
| `/feature-creator status` | Shows repo registry, active branches, uncommitted changes |
| `/feature-creator changelog` | Prints current Unreleased section for all active repos |

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
