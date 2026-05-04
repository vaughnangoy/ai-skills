# feature-creator-skill

A structured feature development workflow for any git repository. Wraps your coding sessions in a consistent loop: **branch → confirm → test-first → run → commit → changelog** — enforced by your AI assistant rather than remembered by you.

Works with **Claude Code** and **VS Code Copilot Chat**. Supports multi-repo sessions, giving each active repository its own branch and `CHANGELOG.md`.

---

## What it does

When activated, the skill manages the following for you automatically:

| Behaviour | What happens |
|---|---|
| **Branch creation** | Offers to create a `feature/<name>` branch from `main`/`master` before any code is touched |
| **Pre-change confirmation** | Asks for explicit approval before writing, editing, or deleting any file |
| **Test-driven development** | Writes the failing test first, confirms it fails, then implements |
| **Visible test runs** | Tests run in a foreground subprocess — you see full output, not a silent pass/fail |
| **Regression detection** | Runs the full test suite after each task, not just the new test |
| **Commit offers** | After each working task (all tests pass), offers to commit with a descriptive message |
| **Changelog updates** | Updates `CHANGELOG.md` in the same commit — every commit, every repo |
| **Multi-repo tracking** | In sessions touching more than one repo, tracks branches and changelogs independently |
| **Superpowers offer** | For non-trivial scope, offers to write a formal plan and work task-by-task |

---

## Prerequisites

### obra/superpowers (required for full functionality)

`feature-creator` references five superpowers skills for non-trivial work:

| Skill | Used for |
|---|---|
| `writing-plans` | Drafting a step-by-step implementation plan before touching code |
| `executing-plans` | Working through a plan task by task with explicit checkboxes |
| `test-driven-development` | Enforcing the write-failing-test-first loop |
| `verification-before-completion` | Final checks before declaring a task done |
| `finishing-a-development-branch` | End-of-session cleanup, test run, and PR readiness check |

