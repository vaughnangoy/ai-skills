---
name: secondbrain-notebooklm-skill
description: Use when the user wants to sync, pull, or import content from NotebookLM into their SecondBrain knowledge base. Triggers on requests like "sync my notebooklm", "pull my notebook sources into secondbrain", "import notebooklm artifacts", or "add notebooklm content to my knowledge base". Also use when the user has finished working in NotebookLM and wants to capture what they built. Depends on the notebooklm skill for direct NotebookLM operations.
---

# secondbrain-notebooklm-skill

Sync NotebookLM notebooks (sources + generated artifacts) into SecondBrain's `raw/` pipeline. Deduplicates against already-ingested content so you never re-ingest files already in your knowledge base.

## Overview

| Step | What happens |
|---|---|
| 0 | Run prerequisite check |
| 1 | Identify which notebook to sync |
| 2 | Build manifest (what's new vs already synced vs dedup-rejected) |
| 3 | Confirm + sync → triggers ingest pipeline |

## Step 0: Check Prerequisites

Always run this first before any sync operation:

```bash
python3 ~/.claude/skills/vaughnangoy-ai-skills/secondbrain-notebooklm-skill/scripts/prereq_setup.py --check
```

If any items show ❌, run with `--install` to auto-fix:

```bash
python3 ~/.claude/skills/vaughnangoy-ai-skills/secondbrain-notebooklm-skill/scripts/prereq_setup.py --install
```

**What it checks:**
- Python 3.12+, pip, uv
- `notebooklm-py` CLI installed (`pip install notebooklm-py` or `uv tool install notebooklm-py`)
- NotebookLM auth (`notebooklm login` if not authenticated)
- SecondBrain path configured in `~/.copilot/skills/secondbrain-notebooklm-skill/config.json`
- `raw/` directory exists in SecondBrain
- `nlm_sync.py` deployed to `SecondBrain/scripts/`

If `--install` can't auto-detect the SecondBrain path, run interactively (no flags) and enter the path when prompted.

## Step 1: Identify the Notebook

If the user hasn't specified which notebook:

```bash
notebooklm list
```

If they have a current context set:

```bash
notebooklm status
```

To switch context: `notebooklm use <notebook_id>`

## Step 2: Show the Manifest

Preview what will be synced before doing anything:

```bash
python3 ~/.claude/skills/vaughnangoy-ai-skills/secondbrain-notebooklm-skill/scripts/nlm_sync.py --manifest [--notebook <id>]
```

Or if `nlm_sync.py` is deployed to SecondBrain:

```bash
cd <secondbrain_path>
uv run python scripts/nlm_sync.py --manifest [--notebook <id>]
```

The manifest shows three categories for each source and artifact:
- 🆕 **to sync** — new content that will be downloaded
- ⏭️  **already synced** — filename already in `state.json` (skip)
- 🚫 **dedup rejected** — title (or title+size for PDFs) matches already-ingested content

Show the manifest to the user and ask for confirmation before proceeding.

## Step 3: Sync

After the user confirms:

```bash
uv run python scripts/nlm_sync.py --sync [--notebook <id>] [--auto]
```

Use `--auto` to skip the interactive confirmation prompt (since you've already confirmed with the user in chat).

This will:
1. Download source fulltext as `.md` files to `raw/notebooklm/<notebook-slug>/`
2. Download artifacts (reports, quizzes, flashcards, mind-maps, slide decks, etc.)
3. For PDF artifacts: check title+size against dedup index; if matched → move to `raw/dedup-rejections/`
4. Call `ingest.py --pending` to process everything through the knowledge base pipeline

## What Gets Synced

| Content type | Format | Notes |
|---|---|---|
| URL sources | `.md` (fulltext) | Extracted via `notebooklm source fulltext` |
| File sources | `.md` (fulltext) | Same extraction |
| Reports / study guides | `.md` | Downloaded directly |
| Quizzes | `.md` | Markdown format |
| Flashcards | `.md` | Markdown format |
| Mind maps | `.md` | Converted from JSON |
| Data tables | `.csv` | Downloaded directly |
| Slide decks | `.pdf` | Dedup-checked by title+size |
| Audio / video | — | Not supported (skipped) |

## Dedup Rules

**Markdown sources** (URL, file): dedup by normalized title only.  
- `normalize_title("My Paper (Final v2).pdf")` → `"my paper final v2"`
- If this slug matches any already-ingested entry in `state.json` → skip before downloading

**PDF artifacts** (slide decks): dedup by title slug + exact file size.  
- Downloaded first, then checked; if matched → moved to `raw/dedup-rejections/YYYY-MM-DDTHH-MM-SS__<filename>`
- Rejection recorded in `state.json["dedup_rejections"]`

## File Layout

```
SecondBrain/
  raw/
    notebooklm/
      <notebook-slug>/
        nlm__<slug>__source__<title-slug>.md
        nlm__<slug>__artifact__report.md
        nlm__<slug>__artifact__quiz.md
        ...
    dedup-rejections/
      2026-05-03T14-22-01__nlm__<slug>__artifact__slide-deck.pdf
```

## Auto-Scan Offer (Known Notebooks)

When the user has a notebook already in context (via `notebooklm status`), offer to auto-scan and sync:

> "You have **[notebook title]** active. Want me to check what's new and sync it to SecondBrain?"

If yes, run Steps 2 and 3 automatically — show manifest first, then ask for final confirmation before syncing.

## Error Handling

- **`notebooklm` not found**: Run `prereq_setup.py --install`
- **Not authenticated**: Run `notebooklm login`
- **No active notebook**: Run `notebooklm use <id>` or pass `--notebook <id>`
- **SecondBrain path not configured**: Run `prereq_setup.py` interactively
- **ingest.py errors**: Check `SecondBrain/ingest.log` — the sync itself succeeded, ingestion can be retried with `uv run python scripts/ingest.py --pending`
