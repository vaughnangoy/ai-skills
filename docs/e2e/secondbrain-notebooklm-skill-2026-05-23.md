# E2E test plan: secondbrain-notebooklm-skill

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`secondbrain-notebooklm-skill/SKILL.md`](../../secondbrain-notebooklm-skill/SKILL.md)
**Test status:** spec (no executable e2e harness yet — depends on a live NotebookLM account and a real SecondBrain vault)

---

## Scenario 1 (happy) — Sync a notebook with one new source + one already-synced source

**Setup**
- `notebooklm-py` installed and `notebooklm login` already completed
- `~/.copilot/skills/secondbrain-notebooklm-skill/config.json` has `secondbrainPath` pointing at a SecondBrain test vault
- The test vault has `raw/`, `processed/`, and `state.json` initialised
- A NotebookLM notebook with at least 2 URL sources: one ingested previously (its slug present in `state.json`), one brand new
- `notebooklm use <notebook_id>` already run

**Steps**
1. Run `python3 ~/.claude/skills/vaughnangoy-ai-skills/secondbrain-notebooklm-skill/scripts/nlm_sync.py --manifest`
2. Verify the manifest shows: 1 🆕 to sync, 1 ⏭️ already synced
3. Run `uv run python scripts/nlm_sync.py --sync --auto` from inside the SecondBrain vault

**Expected**
- `raw/notebooklm/<notebook-slug>/nlm__<slug>__source__<new-title-slug>.md` exists with non-empty content (the fulltext)
- The already-synced source produces **no** new file under `raw/notebooklm/<notebook-slug>/`
- `ingest.py --pending` runs after the sync and the new `.md` file is moved to `processed/notebooklm/<notebook-slug>/`
- `state.json` now contains an entry for the new source slug
- Exit code is 0

---

## Scenario 2 (happy) — PDF slide-deck artifact rejected by dedup

**Setup**
- Same as Scenario 1 plus an active notebook that has generated a slide-deck artifact
- The vault's dedup index already contains a record matching the slide-deck title slug **and** the exact file size (simulate by pre-loading a matching PDF into `processed/` and updating `state.json`)

**Steps**
1. Run `uv run python scripts/nlm_sync.py --sync --auto`

**Expected**
- The slide-deck PDF is downloaded once to a temp location, then **moved** (not copied) to `raw/dedup-rejections/YYYY-MM-DDTHH-MM-SS__nlm__<slug>__artifact__slide-deck.pdf`
- A new entry is appended to `state.json["dedup_rejections"]` with the rejection timestamp, original title, and size
- No copy of the rejected PDF remains under `raw/notebooklm/<notebook-slug>/`
- The non-rejected artifacts in the same notebook still sync normally

---

## Scenario 3 (sad) — Run sync with no active notebook and no `--notebook` flag

**Setup**
- `notebooklm-py` authenticated but no notebook in context (run `notebooklm use --clear` first, or delete the context file)
- SecondBrain config valid

**Steps**
1. Run `uv run python scripts/nlm_sync.py --manifest`

**Expected**
- Exit code is non-zero
- stderr contains a clear message such as "no active notebook — pass `--notebook <id>` or run `notebooklm use <id>` first"
- No files are written under `raw/notebooklm/`
- No changes to `state.json`

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Create a dedicated test NotebookLM account with stable test notebooks (one for happy paths, one for dedup paths)
2. Use a disposable SecondBrain vault per run: `cp -R fixtures/empty-vault /tmp/sb-e2e-$RUN_ID`
3. Mock or fixture-load `state.json` for Scenario 2 to deterministically trigger dedup
4. Capture script output, exit codes, and the resulting filesystem state with `find raw/ processed/ -type f` snapshots
5. Tear down: delete the disposable vault and reset the test account's notebook to a known baseline (or rely on the dedup index to make re-runs idempotent)
