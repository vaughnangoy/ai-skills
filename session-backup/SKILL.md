---
name: session-backup
description: "Save, backup, export, or record the current Copilot Chat session to a Markdown file for review in Obsidian. Use when asked to backup a session, save a conversation, export chat history, record prompts and responses, rename a session file, or set a session title. Organises sessions by workspace name and date with auto-incrementing session numbers (session-1, session-2, etc.). Triggered by /session-backup."
argument-hint: "[date] — optional date to force (e.g. 5/4/26, 1-1-1977, 29)"
---

# Session Backup

Saves the entire current conversation to a formatted Markdown file optimised for Obsidian, stored at:

`<vault_path>/<workspace-or-category>/YYYY-MM-DD/session-N.md`

Works with **VS Code**, **JetBrains**, and **CLI** (any AI assistant that supports skills). Re-running `/session-backup` **overwrites the current chat session's file** with the latest fully formatted conversation. Each new VS Code chat session automatically gets its own new file via the `SessionStart` hook.

## First-time Setup

On first use, the skill checks for a config file at `~/.copilot/skills/session-backup/config.json`. If it doesn't exist or is incomplete, the procedure will walk through setup before saving.

Config is set once and reused across all sessions and workspaces. Users can reconfigure at any time by running:

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py --init
```

## How it runs

This skill operates in complementary modes:

| Mode                                | Trigger                   | What it does                                                                                |
| ----------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------- |
| **SessionStart hook** (VS Code)     | New chat session opens    | Creates a new `session-N.md` file automatically                                             |
| **UserPromptSubmit hook** (VS Code) | Every prompt you submit   | Appends your prompt as a `####` heading to the current session file                         |
| **Manual `/session-backup`**        | You run the slash command | Formats the full conversation (prompts + responses) and overwrites the current session file |

For VS Code, hooks run in the background via `~/.claude/settings.json`. For JetBrains and CLI users, only the manual slash command is used.

---

## Procedure

Follow these steps **exactly** when this skill is invoked.

---

### Step 0 — Check setup (fast path on repeat use)

Run the status check to auto-detect editor and assess setup state:

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py \
  --status --workspace "<current-workspace-name>"
```

Where `<current-workspace-name>` is the last segment of the currently open workspace path (for VS Code) or `general` if unknown.

Parse the JSON output. Use this decision tree:

1. **`workspace_setup_done: true` AND `sessionRootAsked: true`** → **skip to Step 1 immediately.** No questions needed.
2. **`workspace_setup_done: true` but `sessionRootAsked: false`** → ask the session root question (Step 0b) only, then skip to Step 1.
3. **`vault_known: false`** → run full setup from Step 0a.
4. **`vault_known: true` but `workspace_setup_done: false`** → ask for session root (if not asked) and folder name only.

#### First-time setup (only when needed)

**Step 0a — Editor detection (automatic)**

`is_vscode` in the status output is auto-detected from environment variables. Do **not** ask the user which editor they use.

**Step 0b — Vault path (only if `vault_known: false`)**

Ask the user:

> **Where is your Obsidian vault?**
> Paste the full absolute path to the root of your Obsidian vault.
> (e.g. `/Users/you/Documents/Obsidian`)

Validate: must be an absolute path starting with `/`. Then explain to the user:

> **About to run:** `config.py --set-vault-path`
> This saves `<vault-path>` as your Obsidian vault root in `~/.copilot/skills/session-backup/config.json` and creates the directory if it doesn't already exist. No session files are written.
> **Proceed? (yes / no)**

Wait for confirmation, then run:

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py \
  --set-vault-path "<vault-path>"
```

**Step 0c — Session root folder (only if `sessionRootAsked: false`)**

Ask the user:

> **Where inside your vault should all AI session files be stored?**
> This is a single root folder that contains all workspace subfolders.
> Press Enter to use the default **`Ai Session Backup`**, or type a custom name.

If the user presses Enter with no input, use `Ai Session Backup`.

Then explain to the user:

> **About to run:** `config.py --set-session-root`
> This saves `<folder-name>` as the session root in your config and creates `<vault-path>/<folder-name>/` inside your Obsidian vault if it doesn't already exist. No session files are written.
> **Proceed? (yes / no)**

