#!/usr/bin/env python3
"""
session_backup.py

Saves a formatted Copilot Chat session to a Markdown file organised for Obsidian.

Output structure:
    <obsidianVaultPath>/<folder>/YYYY-MM-DD/session-N.md

Usage:
    python3 session_backup.py --input-file <path>
                              --workspace   <name>   (VS Code: project name)
                              --category    <name>   (non-VS Code: user-supplied title)
                              --date        <flexible-date>
                              --stats                (dry-run, print JSON)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SKILL_DIR       = Path.home() / ".copilot" / "skills" / "session-backup"
CONFIG_FILE     = SKILL_DIR / "config.json"
STATE_FILE      = SKILL_DIR / ".session-state.json"
LEGACY_BASE_DIR = Path("/Users/vaughn.angoy/Documents/Personal/AI Sessons")


def active_session_file(workspace: str) -> Path:
    """Per-workspace pointer — mirrors session_start_hook.py."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", workspace)
    return Path("/tmp") / f"copilot_session_{safe}.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def get_base_dir(cfg: dict) -> Path:
    """
    Returns the root directory under which all per-workspace session folders sit.
    Path: <vault>/<sessionRoot>  — falls back to legacy path if not configured.
    """
    vault = cfg.get("obsidianVaultPath", "")
    root  = cfg.get("sessionRoot", "")
    if vault and root:
        return Path(vault) / root
    if vault:
        return Path(vault)
    return LEGACY_BASE_DIR


