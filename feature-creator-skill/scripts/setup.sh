#!/usr/bin/env bash
set -e

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPTS_DIR")"

CLAUDE_MD="$HOME/.claude/CLAUDE.md"
INSTRUCTIONS_ENV="COPILOT_CUSTOM_INSTRUCTIONS_DIRS"
SUPERPOWERS_REPO="git@github.com:obra/superpowers.git"
SUPERPOWERS_HTTPS="https://github.com/obra/superpowers.git"
SUPERPOWERS_HUB_NAME="obra-superpowers"
SUPERPOWERS_SKILLS_DIR="$HOME/.claude/skills/obra-superpowers"
REQUIRED_SUPERPOWERS="writing-plans executing-plans test-driven-development verification-before-completion finishing-a-development-branch"
SUPERPOWERS_MISSING=0

# ── Helpers ───────────────────────────────────────────────────────────────────
step()  { echo ""; echo "── Step $1 of 4: $2 ──────────────────────────────"; echo ""; }
done_() { echo "  ✓  $1"; }
skip()  { echo "  ·  $1"; }
warn()  { echo "  ⚠  $1"; }
fail()  { echo "  ✗  $1"; }

# ── Welcome ───────────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│          feature-creator-skill  —  setup                │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "Registers feature-creator with Claude Code and Copilot Chat."
echo "Safe to re-run — all steps are idempotent."
echo ""

# ── Step 1: Superpowers dependency check ─────────────────────────────────────
step 1 "Superpowers dependency"

echo "  Checking for obra/superpowers at $SUPERPOWERS_SKILLS_DIR"
echo ""

MISSING_LIST=""
for skill in $REQUIRED_SUPERPOWERS; do
    if [ ! -e "$SUPERPOWERS_SKILLS_DIR/$skill" ]; then
        MISSING_LIST="$MISSING_LIST $skill"
        SUPERPOWERS_MISSING=1
    fi
done

if [ "$SUPERPOWERS_MISSING" -eq 0 ]; then
    done_ "obra/superpowers found — all required skills present:"
    for skill in $REQUIRED_SUPERPOWERS; do
        echo "        • $skill"
    done
