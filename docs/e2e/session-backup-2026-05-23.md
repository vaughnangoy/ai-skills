# E2E test plan: session-backup

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`session-backup/SKILL.md`](../../session-backup/SKILL.md)
**Test status:** spec (no executable e2e harness yet — the skill backs up a live AI chat session, so end-to-end coverage needs an AI session driver)

---

## Scenario 1 (happy) — Backup current session via interactive prompt picker

**Setup**
- A configured vault: `~/.copilot/skills/session-backup/config.json` has `vaultPath`, `sessionRoot`, and an entry for the current workspace
- The vault path is a writeable directory (e.g. `/tmp/sb-vault-e2e`)
- An active AI session with at least 4 real prompts (excluding any `/session-backup` invocations)
- The session has a mix of code blocks, tables, lists, and prose

**Steps**
1. In the AI session run `/session-backup`
2. The skill presents 3 numbered options (the last 3 real prompts)
3. Reply `1` to file the backup under the date of the most recent real prompt

**Expected**
- A file appears at `<vaultPath>/<sessionRoot>/<workspace-folder>/YYYY-MM-DD/<derived-title>.md` where `YYYY-MM-DD` matches the picked prompt's date
- The file contains valid YAML frontmatter with `title`, `workspace`, `date`, and `tags: [ai-session, copilot]`
- Every real user prompt appears as a `####` heading
- All assistant code blocks retain their language fences
- `/session-backup` prompts and their bare `yes`/`no` confirmations are **not** present in the output
- The success summary shows the absolute file path

---

## Scenario 2 (happy) — Backup with explicit date argument

**Setup**
- Same configured vault as Scenario 1
- An active AI session with real prompts

**Steps**
1. Run `/session-backup 5/4/26`
2. No prompt picker should appear

**Expected**
- A file appears at `<vaultPath>/<sessionRoot>/<workspace-folder>/2026-04-05/<derived-title>.md` (day-first interpretation: 5 April 2026)
- The skill skips Step 2 (prompt picker) entirely
- File frontmatter `date: 2026-04-05`
- All other content rules from Scenario 1 hold

---

## Scenario 3 (sad) — Cancel first-time setup at vault path prompt

**Setup**
- `~/.copilot/skills/session-backup/config.json` does **not** exist (e.g. `rm` it before the run)
- An active AI session

**Steps**
1. Run `/session-backup`
2. The skill detects no vault is configured and asks for an absolute path
3. The skill explains it's about to run `config.py --set-vault-path` and asks `Proceed? (yes / no)`
4. Reply `no`

**Expected**
- No `config.json` is created
- No directory is created under any path the user may have typed
- No session backup file is written anywhere
- The skill confirms the setup was cancelled and stops
- Re-running `/session-backup` afterwards behaves identically (the same first-time setup is re-offered, not skipped)

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Use a harness that can drive a Copilot Chat or Claude Code session non-interactively
2. Use a disposable vault per scenario: `mktemp -d` and point `vaultPath` at it via `config.py --set-vault-path` from a setup step
3. Pre-seed the AI session transcript with a fixture of canned prompts (the skill scans for the last 3 real prompts in the active session — a recorded session JSON works)
4. Assertions:
   - Walk the vault tree and verify exactly one `.md` file was created at the expected dated path
   - Parse the YAML frontmatter with a lib (e.g. `python-frontmatter`) and assert on field values
   - Count `####` headings and confirm matches the count of real prompts in the input transcript
   - For Scenario 3, assert that the config file path does not exist after the run
5. Tear down: `rm -rf` the disposable vault and the config file
