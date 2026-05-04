# Changelog

All notable changes to sync-skills are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `find_standalone_skills()`: discovers single-skill repos linked directly into SKILLS_HUB (entries with `SKILL.md` at root, not inside a namespace subdirectory)
- `sync_skills()`: processes standalone skills after namespace skills, writing Copilot instructions files without a namespace prefix (e.g. `excalidraw-diagram-skill.instructions.md` not `__standalone__-excalidraw-diagram-skill.instructions.md`)
- Stale cleanup for standalone skills: `--all` removes instructions files when a standalone skill is no longer present in SKILLS_HUB
- `link_to_hub()`: creates flat symlinks at SKILLS_HUB root for every namespaced skill when `hub == SKILLS_DIR` (collapsed mode), enabling Claude Code depth-1 skill discovery at `~/.claude/skills/<skill>/SKILL.md`
- `verify_link()`: added "Flat (Claude)" column in collapsed mode; `all_pass` requires flat symlink to exist alongside namespace symlink and instructions file
- 8 new tests covering flat symlink creation, conflict handling, cleanup, standalone skill indexing and stale removal (29 total)

### Changed
- `find_skills()`: skips dirs with `SKILL.md` at root so flat Claude Code symlinks are not mistakenly treated as namespace directories during the next sync
- `sync_skills()` early-return guard: only fires when `not all_mode`, so `--all` always runs stale cleanup even when the watch path is empty
- `sync_skills()` stale cleanup: skips namespace symlink removal for `__standalone__` entries; uses unprefixed instructions filename for standalone skills; prints just the skill name (not `__standalone__/name`) in removed output
