#!/usr/bin/env python3
"""
update_vscode_settings.py

Safely adds COPILOT_CUSTOM_INSTRUCTIONS_DIRS to VS Code User settings.
Handles JSONC (JSON with comments and trailing commas).

Usage:
  python3 update_vscode_settings.py <instructions_dir>
  python3 update_vscode_settings.py <instructions_dir> --check   # check only, no write
"""

import json
import platform
import re
import sys
from pathlib import Path


def vscode_settings_path() -> Path | None:
    system = platform.system()
    if system == "Darwin":
        p = Path.home() / "Library/Application Support/Code/User/settings.json"
    elif system == "Linux":
        p = Path.home() / ".config/Code/User/settings.json"
    elif system == "Windows":
        import os
        p = Path(os.environ.get("APPDATA", "")) / "Code/User/settings.json"
    else:
        return None
    return p if p.exists() else None


def strip_jsonc(text: str) -> str:
    """
    Strip // comments and trailing commas from JSONC, respecting string literals.
    Handles // inside quoted strings (e.g. URLs) correctly.
    """
    result = []
    i = 0
    in_string = False
    while i < len(text):
        c = text[i]
        if in_string:
            result.append(c)
            if c == '\\':
                # Escape sequence — include next char verbatim
                i += 1
                if i < len(text):
                    result.append(text[i])
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
                result.append(c)
            elif c == '/' and i + 1 < len(text) and text[i + 1] == '/':
                # Line comment — skip to end of line
                while i < len(text) and text[i] != '\n':
                    i += 1
                continue
            else:
                result.append(c)
        i += 1

    cleaned = ''.join(result)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
    return cleaned


def load_settings(path: Path) -> tuple[dict, str]:
    """Returns (parsed dict, raw text)."""
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(strip_jsonc(raw)), raw
    except json.JSONDecodeError as e:
        print(f"  ⚠  Could not parse VS Code settings: {e}", file=sys.stderr)
        sys.exit(2)


def write_settings(path: Path, settings: dict):
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


ENV_KEY_MAP = {
    "Darwin": "terminal.integrated.env.osx",
    "Linux":  "terminal.integrated.env.linux",
    "Windows": "terminal.integrated.env.windows",
}
ENV_VAR = "COPILOT_CUSTOM_INSTRUCTIONS_DIRS"


def main():
    if len(sys.argv) < 2:
        print("Usage: update_vscode_settings.py <instructions_dir> [--check]")
        sys.exit(1)

    instructions_dir = sys.argv[1]
    check_only = "--check" in sys.argv

    settings_path = vscode_settings_path()
    if not settings_path:
        print("vs_code_not_found")
        sys.exit(0)

    print(f"vs_code_found:{settings_path}")

    if check_only:
        sys.exit(0)

    settings, _ = load_settings(settings_path)
    env_key = ENV_KEY_MAP.get(platform.system())
    if not env_key:
        print("  ⚠  Unsupported OS for VS Code settings update", file=sys.stderr)
        sys.exit(1)

    # Merge — don't overwrite existing keys in the env block
    env_block = settings.get(env_key, {})
    if env_block.get(ENV_VAR) == instructions_dir:
        print("already_set")
        sys.exit(0)

    env_block[ENV_VAR] = instructions_dir
    settings[env_key] = env_block
    write_settings(settings_path, settings)
    print(f"updated:{settings_path}")


if __name__ == "__main__":
    main()