Wait for confirmation, then run:

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py \
  --set-session-root "<folder-name>"
```

**Step 0d — Workspace folder name (only if `workspace_setup_done: false`)**

Ask the user:

> **What subfolder name should be used for this workspace?**
> This becomes: `<vault>/<session-root>/<folder>/YYYY-MM-DD/session-N.md`
> Press Enter to use the workspace name **`<current-workspace-name>`** as the folder name.

If the user presses Enter with no input, use `<current-workspace-name>` as the folder name.

Then explain to the user:

> **About to run:** `config.py --set-workspace`
> This registers the workspace **`<workspace-name>`** in your config and creates the folder `<vault-path>/<session-root>/<folder-name>/` inside your Obsidian vault if it doesn't already exist. No session files are written.
> **Proceed? (yes / no)**

Wait for confirmation, then run:

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py \
  --set-workspace "<workspace-name>" \
  --folder "<folder-name>" \
  --editor "<detected-editor>"
```

This creates the folder inside the vault if it doesn't already exist.

Confirm to the user:

> Setup complete. Sessions will be saved to `<vault_path>/<folder>/YYYY-MM-DD/session-N.md`

Then continue to Step 1.

---

### Step 1 — Check for a date argument

If the user invoked `/session-backup` followed by a date (e.g. `/session-backup 5/4/26` or `/session-backup 1-1-1977`), extract that string and pass it directly to `--date` in all script calls below. **Skip Step 2 entirely.**

Accepted formats (day-first):

| Input                    | Meaning                                   |
| ------------------------ | ----------------------------------------- |
| `5`                      | 5th of current month and year             |
| `5/4` or `5-4`           | 5 Apr of current year                     |
| `5/4/26` or `5-4-26`     | 5 Apr 2026 (00–29 → 2000s, 30–99 → 1900s) |
| `5/4/2026` or `5-4-2026` | 5 Apr 2026 (full year)                    |

If no date argument was given, continue to Step 2.

---

### Step 2 — Present the prompt picker

Scan the full conversation and build a list of **real prompts** by filtering out:

- Any prompt that starts with or is exactly `/session-backup` (with or without a date argument)
- Any prompt that is a bare confirmation reply (`yes`, `no`, `y`, `n`) **immediately following** a `/session-backup` prompt

From the remaining real prompts, take the **last 3** (most recent first). For each, show:

- The date from the `The current date is X` context header that was active at the time of that prompt
- The time if available, otherwise omit it
- The first 100 characters of the prompt text

Present as:

> **Which date should this session be filed under?**
>
> **1.** [29 Apr 2026] `I want to create a skill. whats the benefits of doing so?`
> **2.** [29 Apr 2026] `yes I do. I want each session recorded to a markdown file…`
> **3.** [28 Apr 2026] `how to add the vscode workspace file to workspace`
>
> Enter **1**, **2**, or **3** — or **c** to cancel.

**Wait for the user's response.**

- If `c` or cancel — stop and confirm the backup was cancelled.
- If 1, 2, or 3 — use the date from that prompt as `<session-date>`. Continue to Step 3.

---

### Step 3 — Identify the workspace/category name

Run editor detection (fast — reads cached config):

```bash
python3 ~/.copilot/skills/session-backup/scripts/config.py \
  --status --workspace "<current-workspace-name>"
```

**VS Code** (`is_vscode: true`):

- Use `detected_vscode_workspace` from the status output as the workspace name.
- The registered folder for that workspace is looked up automatically by `session_backup.py`. No further questions needed.

**Non-VS Code** (`is_vscode: false`):
Ask the user each session:

> **What is the title or topic for this session?**
> This will be used as the session heading and filed under the `<folder>` subfolder.
> (e.g. `Python async patterns`, `Sprint planning`, `Research - LLM APIs`)

Store this as `<session-title>`. Pass it via `--session-title` in Steps 6 and 7.

Also ask for a category if the workspace key won't be meaningful:

> **What category should this be filed under?**
> Press Enter to reuse `<last-category-from-config>`, or type a new one.

Use `--category "<category>"` (instead of `--workspace`) when calling the backup scripts.

---

### Step 4 — Format the conversation

Review **every message** in the current session from the beginning and produce a single Markdown document using these rules:

