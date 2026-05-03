---
name: sync-skills
description: "Use when new skills have been added to SKILLS_HUB and need to be made available, when a skill is missing or not triggering, or when skill symlinks may be broken or out of date."
argument-hint: "[--all] — re-validate all registered skills and repair broken symlinks"
---

# Sync Skills

## Overview

Discovers skills in your configured SKILLS_HUB path and symlinks them into `~/.claude/skills/` so they are available to both Claude Code and GitHub Copilot CLI. A registry tracks what has already been indexed so only new skills are processed on each run.

## When to Use

- You added a new skill to SKILLS_HUB and it isn't showing up
- A skill that used to work is no longer triggering
- You suspect symlinks are broken (e.g. after moving files or re-cloning)
- You want to audit that all skills are properly indexed (`--all`)

## Procedure

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

## Common Mistakes

- **Running sync-skills on skills already linked at namespace level** — skills inside a namespace dir that is itself a symlink will show as "skipped". This is correct; they are already accessible.
- **Expecting auto-sync** — this skill is manual only. Drop a new skill folder into SKILLS_HUB, then run `/sync-skills`.

## Reference

| Path | Purpose |
|------|---------|
| `~/.config/sync-skills/config.json` | Watch path and namespace config |
| `~/.config/sync-skills/registry.json` | Index of already-linked skills |
| `~/.claude/skills/<namespace>/<skill>/` | Symlink destination (shared by Claude Code + Copilot CLI) |

Skills must be directories containing a `SKILL.md` file, nested as `<watch_path>/<namespace>/<skill-name>/`.