else
    warn "obra/superpowers is not installed (or missing skills:$MISSING_LIST )"
    echo ""
    echo "  feature-creator uses superpowers for non-trivial tasks:"
    echo "  writing-plans, executing-plans, test-driven-development,"
    echo "  verification-before-completion, finishing-a-development-branch"
    echo ""
    echo "  Without it, the skill will still work but will not be able to"
    echo "  offer structured planning or invoke superpowers workflows."
    echo ""
    echo "  ── To install obra/superpowers: ──────────────────────────────"
    echo ""

    # Detect SKILLS_HUB from sync-skills config
    SKILLS_HUB=""
    if command -v python3 &>/dev/null; then
        SKILLS_HUB=$(python3 -c "
import json, pathlib
cfg = pathlib.Path.home() / '.config/sync-skills/config.json'
if cfg.exists():
    d = json.loads(cfg.read_text())
    hub = d.get('watch_path', '')
    if hub:
        print(str(pathlib.Path(hub.replace('~', str(pathlib.Path.home())))))
" 2>/dev/null)
    fi
    SKILLS_HUB="${SKILLS_HUB:-$HOME/code/SKILLS_HUB}"

    # Check whether SSH to github works
    SSH_OK=0
    ssh -Tn git@github.com -o BatchMode=yes -o ConnectTimeout=5 > /tmp/.fc_setup_ssh 2>&1 || true
    grep -q "^Hi " /tmp/.fc_setup_ssh 2>/dev/null && SSH_OK=1
    rm -f /tmp/.fc_setup_ssh

    if [ "$SSH_OK" -eq 1 ]; then
        CLONE_URL="$SUPERPOWERS_REPO"
    else
        warn "SSH to GitHub unavailable — showing HTTPS clone URL instead"
        CLONE_URL="$SUPERPOWERS_HTTPS"
    fi

    echo "  1. Clone the repo into your Skills Hub:"
    echo ""
    echo "       git clone $CLONE_URL \\"
    echo "           $SKILLS_HUB/$SUPERPOWERS_HUB_NAME"
    echo ""
    echo "  2. Register it with sync-skills:"
    echo ""
    echo "       sync-skills --link $SKILLS_HUB/$SUPERPOWERS_HUB_NAME \\"
    echo "           --hub-name $SUPERPOWERS_HUB_NAME"
    echo ""
    echo "  3. Re-run this setup script:"
    echo ""
    echo "       bash $SCRIPTS_DIR/setup.sh"
    echo ""
    echo "  ─────────────────────────────────────────────────────────────"
    echo ""
    echo "  Continuing setup without superpowers..."
fi

# ── Step 2: Claude Code — CLAUDE.md ──────────────────────────────────────────
step 2 "Claude Code — CLAUDE.md"

FEATURE_DEV_SECTION='## Feature Development

When the user says any of the following, automatically invoke the `feature-creator` skill:
- "refactor", "rework", "restructure", "clean up", or "redesign" any code
- "add a module", "add a feature", "new feature", "new module", "new component", "new endpoint"
- "update this repo with", "introduce", "implement", "build out"
- Any request to make non-trivial code changes across one or more files

Do not wait to be asked — activate `/feature-creator` immediately when these patterns appear.'

if [ ! -f "$CLAUDE_MD" ]; then
    mkdir -p "$(dirname "$CLAUDE_MD")"
    printf "# Claude Instructions\n\n%s\n" "$FEATURE_DEV_SECTION" > "$CLAUDE_MD"
    done_ "Created $CLAUDE_MD with Feature Development section"
elif grep -q "## Feature Development" "$CLAUDE_MD" 2>/dev/null; then
    skip "Feature Development section already present in $CLAUDE_MD"
else
    printf "\n\n%s\n" "$FEATURE_DEV_SECTION" >> "$CLAUDE_MD"
    done_ "Appended Feature Development section to $CLAUDE_MD"
fi

# ── Step 3: Copilot Chat — .instructions.md ───────────────────────────────────
step 3 "Copilot Chat — instructions file"

# Resolve instructions directory from env var, then known defaults
if [ -n "${!INSTRUCTIONS_ENV}" ]; then
    INSTRUCTIONS_DIR="${!INSTRUCTIONS_ENV}"
elif [ -d "$HOME/.copilot/instructions" ]; then
    INSTRUCTIONS_DIR="$HOME/.copilot/instructions"
else
    # Fall back to the directory the env var normally points to
    INSTRUCTIONS_DIR="$HOME/.copilot/instructions"
fi

echo "  Instructions dir: $INSTRUCTIONS_DIR"
echo ""

python3 "$SCRIPTS_DIR/compile_instructions.py" "$INSTRUCTIONS_DIR"

# ── Step 4: VS Code settings — COPILOT_CUSTOM_INSTRUCTIONS_DIRS ──────────────
step 4 "VS Code settings — COPILOT_CUSTOM_INSTRUCTIONS_DIRS"

# Detect VS Code settings.json path per platform
OS="$(uname -s)"
case "$OS" in
    Darwin)  VSCODE_SETTINGS="$HOME/Library/Application Support/Code/User/settings.json" ;;
    Linux)   VSCODE_SETTINGS="$HOME/.config/Code/User/settings.json" ;;
    MINGW*|MSYS*|CYGWIN*) VSCODE_SETTINGS="$APPDATA/Code/User/settings.json" ;;
    *)       VSCODE_SETTINGS="" ;;
esac

if [ -z "$VSCODE_SETTINGS" ]; then
    warn "Unrecognised OS ($OS) — skipping VS Code settings update"
    warn "Add this manually to VS Code settings:"
    warn "  \"terminal.integrated.env.osx\": { \"COPILOT_CUSTOM_INSTRUCTIONS_DIRS\": \"$INSTRUCTIONS_DIR\" }"
elif [ ! -f "$VSCODE_SETTINGS" ]; then
    warn "VS Code settings.json not found at:"
    warn "→ $VSCODE_SETTINGS"
    warn "Install VS Code or create the file, then re-run this script."
else
    if python3 -c "