| Content         | Formatting                                                                          |
| --------------- | ----------------------------------------------------------------------------------- |
| User prompt     | `#### ` heading — use the first 80 characters of the message                        |
| Assistant prose | Normal Markdown paragraphs                                                          |
| Assistant code  | Fenced code block with language tag (` ```python `, ` ```bash `, ` ```json `, etc.) |
| Assistant table | Markdown table syntax                                                               |
| Assistant list  | `- ` bullets or `1.` numbered list                                                  |

**Strip the following — do NOT include them in the output:**

- Any prompt starting with or exactly `/session-backup` (with or without a date argument)
- Any user reply that is a bare confirmation (`yes`, `no`, `y`, `n`) **immediately after** a `/session-backup` prompt
- The assistant response that follows a `/session-backup` confirmation exchange
- System messages, tool call internals, and memory file contents

Separate each remaining prompt + response pair with `---`. Preserve all code blocks exactly as written.

---

### Step 5 — Write formatted content to a temp file

Write the formatted Markdown from Step 4 to `/tmp/copilot_session_backup.md`.  
If the file already exists, overwrite it.

---

### Step 6 — Run the backup script

Run immediately — no confirmation prompt needed:

```bash
python3 ~/.copilot/skills/session-backup/scripts/session_backup.py \
  --input-file /tmp/copilot_session_backup.md \
  --workspace "<workspace-name>" \
  --date "<session-date>"
```

For non-VS Code, replace `--workspace` with `--category "<category>"` and add `--session-title "<session-title>"`.

The `--workspace`/`--category` and `--date` values come from Steps 1/2 and Step 3. These always take precedence over the active session pointer, ensuring the file lands in the correct dated directory.

---

### Step 7 — Report completion to the user

Parse the JSON output and confirm. Show the full absolute file path as plain text — do **not** use a markdown link, do not shorten or abbreviate the path:

> **✅ Session saved**
>
> **File:** `/absolute/path/to/vault/workspace/YYYY-MM-DD/<Derived Title>.md`
>
> `<total_prompts>` prompts in session — `<prompts_added>` added this run.

The filename is derived automatically from the first meaningful user prompt — no `session-N` intermediate file is created. If no usable title can be derived the file falls back to `session-N.md`.

**To override the auto-generated title** manually, run `--sync-title` standalone:

```bash
python3 ~/.copilot/skills/session-backup/scripts/session_backup.py \
  --sync-title \
  --workspace "<workspace-name>" \
  --session-title "<your preferred title>"
```

**`--sync-title` can also be run standalone** (without doing a full backup first) if the user says something like "rename this session" or "set the session title". In that case, skip Steps 1–6 and go directly to this step using the active session pointer.

---

### Step 8 — Rename all session files in the workspace (optional)

If the user asks to rename all sessions in a workspace (e.g. "sync all titles for nuk-licensing"), explain:

> **About to run:** `session_backup.py --sync-titles-workspace`
> This walks every `.md` file under `<vault>/<session-root>/<workspace-folder>/` and renames each one whose filename is still `session-N.md` to its frontmatter `title:` value.
> Files that already have a descriptive name, or whose target name already exists, are skipped.
> **Proceed? (yes / no)**

Wait for confirmation, then run:

```bash
python3 ~/.copilot/skills/session-backup/scripts/session_backup.py \
  --sync-titles-workspace \
  --workspace "<workspace-name>"
```

Parse the JSON output and report:

> **✅ Workspace titles synced**
>
> Renamed: `<renamed>` files  
> Skipped: `<skipped>` files (target name exists or no title in frontmatter)  
> No change: `<no_change>` files (already correctly named)

List any skipped files with the reason.

---

## Example Session File Output

```markdown
---
title: Session 1
workspace: nuk-licensing
date: 2026-04-28
tags: [ai-session, copilot]
---

# Session 1

**Workspace:** nuk-licensing  
**Date:** 2026-04-28

---

#### How do I create a Python virtual environment?

To create a virtual environment, run:

\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
\`\`\`

---

#### What packages are installed?

The following packages are currently installed...
```

---

## Notes

- The script tracks the current session number per workspace+date in `~/.copilot/skills/session-backup/.session-state.json`
- Session files use Obsidian-compatible YAML frontmatter and tags
- All content is UTF-8 encoded
