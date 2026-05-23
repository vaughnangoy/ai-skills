# Changelog

All notable changes to feature-creator-skill are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `SKILL.md`: new **Step 5e — End-to-end coverage and documentation** requiring 2 happy + 1 sad e2e scenarios per user-observable task, captured in `<feature_worktree_root>/docs/e2e/<feature-name>-YYYY-MM-DD.md` (one file per feature, dated at first creation, appended-to as the feature grows); includes the doc template, exemption rules for refactor/docs-only/test-only/config changes, and an end-to-end runner table (playwright / cypress / supertest / requests / bats / pipeline scripts)
- `SKILL.md`: new **E2E doc** entry in the Definitions table
- `SKILL.md`: full feature development workflow — worktree creation, pre-change confirmation gates, TDD loop with visible subprocess test runs, per-commit changelog updates, multi-repo session tracking, and superpowers offer for non-trivial scope
- `scripts/setup.sh`: idempotent installer that registers the skill with Claude Code (`~/.claude/CLAUDE.md` auto-activation trigger), compiles instructions for Copilot Chat, and checks/updates VS Code `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` — works across macOS, Linux, and Windows
- `scripts/setup.sh`: Step 1 superpowers dependency check — detects missing `obra/superpowers` skills, prints exact clone and `sync-skills --link` commands (SSH with HTTPS fallback), reads Skills Hub path from sync-skills config
- `scripts/compile_instructions.py`: compiles `SKILL.md` into the Copilot `.instructions.md` format (`applyTo: "**"`) — idempotent, supports `--check` flag for verification without writing
- `README.md`: full installation and usage guide covering Claude Code, VS Code Copilot Chat, auto-activation layers, honest capability comparison between the two tools, and prerequisites (obra/superpowers, sync-skills)

### Changed
- `SKILL.md`: push trigger condition #3 now requires the e2e doc to exist alongside passing scenarios (or an explicit skip reason in the commit body); condition #4 now explicitly calls out `docs/e2e/<feature-name>-YYYY-MM-DD.md` as part of "docs updated"
- `SKILL.md`: old Step 5e ("Confirm the task is working") renamed to Step 5f; Step 6 cross-reference updated accordingly
- `SKILL.md`: rewritten around the [`worktree-strategy`](https://github.com/vaughnangoy/worktree-strategy) POLICY — feature work now happens in sibling worktrees at `<repo>-worktrees/<type>/<name>/`, the main worktree stays on the default branch permanently, integration is PR-only, push cadence is per-change with a 5-condition trigger, the first push opens the PR as `--draft`, and cleanup is delegated to `git prune-worktrees` instead of any local branch deletion or `git merge` into main
- `SKILL.md`: repo registry now tracks `main_worktree_root`, `worktrees_root`, `feature_worktree_root`, `pr_url`, and `pr_state` in addition to the feature branch name
- `SKILL.md`: added Step 8d (`gh pr ready`) and Step 8e (post-merge `git prune-worktrees`); the skill never performs a local merge into `main`
- `SKILL.md`: added `/feature-creator ready` and `/feature-creator prune` flags

