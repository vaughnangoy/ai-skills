#!/usr/bin/env python3
"""
audit_skills.py — Gap analysis for vaughnangoy/ai-skills installation.

Checks every skill in this repo against the full installation chain and
outputs a gap-analysis table plus a prioritised mitigation plan.

Checks performed per skill:
  1. SKILL.md  — exists, valid frontmatter (name + description fields)
  2. Registry  — sync-skills registry.json has an entry for this skill
  3. Claude    — ~/.claude/skills/<ns>/<skill> symlink is valid (Claude Code)
  4. Copilot   — ~/.copilot/instructions/<ns>-<skill>.instructions.md exists
                 and is non-empty (Copilot Chat / GitHub Copilot CLI)
  5. Copilot content — instructions file contains the skill body

Global checks:
  A. Namespace mount type — whether namespace is a per-skill-symlink dir
     (correct) or a single namespace-level symlink (problematic when
     SKILLS_HUB == SKILLS_DIR, because repo internals pollute the namespace)
  B. sync-skills binary — ~/.local/bin/sync-skills installed correctly
  C. VS Code Copilot dirs — customInstructionsDirs or
     COPILOT_CUSTOM_INSTRUCTIONS_DIRS includes ~/.copilot/instructions
  D. Stale registry entries — registry references skills no longer in repo
  E. Orphaned instructions — .instructions.md files with no matching skill

Usage:
  python3 audit_skills.py
  python3 audit_skills.py --fix   # print fix commands only (no table)
  python3 audit_skills.py --json  # machine-readable output
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = Path.home() / ".config" / "sync-skills"
REGISTRY_FILE = CONFIG_DIR / "registry.json"
SKILLS_DIR = Path.home() / ".claude" / "skills"
INSTRUCTIONS_DIR = Path.home() / ".copilot" / "instructions"
VSCODE_SETTINGS = (
    Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
)
SYNC_BIN = Path.home() / ".local" / "bin" / "sync-skills"
SYNC_SCRIPT = REPO_ROOT / "sync-skills" / "sync_skills.py"

# ── Colours ───────────────────────────────────────────────────────────────────

USE_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOUR else text


def green(t):  return _c("32", t)
def red(t):    return _c("31", t)
def yellow(t): return _c("33", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)


# ── Helpers ───────────────────────────────────────────────────────────────────

def derive_namespace(repo: Path) -> str:
    """Derive <grandparent>-<reponame> from repo path."""
    return f"{repo.parent.name}-{repo.name}"


def load_config() -> dict:
    cfg_file = CONFIG_DIR / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text())
    return {"watch_path": "~/code/SKILLS_HUB"}


def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {}


def parse_frontmatter(skill_md: Path) -> dict:
    content = skill_md.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    return fm


def skill_body(skill_md: Path) -> str:
    content = skill_md.read_text()
    return re.sub(r"^---\n.*?\n---\n", "", content, count=1, flags=re.DOTALL).lstrip()


def find_skills_in_repo(repo: Path) -> list[dict]:
    """Return list of {name, path, skill_md} for every skill dir in repo."""
    skills = []
    for d in sorted(repo.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name.startswith("_"):
            continue
        skill_md = d / "SKILL.md"
        if skill_md.exists():
            skills.append({"name": d.name, "path": d, "skill_md": skill_md})
    return skills


def hub_is_skills_dir(config: dict) -> bool:
    watch = Path(config.get("watch_path", "~/code/SKILLS_HUB")).expanduser()
    if not watch.exists():
        return False
    return watch.resolve() == SKILLS_DIR.resolve()


# ── Per-skill checks ──────────────────────────────────────────────────────────

PASS = "pass"
FAIL = "fail"
WARN = "warn"


def check_skill_md(skill: dict) -> tuple[str, str]:
    """Check SKILL.md exists and has name + description in frontmatter."""
    sm = skill["skill_md"]
    if not sm.exists():
        return FAIL, "SKILL.md missing"
    fm = parse_frontmatter(sm)
    missing = [f for f in ("name", "description") if not fm.get(f)]
    if missing:
        return FAIL, f"frontmatter missing: {', '.join(missing)}"
    desc = fm.get("description", "")
    if len(desc) > 1024:
        return WARN, f"description too long ({len(desc)} chars, max 1024)"
    return PASS, fm.get("name", skill["name"])


def check_registry(skill: dict, namespace: str, registry: dict) -> tuple[str, str]:
    """Check registry.json has a valid entry for this skill."""
    key = f"{namespace}/{skill['name']}"
    if key not in registry:
        return FAIL, "not in registry"
    registered_path = Path(registry[key])
    if not registered_path.exists():
        return FAIL, f"registry path does not exist: {registry[key]}"
    if registered_path.resolve() != skill["path"].resolve():
        return WARN, f"registry path mismatch: {registry[key]}"
    return PASS, "registered"


def check_claude_symlink(
    skill: dict, namespace: str, ns_is_symlink: bool
) -> tuple[str, str]:
    """Check ~/.claude/skills/<namespace>/<skill> symlink."""
    skill_link = SKILLS_DIR / namespace / skill["name"]

    if ns_is_symlink:
        # Namespace itself is a symlink to repo root — individual skills are
        # accessible but repo internals are polluting the namespace.
        ns_link = SKILLS_DIR / namespace
        if (ns_link / skill["name"] / "SKILL.md").exists():
            return WARN, "accessible but via namespace-level symlink (noisy)"
        return FAIL, "namespace symlink exists but skill not reachable"

    if not skill_link.exists():
        if skill_link.is_symlink():
            return FAIL, "broken symlink (target missing)"
        return FAIL, "symlink missing"
    if not skill_link.is_symlink():
        return WARN, "exists as real directory (not a symlink)"
    if skill_link.resolve() != skill["path"].resolve():
        return FAIL, f"symlink points to wrong target: {skill_link.resolve()}"
    return PASS, str(skill_link)


def check_instructions_file(skill: dict, namespace: str) -> tuple[str, str]:
    """Check ~/.copilot/instructions/<ns>-<skill>.instructions.md."""
    instr = INSTRUCTIONS_DIR / f"{namespace}-{skill['name']}.instructions.md"
    if not instr.exists():
        return FAIL, ".instructions.md missing"
    content = instr.read_text()
    if not content.strip():
        return FAIL, ".instructions.md is empty"
    if 'applyTo: "**"' not in content:
        return WARN, 'missing applyTo: "**" frontmatter'
    return PASS, str(instr)


def check_instructions_content(skill: dict, namespace: str) -> tuple[str, str]:
    """Check instructions file contains meaningful skill body."""
    instr = INSTRUCTIONS_DIR / f"{namespace}-{skill['name']}.instructions.md"
    if not instr.exists():
        return FAIL, "file absent"
    body = skill_body(skill["skill_md"])
    content = instr.read_text()
    # Heuristic: first 100 chars of skill body should appear in instructions
    snippet = body[:100].strip()
    if snippet and snippet not in content:
        return WARN, "instructions content may be stale (skill body not found)"
    return PASS, "content present"


# ── Global checks ─────────────────────────────────────────────────────────────

def check_namespace_mount(namespace: str, config: dict) -> tuple[str, str]:
    """
    Check whether the namespace is mounted correctly.
    When SKILLS_HUB == SKILLS_DIR the namespace must be a real directory
    with per-skill symlinks, NOT a namespace-level symlink to the repo root.
    """
    ns_path = SKILLS_DIR / namespace
    hub_same = hub_is_skills_dir(config)

    if not ns_path.exists():
        return FAIL, f"~/.claude/skills/{namespace}/ does not exist"

    if ns_path.is_symlink():
        if hub_same:
            return FAIL, (
                f"~/.claude/skills/{namespace} is a namespace-level symlink "
                f"(SKILLS_HUB==SKILLS_DIR: must be a real dir with per-skill symlinks)"
            )
        # Hub ≠ SKILLS_DIR: namespace symlink is the normal mode
        target = ns_path.resolve()
        if target.exists():
            return PASS, f"namespace symlink → {target}"
        return FAIL, f"namespace symlink is broken → {ns_path.readlink()}"

    # Real directory: check it contains at least one skill symlink
    skill_links = [
        d for d in ns_path.iterdir()
        if d.is_symlink() and (d / "SKILL.md").exists()
    ]
    if not skill_links:
        return WARN, f"~/.claude/skills/{namespace}/ is a real dir but has no skill symlinks"
    return PASS, f"real dir with {len(skill_links)} skill symlink(s)"


def check_binary() -> tuple[str, str]:
    """Check ~/.local/bin/sync-skills binary."""
    if not SYNC_BIN.exists():
        return FAIL, f"{SYNC_BIN} not found"
    if not SYNC_BIN.is_symlink():
        return WARN, f"{SYNC_BIN} is not a symlink (may be stale)"
    if not SYNC_SCRIPT.exists():
        return WARN, f"sync_skills.py not found at {SYNC_SCRIPT}"
    if SYNC_BIN.resolve() != SYNC_SCRIPT.resolve():
        return FAIL, (
            f"binary points to {SYNC_BIN.resolve()}, "
            f"not {SYNC_SCRIPT}"
        )
    return PASS, str(SYNC_BIN)


def check_copilot_dirs() -> tuple[str, str]:
    """
    Check that ~/.copilot/instructions is registered as a custom instructions
    directory — either in VS Code settings or via environment variable.
    """
    # Check environment variable
    env_val = os.environ.get("COPILOT_CUSTOM_INSTRUCTIONS_DIRS", "")
    instructions_str = str(INSTRUCTIONS_DIR)
    if instructions_str in env_val:
        return PASS, f"COPILOT_CUSTOM_INSTRUCTIONS_DIRS={env_val}"

    # Check VS Code settings.json
    if VSCODE_SETTINGS.exists():
        try:
            settings = json.loads(VSCODE_SETTINGS.read_text())
            for key in (
                "github.copilot.chat.customInstructionsDirs",
                "chat.promptFilesLocations",
                "github.copilot.advanced",
            ):
                val = settings.get(key)
                if val:
                    val_str = json.dumps(val)
                    if ".copilot/instructions" in val_str or instructions_str in val_str:
                        return PASS, f"VS Code settings: {key} = {val}"
            return WARN, (
                "~/.copilot/instructions not found in VS Code settings "
                "(Copilot Chat may not load skill instructions in other workspaces)"
            )
        except json.JSONDecodeError:
            return WARN, "Could not parse VS Code settings.json"

    return WARN, (
        "VS Code settings.json not found and COPILOT_CUSTOM_INSTRUCTIONS_DIRS not set"
    )


def check_stale_registry(namespace: str, repo_skill_names: set, registry: dict) -> list[str]:
    """Return list of registry keys for this namespace that no longer exist in repo."""
    stale = []
    prefix = f"{namespace}/"
    for key in registry:
        if key.startswith(prefix):
            skill_name = key[len(prefix):]
            if skill_name not in repo_skill_names:
                stale.append(key)
    return stale


def check_orphaned_instructions(namespace: str, repo_skill_names: set) -> list[str]:
    """Return list of .instructions.md files with no matching skill dir."""
    orphans = []
    prefix = f"{namespace}-"
    if not INSTRUCTIONS_DIR.exists():
        return orphans
    for f in sorted(INSTRUCTIONS_DIR.iterdir()):
        if f.name.startswith(prefix) and f.name.endswith(".instructions.md"):
            skill_name = f.name[len(prefix):-len(".instructions.md")]
            if skill_name not in repo_skill_names:
                orphans.append(f.name)
    return orphans


# ── Report ─────────────────────────────────────────────────────────────────────

STATUS_ICONS = {PASS: green("✓"), FAIL: red("✗"), WARN: yellow("~")}


def status_icon(s: str) -> str:
    return STATUS_ICONS.get(s, "?")


def render_table(rows: list[dict], namespace: str):
    """Print aligned gap-analysis table."""
    col_w = max(len(r["name"]) for r in rows) + 2

    header = (
        f"{'Skill':<{col_w}}  "
        f"{'SKILL.md':^8}  {'Registry':^8}  {'Claude':^8}  {'Copilot':^8}  {'Content':^8}"
    )
    print(bold(header))
    print("─" * len(header))

    for r in rows:
        def cell(check_key):
            status, msg = r["checks"][check_key]
            return f"{status_icon(status):^10}"

        print(
            f"{r['name']:<{col_w}}  "
            f"{cell('skill_md')}  "
            f"{cell('registry')}  "
            f"{cell('claude')}  "
            f"{cell('copilot')}  "
            f"{cell('content')}"
        )

    print()
    print(f"  {green('✓')} pass  {yellow('~')} warning  {red('✗')} fail")
    print()


def render_details(rows: list[dict]):
    any_issue = False
    for r in rows:
        skill_issues = [
            (k, status, msg)
            for k, (status, msg) in r["checks"].items()
            if status != PASS
        ]
        if skill_issues:
            any_issue = True
            print(bold(f"  {r['name']}"))
            for k, status, msg in skill_issues:
                icon = STATUS_ICONS[status]
                print(f"    {icon} {k}: {msg}")
    if not any_issue:
        print(f"  {green('All per-skill checks passed.')}")
    print()


def render_global_checks(global_results: dict):
    print(bold("Global checks"))
    print("─" * 40)
    for check, (status, msg) in global_results.items():
        icon = STATUS_ICONS[status]
        print(f"  {icon}  {check}")
        if status != PASS:
            print(f"      {dim(msg)}")
    print()


def render_stale_orphans(stale_keys: list, orphaned_files: list):
    if stale_keys:
        print(bold("Stale registry entries") + " (skill removed from repo)")
        for k in stale_keys:
            print(f"  {red('✗')}  {k}")
        print()
    if orphaned_files:
        print(bold("Orphaned .instructions.md files") + " (no matching skill dir)")
        for f in orphaned_files:
            print(f"  {yellow('~')}  {f}")
        print()


def build_mitigation_plan(
    rows: list[dict],
    global_results: dict,
    stale_keys: list,
    orphaned_files: list,
    namespace: str,
    config: dict,
) -> list[dict]:
    """
    Build a prioritised list of fix actions.
    Each action: {priority, label, commands: [str], reason: str}
    """
    actions = []
    hub_same = hub_is_skills_dir(config)

    # ── P1: Fix namespace mount (root cause of Claude not seeing skills) ──
    ns_status, ns_msg = global_results.get("namespace mount", (PASS, ""))
    if ns_status != PASS and hub_same:
        actions.append({
            "priority": 1,
            "label": "Fix namespace mount (critical — root cause of missing skills)",
            "reason": ns_msg,
            "commands": [
                f"sync-skills --link {REPO_ROOT}",
            ],
            "note": (
                "This converts the namespace-level symlink to a real directory "
                "with per-skill symlinks, which is required when SKILLS_HUB and "
                "~/.claude/skills/ are the same location."
            ),
        })

    # ── P1: Install binary if missing ────────────────────────────────────
    bin_status, bin_msg = global_results.get("sync-skills binary", (PASS, ""))
    if bin_status != PASS:
        install_sh = REPO_ROOT / "sync-skills" / "setup" / "install.sh"
        actions.append({
            "priority": 1,
            "label": "Install sync-skills binary",
            "reason": bin_msg,
            "commands": [f"bash {install_sh}"],
        })

    # ── P2: Sync all skills (handles registry gaps, broken symlinks) ──────
    any_registry_fail = any(
        r["checks"]["registry"][0] == FAIL for r in rows
    )
    any_claude_fail = any(
        r["checks"]["claude"][0] in (FAIL, WARN) for r in rows
    )
    any_copilot_fail = any(
        r["checks"]["copilot"][0] == FAIL for r in rows
    )
    if any_registry_fail or any_claude_fail or any_copilot_fail or stale_keys:
        actions.append({
            "priority": 2,
            "label": "Re-sync all skills (fixes registry gaps, missing symlinks, stale entries)",
            "reason": "One or more skills have registry/symlink/instructions issues",
            "commands": ["sync-skills --all"],
            "note": (
                "Run this after fixing the namespace mount (P1 above). "
                "--all re-validates all registered skills, repairs broken symlinks, "
                "regenerates instructions files, and removes stale entries."
            ),
        })

    # ── P3: Fix Copilot dirs ──────────────────────────────────────────────
    cpd_status, cpd_msg = global_results.get("copilot instructions dirs", (PASS, ""))
    if cpd_status != PASS:
        actions.append({
            "priority": 3,
            "label": "Configure Copilot custom instructions dirs",
            "reason": cpd_msg,
            "commands": [
                (
                    "# Add to ~/.copilot/instructions via VS Code settings:\n"
                    f'# Add to settings.json: "github.copilot.chat.customInstructionsDirs": ["{INSTRUCTIONS_DIR}"]\n'
                    "# OR set environment variable:\n"
                    f'export COPILOT_CUSTOM_INSTRUCTIONS_DIRS="{INSTRUCTIONS_DIR}"'
                )
            ],
        })

    # ── P4: Fix content-stale instructions ────────────────────────────────
    stale_content = [
        r["name"] for r in rows
        if r["checks"]["content"][0] == WARN
    ]
    if stale_content:
        actions.append({
            "priority": 4,
            "label": f"Refresh stale instructions content ({len(stale_content)} skill(s))",
            "reason": f"Instructions files may be out of date: {', '.join(stale_content)}",
            "commands": ["sync-skills --all"],
        })

    # ── P4: Clean orphaned files ──────────────────────────────────────────
    if orphaned_files:
        rm_cmds = [
            f"rm '{INSTRUCTIONS_DIR / f}'" for f in orphaned_files
        ]
        actions.append({
            "priority": 4,
            "label": f"Remove {len(orphaned_files)} orphaned .instructions.md file(s)",
            "reason": "These files reference skills that no longer exist in the repo",
            "commands": rm_cmds,
        })

    return sorted(actions, key=lambda a: a["priority"])


def render_mitigation_plan(actions: list[dict]):
    if not actions:
        print(bold("  ✓ No fixes needed — all checks passed."))
        return

    for i, action in enumerate(actions, 1):
        pcolor = red if action["priority"] == 1 else (
            yellow if action["priority"] <= 3 else dim
        )
        print(bold(f"  [{action['priority']}] {action['label']}"))
        if action.get("reason"):
            print(f"      {dim('Reason: ' + action['reason'])}")
        if action.get("note"):
            print(f"      {dim('Note: ' + action['note'])}")
        print()
        for cmd in action["commands"]:
            for line in cmd.splitlines():
                print(f"      {yellow(line)}")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gap analysis for ai-skills installation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Print only the mitigation commands (no table)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    parser.add_argument(
        "--namespace",
        default=None,
        help="Override the derived namespace (default: grandparent-reponame)",
    )
    args = parser.parse_args()

    namespace = args.namespace or derive_namespace(REPO_ROOT)
    config = load_config()
    registry = load_registry()
    skills = find_skills_in_repo(REPO_ROOT)
    repo_skill_names = {s["name"] for s in skills}

    # Determine namespace mount type
    ns_path = SKILLS_DIR / namespace
    ns_is_symlink = ns_path.is_symlink()

    # ── Per-skill checks ──────────────────────────────────────────────────
    rows = []
    for skill in skills:
        checks = {
            "skill_md":  check_skill_md(skill),
            "registry":  check_registry(skill, namespace, registry),
            "claude":    check_claude_symlink(skill, namespace, ns_is_symlink),
            "copilot":   check_instructions_file(skill, namespace),
            "content":   check_instructions_content(skill, namespace),
        }
        rows.append({"name": skill["name"], "path": skill["path"], "checks": checks})

    # ── Global checks ─────────────────────────────────────────────────────
    global_results = {
        "namespace mount":          check_namespace_mount(namespace, config),
        "sync-skills binary":       check_binary(),
        "copilot instructions dirs": check_copilot_dirs(),
    }

    # ── Stale / orphan checks ─────────────────────────────────────────────
    stale_keys = check_stale_registry(namespace, repo_skill_names, registry)
    orphaned_files = check_orphaned_instructions(namespace, repo_skill_names)

    # ── Build mitigation plan ─────────────────────────────────────────────
    actions = build_mitigation_plan(
        rows, global_results, stale_keys, orphaned_files, namespace, config
    )

    # ── Output ────────────────────────────────────────────────────────────
    if args.json:
        output = {
            "namespace": namespace,
            "skills": [
                {
                    "name": r["name"],
                    "checks": {k: {"status": s, "detail": m} for k, (s, m) in r["checks"].items()},
                }
                for r in rows
            ],
            "global_checks": {k: {"status": s, "detail": m} for k, (s, m) in global_results.items()},
            "stale_registry_entries": stale_keys,
            "orphaned_instructions": orphaned_files,
            "actions": actions,
        }
        print(json.dumps(output, indent=2, default=str))
        return

    if args.fix:
        print()
        print(bold("Mitigation Plan"))
        print("─" * 54)
        print()
        render_mitigation_plan(actions)
        return

    # ── Full report ───────────────────────────────────────────────────────
    print()
    print(bold(f"Skills Audit — {namespace}"))
    print(bold(f"Repo: {REPO_ROOT}"))
    print(bold(f"Date: {__import__('datetime').date.today()}"))
    print()

    # Summary counts
    total_skills = len(rows)
    checks_keys = ["skill_md", "registry", "claude", "copilot", "content"]
    fails = sum(
        1 for r in rows for k in checks_keys if r["checks"][k][0] == FAIL
    )
    warns = sum(
        1 for r in rows for k in checks_keys if r["checks"][k][0] == WARN
    )
    g_fails = sum(1 for s, _ in global_results.values() if s == FAIL)
    g_warns = sum(1 for s, _ in global_results.values() if s == WARN)

    if fails + g_fails == 0 and warns + g_warns == 0:
        summary = green(f"✓ All {total_skills} skills fully installed")
    elif fails + g_fails == 0:
        summary = yellow(f"~ {total_skills} skills with {warns + g_warns} warning(s)")
    else:
        summary = red(f"✗ {fails + g_fails} failure(s), {warns + g_warns} warning(s) across {total_skills} skills")

    print(f"  {summary}")
    print()

    print(bold("Per-skill checks"))
    print("─" * 60)
    render_table(rows, namespace)
    render_details(rows)

    render_global_checks(global_results)

    render_stale_orphans(stale_keys, orphaned_files)

    print(bold("Mitigation Plan"))
    print("─" * 54)
    print()
    render_mitigation_plan(actions)


if __name__ == "__main__":
    main()