import json, re, sys
from pathlib import Path

settings_path = Path(\"$VSCODE_SETTINGS\")
instructions_dir = \"$INSTRUCTIONS_DIR\"

text = settings_path.read_text(encoding='utf-8')

# Strip JSONC comments and trailing commas to parse safely
def strip_jsonc(text):
    result = []
    i = 0
    in_string = False
    while i < len(text):
        c = text[i]
        if in_string:
            result.append(c)
            if c == '\\\\':
                i += 1
                if i < len(text): result.append(text[i])
            elif c == '\"': in_string = False
        else:
            if c == '\"':
                in_string = True
                result.append(c)
            elif c == '/' and i + 1 < len(text) and text[i+1] == '/':
                while i < len(text) and text[i] != '\n': i += 1
                continue
            else:
                result.append(c)
        i += 1
    cleaned = ''.join(result)
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    return cleaned

try:
    data = json.loads(strip_jsonc(text))
except Exception:
    print('PARSE_ERROR')
    sys.exit(0)

env_key = 'terminal.integrated.env.osx'
env_block = data.get(env_key, {})
current = env_block.get('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', '')

if current == instructions_dir:
    print('ALREADY_SET')
else:
    print('NOT_SET')
" 2>/dev/null; then
        :
    fi

    CHECK_RESULT=$(python3 -c "
import json, re, sys
from pathlib import Path

settings_path = Path(\"$VSCODE_SETTINGS\")
instructions_dir = \"$INSTRUCTIONS_DIR\"

text = settings_path.read_text(encoding='utf-8')

def strip_jsonc(text):
    result = []
    i = 0
    in_string = False
    while i < len(text):
        c = text[i]
        if in_string:
            result.append(c)
            if c == '\\\\':
                i += 1
                if i < len(text): result.append(text[i])
            elif c == '\"': in_string = False
        else:
            if c == '\"':
                in_string = True
                result.append(c)
            elif c == '/' and i + 1 < len(text) and text[i+1] == '/':
                while i < len(text) and text[i] != '\n': i += 1
                continue
            else:
                result.append(c)
        i += 1
    cleaned = ''.join(result)
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    return cleaned

try:
    data = json.loads(strip_jsonc(text))
except Exception:
    print('PARSE_ERROR')
    sys.exit(0)

env_key = 'terminal.integrated.env.osx'
env_block = data.get(env_key, {})
current = env_block.get('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', '')

if current == instructions_dir:
    print('ALREADY_SET')
else:
    print('NOT_SET')
" 2>/dev/null)

    case "$CHECK_RESULT" in
        ALREADY_SET)
            skip "COPILOT_CUSTOM_INSTRUCTIONS_DIRS already set in VS Code settings"
            ;;
        NOT_SET)
            python3 "$(dirname "$SCRIPTS_DIR")/../../sync-skills/setup/update_vscode_settings.py" "$INSTRUCTIONS_DIR" 2>/dev/null \
                && done_ "Added COPILOT_CUSTOM_INSTRUCTIONS_DIRS to VS Code settings" \
                || warn "Could not auto-update VS Code settings. Add this manually:
          \"terminal.integrated.env.osx\": { \"COPILOT_CUSTOM_INSTRUCTIONS_DIRS\": \"$INSTRUCTIONS_DIR\" }"
            ;;
        PARSE_ERROR)
            warn "Could not parse VS Code settings.json — add COPILOT_CUSTOM_INSTRUCTIONS_DIRS manually"
            ;;
    esac
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│                     Setup complete                      │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "  feature-creator is now registered with:"
echo "  • Claude Code  — auto-activates via ~/.claude/CLAUDE.md"
echo "  • Copilot Chat — loaded via $INSTRUCTIONS_DIR"
echo ""
if [ "$SUPERPOWERS_MISSING" -eq 0 ]; then
    echo "  • obra/superpowers — ✓ installed"
else
    echo "  • obra/superpowers — ⚠ not installed (see Step 1 above)"
    echo "    Install it and re-run this script for full functionality."
fi
echo ""
echo "  Reload VS Code for the Copilot instructions to take effect."
echo ""
