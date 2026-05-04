---
name: sync-skills
description: "Use when new skills have been added to SKILLS_HUB and need to be made available, when a skill is missing or not triggering, when skill symlinks may be broken or out of date, when the user wants to link a git repo into SKILLS_HUB, or when checking whether the sync-skills binary is correctly installed."
argument-hint: "[--all] [--link <path>] [--verify <hub-name>]"
---

# Sync Skills

## Overview

Discovers skills in your configured SKILLS_HUB path and symlinks them into `~/.claude/skills/` so they are available to both Claude Code and GitHub Copilot CLI. A registry tracks what has already been indexed so only new skills are processed on each run.

Also supports `--link` to bring a git repo into SKILLS_HUB as a symlink, and `--verify` to check the full chain is intact.

## When to Use

- You added a new skill to SKILLS_HUB and it isn't showing up
- A skill that used to work is no longer triggering
- You suspect symlinks are broken (e.g. after moving files or re-cloning)
- You want to audit that all skills are properly indexed (`--all`)
- You have a git repo of skills you want to link into SKILLS_HUB (`--link`)
- You want to confirm the entire chain is working for a namespace (`--verify`)
- You want to check whether the `sync-skills` binary is installed and up to date

## Procedure

### Standard sync

1. Run the sync script:
   ```
   ~/.local/bin/sync-skills
   ```
   If the `--all` flag was provided, run:
   ```
   ~/.local/bin/sync-skills --all
   ```

2. Report the output to the user exactly as returned — which skills were linked, repaired, or already indexed.

3. If the script is not found at `~/.local/bin/sync-skills`, inform the user to reinstall:
   ```
   bash ~/path/to/sync-skills/setup/install.sh
   ```

### Linking a git repo into SKILLS_HUB

Use `--link <path>` to create a SKILLS_HUB symlink pointing at a git repo that contains skill subdirectories:

```
sync-skills --link ~/code/git-repos/vaughnangoy/ai-skills
```

The hub name is derived as `<parent-dir>-<repo-name>`, e.g.:
- `~/code/git-repos/vaughnangoy/ai-skills` → `vaughnangoy-ai-skills`
- `~/code/git-repos/teng-lin/notebooklm-py` → `teng-lin-notebooklm-py`

`--link` also runs `--all` automatically, prints verification results, and confirms the `sync-skills` binary at `~/.local/bin/sync-skills` is correctly installed.

If SKILLS_HUB already has a real directory with that name (e.g. created manually):
- **Same skill names**: migrated silently — real dir replaced with symlink
- **Extra skills not in target**: requires `--force` to replace

### Verifying a linked namespace

```
sync-skills --verify vaughnangoy-ai-skills
```

Prints a table showing ✅/❌ for each skill across three checks:

| Check | What it verifies |
|-------|-----------------|
| SKILLS_HUB symlink | `SKILLS_HUB/<hub-name>` is a symlink to a live directory |
| Claude symlink | `~/.claude/skills/<hub-name>/<skill>` is a valid symlink |
| Copilot `.instructions.md` | `~/.copilot/instructions/<hub-name>-<skill>.instructions.md` exists and is non-empty |

Also checks that `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` is configured (env var, VS Code settings, or shell profile).

## Common Mistakes

- **Running sync-skills on skills already linked at namespace level** — skills inside a namespace dir that is itself a symlink will show as "skipped". This is correct; they are already accessible.
- **Expecting auto-sync** — this skill is manual only. Drop a new skill folder into SKILLS_HUB or run `--link`, then run `/sync-skills`.
- **Forgetting `--force`** — if a real directory in SKILLS_HUB has skills that don't exist in the target repo, `--link` will refuse and tell you to add `--force`.
- **Binary not found** — if `sync-skills` isn't on your PATH, run `bash <repo>/sync-skills/setup/install.sh`. The binary is a symlink, so it picks up code changes automatically.

## Reference

| Path | Purpose |
|------|---------|
| `~/.config/sync-skills/config.json` | Watch path and namespace config |
| `~/.config/sync-skills/registry.json` | Index of already-linked skills |
| `~/.claude/skills/<namespace>/<skill>/` | Symlink destination (shared by Claude Code + Copilot CLI) |
| `~/.copilot/instructions/<ns>-<skill>.instructions.md` | Copilot Chat / CLI instructions file |

Skills must be directories containing a `SKILL.md` file, nested as `<watch_path>/<namespace>/<skill-name>/`.
