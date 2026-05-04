"""
Tests for sync-skills --link functionality:
  - derive_hub_name
  - link_to_hub
  - verify_link
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the parent package importable when running from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))
import sync_skills as ss


# ── derive_hub_name ────────────────────────────────────────────────────


def test_derive_hub_name_standard():
    p = Path("/Users/vaughnangoy/code/git-repos/vaughnangoy/ai-skills")
    assert ss.derive_hub_name(p) == "vaughnangoy-ai-skills"


def test_derive_hub_name_other_org():
    p = Path("/home/user/repos/teng-lin/notebooklm-py")
    assert ss.derive_hub_name(p) == "teng-lin-notebooklm-py"


def test_derive_hub_name_simple():
    p = Path("/tmp/org/repo")
    assert ss.derive_hub_name(p) == "org-repo"


# ── link_to_hub helpers ────────────────────────────────────────────────


def _make_skill_repo(base: Path, skill_names: list[str]) -> Path:
    """Create a fake skill repo with given skill subdirectories."""
    base.mkdir(parents=True, exist_ok=True)
    for name in skill_names:
        skill_dir = base / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill {name}\n---\n# {name}\n"
        )
    return base


def _write_config(tmp_path: Path, hub: Path):
    config_dir = tmp_path / ".config" / "sync-skills"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps({"watch_path": str(hub), "copilot_namespace": None})
    )
    return config_dir


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """
    Isolated environment with:
      - tmp_path/hub/          → SKILLS_HUB
      - tmp_path/claude/skills → SKILLS_DIR
      - tmp_path/copilot/instr → INSTRUCTIONS_DIR
      - tmp_path/config/       → CONFIG_DIR
    """
    hub = tmp_path / "hub"
    hub.mkdir()
    claude_skills = tmp_path / "claude" / "skills"
    claude_skills.mkdir(parents=True)
    instr_dir = tmp_path / "copilot" / "instructions"
    instr_dir.mkdir(parents=True)
    config_dir = tmp_path / "config" / "sync-skills"
    config_dir.mkdir(parents=True)

    cfg = {"watch_path": str(hub), "copilot_namespace": None}
    (config_dir / "config.json").write_text(json.dumps(cfg))
    (config_dir / "registry.json").write_text("{}")

    monkeypatch.setattr(ss, "SKILLS_DIR", claude_skills)
    monkeypatch.setattr(ss, "INSTRUCTIONS_DIR", instr_dir)
    monkeypatch.setattr(ss, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(ss, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(ss, "REGISTRY_FILE", config_dir / "registry.json")

    return {
        "hub": hub,
        "claude_skills": claude_skills,
        "instr_dir": instr_dir,
        "config_dir": config_dir,
        "tmp_path": tmp_path,
    }


# ── link_to_hub: new link ──────────────────────────────────────────────


def test_link_creates_symlink(env):
    hub = env["hub"]
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    link_path = hub / hub_name
    assert link_path.is_symlink(), "SKILLS_HUB entry should be a symlink"
    assert link_path.resolve() == target.resolve()
    assert ok is True


def test_link_creates_claude_symlinks(env):
    hub = env["hub"]
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    claude_link = env["claude_skills"] / hub_name / "skill-a"
    assert claude_link.is_symlink()
    assert claude_link.resolve() == (target / "skill-a").resolve()


def test_link_creates_instructions_file(env):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    instr = env["instr_dir"] / f"{hub_name}-skill-a.instructions.md"
    assert instr.exists()
    assert instr.stat().st_size > 0


# ── link_to_hub: idempotent ────────────────────────────────────────────


def test_link_idempotent(env):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok1 = ss.link_to_hub(str(target))
        ok2 = ss.link_to_hub(str(target))

    assert ok1 and ok2


# ── link_to_hub: updates stale symlink ────────────────────────────────


def test_link_updates_stale_symlink(env):
    hub = env["hub"]
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])
    stale_target = env["tmp_path"] / "org" / "old-skills"
    _make_skill_repo(stale_target, ["skill-a"])

    hub_name = ss.derive_hub_name(target)
    link_path = hub / hub_name
    link_path.symlink_to(stale_target)

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    assert ok
    assert link_path.resolve() == target.resolve()


# ── link_to_hub: real dir migration ───────────────────────────────────


def test_link_migrates_real_dir_matching_content(env, capsys):
    hub = env["hub"]
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    # Pre-populate SKILLS_HUB with a real dir containing same skill names
    hub_name = ss.derive_hub_name(target)
    real_dir = hub / hub_name
    for name in ["skill-a", "skill-b"]:
        (real_dir / name).mkdir(parents=True)
        (real_dir / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    assert ok
    link_path = hub / hub_name
    assert link_path.is_symlink()
    assert link_path.resolve() == target.resolve()


def test_link_migration_requires_force_on_diverged_content(env, capsys):
    hub = env["hub"]
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    # Real dir has an extra skill not in target
    hub_name = ss.derive_hub_name(target)
    real_dir = hub / hub_name
    for name in ["skill-a", "skill-extra"]:
        (real_dir / name).mkdir(parents=True)
        (real_dir / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok_no_force = ss.link_to_hub(str(target), force=False)

    assert ok_no_force is False
    assert not (hub / hub_name).is_symlink(), "Should not have replaced the real dir"

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok_force = ss.link_to_hub(str(target), force=True)

    assert ok_force is True
    assert (hub / hub_name).is_symlink()


# ── link_to_hub: error cases ───────────────────────────────────────────


def test_link_rejects_nonexistent_target(env, capsys):
    ok = ss.link_to_hub("/nonexistent/path/that/does/not/exist")
    assert ok is False


def test_link_rejects_target_with_no_skills(env, capsys):
    target = env["tmp_path"] / "empty-repo"
    target.mkdir()
    ok = ss.link_to_hub(str(target))
    assert ok is False


# ── verify_link ────────────────────────────────────────────────────────


def test_verify_link_all_present(env, capsys):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub = env["hub"]
    hub_name = ss.derive_hub_name(target)

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.verify_link(hub_name, hub)

    assert ok is True


def test_verify_link_missing_claude_skill(env, capsys):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    # Remove the claude symlink to simulate a broken install
    hub_name = ss.derive_hub_name(target)
    claude_link = env["claude_skills"] / hub_name / "skill-a"
    claude_link.unlink()

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.verify_link(hub_name, env["hub"])

    assert ok is False


def test_verify_link_broken_instructions(env, capsys):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    # Delete the instructions file to simulate a broken install
    hub_name = ss.derive_hub_name(target)
    instr = env["instr_dir"] / f"{hub_name}-skill-a.instructions.md"
    instr.unlink()

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.verify_link(hub_name, env["hub"])

    assert ok is False


def test_verify_link_instructions_env_not_configured(env, capsys):
    target = env["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)

    with patch.object(ss, "_check_instructions_env", return_value=False):
        ok = ss.verify_link(hub_name, env["hub"])

    assert ok is False


# ── hub == SKILLS_DIR (collapsed mode) ────────────────────────────────


@pytest.fixture()
def env_collapsed(tmp_path, monkeypatch):
    """
    Collapsed environment: hub and SKILLS_DIR resolve to the same directory.
    This mimics ~/.claude/skills → ~/code/SKILLS_HUB.
    """
    hub = tmp_path / "hub"
    hub.mkdir()

    # Make SKILLS_DIR a symlink to hub (the real-world scenario)
    claude_base = tmp_path / "claude"
    claude_base.mkdir()
    skills_symlink = claude_base / "skills"
    skills_symlink.symlink_to(hub)

    instr_dir = tmp_path / "copilot" / "instructions"
    instr_dir.mkdir(parents=True)
    config_dir = tmp_path / "config" / "sync-skills"
    config_dir.mkdir(parents=True)

    cfg = {"watch_path": str(hub), "copilot_namespace": None}
    (config_dir / "config.json").write_text(json.dumps(cfg))
    (config_dir / "registry.json").write_text("{}")

    # SKILLS_DIR points to the symlink (which resolves to hub)
    monkeypatch.setattr(ss, "SKILLS_DIR", skills_symlink)
    monkeypatch.setattr(ss, "INSTRUCTIONS_DIR", instr_dir)
    monkeypatch.setattr(ss, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(ss, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(ss, "REGISTRY_FILE", config_dir / "registry.json")

    return {
        "hub": hub,
        "skills_dir": skills_symlink,
        "instr_dir": instr_dir,
        "config_dir": config_dir,
        "tmp_path": tmp_path,
    }


def test_link_collapsed_creates_per_skill_symlinks(env_collapsed):
    """When hub == SKILLS_DIR, per-skill symlinks are created pointing to the repo."""
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    ns_dir = hub / hub_name

    # Namespace should be a real directory, not a symlink
    assert ns_dir.is_dir()
    assert not ns_dir.is_symlink()

    # Individual skills should be symlinks pointing directly to the repo
    for skill in ["skill-a", "skill-b"]:
        skill_link = ns_dir / skill
        assert skill_link.is_symlink(), f"{skill} should be a symlink"
        assert skill_link.resolve() == (target / skill).resolve()

    assert ok is True


def test_link_collapsed_creates_instructions_files(env_collapsed):
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    instr = env_collapsed["instr_dir"] / f"{hub_name}-skill-a.instructions.md"
    assert instr.exists() and instr.stat().st_size > 0


def test_link_collapsed_verify_passes(env_collapsed):
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    assert ok is True


def test_link_collapsed_no_namespace_symlink_created(env_collapsed):
    """Ensure no circular symlinks are created in collapsed mode."""
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    hub_name = ss.derive_hub_name(target)
    ns_dir = hub / hub_name
    skill_link = ns_dir / "skill-a"

    # Skill symlink must NOT point back into SKILLS_HUB (that would be circular)
    assert skill_link.resolve() == (target / "skill-a").resolve()
    assert not str(skill_link.resolve()).startswith(str(hub))
