# E2E test plan: sync-skills

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`sync-skills/SKILL.md`](../../sync-skills/SKILL.md)
**Test status:** spec (no executable e2e harness yet — the binary is a real shell tool so `bats` or a Python `subprocess` runner is the natural fit once written)

---

## Scenario 1 (happy) — Sync a freshly-added skill into `~/.claude/skills/`

**Setup**
- `sync-skills` installed at `~/.local/bin/sync-skills` and on `PATH`
- `~/.config/sync-skills/config.json` exists with a watch path of `/tmp/skills-hub-e2e/`
- An existing namespace `/tmp/skills-hub-e2e/my-ns/` registered in the config
- A brand-new skill at `/tmp/skills-hub-e2e/my-ns/hello-skill/SKILL.md` (any valid SKILL.md content)
- The skill is **not** present in `~/.config/sync-skills/registry.json`

**Steps**
1. Run `~/.local/bin/sync-skills` (no flags)

**Expected**
- Exit code 0
- Output indicates the new skill was linked (e.g. "linked: my-ns/hello-skill")
- `~/.claude/skills/my-ns/hello-skill` exists and is a symlink resolving to `/tmp/skills-hub-e2e/my-ns/hello-skill/`
- `~/.copilot/instructions/my-ns-hello-skill.instructions.md` exists, is non-empty, and starts with a YAML frontmatter block containing `applyTo: "**"`
- `~/.config/sync-skills/registry.json` now contains an entry for `my-ns/hello-skill`
- A second invocation produces "already indexed" output and makes no further changes (idempotent)

---

## Scenario 2 (happy) — `--link` a git repo as a SKILLS_HUB namespace

**Setup**
- `sync-skills` installed
- A git repo at `/tmp/source-repo-e2e/vendor/cool-skills/` containing two skill subdirectories each with a `SKILL.md`
- `/tmp/skills-hub-e2e/vendor-cool-skills/` does **not** exist yet

**Steps**
1. Run `~/.local/bin/sync-skills --link /tmp/source-repo-e2e/vendor/cool-skills`

**Expected**
- Exit code 0
- `/tmp/skills-hub-e2e/vendor-cool-skills` is created as a symlink to `/tmp/source-repo-e2e/vendor/cool-skills/`
- Both skills inside it are automatically indexed (output shows the equivalent of `--all`)
- `sync-skills --verify vendor-cool-skills` prints a verification table with ✅ in all three columns (SKILLS_HUB symlink, Claude symlink, Copilot `.instructions.md`) for both skills
- The verification output also confirms the `sync-skills` binary at `~/.local/bin/sync-skills` is installed correctly

---

## Scenario 3 (sad) — `--link` refuses when SKILLS_HUB has a real dir with extra skills

**Setup**
- `sync-skills` installed
- A git repo at `/tmp/source-repo-e2e/v2/some-skills/` containing skills `a` and `b`
- A pre-existing **real directory** (not a symlink) at `/tmp/skills-hub-e2e/v2-some-skills/` containing skills `a`, `b`, and an extra `c` (a skill not present in the target repo)

**Steps**
1. Run `~/.local/bin/sync-skills --link /tmp/source-repo-e2e/v2/some-skills` **without** `--force`

**Expected**
- Exit code is non-zero
- Output explicitly lists the extra skill (`c`) that would be lost
- Output instructs the user to re-run with `--force` if they want to proceed
- `/tmp/skills-hub-e2e/v2-some-skills/` remains a real directory (not converted to a symlink)
- Skill `c` is still present in `/tmp/skills-hub-e2e/v2-some-skills/c/`
- No new entries are added to `~/.config/sync-skills/registry.json`

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Pick `bats` (`tests/e2e/*.bats`) or pytest with `subprocess` — both invoke the real binary on disk
2. Per-scenario isolation:
   - `export XDG_CONFIG_HOME=$(mktemp -d)` so `~/.config/sync-skills/` is fresh
   - Override `~/.claude/` and `~/.copilot/` to disposable temp dirs (the script reads these from envs or hardcoded paths — confirm at implementation time)
   - Build the SKILLS_HUB fixture under `$(mktemp -d)`
3. Assertions:
   - Use `test -L <path>` to assert symlinks
   - `readlink <path>` to assert symlink targets
   - `jq '.indexed | length'` (or grep) on `registry.json`
   - For Scenario 3, capture exit code, stdout, and stderr — assert non-zero exit and presence of the offending skill name in the error message
4. Tear down: `rm -rf` the disposable hub, config, claude, and copilot dirs
