# sync-skills

Keeps your AI skills available everywhere. Discovers skill directories in a central hub and wires them into Claude Code, GitHub Copilot CLI, and VS Code Copilot Chat automatically.

---

## What it does

Skills are directories containing a `SKILL.md` file. They need to appear in three places to be fully available:

| Location | Used by |
|----------|---------|
| `~/.claude/skills/<namespace>/<skill>/` | Claude Code, Copilot CLI |
| `~/.copilot/instructions/<namespace>-<skill>.instructions.md` | VS Code Copilot Chat |
| `~/.config/sync-skills/registry.json` | sync-skills (dedup tracking) |

`sync-skills` manages all three. You point it at a git repo of skills once (`--link`), and it creates the symlinks and instruction files so every AI tool picks them up immediately. The installed binary is a live symlink — code changes in the repo take effect automatically without reinstalling.

---

## How it works

```
git repo (source of truth)
  └── clone-repo/SKILL.md
  └── explain-code/SKILL.md
  └── sync-skills/SKILL.md
        │
        │  sync-skills --link ~/code/git-repos/vaughnangoy/ai-skills
        ▼
~/code/SKILLS_HUB/vaughnangoy-ai-skills/
  ├── clone-repo       →  (symlink → repo skill dir)
  ├── explain-code     →  (symlink → repo skill dir)
  └── sync-skills      →  (symlink → repo skill dir)
        │
        │  (wired automatically by sync-skills)
        ▼
~/.claude/skills/vaughnangoy-ai-skills/
  ├── clone-repo       →  (symlink)
  └── ...

~/.copilot/instructions/
  ├── vaughnangoy-ai-skills-clone-repo.instructions.md
  └── ...
```

The hub name is derived from the repo path as `<parent-dir>-<repo-name>`:
- `vaughnangoy/ai-skills` → `vaughnangoy-ai-skills`
- `teng-lin/notebooklm-py` → `teng-lin-notebooklm-py`

**Collapsed mode**: when `~/.claude/skills` is itself a symlink to SKILLS_HUB (a common setup), namespace-level symlinks would create circular references. sync-skills detects this and creates individual per-skill symlinks pointing directly at the repo instead.

---

## Installation

```bash
bash ~/code/git-repos/vaughnangoy/ai-skills/sync-skills/setup/install.sh
```

The installer:
1. Asks where your Skills Hub should live (default: `~/code/SKILLS_HUB`)
2. Writes `~/.config/sync-skills/config.json`
3. Creates `~/.local/bin/sync-skills` as a symlink to `sync_skills.py`
4. Ensures `~/.claude/skills/` and `~/.copilot/instructions/` exist
5. Adds `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` to your shell profile
6. Runs an initial sync

After install, reload your shell (`source ~/.zshrc`) so VS Code picks up the environment variable.

Make sure `~/.local/bin` is on your `PATH`:
```bash
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc
```

---

## Usage

### Link a git repo (first-time setup for a skill namespace)

```bash
sync-skills --link ~/code/git-repos/vaughnangoy/ai-skills
```

- Creates `SKILLS_HUB/vaughnangoy-ai-skills/` with symlinks to each skill in the repo
- Registers all skills and writes `.instructions.md` files
- Prints a full ✅/❌ verification table
- Confirms the `sync-skills` binary is installed correctly

If SKILLS_HUB already has a real directory for that namespace with extra skills not in the repo, `--link` will refuse — use `--force` to replace it:

```bash
sync-skills --link ~/code/git-repos/org/repo --force
```

### Verify a namespace

```bash
sync-skills --verify vaughnangoy-ai-skills
```

Prints a table checking for every skill:
- Hub entry is valid
- `~/.claude/skills/<ns>/<skill>` symlink is live
- `~/.copilot/instructions/<ns>-<skill>.instructions.md` exists and is non-empty
- `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` is configured

### Re-validate all skills

```bash
sync-skills --all
```

Re-checks every registered skill, repairs broken symlinks, rewrites any missing instruction files, and removes entries for skills that no longer exist in the hub.

### Incremental sync (default)

```bash
sync-skills
```

Only processes skills not yet in the registry. Fast for day-to-day use when you've added a new skill to an existing linked repo.

---

## File layout

```
SKILLS_HUB/
  <namespace>/                ← symlink → git repo (or real dir in collapsed mode)
    <skill-name>/
      SKILL.md                ← required; must exist for a dir to be treated as a skill

~/.config/sync-skills/
  config.json                 ← watch_path
  registry.json               ← index of registered skills (namespace/name → source path)

~/.claude/skills/
  <namespace>/
    <skill-name>/             ← symlink → repo skill dir

~/.copilot/instructions/
  <namespace>-<skill-name>.instructions.md   ← generated from SKILL.md frontmatter + body

~/.local/bin/
  sync-skills                 ← symlink → sync_skills.py
```

---

## Writing a skill

A skill is a directory with a `SKILL.md` at its root:

```
my-skill/
  SKILL.md        ← required
  scripts/        ← optional
  references/     ← optional
```

Minimal `SKILL.md`:

```markdown
---
name: my-skill
description: "Use when [triggering conditions, not a summary of what the skill does]"
---

# My Skill

## Overview
What this skill does in one sentence.

## Procedure
Steps the agent should follow.
```

The `description` field is what the AI reads to decide whether to invoke the skill. Write it as triggering conditions, not a description of the skill's process.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `sync-skills: command not found` | Run `install.sh`; ensure `~/.local/bin` is on `PATH` |
| Skill not triggering in VS Code | Check `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` points to `~/.copilot/instructions/`; run `sync-skills --verify <ns>` |
| Skill not triggering in Claude Code | Run `sync-skills --all`; check `~/.claude/skills/<ns>/<skill>` is a live symlink |
| `--link` refuses with "real directory exists" | Run with `--force`, or manually remove the SKILLS_HUB directory |
| Binary check shows wrong target | Re-run `install.sh` |
| Circular symlinks in SKILLS_HUB | Delete the namespace dir and re-run `--link` — collapsed mode will rebuild it correctly |

---

## Tests

```bash
cd sync-skills
python3 -m venv .venv && .venv/bin/pip install pytest -q
.venv/bin/python -m pytest tests/test_link.py -v
```

20 tests covering `derive_hub_name`, `link_to_hub` (normal and collapsed mode), and `verify_link`.

