# E2E test plan: secondbrain-transcribe-audio-skill

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`secondbrain-transcribe-audio-skill/SKILL.md`](../../secondbrain-transcribe-audio-skill/SKILL.md)
**Test status:** spec (no executable e2e harness yet — depends on NotebookLM audio artifacts and a working `ffmpeg` + `faster-whisper` install)

---

## Scenario 1 (happy) — Download + transcribe an audio overview, then ingest both files

**Setup**
- Prereqs all green: `prereq_setup.py --check` reports ✅ for `notebooklm-py`, NotebookLM auth, SecondBrain path, `raw/` directory, `faster-whisper`, `ffmpeg`, and `audio_transcribe.py` deployed
- A NotebookLM notebook with a completed audio overview artifact (status `COMPLETED`)
- `notebooklm use <notebook_id>` already run
- The audio artifact ID captured from `notebooklm artifact list --type audio --json`

**Steps**
1. Run `python3 .../scripts/audio_transcribe.py --download-only --notebook <notebook_id> --artifact <artifact_id> --out-dir <vault>/raw/notebooklm/<slug>/`
2. Confirm the `.mp3` size and path in the output
3. Run `python3 .../scripts/audio_transcribe.py --transcribe --audio <path-to-mp3> --notebook-slug <slug> --notebook-title "<title>" --artifact-id <artifact_id>`
4. Run `cd <vault> && uv run python scripts/ingest.py --pending`

**Expected**
- `raw/notebooklm/<slug>/nlm__<slug>__artifact__audio.mp3` exists and is non-zero bytes
- `raw/notebooklm/<slug>/nlm__<slug>__artifact__audio-transcript.md` exists with valid YAML frontmatter containing: `title`, `notebook`, `artifact_id`, `transcribed_at`, `duration_seconds`, `word_count`, non-empty `tags`, non-empty `categories`, `source_type: notebooklm-audio`
- Transcript body is non-empty (word_count > 0)
- After `ingest.py --pending`: both files move from `raw/notebooklm/<slug>/` to `processed/notebooklm/<slug>/`
- Both files have new entries in `state.json`

---

## Scenario 2 (happy) — Download-only path (skip transcription)

**Setup**
- Same prereqs as Scenario 1
- Active notebook with an audio artifact

**Steps**
1. Run `python3 .../scripts/audio_transcribe.py --download-only --notebook <notebook_id> --artifact <artifact_id> --out-dir <vault>/raw/notebooklm/<slug>/`
2. Do **not** run the transcribe step
3. Run `cd <vault> && uv run python scripts/ingest.py --pending`

**Expected**
- Only `nlm__<slug>__artifact__audio.mp3` exists under `raw/notebooklm/<slug>/`
- No `audio-transcript.md` file is created
- After `ingest.py --pending`: the `.mp3` is registered in `state.json` and moved to `processed/notebooklm/<slug>/`
- Exit code is 0

---

## Scenario 3 (sad) — Transcription requested but `ffmpeg` is missing

**Setup**
- Same as Scenario 1 **except** `ffmpeg` is not on `PATH` (temporarily mask it: `PATH=/usr/bin:/bin` with no homebrew dirs)
- An `.mp3` already downloaded to `raw/notebooklm/<slug>/`

**Steps**
1. Run `python3 .../scripts/prereq_setup.py --check` to confirm the missing prereq is reported
2. Run `python3 .../scripts/audio_transcribe.py --transcribe --audio <path-to-mp3> --notebook-slug <slug> --notebook-title "<title>" --artifact-id <artifact_id>`

**Expected**
- `prereq_setup.py --check` reports `ffmpeg` as ❌ with installation guidance
- `audio_transcribe.py --transcribe` exits non-zero with a clear error referencing `ffmpeg`
- No `audio-transcript.md` is written
- The `.mp3` is left untouched
- No partial `.md` file is left behind in the output directory

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Fixture a short (~10 second) audio file for Scenario 3's "already downloaded" state to avoid network during the failure scenario
2. For Scenarios 1 and 2, use a dedicated test NotebookLM account with a stable audio artifact
3. Sandbox `$PATH` per scenario to deterministically include/exclude `ffmpeg`
4. Assert on `state.json` deltas before/after each scenario
5. Tear down with `rm -rf <vault>/raw/notebooklm/<slug>/ <vault>/processed/notebooklm/<slug>/` and reset `state.json` from a baseline snapshot
