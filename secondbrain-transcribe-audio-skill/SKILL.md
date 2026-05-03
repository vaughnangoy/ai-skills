---
name: secondbrain-transcribe-audio-skill
description: Use when the user wants to download, transcribe, or process audio overviews from NotebookLM into SecondBrain. Triggers on requests like "download audio overview", "transcribe the podcast", "get the audio from my notebook", or "add audio transcription to secondbrain". Augments secondbrain-notebooklm-skill by handling audio artifacts — superseding the default skip behaviour. Audio is downloaded, transcribed with Whisper, enriched with tags and metadata, and both files are moved through the ingest pipeline together. Use this whenever audio from NotebookLM needs to end up in the knowledge base.
---

# secondbrain-transcribe-audio-skill

Download audio overviews from NotebookLM, transcribe them with Whisper, enrich the transcript with tags and categorisation, and ingest both files into SecondBrain alongside the rest of the notebook content.

**Augments:** `secondbrain-notebooklm-skill` — supersedes the "Audio / video → Not supported (skipped)" behaviour.

## Overview

| Step | What happens |
|---|---|
| 0 | Run prerequisite check (includes transcription deps) |
| 1 | Identify notebook and audio artifact |
| 2 | Download `.mp3` to `raw/notebooklm/<notebook-slug>/` |
| 3 | Transcribe with Whisper → `.md` with frontmatter |
| 4 | Confirm + trigger ingest pipeline (audio + transcript together) |

---

## Step 0: Check Prerequisites

Always run this first:

```bash
python3 /Users/vaughnangoy/code/git-repos/vaughnangoy/ai-skills/secondbrain-transcribe-audio-skill/scripts/prereq_setup.py --check
```

Auto-fix anything missing:

```bash
python3 /Users/vaughnangoy/code/git-repos/vaughnangoy/ai-skills/secondbrain-transcribe-audio-skill/scripts/prereq_setup.py --install
```

**What it checks (in addition to notebooklm prereqs):**
- Python 3.12+, uv
- `notebooklm-py` CLI + auth
- SecondBrain path configured
- `raw/` directory exists
- `faster-whisper` available via uv (installed into isolated env)
- `ffmpeg` on PATH (required by Whisper)
- `audio_transcribe.py` deployed to `SecondBrain/scripts/`

---

## Step 1: Identify the Notebook and Audio Artifact

If the user hasn't specified a notebook:

```bash
notebooklm status
```

List available audio artifacts:

```bash
notebooklm artifact list --type audio --json
```

If there are multiple audio artifacts, show them to the user and ask which to download. If there is only one, proceed automatically.

---

## Step 2: Download Audio

Download to the notebook's raw folder:

```bash
python3 /Users/vaughnangoy/code/git-repos/vaughnangoy/ai-skills/secondbrain-transcribe-audio-skill/scripts/audio_transcribe.py \
  --download-only \
  --notebook <notebook_id> \
  --artifact <artifact_id> \
  --out-dir <secondbrain_path>/raw/notebooklm/<notebook-slug>/
```

The file is named: `nlm__<notebook-slug>__artifact__audio.mp3`

Show the user the download path and file size before transcribing.

---

## Step 3: Transcribe

Run Whisper transcription:

```bash
python3 /Users/vaughnangoy/code/git-repos/vaughnangoy/ai-skills/secondbrain-transcribe-audio-skill/scripts/audio_transcribe.py \
  --transcribe \
  --audio <path/to/audio.mp3> \
  --notebook-slug <notebook-slug> \
  --notebook-title "<notebook title>" \
  --artifact-id <artifact_id>
```

This produces a `.md` file alongside the audio:
`nlm__<notebook-slug>__artifact__audio-transcript.md`

The transcript includes YAML frontmatter with:
- `title`, `notebook`, `artifact_id`
- `transcribed_at` (ISO timestamp)
- `duration_seconds`
- `word_count`
- `tags` (auto-generated from transcript content)
- `categories` (mapped from notebook title and tags)
- `source_type: notebooklm-audio`

---

## Step 4: Ingest Both Files

After transcription, trigger the ingest pipeline:

```bash
cd <secondbrain_path>
uv run python scripts/ingest.py --pending
```

Both the `.mp3` and the `.md` transcript are registered in `state.json` and moved to `processed/` by the ingest pipeline.

If the user declines transcription (just wants the audio), only the `.mp3` is ingested.

---

## Integration with secondbrain-notebooklm-skill

When running a full notebook sync via `secondbrain-notebooklm-skill`, audio artifacts that would normally be skipped can now be handled:

> "I see this notebook has an audio overview that was skipped. Want me to download and transcribe it? (uses secondbrain-transcribe-audio-skill)"

If yes: run Steps 1–4 for the audio artifact, then continue the normal sync.

The `nlm_sync.py` manifest will still mark audio as `skip` — this skill handles audio as a **parallel opt-in step**, not a modification to the sync script.

---

## File Layout

```
SecondBrain/
  raw/
    notebooklm/
      <notebook-slug>/
        nlm__<slug>__artifact__audio.mp3
        nlm__<slug>__artifact__audio-transcript.md   ← Whisper output + enriched frontmatter
  processed/
    notebooklm/
      <notebook-slug>/
        nlm__<slug>__artifact__audio.mp3              ← after ingest
        nlm__<slug>__artifact__audio-transcript.md    ← after ingest
```

---

## Transcript Frontmatter Example

```yaml
---
title: "Audio Overview: My Research Notebook"
notebook: my-research-notebook
artifact_id: abc123def456
source_type: notebooklm-audio
transcribed_at: 2026-05-03T17:00:00+01:00
duration_seconds: 847
word_count: 1423
tags:
  - notebooklm
  - audio-overview
  - research
  - machine-learning
categories:
  - AI/ML
  - Research Notes
---
```

---

## Error Handling

- **`ffmpeg` not found**: `brew install ffmpeg` or `sudo apt install ffmpeg`
- **`faster-whisper` install fails**: Run `prereq_setup.py --install` to set up isolated uv env
- **Audio download fails**: Check `notebooklm artifact list --type audio` — artifact may not be complete yet
- **Transcript empty**: Audio may be too short or silent — verify the `.mp3` plays correctly
- **ingest.py errors**: Check `SecondBrain/ingest.log` — audio and transcript can be re-ingested with `uv run python scripts/ingest.py --pending`
