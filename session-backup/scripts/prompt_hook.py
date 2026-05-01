#!/usr/bin/env python3
"""
prompt_hook.py

UserPromptSubmit hook — fires every time the user submits a prompt.

Reads /tmp/copilot_active_session.json (written by session_start_hook.py)
to find the current session's file, then appends the user's prompt as a
#### heading so the file always has every prompt captured automatically.

Hook JSON input shape (relevant fields):
    {
        "prompt": "<user message text>",
        "cwd":    "<current working directory>"
    }
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR  = Path.home() / ".copilot" / "skills" / "session-backup"
SESSION_POINTER_DIR = Path("/tmp")


def active_session_file(workspace: str) -> Path:
    """Per-workspace pointer — mirrors session_start_hook.py."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", workspace)
    return SESSION_POINTER_DIR / f"copilot_session_{safe}.json"


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


def load_active_session(workspace: str) -> dict | None:
    """Read the per-workspace session pointer written by session_start_hook.py."""
    pointer = active_session_file(workspace)
    if pointer.exists():
        try:
            with open(pointer, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def create_fallback_session(workspace: str, today: str) -> Path:
    """
    Fallback: if SessionStart hook did not fire, create session-1.md to
    avoid losing prompts.
    """
    config_file = SKILL_DIR / "config.json"
    base_dir = Path("/Users/vaughn.angoy/Documents/Personal/AI Sessons")
    if config_file.exists():
        try:
            cfg          = json.loads(config_file.read_text(encoding="utf-8"))
            vp           = cfg.get("obsidianVaultPath", "")
            session_root = cfg.get("sessionRoot", "")
            ws_cfg       = cfg.get("workspaces", {}).get(workspace, {})
            folder       = ws_cfg.get("folder", workspace)
            if vp and session_root:
                session_dir = Path(vp) / session_root / folder / today
            elif vp:
                session_dir = Path(vp) / folder / today
            else:
                session_dir = base_dir / workspace / today
        except (json.JSONDecodeError, OSError):
            session_dir = base_dir / workspace / today
    else:
        session_dir = base_dir / workspace / today

    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "session-1.md"

    if not session_file.exists():
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(
                f"---\ntitle: Session 1\nworkspace: {workspace}\ndate: {today}\n"
                f"tags: [ai-session, copilot]\n---\n\n"
                f"# Session 1\n\n**Workspace:** {workspace}  \n**Date:** {today}  \n\n"
            )
        pointer_file = active_session_file(workspace)
        with open(pointer_file, "w", encoding="utf-8") as pf:
            json.dump(
                {"session_file": str(session_file), "workspace": workspace,
                 "date": today, "session_num": 1},
                pf, indent=2,
            )
    return session_file


def truncate_for_heading(text: str, max_len: int = 100) -> str:
    first_line = text.strip().split("\n")[0]
    if len(first_line) > max_len:
        return first_line[:max_len].rstrip() + "…"
    return first_line


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}

    prompt_text = payload.get("prompt", "").strip()
    cwd = payload.get("cwd", "")

    if not prompt_text:
        sys.exit(0)

    today = datetime.now().strftime("%Y-%m-%d")

    # Primary: use the session file created by session_start_hook.py
    workspace = sanitise_workspace_name(derive_workspace_from_cwd(cwd))
    active = load_active_session(workspace)
    if active and active.get("session_file"):
        session_file = Path(active["session_file"])
    else:
        # Fallback: session_start hook may not be registered yet
        session_file = create_fallback_session(workspace, today)

    # Recreate if manually deleted
    if not session_file.exists():
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.touch()

    heading = truncate_for_heading(prompt_text)

    with open(session_file, "a", encoding="utf-8") as f:
        f.write(f"\n#### {heading}\n\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