def get_folder_for_workspace(cfg: dict, workspace: str) -> str:
    """Return the configured folder name for a workspace, or the workspace name itself."""
    ws = cfg.get("workspaces", {}).get(workspace, {})
    return ws.get("folder", workspace)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_active_session(workspace: str | None = None) -> dict | None:
    """Read the per-workspace session pointer. Falls back to legacy global pointer."""
    if workspace:
        pointer = active_session_file(workspace)
        if pointer.exists():
            try:
                with open(pointer, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
    # Legacy fallback for old pointer files
    legacy = Path("/tmp/copilot_active_session.json")
    if legacy.exists():
        try:
            with open(legacy, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def sanitise_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[/\\\x00]", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"-{2,}", "-", name)
    return name or "general"


def get_next_session_num(session_dir: Path) -> int:
    nums = []
    for f in session_dir.glob("session-*.md"):
        parts = f.stem.split("-")
        if len(parts) == 2:
            try:
                nums.append(int(parts[1]))
            except ValueError:
                pass
    return max(nums) + 1 if nums else 1


def count_prompts_in_text(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("#### "))


def parse_flexible_date(date_str: str) -> str:
    """
    Parse a flexible user-supplied date string into YYYY-MM-DD.
    Formats (day-first): D  |  D/M  |  D/M/YY  |  D/M/YYYY  (/ or - separator)
    """
    from datetime import date as date_type

    today = date_type.today()
    s = date_str.strip()

    if re.fullmatch(r"\d{1,2}", s):
        return date_type(today.year, today.month, int(s)).strftime("%Y-%m-%d")

    sep = "/" if "/" in s else "-"
    parts = s.split(sep)

    try:
        if len(parts) == 2:
            day, month = int(parts[0]), int(parts[1])
            return date_type(today.year, month, day).strftime("%Y-%m-%d")
        if len(parts) == 3:
            day, month, yr = int(parts[0]), int(parts[1]), int(parts[2])
            if yr < 100:
                yr += 2000 if yr < 30 else 1900
            return date_type(yr, month, day).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass

    raise ValueError(
        f"Cannot parse date: '{date_str}'. Use D, D/M, D/M/YY or D/M/YYYY (day-first)."
    )


# ── Title-cleaning helpers (module-level so both save flow and --sync-titles can use them) ──────
_uuid_re    = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_generic_re = re.compile(r'^"?Session\s+\d+"?$', re.IGNORECASE)
_allowed_re = re.compile(r"[^a-zA-Z0-9 ]")
_spaces_re  = re.compile(r" {2,}")
_url_re     = re.compile(r"https?://\S+")                # full URLs
_path_re    = re.compile(r"\S*[/\\]\S+")                 # slash-separated tokens (org/repo, /file/path)
# Words that make poor title endings — trim from the right when truncating
_weak_tail  = {"a", "an", "the", "is", "are", "was", "be", "been",
               "to", "of", "in", "on", "at", "by", "for",
               "and", "or", "but", "this", "that", "do", "does"}


def clean_to_title(raw: str) -> str | None:
    """Derive a readable title: strip technical noise, keep first 8 natural-language words,
    trim trailing weak words, title-case. Returns None if no usable text found."""
    first_line = raw.strip().splitlines()[0].strip()
    if _uuid_re.match(first_line):
        return None
    # Remove technical noise before splitting into words
    text = _url_re.sub(" ", first_line)   # strip URLs
    text = _path_re.sub(" ", text)         # strip path/repo tokens (github/Org/repo, etc.)
    # Replace all remaining non-alphanumeric chars with spaces (hyphens, underscores, punctuation)
    text = _allowed_re.sub(" ", text)
    text = _spaces_re.sub(" ", text).strip()
    if not text:
        return None
    words = text.split()[:8]
    # Trim trailing weak words so the title ends on something meaningful
    while words and words[-1].lower() in _weak_tail:
        words.pop()
    if not words:
        return None
    title = " ".join(words)
    if len(title) > 60:
        title = title[:60].rsplit(" ", 1)[0]
    return title.title() or None


def sanitise_filename(title: str) -> str:
    """
    Convert a session title into a safe filename (no extension).
    Replaces characters illegal on macOS/Windows with spaces, collapses whitespace.
    """
    title = title.strip()
    # Replace characters illegal in filenames with a space (preserves word boundaries)
    title = re.sub(r'[\x00-\x1f/\\:*?"<>|]', " ", title)
    # Collapse multiple spaces
    title = re.sub(r" {2,}", " ", title).strip()
    return title or "session"


def update_frontmatter_title(text: str, new_title: str) -> str:
    """Replace the title: line in YAML frontmatter."""
    return re.sub(
        r"(?m)^(title:\s*).*$",
        f'title: "{new_title}"',
        text,
        count=1,
    )


def build_frontmatter(session_num: int, workspace: str, date_str: str,
                      session_title: str | None = None) -> str:
    title_line = f'title: "{session_title}"' if session_title else f"title: Session {session_num}"
    return (
        f"---\n"
        f"{title_line}\n"
        f"workspace: {workspace}\n"
        f"date: {date_str}\n"
        f"session: {session_num}\n"
        f"tags: [ai-session, copilot]\n"
        f"---\n\n"
    )


def build_header(session_num: int, workspace: str, date_str: str,
                 session_title: str | None = None) -> str:
    heading = session_title if session_title else f"Session {session_num}"
    return (
        f"# {heading}\n\n"
        f"**Workspace:** {workspace}  \n"
        f"**Date:** {date_str}  \n\n"
        f"---\n\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save a Copilot Chat session to Markdown for Obsidian"
    )
    parser.add_argument("--input-file", default=None,
                        help="Path to the formatted Markdown session content (required for save)")
    parser.add_argument("--workspace", default=None,
                        help="Workspace name (VS Code: project name; auto-detected)")
    parser.add_argument("--category", default=None,
                        help="Category/title (non-VS Code users — asked each session)")
    parser.add_argument("--session-title", default=None,
                        help="Human title for this session (used in frontmatter and H1)")
    parser.add_argument("--date", default=None,
                        help="Session date override (flexible formats: D, D/M, D/M/YY, D/M/YYYY)")
    parser.add_argument("--stats", action="store_true",
                        help="Dry-run: print JSON stats without writing")
    parser.add_argument("--sync-title", action="store_true",
                        help="Rename the active session file to match --session-title and update frontmatter")
    parser.add_argument("--sync-titles-workspace", action="store_true",
                        help="Rename ALL session files in the workspace using their frontmatter titles")
    args = parser.parse_args()

    # Normalise date
    if args.date:
        try:
            args.date = parse_flexible_date(args.date)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    # --sync-title: rename the active session file to match --session-title
    if args.sync_title:
        if not args.session_title:
            print("ERROR: --sync-title requires --session-title", file=sys.stderr)
            sys.exit(1)

        cfg    = load_config()
        active = load_active_session(args.category or args.workspace)

        if active and active.get("session_file"):
            old_file = Path(active["session_file"])
        else:
            print("ERROR: No active session pointer found. Cannot sync title.", file=sys.stderr)
            sys.exit(1)

        if not old_file.exists():
            print(f"ERROR: Session file not found: {old_file}", file=sys.stderr)
            sys.exit(1)

        safe_name = sanitise_filename(args.session_title)
        new_file  = old_file.parent / f"{safe_name}.md"

        if old_file == new_file:
            print(json.dumps({"status": "no_change", "session_file": str(old_file)}))
            sys.exit(0)

        if new_file.exists():
            print(f"ERROR: Target file already exists: {new_file}", file=sys.stderr)
            sys.exit(1)

        # Update frontmatter title and H1 heading inside the file before renaming
        original = old_file.read_text(encoding="utf-8")
        updated  = update_frontmatter_title(original, args.session_title)
        updated  = re.sub(r"(?m)^# Session \d+\s*$", f"# {args.session_title}", updated, count=1)
        old_file.write_text(updated, encoding="utf-8")
        old_file.rename(new_file)

        # Update active session pointer
        workspace = active.get("workspace", "")
        pointer   = active_session_file(workspace)
        active["session_file"] = str(new_file)
        pointer.write_text(json.dumps(active, indent=2), encoding="utf-8")

        print(json.dumps({
            "status":   "renamed",
            "old_file": str(old_file),
            "new_file": str(new_file),
            "title":    args.session_title,
        }))
        sys.exit(0)

    # --sync-titles-workspace: rename ALL session files in the workspace using their frontmatter titles
    if args.sync_titles_workspace:
        if not args.workspace and not args.category:
            print("ERROR: --sync-titles-workspace requires --workspace or --category", file=sys.stderr)
            sys.exit(1)

        cfg           = load_config()
        workspace     = sanitise_name(args.category or args.workspace)
        folder        = sanitise_name(get_folder_for_workspace(cfg, workspace))
        base_dir      = get_base_dir(cfg)
        workspace_dir = base_dir / folder

        if not workspace_dir.exists():
            print(f"ERROR: Workspace directory not found: {workspace_dir}", file=sys.stderr)
            sys.exit(1)

        results = []
        # Walk all date subdirectories
        for date_dir in sorted(workspace_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            for md_file in sorted(date_dir.glob("*.md")):
                text = md_file.read_text(encoding="utf-8")

                # Extract frontmatter title
                fm_match = re.search(r"(?m)^title:\s*[\"']?(.+?)[\"']?\s*$", text)
                fm_title = fm_match.group(1).strip() if fm_match else None

                # Decide on the title to use:
                # 1. Non-generic frontmatter title  → use it directly
                # 2. Generic / missing → fall back to first #### heading in body
                if fm_title and not _generic_re.match(fm_title):
                    title = fm_title
                else:
                    # Find first #### heading
                    h_match = re.search(r"(?m)^#### (.+)$", text)
                    if not h_match:
                        results.append({"file": str(md_file), "status": "skipped", "reason": "no prompts captured yet"})
                        continue
                    title = clean_to_title(h_match.group(1))
                    if not title:
                        results.append({"file": str(md_file), "status": "skipped", "reason": "first heading is a UUID or unusable"})
                        continue

                safe_name = sanitise_filename(title)
                new_file  = md_file.parent / f"{safe_name}.md"

                if md_file == new_file:
                    results.append({"file": str(md_file), "status": "no_change"})
                    continue
                if new_file.exists():
                    results.append({"file": str(md_file), "status": "skipped", "reason": f"target exists: {new_file.name}"})
                    continue

                # Update frontmatter title and H1 inside the file before renaming
                updated = update_frontmatter_title(text, title)
                updated = re.sub(r"(?m)^# Session \d+\s*$", f"# {title}", updated, count=1)
                md_file.write_text(updated, encoding="utf-8")
                md_file.rename(new_file)

                # Update active pointer if it pointed at the old file
                pointer = active_session_file(workspace)
                if pointer.exists():
                    try:
                        ptr_data = json.loads(pointer.read_text(encoding="utf-8"))
                        if ptr_data.get("session_file") == str(md_file):
                            ptr_data["session_file"] = str(new_file)
                            pointer.write_text(json.dumps(ptr_data, indent=2), encoding="utf-8")
                    except (json.JSONDecodeError, OSError):
                        pass

                results.append({"old_file": str(md_file), "new_file": str(new_file), "title": title, "status": "renamed"})

        renamed    = sum(1 for r in results if r["status"] == "renamed")
        skipped    = sum(1 for r in results if r["status"] == "skipped")
        no_change  = len(results) - renamed - skipped
        print(json.dumps({"renamed": renamed, "skipped": skipped, "no_change": no_change, "files": results}, indent=2))
        sys.exit(0)

    # Require --input-file for all other modes
    if not args.input_file:
        print("ERROR: --input-file is required (except with --sync-title or --sync-titles-workspace)", file=sys.stderr)
        sys.exit(1)

    # Read input
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    content = input_path.read_text(encoding="utf-8").strip()
    if not content:
        print("ERROR: Input file is empty.", file=sys.stderr)
        sys.exit(1)

    new_prompt_count = count_prompts_in_text(content)

    # Load config — drives vault path and folder lookup
    cfg = load_config()
    BASE_DIR = get_base_dir(cfg)
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve folder name:
    # --category (non-VS Code) > --workspace lookup in config > --workspace raw > active pointer
    effective_workspace = args.category or args.workspace
    active = load_active_session(effective_workspace)

    if effective_workspace:
        workspace = sanitise_name(effective_workspace)
        # If workspace has a registered folder in config, use that as the subdir
        folder = sanitise_name(get_folder_for_workspace(cfg, workspace))
        today = args.date or datetime.now().strftime("%Y-%m-%d")
        session_dir = BASE_DIR / folder / today
        session_dir.mkdir(parents=True, exist_ok=True)

        # Use the active session pointer if it points to this exact directory
        # (i.e. the user is still in the same VS Code session that started it).
        # Any other situation — no pointer, stale date, explicit --date override
        # — means this is a new/different session: scan the dir and find the
        # next unused session-N.md number.
        if (
            not args.date
            and active
            and active.get("session_file")
            and Path(active["session_file"]).parent == session_dir
        ):
            session_file = Path(active["session_file"])
            session_num = active.get("session_num", 1)
        else:
            session_num = get_next_session_num(session_dir)
            session_file = session_dir / f"session-{session_num}.md"

        state = load_state()
        state[f"{folder}:{today}"] = session_num
        save_state(state)

    elif active and active.get("session_file") and not args.date:
        session_file = Path(active["session_file"])
        workspace    = active["workspace"]
        today        = active["date"]
        session_num  = active["session_num"]
        folder       = Path(session_file).parent.parent.name

    elif active and active.get("workspace"):
        workspace = active["workspace"]
        folder    = sanitise_name(get_folder_for_workspace(cfg, workspace))
        today     = args.date or datetime.now().strftime("%Y-%m-%d")
        session_dir = BASE_DIR / folder / today
        session_dir.mkdir(parents=True, exist_ok=True)

        if (
            not args.date
            and Path(active.get("session_file", "")).parent == session_dir
        ):
            session_file = Path(active["session_file"])
            session_num = active.get("session_num", 1)
        else:
            session_num = get_next_session_num(session_dir)
            session_file = session_dir / f"session-{session_num}.md"

        state = load_state()
        state[f"{folder}:{today}"] = session_num
        save_state(state)

    else:
        print(
            "ERROR: No workspace/category provided and no active session pointer found.\n"
            "Pass --workspace or --category, or ensure the SessionStart hook is registered.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Resolve final filename before any file I/O ──────────────────────────────
    # Derive title now so the file is written directly to its final name,
    # avoiding the write-then-rename two-step entirely.
    _generic_file_re = re.compile(r"^session-\d+\.md$")
    auto_title = args.session_title
    if not auto_title:
        for h_match in re.finditer(r"(?m)^#### (.+)$", content):
            candidate = clean_to_title(h_match.group(1))
            if candidate:
                auto_title = candidate
                break

    # Remap only when the resolved path is still a generic session-N.md name
    if auto_title and _generic_file_re.match(session_file.name):
        safe_name = sanitise_filename(auto_title)
        titled_file = session_file.parent / f"{safe_name}.md"
        # Only remap if target doesn't already exist as a *different* session
        if titled_file == session_file or not titled_file.exists():
            session_file = titled_file

    # Existing file stats
    existing_count = 0
    session_exists = session_file.exists()
    if session_exists:
        existing_count = count_prompts_in_text(session_file.read_text(encoding="utf-8"))

    if args.stats:
        print(json.dumps({
            "session_file":          str(session_file),
            "session_num":           session_num,
            "workspace":             workspace,
            "date":                  today,
            "session_exists":        session_exists,
            "existing_prompt_count": existing_count,
            "new_prompt_count":      new_prompt_count,
            "prompts_to_add":        max(0, new_prompt_count - existing_count),
        }, indent=2))
        sys.exit(0)

    # Write directly to the final path (title already resolved above)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = build_frontmatter(session_num, workspace, today, auto_title)
    header      = build_header(session_num, workspace, today, auto_title)
    session_file.write_text(frontmatter + header + content, encoding="utf-8")

    # Keep active session pointer in sync with final path
    pointer = active_session_file(workspace)
    if pointer.exists():
        try:
            ptr_data = json.loads(pointer.read_text(encoding="utf-8"))
            ptr_data["session_file"] = str(session_file)
            if auto_title:
                ptr_data["title"] = auto_title
            pointer.write_text(json.dumps(ptr_data, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    print(json.dumps({
        "session_file":   str(session_file),
        "session_num":    session_num,
        "title":          auto_title,
        "total_prompts":  new_prompt_count,
        "prompts_added":  max(0, new_prompt_count - existing_count),
    }))


if __name__ == "__main__":
    main()
