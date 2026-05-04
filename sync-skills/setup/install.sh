#!/usr/bin/env bash
set -e

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SETUP_DIR")"   # sync-skills/
REPO_DIR="$(dirname "$SKILL_DIR")"    # ai-skills/ (or wherever the skill lives)
BIN_TARGET="$HOME/.local/bin/sync-skills"
CONFIG_DIR="$HOME/.config/sync-skills"
CONFIG_FILE="$CONFIG_DIR/config.json"
INSTRUCTIONS_DIR="$HOME/.copilot/instructions"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
INSTRUCTIONS_ENV="COPILOT_CUSTOM_INSTRUCTIONS_DIRS"

# ── Helpers ──────────────────────────────────────────────────────────────────
step()  { echo ""; echo "── Step $1 of 6: $2 ──────────────────────────────"; echo ""; }
done_() { echo "  ✓  $1"; }
skip()  { echo "  ·  $1"; }
warn()  { echo "  ⚠  $1"; }

# ── Welcome ───────────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│              sync-skills  —  installer                  │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "This sets up sync-skills so any skill you place in your"
echo "Skills Hub is automatically available in Claude Code,"
echo "GitHub Copilot CLI, and VS Code Copilot Chat."

# ── Step 1: Skills Hub ────────────────────────────────────────────────────────
step 1 "Skills Hub"
echo "Your Skills Hub is the folder where you store skill sets."
echo "Each skill is a sub-folder containing a SKILL.md file, organised"
echo "under a namespace: <Skills Hub>/<namespace>/<skill-name>/SKILL.md"
echo ""
DEFAULT_HUB="$HOME/code/SKILLS_HUB"
echo -n "  Where should your Skills Hub live? [$DEFAULT_HUB]: "
read -r HUB_INPUT
SKILLS_HUB="${HUB_INPUT:-$DEFAULT_HUB}"
SKILLS_HUB="${SKILLS_HUB/#\~/$HOME}"
echo ""

if [ -d "$SKILLS_HUB" ]; then
  skip "Skills Hub already exists at:"
  skip "→ $SKILLS_HUB"
else
  mkdir -p "$SKILLS_HUB"
  done_ "Created Skills Hub at:"
  done_ "→ $SKILLS_HUB"
fi

# ── Step 2: Config ────────────────────────────────────────────────────────────
step 2 "Configuration"
mkdir -p "$CONFIG_DIR"
SKILLS_HUB_STORED="${SKILLS_HUB/#$HOME/~}"

if [ -f "$CONFIG_FILE" ]; then
  skip "Config already exists — leaving untouched"
  skip "→ $CONFIG_FILE"
else
  cat > "$CONFIG_FILE" <<EOF
{
  "watch_path": "$SKILLS_HUB_STORED",
  "copilot_namespace": null
}
EOF
  done_ "Created config:"
  done_ "→ $CONFIG_FILE"
  done_ "   watch_path: $SKILLS_HUB"
fi

# ── Step 3: sync-skills command ───────────────────────────────────────────────
step 3 "sync-skills command"
mkdir -p "$(dirname "$BIN_TARGET")"
ln -sf "$SKILL_DIR/sync_skills.py" "$BIN_TARGET"
chmod +x "$SKILL_DIR/sync_skills.py"
done_ "Command installed:"
done_ "→ sync-skills  (available anywhere in your terminal)"
done_ "   Source:    $SKILL_DIR/sync_skills.py"
done_ "   Linked at: $BIN_TARGET"

# ── Step 4: Claude Code & Copilot ─────────────────────────────────────────────
step 4 "Claude Code & Copilot"

echo "  Claude Code + Copilot CLI:"
if [ -d "$CLAUDE_SKILLS_DIR" ]; then
  skip "Skills directory already exists"
else
  mkdir -p "$CLAUDE_SKILLS_DIR"
  done_ "Created skills directory"
fi
done_ "→ $CLAUDE_SKILLS_DIR"
echo "     Skills symlinked here are auto-loaded by Claude Code"
echo "     and GitHub Copilot CLI in every session."
echo ""

echo "  VS Code Copilot Chat:"
mkdir -p "$INSTRUCTIONS_DIR"
done_ "Created Copilot instructions directory:"
done_ "→ $INSTRUCTIONS_DIR"
echo "     sync-skills writes a .instructions.md file here for each skill."
echo "     These are loaded into VS Code Copilot Chat sessions when"
echo "     COPILOT_CUSTOM_INSTRUCTIONS_DIRS points to this directory."
echo ""

