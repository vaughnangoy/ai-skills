# Changelog

All notable changes to feature-creator-skill are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `SKILL.md`: full feature development workflow — branch creation, pre-change confirmation gates, TDD loop with visible subprocess test runs, per-commit changelog updates, multi-repo session tracking, and superpowers offer for non-trivial scope
- `scripts/setup.sh`: idempotent installer that registers the skill with Claude Code (`~/.claude/CLAUDE.md` auto-activation trigger), compiles instructions for Copilot Chat, and checks/updates VS Code `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` — works across macOS, Linux, and Windows
- `scripts/setup.sh`: Step 1 superpowers dependency check — detects missing `obra/superpowers` skills, prints exact clone and `sync-skills --link` commands (SSH with HTTPS fallback), reads Skills Hub path from sync-skills config
- `scripts/compile_instructions.py`: compiles `SKILL.md` into the Copilot `.instructions.md` format (`applyTo: "**"`) — idempotent, supports `--check` flag for verification without writing
- `README.md`: full installation and usage guide covering Claude Code, VS Code Copilot Chat, auto-activation layers, honest capability comparison between the two tools, and prerequisites (obra/superpowers, sync-skills)
