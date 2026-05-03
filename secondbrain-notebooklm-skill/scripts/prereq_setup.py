"""
Prerequisite checker and auto-installer for secondbrain-notebooklm-skill.

Usage:
    python prereq_setup.py --check     # Check only, exit 1 if any fail
    python prereq_setup.py --install   # Auto-install everything fixable
    python prereq_setup.py             # Interactive mode
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path("~/.copilot/skills/secondbrain-notebooklm-skill").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.json"

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
NLM_SYNC_SRC = SKILL_SCRIPTS_DIR / "nlm_sync.py"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✅{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}❌{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠️ {RESET}  {msg}")


def info(msg: str) -> None:
    print(f"     {msg}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Individual checks ──────────────────────────────────────────────────

def check_python() -> tuple[bool, str]:
    v = sys.version_info
    if v >= (3, 12):
        return True, f"Python {v.major}.{v.minor}.{v.micro}"
    return False, f"Python {v.major}.{v.minor}.{v.micro} (need 3.12+)"


def check_pip() -> tuple[bool, str]:
    r = run([sys.executable, "-m", "pip", "--version"])
    if r.returncode == 0:
        return True, r.stdout.split()[1] if r.stdout else "ok"
    return False, "pip not found"


def install_uv() -> bool:
    """Try pip → curl installer → brew (install brew if needed)."""
    # Try pip first
    r = run([sys.executable, "-m", "pip", "install", "uv", "--quiet"])
    if r.returncode == 0 and shutil.which("uv"):
        return True

    # Try curl astral.sh installer
    print("     Trying curl installer for uv...")
    r = subprocess.run(
        ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
        capture_output=False,
    )
    if r.returncode == 0 and shutil.which("uv"):
        return True

    # Try brew
    if shutil.which("brew"):
        print("     Trying brew install uv...")
        r = subprocess.run(["brew", "install", "uv"], capture_output=False)
        if r.returncode == 0 and shutil.which("uv"):
            return True
    else:
        # Install brew
        print("     brew not found — installing Homebrew (NONINTERACTIVE)...")
        env = {**os.environ, "NONINTERACTIVE": "1"}
        r = subprocess.run(
            ["bash", "-c",
             '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
            capture_output=False,
            env=env,
        )
        if r.returncode == 0:
            r2 = subprocess.run(["brew", "install", "uv"], capture_output=False)
            if r2.returncode == 0 and shutil.which("uv"):
                return True

    return False


def check_uv() -> tuple[bool, str]:
    if shutil.which("uv"):
        r = run(["uv", "--version"])
        ver = r.stdout.strip() if r.returncode == 0 else "unknown"
        return True, ver
    return False, "uv not found"


def check_notebooklm_py() -> tuple[bool, str]:
    if shutil.which("notebooklm"):
        r = run(["notebooklm", "--version"])
        ver = r.stdout.strip() if r.returncode == 0 else "installed"
        return True, ver
    return False, "notebooklm command not found (pip install notebooklm-py)"


def install_notebooklm_py() -> bool:
    if shutil.which("uv"):
        r = subprocess.run(["uv", "tool", "install", "notebooklm-py"], capture_output=False)
    else:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "notebooklm-py"],
                           capture_output=False)
    return r.returncode == 0 and shutil.which("notebooklm") is not None


def check_notebooklm_auth() -> tuple[bool, str]:
    r = run(["notebooklm", "status"])
    if r.returncode == 0 and "authenticated" in r.stdout.lower():
        return True, "authenticated"
    if r.returncode == 0 and r.stdout.strip():
        return True, r.stdout.strip()[:60]
    return False, "not authenticated (run: notebooklm login)"


def check_secondbrain_config() -> tuple[bool, str]:
    if not CONFIG_FILE.exists():
        return False, f"config not found at {CONFIG_FILE}"
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False, "secondbrain_path not set in config"
        p = Path(sb_path).expanduser()
        if not p.exists():
            return False, f"secondbrain_path does not exist: {p}"
        return True, str(p)
    except Exception as e:
        return False, f"config error: {e}"


def setup_secondbrain_config(install: bool) -> bool:
    """Prompt for SecondBrain path and write config."""
    if install:
        # Non-interactive: try to detect from common locations
        candidates = [
            Path("~/Obsidian/SecondBrain").expanduser(),
            Path("~/Documents/SecondBrain").expanduser(),
        ]
        for c in candidates:
            if c.exists() and (c / "scripts" / "ingest.py").exists():
                print(f"     Auto-detected SecondBrain at: {c}")
                _write_config(str(c))
                return True
        fail("Cannot auto-detect SecondBrain path — run without --install to configure interactively")
        return False
    else:
        print()
        print(f"  {BOLD}SecondBrain path not configured.{RESET}")
        print("  This is the root of your SecondBrain repo (contains scripts/ingest.py).")
        while True:
            path_str = input("  Enter path (or press Enter to skip): ").strip()
            if not path_str:
                return False
            p = Path(path_str).expanduser()
            if not p.exists():
                warn(f"Path does not exist: {p}")
                continue
            if not (p / "scripts" / "ingest.py").exists():
                warn(f"scripts/ingest.py not found in {p} — are you sure this is SecondBrain?")
                answer = input("  Use this path anyway? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    continue
            _write_config(str(p))
            return True


def _write_config(secondbrain_path: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    cfg["secondbrain_path"] = secondbrain_path
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def check_raw_dir() -> tuple[bool, str]:
    if not CONFIG_FILE.exists():
        return False, "config not set up yet"
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False, "secondbrain_path not configured"
        raw_dir = Path(sb_path).expanduser() / "raw"
        if raw_dir.exists():
            return True, str(raw_dir)
        return False, f"raw/ does not exist in {sb_path}"
    except Exception as e:
        return False, str(e)


def check_nlm_sync_deployed() -> tuple[bool, str]:
    if not CONFIG_FILE.exists():
        return False, "config not set up yet"
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False, "secondbrain_path not configured"
        dest = Path(sb_path).expanduser() / "scripts" / "nlm_sync.py"
        if dest.exists():
            return True, str(dest)
        return False, f"nlm_sync.py not in {dest}"
    except Exception as e:
        return False, str(e)


def deploy_nlm_sync() -> bool:
    if not CONFIG_FILE.exists():
        return False
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False
        dest = Path(sb_path).expanduser() / "scripts" / "nlm_sync.py"
        import shutil as _shutil
        _shutil.copy2(str(NLM_SYNC_SRC), str(dest))
        return dest.exists()
    except Exception as e:
        warn(f"Deploy failed: {e}")
        return False


# ── Main checklist ─────────────────────────────────────────────────────

CHECKS = [
    ("Python 3.12+", check_python, None),
    ("pip", check_pip, None),
    ("uv", check_uv, install_uv),
    ("notebooklm-py", check_notebooklm_py, install_notebooklm_py),
    ("NotebookLM auth", check_notebooklm_auth, None),
    ("SecondBrain config", check_secondbrain_config, None),  # special-cased below
    ("raw/ directory", check_raw_dir, None),
    ("nlm_sync.py deployed", check_nlm_sync_deployed, deploy_nlm_sync),
]


def run_checks(install: bool = False, check_only: bool = False) -> dict[str, bool]:
    print(f"\n{BOLD}secondbrain-notebooklm-skill prerequisites{RESET}\n")
    results: dict[str, bool] = {}

    for name, check_fn, install_fn in CHECKS:
        passed, detail = check_fn()

        # Special case: SecondBrain config — prompt interactively if needed (never in --check mode)
        if not passed and name == "SecondBrain config" and not check_only:
            if install or not sys.stdin.isatty():
                passed = setup_secondbrain_config(install=True)
            else:
                passed = setup_secondbrain_config(install=False)
            if passed:
                passed2, detail2 = check_fn()
                passed, detail = passed2, detail2

        if passed:
            ok(f"{name}: {detail}")
        else:
            if install and install_fn:
                warn(f"{name}: {detail} — installing...")
                success = install_fn()
                if success:
                    passed2, detail2 = check_fn()
                    if passed2:
                        ok(f"{name}: {detail2}")
                        passed = True
                    else:
                        fail(f"{name}: {detail2}")
                else:
                    fail(f"{name}: install failed")
            else:
                fail(f"{name}: {detail}")
                if name == "NotebookLM auth":
                    info("Run: notebooklm login")
                elif name == "uv":
                    info("Run: curl -LsSf https://astral.sh/uv/install.sh | sh")
                elif name == "notebooklm-py":
                    info("Run: pip install notebooklm-py  or  uv tool install notebooklm-py")

        results[name] = passed

    all_pass = all(results.values())
    print()
    if all_pass:
        print(f"{GREEN}{BOLD}✅ All prerequisites met.{RESET}\n")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"{RED}{BOLD}❌ {len(failed)} prerequisite(s) failed: {', '.join(failed)}{RESET}")
        print(f"   Run with --install to auto-fix where possible.\n")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check and install prerequisites for secondbrain-notebooklm-skill"
    )
    parser.add_argument("--check", action="store_true",
                        help="Check only — exit 1 if any prerequisite fails")
    parser.add_argument("--install", action="store_true",
                        help="Auto-install all fixable prerequisites")
    args = parser.parse_args()

    results = run_checks(install=args.install, check_only=args.check)

    if args.check and not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
