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
        # Skip flat skill dirs. When hub == SKILLS_DIR, flat symlinks are
        # created at depth 1 for Claude Code discovery; they should not be
        # treated as namespace directories by find_skills.
        if (namespace_dir / "SKILL.md").exists():
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


def find_standalone_skills(watch_path: Path, exclude_names: set | None = None) -> list[dict]:
    """
    Find standalone skills in watch_path — entries with SKILL.md at root
    that are not part of a namespace collection. These are single-skill repos
    linked directly into SKILLS_HUB. exclude_names filters out flat symlinks
    already accounted for as namespace skills.
    """
    exclude_names = exclude_names or set()
    skills = []
    if not watch_path.exists():
        return skills
    for entry in sorted(watch_path.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if entry.name in exclude_names:
            continue
        if (entry / "SKILL.md").exists():
            skills.append(
                {
                    "namespace": "__standalone__",
                    "name": entry.name,
                    "source_path": str(entry.resolve()),
                }
            )
    return skills


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

    ns = skill["namespace"]
    instr_name = f"{ns}-{skill['name']}" if ns and ns != "__standalone__" else skill["name"]
    out = INSTRUCTIONS_DIR / f"{instr_name}.instructions.md"
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
        # If namespace dir is itself a symlink, migrate to a real directory so
        # Copilot CLI can discover individual skills inside it as plugin skills.
        if target_ns_dir.is_symlink():
            print(f"  [migrate] {namespace}/: namespace symlink → real directory")
            target_ns_dir.unlink()
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
    namespace_names = {s["name"] for s in discovered}
    standalone_skills = find_standalone_skills(watch_path, exclude_names=namespace_names)
    if not discovered and not standalone_skills:
        if not all_mode:
            print("No skills found in watch path.")
            return
        # In --all mode fall through so stale cleanup can remove old registry entries.

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

    # Process standalone skills (single-skill repos linked directly into SKILLS_HUB).
    # These have SKILL.md at root and are not part of any namespace collection.
    # (standalone_skills is computed at the top of sync_skills alongside discovered)
    for skill in standalone_skills:
        key = skill_key(skill["namespace"], skill["name"])
        if key in registry and not all_mode:
            already_linked.append(key)
            continue
        is_new = key not in registry
        registry[key] = skill["source_path"]
        write_instructions_file(skill)
        if is_new:
            added.append(key)
        else:
            already_linked.append(key)

    if all_mode:
        # Check for registered skills that no longer exist in watch path
        discovered_keys = {skill_key(s["namespace"], s["name"]) for s in discovered}
        standalone_keys = {skill_key(s["namespace"], s["name"]) for s in standalone_skills}
        stale = [k for k in list(registry.keys()) if k not in discovered_keys | standalone_keys]
        for key in stale:
            ns, name = key.split("/", 1)
            stale_source = Path(registry[key]).resolve()
            if ns != "__standalone__":
                target = SKILLS_DIR / ns / name
                if target.is_symlink():
                    target.unlink()
                # Remove the flat symlink at SKILLS_DIR root if it points to the same source.
                flat_link = SKILLS_DIR / name
                if flat_link.is_symlink() and flat_link.resolve() == stale_source:
                    flat_link.unlink()
            instr_name = name if ns == "__standalone__" else f"{ns}-{name}"
            stale_instructions = INSTRUCTIONS_DIR / f"{instr_name}.instructions.md"
            if stale_instructions.exists():
                stale_instructions.unlink()
            display_key = name if ns == "__standalone__" else key
            print(f"  [removed] {display_key}: source no longer exists")
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


# ── --link ─────────────────────────────────────────────────────────────


def derive_hub_name(target: Path) -> str:
    """
    Derive the SKILLS_HUB directory name from a target path.

    Uses <grandparent.name>-<parent.name> to mirror the GitHub
    username/repo-name convention, e.g.:
      ~/code/git-repos/vaughnangoy/ai-skills  →  vaughnangoy-ai-skills
      ~/code/git-repos/teng-lin/notebooklm-py →  teng-lin-notebooklm-py
    """
    t = target.resolve()
    return f"{t.parent.name}-{t.name}"


def _has_skills(path: Path) -> bool:
    """Return True if path contains at least one <skill>/SKILL.md."""
    for child in path.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            if (child / "SKILL.md").exists():
                return True
    return False


def link_to_hub(target_str: str, force: bool = False) -> bool:
    """
    Create a symlink in SKILLS_HUB pointing at target_str, then sync.

    Hub name is derived as <grandparent>-<target.name>.  Handles:
    - New link: create straightforwardly.
    - Existing symlink to same target: no-op.
    - Existing symlink to different target: update silently.
    - Existing real dir whose skill subdirs are all present in target:
      migrate silently (replace with symlink).
    - Existing real dir with content not in target: require --force.

    Special case: when SKILLS_HUB resolves to the same directory as
    SKILLS_DIR (e.g. ~/.claude/skills → ~/code/SKILLS_HUB), a
    namespace-level symlink can't be used (sync_skills would overwrite it
    with a real dir).  In that case, individual skill symlinks are created
    directly pointing at the repo, which is functionally equivalent.
    """
    config = load_config()
    hub = Path(config["watch_path"]).expanduser()
    target = Path(target_str).expanduser().resolve()

    if not target.exists():
        print(f"❌  Target does not exist: {target}", file=sys.stderr)
        return False

    if not _has_skills(target):
        print(
            f"❌  No skills found in target (expected subdirs containing SKILL.md): {target}",
            file=sys.stderr,
        )
        return False

    hub_name = derive_hub_name(target)
    link_path = hub / hub_name
    hub.mkdir(parents=True, exist_ok=True)

    # Detect the SKILLS_HUB == SKILLS_DIR case (e.g. ~/.claude/skills → SKILLS_HUB).
    hub_is_skills_dir = hub.resolve() == SKILLS_DIR.resolve()

    skill_dirs = [
        d for d in sorted(target.iterdir())
        if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").exists()
    ]

    if hub_is_skills_dir:
        # Hub and SKILLS_DIR are the same location. A namespace-level symlink
        # would be overwritten by symlink_skill's migration code. Instead, use
        # SKILLS_DIR/hub_name as a real directory with per-skill symlinks that
        # point directly to the repo (not through SKILLS_HUB).

        # If a namespace-level symlink already exists (e.g. from a manual setup
        # or an older version of this tool), remove it before creating the real
        # directory.  Without this, mkdir(exist_ok=True) silently follows the
        # symlink and subsequent skill-link creation hits the repo's own dirs,
        # causing every skill to be skipped as "already exists as non-symlink".
        if link_path.is_symlink():
            old_target = link_path.resolve()
            link_path.unlink()
            print(f"  [migrate] {hub_name}: removed namespace-level symlink → {old_target}")

        link_path.mkdir(parents=True, exist_ok=True)
        print(f"✓  {hub_name}: SKILLS_HUB == SKILLS_DIR, creating per-skill symlinks → {target}")

        registry = load_registry()
        target_skill_names = {d.name for d in skill_dirs}

        # ── Cleanup: remove stale skill entries no longer in target ──
        removed = []
        if link_path.exists():
            for existing in sorted(link_path.iterdir()):
                if existing.name.startswith("."):
                    continue
                if existing.name not in target_skill_names:
                    if existing.is_symlink():
                        stale_source = existing.resolve()
                        existing.unlink()
                        removed.append(existing.name)
                        print(f"  🗑  {hub_name}/{existing.name}: removed (no longer in repo)")
                        # Also remove the flat symlink at SKILLS_HUB root if it
                        # points to the same source as the namespace skill we just removed.
                        flat_link = hub / existing.name
                        if flat_link.is_symlink() and flat_link.resolve() == stale_source:
                            flat_link.unlink()
                    stale_instr = INSTRUCTIONS_DIR / f"{hub_name}-{existing.name}.instructions.md"
                    if stale_instr.exists():
                        stale_instr.unlink()
                    stale_key = skill_key(hub_name, existing.name)
                    if stale_key in registry:
                        del registry[stale_key]

        added = []
        updated = []
        unchanged = []

        for skill_dir in skill_dirs:
            skill_name = skill_dir.name
            skill_source = target / skill_name  # Direct link to the repo subdir
            skill_link = link_path / skill_name

            if skill_link.is_symlink():
                if skill_link.resolve() == skill_source.resolve():
                    unchanged.append(skill_name)
                else:
                    skill_link.unlink()
                    skill_link.symlink_to(skill_source)
                    updated.append(skill_name)
                    print(f"  ↺ {hub_name}/{skill_name}: updated symlink → {skill_source}")
            elif skill_link.exists():
                print(f"  · {hub_name}/{skill_name}: already exists as non-symlink, skipping")
                unchanged.append(skill_name)
                continue
            else:
                skill_link.symlink_to(skill_source)
                added.append(skill_name)

            # Create a flat symlink at SKILLS_HUB root for Claude Code skill
            # discovery. Claude Code only loads SKILL.md at depth 1:
            #   ~/.claude/skills/<skill>/SKILL.md
            # Without this, namespaced skills at depth 2 are invisible to it.
            flat_link = hub / skill_name
            if not flat_link.exists() and not flat_link.is_symlink():
                flat_link.symlink_to(skill_source)
            elif flat_link.is_symlink() and flat_link.resolve() != skill_source.resolve():
                # Another namespace already owns this skill name at the hub root.
                # First-linked namespace wins; later ones skip silently.
                pass
            # else: already a symlink to the correct source — no-op.

            skill = {
                "namespace": hub_name,
                "name": skill_name,
                "source_path": str(skill_source),
            }
            write_instructions_file(skill)
            registry[skill_key(hub_name, skill_name)] = str(skill_source)

        save_registry(registry)

    else:
        # Normal case: SKILLS_HUB is a separate directory from SKILLS_DIR.
        # Create a namespace-level symlink in SKILLS_HUB, then let sync_skills
        # create individual skill symlinks in SKILLS_DIR.
        added = updated = removed = unchanged = []  # tracked by sync_skills() output

        if link_path.is_symlink():
            existing_target = link_path.resolve()
            if existing_target == target:
                print(f"· {hub_name}: already linked → {target}")
            else:
                print(f"↺  {hub_name}: updating symlink {existing_target} → {target}")
                link_path.unlink()
                link_path.symlink_to(target)
        elif link_path.exists():
            # Real directory — check if content is a strict subset of target skill names
            hub_skill_names = {
                d.name for d in link_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            }
            target_skill_names = {d.name for d in skill_dirs}
            extra = hub_skill_names - target_skill_names
            if extra and not force:
                print(
                    f"❌  {hub_name}: real directory exists with skills not in target: "
                    f"{', '.join(sorted(extra))}\n"
                    f"    Use --force to replace it with a symlink.",
                    file=sys.stderr,
                )
                return False
            print(f"↺  {hub_name}: replacing real directory with symlink → {target}")
            import shutil
            shutil.rmtree(link_path)
            link_path.symlink_to(target)
        else:
            link_path.symlink_to(target)
            print(f"✓  {hub_name}: linked → {target}")

        # Sync all skills in the new namespace
        print(f"\nSyncing skills in {hub_name}...")
        sync_skills(all_mode=True)

    # ── Verify ────────────────────────────────────────────────────────
    print()
    ok = verify_link(hub_name, hub)

    # ── Binary check ──────────────────────────────────────────────────
    bin_path = Path.home() / ".local" / "bin" / "sync-skills"
    this_script = Path(__file__).resolve()
    bin_ok = (
        bin_path.is_symlink()
        and bin_path.resolve() == this_script
    )
    _check_binary()

    # ── Final summary ─────────────────────────────────────────────────
    total_skills = len(skill_dirs) if hub_is_skills_dir else len(
        [d for d in link_path.iterdir()
         if d.is_dir() and not d.name.startswith(".")]
        if link_path.exists() else []
    )
    print()
    print("─" * 54)
    print(f"  Namespace : {hub_name}")
    print(f"  Source    : {target}")
    if hub_is_skills_dir:
        print(f"  Skills    : {len(skill_dirs)} total  "
              f"| {len(added)} added  "
              f"| {len(updated)} updated  "
              f"| {len(removed)} removed")
    else:
        print(f"  Skills    : {total_skills} total (see sync output above)")
    print(f"  Chain     : {'✅ all checks passed' if ok else '❌ some checks failed — run: sync-skills --all'}")
    print(f"  Binary    : {'✅ installed at ' + str(bin_path) if bin_ok else '⚠  not installed — run: bash ' + str(Path(__file__).parent / 'setup' / 'install.sh')}")
    print("─" * 54)

    return ok


def verify_link(hub_name: str, hub: Path | None = None) -> bool:
    """
    Verify the full chain for every skill in a SKILLS_HUB namespace:
      Normal (hub ≠ SKILLS_DIR):
        1. SKILLS_HUB/<hub-name>  is a symlink to a live directory
        2. ~/.claude/skills/<hub-name>/<skill>  is a valid symlink
      Collapsed (hub == SKILLS_DIR):
        1. SKILLS_HUB/<hub-name>  exists as a directory
        2. SKILLS_HUB/<hub-name>/<skill>  is a symlink to the repo skill

      Both:
        3. ~/.copilot/instructions/<hub-name>-<skill>.instructions.md  exists
        4. Copilot CLI instructions dir is configured

    Prints a table and returns True if all checks pass.
    """
    if hub is None:
        config = load_config()
        hub = Path(config["watch_path"]).expanduser()

    link_path = hub / hub_name
    hub_is_skills_dir = hub.resolve() == SKILLS_DIR.resolve()

    # Check 1: hub entry exists
    if not link_path.exists():
        print(f"❌  SKILLS_HUB/{hub_name} does not exist — run sync-skills --link <path> first")
        return False

    if hub_is_skills_dir:
        # In collapsed mode the namespace IS a real directory in SKILLS_DIR.
        hub_ok = link_path.is_dir() and not link_path.is_symlink()
    else:
        hub_ok = link_path.is_symlink() and link_path.resolve().exists()

    # Collect skills in the namespace
    skills_in_ns = [
        d.name for d in link_path.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and (
            (d.is_symlink() and d.resolve().exists() and (d.resolve() / "SKILL.md").exists())
            or ((d / "SKILL.md").exists())
        )
    ]
    if not skills_in_ns:
        print(f"⚠  No skills found under SKILLS_HUB/{hub_name}")
        return False

    # Check 4: instructions dir configured
    env_ok = _check_instructions_env()

    all_pass = hub_ok and env_ok
    col_w = max(len(s) for s in skills_in_ns) + 2

    print(f"Verification: {hub_name}")
    hub_label = "real directory" if hub_is_skills_dir else "symlink"
    print(f"  SKILLS_HUB entry ({hub_label}): {'✅' if hub_ok else '❌'}")
    print(f"  Instructions env               : {'✅' if env_ok else '❌  COPILOT_CUSTOM_INSTRUCTIONS_DIRS not set'}")
    print()

    if hub_is_skills_dir:
        # In collapsed mode: check the individual skill symlinks in link_path
        print(f"  {'Skill':<{col_w}}  Skill symlink  Flat (Claude)  Copilot .md")
        print(f"  {'-' * col_w}  -------------  -------------  -----------")
        for skill_name in sorted(skills_in_ns):
            skill_link = link_path / skill_name
            skill_ok = skill_link.is_symlink() and skill_link.resolve().exists()
            # Flat symlink at SKILLS_HUB root enables Claude Code to discover the skill.
            flat_link = hub / skill_name
            flat_ok = flat_link.is_symlink() and flat_link.resolve().exists()
            instr_file = INSTRUCTIONS_DIR / f"{hub_name}-{skill_name}.instructions.md"
            instr_ok = instr_file.exists() and instr_file.stat().st_size > 0
            all_pass = all_pass and skill_ok and flat_ok and instr_ok
            print(
                f"  {skill_name:<{col_w}}  "
                f"{'✅' if skill_ok else '❌'}             "
                f"{'✅' if flat_ok else '❌'}             "
                f"{'✅' if instr_ok else '❌'}"
            )
    else:
        # Normal mode: check the per-skill symlinks in SKILLS_DIR
        print(f"  {'Skill':<{col_w}}  Claude symlink  Copilot .md")
        print(f"  {'-' * col_w}  --------------  -----------")
        for skill_name in sorted(skills_in_ns):
            claude_target = SKILLS_DIR / hub_name / skill_name
            claude_ok = claude_target.is_symlink() and claude_target.resolve().exists()
            instr_file = INSTRUCTIONS_DIR / f"{hub_name}-{skill_name}.instructions.md"
            instr_ok = instr_file.exists() and instr_file.stat().st_size > 0
            all_pass = all_pass and claude_ok and instr_ok
            print(
                f"  {skill_name:<{col_w}}  "
                f"{'✅' if claude_ok else '❌'}              "
                f"{'✅' if instr_ok else '❌'}"
            )

    print()
    if all_pass:
        print(f"✅  All checks passed for {hub_name}")
    else:
        print(f"❌  Some checks failed — run: sync-skills --all")

    return all_pass


def _check_instructions_env() -> bool:
    """Check whether COPILOT_CUSTOM_INSTRUCTIONS_DIRS is configured."""
    import os

    # Check current process env
    if os.environ.get("COPILOT_CUSTOM_INSTRUCTIONS_DIRS"):
        return True

    # Check VS Code settings as a fallback
    vscode_settings = _vscode_settings_path()
    if vscode_settings and vscode_settings.exists():
        try:
            import re as _re
            raw = vscode_settings.read_text()
            if "COPILOT_CUSTOM_INSTRUCTIONS_DIRS" in raw:
                return True
        except Exception:
            pass

    # Check shell profiles
    for profile in ("~/.zshrc", "~/.zprofile", "~/.bashrc", "~/.bash_profile"):
        p = Path(profile).expanduser()
        if p.exists() and "COPILOT_CUSTOM_INSTRUCTIONS_DIRS" in p.read_text():
            return True

    return False


def _vscode_settings_path() -> Path | None:
    import platform
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Code/User/settings.json"
    if system == "Linux":
        return Path.home() / ".config/Code/User/settings.json"
    return None


def _check_binary():
    """
    Check that ~/.local/bin/sync-skills exists and is a symlink to this script.
    Prints a warning with the install command if not.
    """
    bin_path = Path.home() / ".local" / "bin" / "sync-skills"
    this_script = Path(__file__).resolve()

    if not bin_path.exists() and not bin_path.is_symlink():
        print(
            f"⚠  sync-skills binary not installed at {bin_path}\n"
            f"   Run the installer to set it up:\n"
            f"   bash {this_script.parent}/setup/install.sh"
        )
        return

    if bin_path.is_symlink():
        target = bin_path.resolve()
        if target == this_script:
            print(f"✅  sync-skills binary: {bin_path} → {this_script}")
        else:
            print(
                f"⚠  sync-skills binary points to a different file:\n"
                f"   {bin_path} → {target}\n"
                f"   Expected: {this_script}\n"
                f"   Re-run installer to fix: bash {this_script.parent}/setup/install.sh"
            )
    else:
        print(
            f"⚠  {bin_path} exists but is not a symlink — it may be stale.\n"
            f"   Re-run installer to fix: bash {this_script.parent}/setup/install.sh"
        )


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
    parser.add_argument(
        "--link",
        metavar="PATH",
        help=(
            "Link a skill namespace from a git repo into SKILLS_HUB. "
            "PATH should be the repo root containing skill subdirectories. "
            "Hub name is derived as <parent>-<repo> (e.g. vaughnangoy-ai-skills)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --link: replace an existing real directory even if it has diverged content",
    )
    parser.add_argument(
        "--verify",
        metavar="HUB_NAME",
        help="Verify the full chain for a linked namespace (e.g. vaughnangoy-ai-skills)",
    )
    args = parser.parse_args()

    if args.init:
        init_config()
        return

    if args.link:
        ok = link_to_hub(args.link, force=args.force)
        sys.exit(0 if ok else 1)

    if args.verify:
        ok = verify_link(args.verify)
        sys.exit(0 if ok else 1)

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
