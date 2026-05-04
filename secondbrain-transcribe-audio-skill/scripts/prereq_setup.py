"""
Prerequisite checker and auto-installer for secondbrain-transcribe-audio-skill.

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

# Config shared with secondbrain-notebooklm-skill (same config file).
NLM_CONFIG_DIR = Path("~/.copilot/skills/secondbrain-notebooklm-skill").expanduser()
NLM_CONFIG_FILE = NLM_CONFIG_DIR / "config.json"

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
TRANSCRIBE_SRC = SKILL_SCRIPTS_DIR / "audio_transcribe.py"

# Isolated uv environment for Whisper deps
UV_ENV_DIR = Path("~/.copilot/skills/secondbrain-transcribe-audio-skill/venv").expanduser()

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


def check_uv() -> tuple[bool, str]:
    if shutil.which("uv"):
        r = run(["uv", "--version"])
        ver = r.stdout.strip() if r.returncode == 0 else "unknown"
        return True, ver
    return False, "uv not found"


def install_uv() -> bool:
    r = run([sys.executable, "-m", "pip", "install", "uv", "--quiet"])
    if r.returncode == 0 and shutil.which("uv"):
        return True
    print("     Trying curl installer for uv...")
    r = subprocess.run(
        ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
        capture_output=False,
    )
    if r.returncode == 0 and shutil.which("uv"):
        return True
    if shutil.which("brew"):
        r = subprocess.run(["brew", "install", "uv"], capture_output=False)
        return r.returncode == 0 and shutil.which("uv") is not None
    return False


def check_notebooklm_py() -> tuple[bool, str]:
    if shutil.which("notebooklm"):
        r = run(["notebooklm", "--version"])
        ver = r.stdout.strip() if r.returncode == 0 else "installed"
        return True, ver
    return False, "notebooklm command not found"


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
    if not NLM_CONFIG_FILE.exists():
        return False, f"config not found at {NLM_CONFIG_FILE}"
    try:
        cfg = json.loads(NLM_CONFIG_FILE.read_text())
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
    if install:
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
        while True:
            path_str = input("  Enter path (or press Enter to skip): ").strip()
            if not path_str:
                return False
            p = Path(path_str).expanduser()
            if not p.exists():
                warn(f"Path does not exist: {p}")
                continue
            if not (p / "scripts" / "ingest.py").exists():
                warn(f"scripts/ingest.py not found in {p}")
                answer = input("  Use this path anyway? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    continue
            _write_config(str(p))
            return True


def _write_config(secondbrain_path: str) -> None:
    NLM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if NLM_CONFIG_FILE.exists():
        try:
            cfg = json.loads(NLM_CONFIG_FILE.read_text())
        except Exception:
            pass
    cfg["secondbrain_path"] = secondbrain_path
    NLM_CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def check_raw_dir() -> tuple[bool, str]:
    if not NLM_CONFIG_FILE.exists():
        return False, "config not set up yet"
    try:
        cfg = json.loads(NLM_CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False, "secondbrain_path not configured"
        raw_dir = Path(sb_path).expanduser() / "raw"
        if raw_dir.exists():
            return True, str(raw_dir)
        return False, f"raw/ does not exist in {sb_path}"
    except Exception as e:
        return False, str(e)


def check_ffmpeg() -> tuple[bool, str]:
    if shutil.which("ffmpeg"):
        r = run(["ffmpeg", "-version"])
        ver = r.stdout.splitlines()[0] if r.returncode == 0 else "installed"
        return True, ver
    return False, "ffmpeg not found (required by Whisper)"


def install_ffmpeg() -> bool:
    if shutil.which("brew"):
        print("     Installing ffmpeg via brew...")
        r = subprocess.run(["brew", "install", "ffmpeg"], capture_output=False)
        return r.returncode == 0 and shutil.which("ffmpeg") is not None
    if shutil.which("apt-get"):
        print("     Installing ffmpeg via apt-get...")
        r = subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], capture_output=False)
        return r.returncode == 0 and shutil.which("ffmpeg") is not None
    return False


def check_faster_whisper() -> tuple[bool, str]:
    """Check that faster-whisper is importable inside the uv venv."""
    python = UV_ENV_DIR / "bin" / "python"
    if python.exists():
        r = run([str(python), "-c", "import faster_whisper; print(faster_whisper.__version__)"])
        if r.returncode == 0:
            return True, f"faster-whisper {r.stdout.strip()} (uv env)"
    # Fallback: check system python
    r = run([sys.executable, "-c", "import faster_whisper; print(faster_whisper.__version__)"])
    if r.returncode == 0:
        return True, f"faster-whisper {r.stdout.strip()} (system)"
    return False, "faster-whisper not installed"


def install_faster_whisper() -> bool:
    """Create isolated uv venv and install faster-whisper + ctranslate2."""
    if not shutil.which("uv"):
        warn("uv not available — cannot create isolated env")
        return False
    print(f"     Creating uv venv at {UV_ENV_DIR}...")
    UV_ENV_DIR.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["uv", "venv", str(UV_ENV_DIR), "--python", "3.12", "--clear"],
        capture_output=False,
    )
    if r.returncode != 0:
        return False
    print("     Installing faster-whisper via uv pip...")
    r = subprocess.run(
        ["uv", "pip", "install", "faster-whisper",
         "--python", str(UV_ENV_DIR / "bin" / "python")],
        capture_output=False,
    )
    if r.returncode != 0:
        return False
    passed, _ = check_faster_whisper()
    return passed


def check_transcribe_deployed() -> tuple[bool, str]:
    if not NLM_CONFIG_FILE.exists():
        return False, "config not set up yet"
    try:
        cfg = json.loads(NLM_CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False, "secondbrain_path not configured"
        dest = Path(sb_path).expanduser() / "scripts" / "audio_transcribe.py"
        if dest.exists():
            return True, str(dest)
        return False, f"audio_transcribe.py not in {dest}"
    except Exception as e:
        return False, str(e)


def deploy_transcribe() -> bool:
    if not NLM_CONFIG_FILE.exists():
        return False
    try:
        cfg = json.loads(NLM_CONFIG_FILE.read_text())
        sb_path = cfg.get("secondbrain_path", "")
        if not sb_path:
            return False
        dest = Path(sb_path).expanduser() / "scripts" / "audio_transcribe.py"
        import shutil as _shutil
        _shutil.copy2(str(TRANSCRIBE_SRC), str(dest))
        return dest.exists()
    except Exception as e:
        warn(f"Deploy failed: {e}")
        return False


# ── Main checklist ─────────────────────────────────────────────────────

CHECKS = [
    ("Python 3.12+",              check_python,              None),
    ("uv",                        check_uv,                  install_uv),
    ("notebooklm-py",             check_notebooklm_py,       install_notebooklm_py),
    ("NotebookLM auth",           check_notebooklm_auth,     None),
    ("SecondBrain config",        check_secondbrain_config,  None),   # special-cased
    ("raw/ directory",            check_raw_dir,             None),
    ("ffmpeg",                    check_ffmpeg,              install_ffmpeg),
    ("faster-whisper",            check_faster_whisper,      install_faster_whisper),
    ("audio_transcribe.py deployed", check_transcribe_deployed, deploy_transcribe),
]


def run_checks(install: bool = False, check_only: bool = False) -> dict[str, bool]:
    print(f"\n{BOLD}secondbrain-transcribe-audio-skill prerequisites{RESET}\n")
    results: dict[str, bool] = {}

    for name, check_fn, install_fn in CHECKS:
        passed, detail = check_fn()

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
                elif name == "ffmpeg":
                    info("Run: brew install ffmpeg  (macOS)  or  sudo apt install ffmpeg  (Linux)")
                elif name == "faster-whisper":
                    info("Run this script with --install to create an isolated uv env")
                elif name == "uv":
                    info("Run: curl -LsSf https://astral.sh/uv/install.sh | sh")

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
        description="Check and install prerequisites for secondbrain-transcribe-audio-skill"
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