SHELL_LINE="export $INSTRUCTIONS_ENV=\"$INSTRUCTIONS_DIR\""
PROFILE_UPDATED=false
for profile in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile"; do
  if [ -f "$profile" ]; then
    if grep -q "$INSTRUCTIONS_ENV" "$profile"; then
      skip "$INSTRUCTIONS_ENV already set in: $profile"
    else
      printf "\n# Added by sync-skills\n%s\n" "$SHELL_LINE" >> "$profile"
      done_ "Added $INSTRUCTIONS_ENV to: $profile"
    fi
    PROFILE_UPDATED=true
    break
  fi
done

if [ "$PROFILE_UPDATED" = false ]; then
  warn "No shell profile found. Add this to your shell config manually:"
  echo "     $SHELL_LINE"
fi

# ── Step 5: VS Code ───────────────────────────────────────────────────────────
step 5 "VS Code (optional)"

VSCODE_RESULT=$(python3 "$SETUP_DIR/update_vscode_settings.py" "$INSTRUCTIONS_DIR" --check 2>/dev/null || true)

if echo "$VSCODE_RESULT" | grep -q "^vs_code_not_found"; then
  skip "VS Code not detected — skipping"
else
  VSCODE_SETTINGS_PATH=$(echo "$VSCODE_RESULT" | grep "^vs_code_found:" | cut -d: -f2-)
  echo "  VS Code detected at:"
  echo "     $VSCODE_SETTINGS_PATH"
  echo ""
  echo "  Adding COPILOT_CUSTOM_INSTRUCTIONS_DIRS to your VS Code User settings"
  echo "  allows skills to load in VS Code Copilot Chat even when VS Code is"
  echo "  launched from the Dock (not a terminal)."
  echo ""
  echo -n "  Add this setting to VS Code User settings? [Y/n]: "
  read -r VSCODE_CONSENT
  VSCODE_CONSENT="${VSCODE_CONSENT:-Y}"
  echo ""

  if [[ "$VSCODE_CONSENT" =~ ^[Yy] ]]; then
    UPDATE_RESULT=$(python3 "$SETUP_DIR/update_vscode_settings.py" "$INSTRUCTIONS_DIR" 2>&1)
    if echo "$UPDATE_RESULT" | grep -q "^already_set"; then
      skip "VS Code setting already present — nothing to do"
    elif echo "$UPDATE_RESULT" | grep -q "^updated:"; then
      done_ "Added COPILOT_CUSTOM_INSTRUCTIONS_DIRS to VS Code User settings"
      done_ "→ $VSCODE_SETTINGS_PATH"
    else
      warn "Could not update VS Code settings automatically."
      echo "     Add this manually in VS Code (Cmd+, → Open Settings JSON):"
      echo '     "terminal.integrated.env.osx": {'
      echo "       \"COPILOT_CUSTOM_INSTRUCTIONS_DIRS\": \"$INSTRUCTIONS_DIR\""
      echo '     }'
    fi
  else
    skip "Skipped. You can add it later by re-running this installer."
  fi
fi

# ── Step 6: Initial sync ──────────────────────────────────────────────────────
step 6 "Initial sync"
python3 "$BIN_TARGET" --all

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│                  Setup complete!  🎉                    │"
echo "├─────────────────────────────────────────────────────────┤"
echo "│  What was configured:                                   │"
printf "│    Skills Hub     %s\n" "$(printf '%-38s │' "$SKILLS_HUB")"
printf "│    Config         %s\n" "$(printf '%-38s │' "$CONFIG_FILE")"
printf "│    Command        %s\n" "$(printf '%-38s │' "$BIN_TARGET")"
printf "│    Claude skills  %s\n" "$(printf '%-38s │' "$CLAUDE_SKILLS_DIR")"
printf "│    Instructions   %s\n" "$(printf '%-38s │' "$INSTRUCTIONS_DIR")"
echo "├─────────────────────────────────────────────────────────┤"
echo "│  Next steps:                                            │"
echo "│    1. Reload your shell:                                │"
echo "│       source ~/.zshrc  (or open a new terminal)        │"
echo "│    2. Add a skill folder to your Skills Hub             │"
echo "│    3. Run sync-skills to register it:                   │"
echo "│       • In terminal:    sync-skills                     │"
echo "│       • In Claude Code: /sync-skills                    │"
echo "│       • In Copilot CLI: /sync-skills                    │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
