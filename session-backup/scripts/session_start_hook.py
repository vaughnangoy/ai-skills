#!/usr/bin/env python3
"""
session_start_hook.py

SessionStart hook — fires on the very first prompt of a new agent chat session.

Always creates a new numbered session file (session-1.md, session-2.md, etc.)
and writes the active session pointer to /tmp/copilot_session_<workspace>.json so
prompt_hook.py and session_backup.py know exactly which file belongs to this
chat session.

Title is derived from the first user.message in the VS Code transcript JSONL
(VSCODE_TARGET_SESSION_LOG env var). Falls back to "Session N" if the transcript
is not yet available at hook fire time.

Hook JSON input shape (relevant fields):
    {
        "cwd": "<current working directory>"
    }
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR  = Path.home() / ".copilot" / "skills" / "session-backup"
STATE_FILE = SKILL_DIR / ".session-state.json"
SESSION_POINTER_DIR = Path("/tmp")

# Characters kept in the cleaned title — letters, digits, spaces only.
_ALLOWED = re.compile(r"[^a-zA-Z0-9 ]")
# Collapse multiple spaces
_SPACES  = re.compile(r" {2,}")
# Max words and characters for a derived title
_MAX_WORDS = 8
_MAX_CHARS = 60


def active_session_file(workspace: str) -> Path:
    """Per-workspace pointer — safe for concurrent VS Code windows."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", workspace)
    return SESSION_POINTER_DIR / f"copilot_session_{safe}.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def sanitise_workspace_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[/\\\x00]", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"-{2,}", "-", name)
    return name or "general"


def derive_workspace_from_cwd(cwd: str) -> str:
    for var in ("VSCODE_WORKSPACE_FOLDER", "VSCODE_CWD"):
        val = os.environ.get(var, "")
        if val:
            return Path(val).name
    if cwd:
        return Path(cwd).name
    return "general"


def derive_title_from_transcript(fallback: str) -> str:
    """
    Read VSCODE_TARGET_SESSION_LOG (path to the current session's .jsonl file)
    and extract the first user.message content. Clean it to a short, descriptive,
    special-character-free title.

    Rules:
    - Keep only letters, digits and spaces (strip everything else)
    - Collapse whitespace, strip leading/trailing
    - Truncate to _MAX_WORDS words, then to _MAX_CHARS characters
    - Title-case each word
    - Return fallback if transcript unavailable or has no user message yet
    """
    log_path = os.environ.get("VSCODE_TARGET_SESSION_LOG", "")
    if not log_path:
        return fallback

    transcript = Path(log_path)
    if not transcript.exists():
        return fallback

    try:
        for raw_line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                rec = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "user.message":
                continue
            content = rec.get("data", {}).get("content", "").strip()
            if not content:
                continue

            # Take only the first line (skip multi-line pastes / code dumps)
            first_line = content.splitlines()[0].strip()

            # Remove all non-alphanumeric characters except spaces
            clean = _ALLOWED.sub(" ", first_line)
            clean = _SPACES.sub(" ", clean).strip()

            if not clean:
                return fallback

            # Truncate to max words then max chars
            words = clean.split()[:_MAX_WORDS]
            title = " ".join(words)
            if len(title) > _MAX_CHARS:
                title = title[:_MAX_CHARS].rsplit(" ", 1)[0]

            # Title-case
            title = title.title()
            return title if title else fallback

    except OSError:
        pass

    return fallback