These come from the [`obra/superpowers`](https://github.com/obra/superpowers) repo.

**The setup script checks for this automatically.** If it's missing, Step 1 of `setup.sh` will print the exact commands to install it and then continue setting up everything else. You can install superpowers afterwards and re-run `setup.sh` — it will pick it up on the next run.

**Without superpowers installed**, `feature-creator` still works — branch creation, confirmation gates, tests, commits, and changelogs all function normally. The only missing piece is the structured planning workflow for non-trivial tasks (the *"would you like to use the superpowers approach?"* offer in Step 1 of the skill).

To install superpowers manually:

```bash
# 1. Clone into your Skills Hub (adjust path to match your setup)
git clone git@github.com:obra/superpowers.git ~/code/SKILLS_HUB/obra-superpowers

# 2. Register with sync-skills
sync-skills --link ~/code/SKILLS_HUB/obra-superpowers --hub-name obra-superpowers

# 3. Re-run feature-creator setup to confirm detection
bash ~/code/git-repos/vaughnangoy/ai-skills/feature-creator-skill/scripts/setup.sh
```

If SSH to GitHub is unavailable, use HTTPS:

```bash
git clone https://github.com/obra/superpowers.git ~/code/SKILLS_HUB/obra-superpowers
```

### sync-skills (required)

`setup.sh` reads your Skills Hub path from `~/.config/sync-skills/config.json`. If sync-skills isn't installed yet, install it first:

```bash
bash ~/code/git-repos/vaughnangoy/ai-skills/sync-skills/setup/install.sh
```

---

## Installation

### 1. Clone the repo (if you haven't already)

```bash
git clone git@github.com:vaughnangoy/ai-skills.git ~/code/git-repos/vaughnangoy/ai-skills
```

### 2. Run the setup script

```bash
bash ~/code/git-repos/vaughnangoy/ai-skills/feature-creator-skill/scripts/setup.sh
```

The script is idempotent — safe to run on any machine, any number of times. It handles:

- Registering the skill with Claude Code (`~/.claude/skills/`)
- Compiling the skill into Copilot Chat's instructions format (`~/.copilot/instructions/`)
- Wiring the auto-activation trigger into `~/.claude/CLAUDE.md`
- Checking that VS Code's `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` env var points at the instructions directory

### 3. Reload VS Code

Copilot Chat loads instruction files at startup. Reload the window (`Cmd+Shift+P` → *Reload Window*) after running setup for the first time.

---

## Using the skill

### Claude Code

Invoke explicitly:

```
/feature-creator
/feature-creator add-dark-mode
/feature-creator refactor-auth
```

Or just start describing the work — the skill activates automatically when you say things like:

- *"I want to refactor the auth module"*
- *"Add a new payments endpoint"*
- *"Update this repo with a caching layer"*
- *"Restructure the config handling"*

### VS Code Copilot Chat

No slash command needed. Once the instructions file is in place, Copilot Chat reads the workflow rules on every request and applies them when it detects feature development language in your message.

---

## Auto-activation: the two layers

There are two ways to make the skill activate without a slash command. They work differently and complement each other.

### Layer 1 — `~/.claude/CLAUDE.md` (Claude Code only)

The setup script adds a **Feature Development** section to your global `CLAUDE.md`:

```markdown
## Feature Development

When the user says any of the following, automatically invoke the `feature-creator` skill:
- "refactor", "rework", "restructure", "clean up", or "redesign" any code
- "add a module", "add a feature", "new feature", "new module", "new component", "new endpoint"
- "update this repo with", "introduce", "implement", "build out"
- Any request to make non-trivial code changes across one or more files

Do not wait to be asked — activate `/feature-creator` immediately when these patterns appear.
```

`CLAUDE.md` is loaded into every Claude Code session. When Claude sees the trigger language, it invokes the skill without being asked.

**Benefit of having this:** Zero friction. You never need to remember to type `/feature-creator`. Claude reads the intent from your natural language and starts the workflow immediately — branch creation offer, confirmation gates, and all.

**Limitation without it:** The skill exists but Claude won't invoke it automatically. You must type `/feature-creator` at the start of every session. If you forget, you get no branch, no gates, no guaranteed changelog — just Claude's default behaviour with no structure.

---

### Layer 2 — `~/.copilot/instructions/` (Copilot Chat)

The setup script compiles `SKILL.md` into a `.instructions.md` file that Copilot Chat loads automatically via `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`:

```
~/.copilot/instructions/vaughnangoy-ai-skills-feature-creator-skill.instructions.md
```

The file contains the full skill procedure with `applyTo: "**"` so it applies to every workspace.

**Benefit of having this:** Copilot Chat follows the same workflow rules as Claude Code — branch first, confirm before changes, tests required, commit with changelog. The rules are in every Copilot Chat session without any extra steps.

**Limitation without it:** Copilot Chat has no knowledge of the workflow. It will make changes without asking, skip tests unless you remind it, and never update `CHANGELOG.md`. Every session starts from scratch with no structure.

---

## Honest comparison: Claude Code vs Copilot Chat

The same rules are loaded into both tools, but they behave differently.

| | Claude Code | VS Code Copilot Chat |
|---|---|---|
| **Follows the procedure reliably** | Yes — executes numbered steps as written | Partially — interprets rules as guidance, not hard constraints |
| **Pre-change confirmation gate** | Enforced on every file change | Applied most of the time, but not guaranteed |
| **Tests run in subprocess** | Yes — full visible output via Bash tool | Depends on whether Copilot has terminal access |
| **Changelog updated per commit** | Yes — part of the commit flow | Reminded to do so, but may need prompting |
| **Multi-repo tracking** | Yes — session registry maintained | Awareness only — no programmatic tracking |
| **Auto-activation** | Strong — CLAUDE.md trigger is always loaded | Moderate — instruction file is loaded but Copilot applies it loosely |

Copilot Chat is a powerful tool and these instructions meaningfully improve its output. But if procedural fidelity matters — especially the confirmation gates, test-first enforcement, and per-repo changelog — Claude Code is the more reliable executor of this workflow.

---

## Keeping it up to date

When `SKILL.md` changes (new steps, updated triggers), re-run the setup script to recompile the Copilot instructions file:

```bash
bash ~/code/git-repos/vaughnangoy/ai-skills/feature-creator-skill/scripts/setup.sh
```

The script detects whether the compiled file is already current and skips the write if nothing has changed.

---

## File structure

```
feature-creator-skill/
├── SKILL.md                     # Full skill procedure (source of truth)
├── README.md                    # This file
└── scripts/
    ├── setup.sh                 # Installation script — run on each new machine
    └── compile_instructions.py  # Compiles SKILL.md → Copilot .instructions.md format
```

After setup, the following files are written to your home directory:

```
~/.claude/CLAUDE.md                          # auto-activation trigger added here
~/.claude/skills/vaughnangoy-ai-skills/
    feature-creator-skill/SKILL.md           # symlinked from the repo
~/.copilot/instructions/
    vaughnangoy-ai-skills-feature-creator-skill.instructions.md   # compiled from SKILL.md
```
