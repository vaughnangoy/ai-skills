#!/usr/bin/env python3
"""
sync-skills: Discovers skills in a watch path and symlinks them into
~/.claude/skills/ so they are available to both Claude Code and GitHub Copilot CLI.
Also writes .instructions.md files to ~/.copilot/instructions/ so skills are
registered in active Copilot sessions (VS Code chat, etc).

Skills must be directories containing a SKILL.md file, nested under a namespace:
  <watch_path>/<namespace>/<skill-name>/SKILL.md

Usage:
  sync-skills           # sync only new/untracked skills
  sync-skills --all     # re-validate all registered skills, repair broken symlinks
"""

import argparse
import json
import re
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "sync-skills"
CONFIG_FILE = CONFIG_DIR / "config.json"
REGISTRY_FILE = CONFIG_DIR / "registry.json"
SKILLS_DIR = Path.home() / ".claude" / "skills"
INSTRUCTIONS_DIR = Path.home() / ".copilot" / "instructions"

DEFAULT_CONFIG = {
    "watch_path": "~/code/SKILLS_HUB",
    "copilot_namespace": None,  # None means preserve source namespace
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        # Merge with defaults for any missing keys
        return {**DEFAULT_CONFIG, **cfg}
    return DEFAULT_CONFIG.copy()


def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {}


def save_registry(registry: dict):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def find_skills(watch_path: Path) -> list[dict]:
    """
    Scan watch_path for skill directories (dirs containing SKILL.md).
    Returns list of {namespace, name, source_path}.
    """
    skills = []
    if not watch_path.exists():
        print(f"[warn] Watch path does not exist: {watch_path}", file=sys.stderr)
        return skills

    for namespace_dir in sorted(watch_path.iterdir()):
        if not namespace_dir.is_dir() or namespace_dir.name.startswith("."):
            continue
        for skill_dir in sorted(namespace_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            if (skill_dir / "SKILL.md").exists():
                skills.append(
                    {
                        "namespace": namespace_dir.name,
                        "name": skill_dir.name,
                        "source_path": str(skill_dir),
                    }
                )
    return skills


def skill_key(namespace: str, name: str) -> str:
    return f"{namespace}/{name}"


def parse_skill_frontmatter(skill_md: Path) -> dict:
    """Extract YAML frontmatter fields from a SKILL.md."""
    content = skill_md.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    return fm


def skill_body(skill_md: Path) -> str:
    """Return SKILL.md content with frontmatter stripped."""
    content = skill_md.read_text()
    return re.sub(r"^---\n.*?\n---\n", "", content, count=1, flags=re.DOTALL).lstrip()


def write_instructions_file(skill: dict):
    """
    Write a .instructions.md to ~/.copilot/instructions/ so the skill
    is registered in active Copilot sessions (VS Code chat, Copilot CLI, etc).
    """
    INSTRUCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    skill_md = Path(skill["source_path"]) / "SKILL.md"
    if not skill_md.exists():
        return

    fm = parse_skill_frontmatter(skill_md)
    name = fm.get("name", skill["name"])
    description = fm.get("description", "")
    body = skill_body(skill_md)

    out = INSTRUCTIONS_DIR / f"{skill['namespace']}-{skill['name']}.instructions.md"
    content = f'---\napplyTo: "**"\n---\n# Skill: {name}\n\n'
    if description:
        content += f"> {description}\n\n"
    content += body
    out.write_text(content)


def symlink_skill(skill: dict, dry_run: bool = False) -> bool:
    """Create symlink for a skill. Returns True if successful."""
    source = Path(skill["source_path"])
    namespace = skill["namespace"]
    name = skill["name"]

    target_ns_dir = SKILLS_DIR / namespace
    target = target_ns_dir / name

    if not dry_run:
        target_ns_dir.mkdir(parents=True, exist_ok=True)

    if target.exists() and not target.is_symlink():
        print(f"  [skip] {namespace}/{name}: target exists and is not a symlink")
        # Still write instructions so the skill is registered in Copilot sessions
        write_instructions_file(skill)
        return False

    if target.is_symlink():
        if target.resolve() == source.resolve():
            return True  # already correct
        if not dry_run:
            target.unlink()

    if not dry_run:
        target.symlink_to(source)

    return True


def sync_skills(all_mode: bool = False):
    config = load_config()
    watch_path = Path(config["watch_path"]).expanduser()
    registry = load_registry()

    discovered = find_skills(watch_path)
    if not discovered:
        print("No skills found in watch path.")
        return

    added = []
    repaired = []
    already_linked = []
    skipped = []

    for skill in discovered:
        key = skill_key(skill["namespace"], skill["name"])
        target = SKILLS_DIR / skill["namespace"] / skill["name"]
        source = Path(skill["source_path"])

        if key in registry and not all_mode:
            # Already registered — skip unless --all
            already_linked.append(key)
            continue

        if target.is_symlink() and target.resolve() == source.resolve():
            # Symlink already correct — just update registry and instructions
            if key not in registry:
                registry[key] = skill["source_path"]
                write_instructions_file(skill)
                added.append(key)
            else:
                if all_mode:
                    write_instructions_file(skill)
                already_linked.append(key)
            continue

        # Broken symlink or missing — (re)create
        success = symlink_skill(skill)
        if success:
            registry[key] = skill["source_path"]
            write_instructions_file(skill)
            if all_mode and key in registry:
                repaired.append(key)
            else:
                added.append(key)
        else:
            skipped.append(key)

    if all_mode:
        # Check for registered skills that no longer exist in watch path
        discovered_keys = {skill_key(s["namespace"], s["name"]) for s in discovered}
        stale = [k for k in list(registry.keys()) if k not in discovered_keys]
        for key in stale:
            ns, name = key.split("/", 1)
            target = SKILLS_DIR / ns / name
            if target.is_symlink():
                target.unlink()
            stale_instructions = INSTRUCTIONS_DIR / f"{ns}-{name}.instructions.md"
            if stale_instructions.exists():
                stale_instructions.unlink()
            print(f"  [removed] {key}: source no longer exists")
            del registry[key]

    save_registry(registry)

    # Summary
    if added:
        print(f"✓ Linked {len(added)} new skill(s):")
        for k in added:
            print(f"    {k}")
    if repaired:
        print(f"↺ Repaired {len(repaired)} skill(s):")
        for k in repaired:
            print(f"    {k}")
    if already_linked and not all_mode:
        print(f"· {len(already_linked)} skill(s) already indexed (use --all to re-validate)")
    if skipped:
        print(f"⚠ Skipped {len(skipped)} skill(s):")
        for k in skipped:
            print(f"    {k}")
    if not added and not repaired:
        print("Everything up to date.")


def init_config():
    """Create default config if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {"watch_path": "~/code/SKILLS_HUB", "copilot_namespace": None},
                f,
                indent=2,
            )
        print(f"Created config: {CONFIG_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="Sync skills from a watch path to ~/.claude/skills/"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_mode",
        help="Re-validate all registered skills and repair broken symlinks",
    )
    parser.add_argument(
        "--watch-path",
        help="Override the watch path from config",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create default config file",
    )
    args = parser.parse_args()

    if args.init:
        init_config()
        return

    if args.watch_path:
        # Temporarily override config
        config = load_config()
        config["watch_path"] = args.watch_path
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Updated watch_path to: {args.watch_path}")

    sync_skills(all_mode=args.all_mode)


if __name__ == "__main__":
    main()
