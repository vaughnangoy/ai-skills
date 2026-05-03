# sync-skills

Automatically discover and register skills from a local **Skills Hub** directory, making them available in **Claude Code**, **GitHub Copilot CLI**, and **VS Code Copilot Chat** — without any manual configuration per project.

---

## How it works

### 1. You organise skills in a Skills Hub

A Skills Hub is a folder on your machine. Inside it, skills are grouped under a namespace (usually your GitHub username or team name):

```
~/code/SKILLS_HUB/
└── my-namespace/
    ├── my-skill/
    │   └── SKILL.md          ← skill definition
    └── another-skill/
        ├── SKILL.md
        └── config.json
```

Any directory containing a `SKILL.md` file is recognised as a skill.

### 2. sync-skills symlinks them into the right places

Running `sync-skills` (or `/sync-skills` in Claude Code / Copilot CLI):

- **Symlinks** each skill into `~/.claude/skills/<namespace>/<skill-name>/`
  → Claude Code and Copilot CLI scan this directory automatically in every session
- **Writes** a `.instructions.md` file to `~/.copilot/instructions/`
  → VS Code Copilot Chat loads these when `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` is set

### 3. A registry tracks what's been indexed

`~/.config/sync-skills/registry.json` records every skill that has been linked. On the next run, only *new* skills are processed. Use `--all` to re-validate everything.

---

## Install

```bash
bash install.sh
```

The installer will:

1. Ask where your Skills Hub should live (default: `~/code/SKILLS_HUB`)
2. Write config to `~/.config/sync-skills/config.json`
3. Install the `sync-skills` command to `~/.local/bin/sync-skills`
4. Set up `~/.claude/skills/` for Claude Code + Copilot CLI
5. Set up `~/.copilot/instructions/` and add `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` to your shell profile
6. Run an initial sync

After install, **reload your shell** (`source ~/.zshrc`) so VS Code picks up the new environment variable.

---

## Usage

### Terminal

```bash
sync-skills          # sync new skills only
sync-skills --all    # re-validate all skills, repair broken symlinks
```

### Inside Claude Code or Copilot CLI

```
/sync-skills         # sync new skills
/sync-skills --all   # re-validate all
```

---

## Writing a skill

Create a folder inside your Skills Hub with a `SKILL.md`:

```
~/code/SKILLS_HUB/
└── my-namespace/
    └── my-skill/
        └── SKILL.md
```

Minimal `SKILL.md`:

```markdown
---
name: my-skill
description: "Use when [triggering conditions]"
---

# My Skill

## Overview
What this skill does in one or two sentences.

## Procedure
Steps the agent should follow.
```

Then run `sync-skills` (or `/sync-skills`) — the skill is immediately available.

---

## Configuration

`~/.config/sync-skills/config.json`:

```json
{
  "watch_path": "~/code/SKILLS_HUB"
}
```

To change your Skills Hub path:

```bash
sync-skills --watch-path ~/new/path
```

---

## File locations

| Path | Purpose |
|------|---------|
| `~/.config/sync-skills/config.json` | Watch path configuration |
| `~/.config/sync-skills/registry.json` | Index of linked skills |
| `~/.claude/skills/<namespace>/<skill>/` | Symlink target (Claude Code + Copilot CLI) |
| `~/.copilot/instructions/<ns>-<skill>.instructions.md` | VS Code Copilot Chat registration |
| `~/.local/bin/sync-skills` | Installed command |