def get_next_session_num(session_dir: Path) -> int:
    """Scan the directory for existing session-N.md files and return next number."""
    existing = list(session_dir.glob("session-*.md"))
    nums = []
    for f in existing:
        parts = f.stem.split("-")
        if len(parts) == 2:
            try:
                nums.append(int(parts[1]))
            except ValueError:
                pass
    return max(nums) + 1 if nums else 1


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}

    cwd = payload.get("cwd", "")
    today = datetime.now().strftime("%Y-%m-%d")
    workspace = sanitise_workspace_name(derive_workspace_from_cwd(cwd))

    # Resolve vault path from config
    config_file = SKILL_DIR / "config.json"
    base_dir = Path("/Users/vaughn.angoy/Documents/Personal/AI Sessons")  # legacy fallback
    if config_file.exists():
        try:
            cfg          = json.loads(config_file.read_text(encoding="utf-8"))
            vp           = cfg.get("obsidianVaultPath", "")
            session_root = cfg.get("sessionRoot", "")
            ws_cfg       = cfg.get("workspaces", {}).get(workspace, {})
            folder       = ws_cfg.get("folder", workspace)
            if vp and session_root:
                workspace_dir = Path(vp) / session_root / folder
            elif vp:
                workspace_dir = Path(vp) / folder
            else:
                workspace_dir = base_dir / workspace
        except (json.JSONDecodeError, OSError):
            workspace_dir = base_dir / workspace
    else:
        workspace_dir = base_dir / workspace

    session_dir = workspace_dir / today
    session_dir.mkdir(parents=True, exist_ok=True)

    # Always increment — each new chat session gets its own file
    session_num = get_next_session_num(session_dir)
    session_file = session_dir / f"session-{session_num}.md"

    # Derive title from transcript; fall back to generic "Session N"
    generic_title = f"Session {session_num}"
    title = derive_title_from_transcript(generic_title)

    # Update the state tracker
    state = load_state()
    state[f"{workspace}:{today}"] = session_num
    save_state(state)

    # Write session file with Obsidian-compatible frontmatter
    with open(session_file, "w", encoding="utf-8") as f:
        f.write(
            f"---\n"
            f"title: {title}\n"
            f"workspace: {workspace}\n"
            f"date: {today}\n"
            f"session: {session_num}\n"
            f"tags: [ai-session, copilot]\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"**Workspace:** {workspace}  \n"
            f"**Date:** {today}  \n\n"
        )

    # Write per-workspace pointer — safe for concurrent VS Code windows
    pointer_data = {
        "session_file": str(session_file),
        "workspace":    workspace,
        "date":         today,
        "session_num":  session_num,
        "title":        title,
    }
    pointer_file = active_session_file(workspace)
    with open(pointer_file, "w", encoding="utf-8") as f:
        json.dump(pointer_data, f, indent=2)

    # Exit 0 — non-blocking
    sys.exit(0)


if __name__ == "__main__":
    main()


def active_session_file(workspace: str) -> Path:
    """Per-workspace pointer — safe for concurrent VS Code windows."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", workspace)
    return SESSION_POINTER_DIR / f"copilot_session_{safe}.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def sanitise_workspace_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[/\\\x00]", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"-{2,}", "-", name)
    return name or "general"


def derive_workspace_from_cwd(cwd: str) -> str:
    for var in ("VSCODE_WORKSPACE_FOLDER", "VSCODE_CWD"):
        val = os.environ.get(var, "")
        if val:
            return Path(val).name
    if cwd:
        return Path(cwd).name
    return "general"


def get_next_session_num(session_dir: Path) -> int:
    """Scan the directory for existing session-N.md files and return next number."""
    existing = list(session_dir.glob("session-*.md"))
    nums = []
    for f in existing:
        parts = f.stem.split("-")
        if len(parts) == 2:
            try:
                nums.append(int(parts[1]))
            except ValueError:
                pass
    return max(nums) + 1 if nums else 1


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}

    cwd = payload.get("cwd", "")
    today = datetime.now().strftime("%Y-%m-%d")
    workspace = sanitise_workspace_name(derive_workspace_from_cwd(cwd))

    # Resolve vault path from config
    config_file = SKILL_DIR / "config.json"
    base_dir = Path("/Users/vaughn.angoy/Documents/Personal/AI Sessons")  # legacy fallback
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            vp          = cfg.get("obsidianVaultPath", "")
            session_root = cfg.get("sessionRoot", "")
            ws_cfg      = cfg.get("workspaces", {}).get(workspace, {})
            folder      = ws_cfg.get("folder", workspace)
            if vp and session_root:
                workspace_dir = Path(vp) / session_root / folder
            elif vp:
                workspace_dir = Path(vp) / folder
            else:
                workspace_dir = base_dir / workspace
        except (json.JSONDecodeError, OSError):
            workspace_dir = base_dir / workspace
    else:
        workspace_dir = base_dir / workspace

    session_dir = workspace_dir / today
    session_dir.mkdir(parents=True, exist_ok=True)

    # Always increment — each new chat session gets its own file
    session_num = get_next_session_num(session_dir)
    session_file = session_dir / f"session-{session_num}.md"

    # Update the state tracker
    state = load_state()
    state[f"{workspace}:{today}"] = session_num
    save_state(state)

    # Write session file with Obsidian-compatible frontmatter
    with open(session_file, "w", encoding="utf-8") as f:
        f.write(
            f"---\n"
            f"title: Session {session_num}\n"
            f"workspace: {workspace}\n"
            f"date: {today}\n"
            f"tags: [ai-session, copilot]\n"
            f"---\n\n"
            f"# Session {session_num}\n\n"
            f"**Workspace:** {workspace}  \n"
            f"**Date:** {today}  \n\n"
        )

    # Write per-workspace pointer — safe for concurrent VS Code windows
    pointer_data = {
        "session_file": str(session_file),
        "workspace": workspace,
        "date": today,
        "session_num": session_num,
    }
    pointer_file = active_session_file(workspace)
    with open(pointer_file, "w", encoding="utf-8") as f:
        json.dump(pointer_data, f, indent=2)

    # Exit 0 — non-blocking
    sys.exit(0)


if __name__ == "__main__":
    main()
