#!/usr/bin/env python3
"""
config.py

Reads, writes, and validates the session-backup user configuration.

Config file: ~/.copilot/skills/session-backup/config.json

Schema:
    {
        "obsidianVaultPath":  "/absolute/path/to/obsidian/vault",
        "sessionRoot":        "Ai Session Backup",
        "sessionRootAsked":  true,
        "workspaces": {
            "nuk-licensing": {
                "folder":    "nuk-licensing",
                "editor":    "vscode",
                "setupDone": true
            },
            "Research": {
                "folder":    "Research",
                "editor":    "cli",
                "setupDone": true,
                "lastTitle": "Python async patterns"
            }
        }
    }

File output path:
    <obsidianVaultPath>/<sessionRoot>/<workspace-folder>/YYYY-MM-DD/session-N.md

Usage (called by the agent -- not interactive):
    python3 config.py --status  [--workspace NAME]
    python3 config.py --detect-editor
    python3 config.py --set-vault-path PATH
    python3 config.py --set-session-root FOLDER
    python3 config.py --set-workspace NAME --folder FOLDER --editor EDITOR
    python3 config.py --set-last-title --workspace NAME --title TITLE
"""

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_DIR   = Path.home() / ".copilot" / "skills" / "session-backup"
CONFIG_FILE = SKILL_DIR / "config.json"


def detect_editor() -> dict:
    is_vscode = bool(
        os.environ.get("VSCODE_PID")
        or os.environ.get("TERM_PROGRAM", "").lower() == "vscode"
        or os.environ.get("VSCODE_INJECTION")
        or os.environ.get("VSCODE_CWD")
    )
    vscode_workspace = None
    if is_vscode:
        cwd = os.environ.get("VSCODE_CWD") or os.getcwd()
        vscode_workspace = Path(cwd).name or None
    return {
        "editor": "vscode" if is_vscode else "cli",
        "vscode_workspace": vscode_workspace,
    }


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("workspaces", {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"workspaces": {}}


def save_config(cfg: dict) -> None:
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_workspace_config(cfg: dict, workspace: str) -> dict | None:
    return cfg.get("workspaces", {}).get(workspace)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage session-backup configuration")
    parser.add_argument("--status",          action="store_true")
    parser.add_argument("--detect-editor",   action="store_true")
    parser.add_argument("--set-vault-path",   metavar="PATH")
    parser.add_argument("--set-session-root", metavar="FOLDER",
                        help="Root subfolder inside vault for all session files")
    parser.add_argument("--set-workspace",    metavar="NAME")
    parser.add_argument("--folder",           metavar="FOLDER")
    parser.add_argument("--editor",           metavar="EDITOR")
    parser.add_argument("--set-last-title",   action="store_true")
    parser.add_argument("--workspace",        metavar="NAME")
    parser.add_argument("--title",            metavar="TITLE")
    args   = parser.parse_args()
    cfg    = load_config()

    if args.detect_editor:
        print(json.dumps(detect_editor(), indent=2))
        sys.exit(0)

    if args.set_vault_path:
        p = Path(args.set_vault_path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        cfg["obsidianVaultPath"] = str(p)
        save_config(cfg)
        print(json.dumps({"obsidianVaultPath": str(p), "created": True}, indent=2))
        sys.exit(0)

    if args.set_session_root:
        root_name = args.set_session_root.strip()
        vault_path = cfg.get("obsidianVaultPath", "")
        root_path = Path(vault_path) / root_name if vault_path else None
        if root_path:
            root_path.mkdir(parents=True, exist_ok=True)
        cfg["sessionRoot"] = root_name
        cfg["sessionRootAsked"] = True
        save_config(cfg)
        print(json.dumps({
            "sessionRoot": root_name,
            "path": str(root_path) if root_path else None,
            "created": True,
        }, indent=2))
        sys.exit(0)

    if args.set_workspace:
        if not args.folder or not args.editor:
            print("ERROR: --set-workspace requires --folder and --editor", file=sys.stderr)
            sys.exit(1)
        vault_path   = cfg.get("obsidianVaultPath", "")
        session_root = cfg.get("sessionRoot", "")
        if vault_path and session_root:
            folder_path = Path(vault_path) / session_root / args.folder
        elif vault_path:
            folder_path = Path(vault_path) / args.folder
        else:
            folder_path = Path(args.folder)
        folder_path.mkdir(parents=True, exist_ok=True)
        cfg["workspaces"][args.set_workspace] = {
            "folder":    args.folder,
            "editor":    args.editor,
            "setupDone": True,
        }
        save_config(cfg)
        print(json.dumps({
            "workspace": args.set_workspace,
            "folder":    args.folder,
            "path":      str(folder_path),
            "created":   True,
        }, indent=2))
        sys.exit(0)

    if args.set_last_title:
        if not args.workspace or not args.title:
            print("ERROR: --set-last-title requires --workspace and --title", file=sys.stderr)
            sys.exit(1)
        if args.workspace not in cfg["workspaces"]:
            print(f"ERROR: Workspace '{args.workspace}' not found", file=sys.stderr)
            sys.exit(1)
        cfg["workspaces"][args.workspace]["lastTitle"] = args.title
        save_config(cfg)
        print(json.dumps({"workspace": args.workspace, "lastTitle": args.title}, indent=2))
        sys.exit(0)

    # Default: --status
    vault_path         = cfg.get("obsidianVaultPath", "")
    vault_exists       = bool(vault_path and Path(vault_path).exists())
    session_root       = cfg.get("sessionRoot", "")
    session_root_asked = cfg.get("sessionRootAsked", False)
    workspace_name     = args.workspace
    workspace_cfg      = get_workspace_config(cfg, workspace_name) if workspace_name else None
    detected           = detect_editor()
    print(json.dumps({
        "vault_known":                 vault_exists,
        "obsidianVaultPath":           vault_path,
        "sessionRoot":                 session_root,
        "sessionRootAsked":            session_root_asked,
        "is_vscode":                   detected["editor"] == "vscode",
        "detected_editor":             detected["editor"],
        "detected_vscode_workspace":   detected["vscode_workspace"],
        "workspace_name":              workspace_name,
        "workspace_config":            workspace_cfg,
        "workspace_setup_done":        bool(workspace_cfg and workspace_cfg.get("setupDone")),
    }, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
