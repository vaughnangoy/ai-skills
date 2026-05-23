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


def test_link_collapsed_migrates_existing_namespace_symlink(env_collapsed):
    """
    Regression test for the 'keeps breaking' bug.

    When hub_is_skills_dir=True and a namespace-level symlink already exists
    (e.g. created manually or by an older version of the tool), running
    --link must unlink it and replace it with a real directory containing
    per-skill symlinks.

    Previously, mkdir(exist_ok=True) silently followed the symlink to the
    repo root, and every skill was then skipped as 'already exists as
    non-symlink', leaving the namespace symlink intact.
    """
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    # Pre-create the broken state: namespace-level symlink to the repo root
    hub_name = ss.derive_hub_name(target)
    ns_link = hub / hub_name
    ns_link.symlink_to(target)
    assert ns_link.is_symlink(), "precondition: namespace symlink exists"

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    # After repair: must be a real directory, not a symlink
    assert not ns_link.is_symlink(), "namespace-level symlink should have been removed"
    assert ns_link.is_dir(), "namespace entry should now be a real directory"


# ── flat symlinks (Claude Code depth-1 discovery) ─────────────────────


def test_link_collapsed_creates_flat_symlinks(env_collapsed):
    """
    In collapsed mode, link_to_hub creates flat symlinks at SKILLS_HUB root
    (depth 1) so Claude Code can discover skills via ~/.claude/skills/<skill>/SKILL.md.
    """
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    assert ok is True

    # Flat symlinks at SKILLS_HUB root (depth 1, Claude Code readable)
    for skill in ["skill-a", "skill-b"]:
        flat = hub / skill
        assert flat.is_symlink(), f"flat symlink {skill} should exist at hub root"
        assert flat.resolve() == (target / skill).resolve(), (
            f"flat symlink {skill} should point directly to the skill source"
        )
        # SKILL.md must be accessible at depth 1
        assert (flat / "SKILL.md").exists(), f"SKILL.md should be accessible via flat link"


def test_link_collapsed_verify_requires_flat_symlinks(env_collapsed):
    """verify_link returns False when flat symlinks are missing in collapsed mode."""
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    # Remove the flat symlink to simulate broken install
    flat = hub / "skill-a"
    assert flat.is_symlink(), "flat symlink should exist after link_to_hub"
    flat.unlink()

    hub_name = ss.derive_hub_name(target)
    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.verify_link(hub_name, hub)

    assert ok is False, "verify_link should fail when flat symlink is missing"


def test_link_collapsed_cleanup_removes_flat_symlinks(env_collapsed):
    """When a skill is removed from the repo, re-running link removes its flat symlink."""
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a", "skill-b"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    assert (hub / "skill-a").is_symlink()
    assert (hub / "skill-b").is_symlink()

    # Remove skill-b from the repo
    import shutil
    shutil.rmtree(target / "skill-b")

    # Re-link: should clean up skill-b's namespace and flat symlinks
    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    assert (hub / "skill-a").is_symlink(), "skill-a flat symlink should remain"
    assert not (hub / "skill-b").is_symlink(), (
        "flat symlink for removed skill should be cleaned up"
    )


def test_link_collapsed_flat_conflict_first_wins(env_collapsed):
    """When two namespaces share a skill name, the first flat symlink wins."""
    hub = env_collapsed["hub"]

    repo1 = env_collapsed["tmp_path"] / "org1" / "skills1"
    _make_skill_repo(repo1, ["shared-skill"])
    repo2 = env_collapsed["tmp_path"] / "org2" / "skills2"
    _make_skill_repo(repo2, ["shared-skill"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok1 = ss.link_to_hub(str(repo1))
        ok2 = ss.link_to_hub(str(repo2))

    assert ok1 and ok2, "both link operations should succeed (no crash on conflict)"

    flat = hub / "shared-skill"
    assert flat.is_symlink(), "flat symlink should exist"
    assert flat.resolve() == (repo1 / "shared-skill").resolve(), (
        "first-linked namespace should own the flat symlink"
    )


def test_link_collapsed_flat_conflict_no_conflict_with_namespace_dir(env_collapsed):
    """A flat skill name must not collide with a real namespace directory."""
    hub = env_collapsed["hub"]

    # Pre-create a real namespace dir whose name matches a skill in the target repo
    (hub / "skill-a").mkdir()  # Real dir — simulates another namespace called "skill-a"

    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ok = ss.link_to_hub(str(target))

    # verify_link returns False because flat_ok=False (real dir blocks flat symlink).
    # The namespace structure itself is installed correctly; the False reflects that
    # Claude Code depth-1 discovery is blocked for this skill.
    assert ok is False, "link reports failure when flat symlink is blocked by a real dir"

    # The real dir must remain untouched — never replace a real dir with a symlink
    flat = hub / "skill-a"
    assert not flat.is_symlink(), "should not replace real dir with a symlink"
    assert flat.is_dir(), "real dir should remain intact"


def test_find_skills_skips_flat_skill_dirs(env_collapsed):
    """
    After link_to_hub creates flat symlinks, find_skills must not mistake them
    for namespace directories. Without the skip-guard, a skill subdir that itself
    contains nested dirs with SKILL.md would be reported as an extra skill.
    """
    hub = env_collapsed["hub"]
    target = env_collapsed["tmp_path"] / "org" / "my-skills"
    _make_skill_repo(target, ["skill-a"])

    # Add a nested sub-dir inside skill-a that also has a SKILL.md.
    # Without the fix, find_skills would walk into hub/skill-a (flat) as a
    # namespace and find this nested SKILL.md, yielding an extra spurious skill.
    nested = target / "skill-a" / "nested-doc"
    nested.mkdir()
    (nested / "SKILL.md").write_text("---\nname: nested-doc\ndescription: nested\n---\n# nested\n")

    with patch.object(ss, "_check_instructions_env", return_value=True):
        ss.link_to_hub(str(target))

    assert (hub / "skill-a").is_symlink(), "flat symlink should be present"

    skills = ss.find_skills(hub)

    assert len(skills) == 1, f"Expected 1 skill, got {len(skills)}: {skills}"
    assert skills[0]["name"] == "skill-a"
    assert skills[0]["namespace"] == "org-my-skills"


# ── sync_skills: standalone single-skill repos ────────────────────────


def test_sync_standalone_creates_instructions(env_collapsed):
    """sync_skills() writes a Copilot instructions file for a standalone skill."""
    hub = env_collapsed["hub"]
    instr_dir = env_collapsed["instr_dir"]

    # Standalone skill: SKILL.md at root, linked directly into hub
    standalone = hub / "solo-skill"
    standalone.mkdir()
    (standalone / "SKILL.md").write_text(
        "---\nname: solo-skill\ndescription: A standalone skill.\n---\n\nBody text."
    )

    ss.sync_skills(all_mode=True)

    instr = instr_dir / "solo-skill.instructions.md"
    assert instr.exists(), "instructions file should be created for standalone skill"
    content = instr.read_text()
    assert "solo-skill" in content
    # Must NOT have a namespace prefix like "__standalone__-solo-skill"
    assert not (instr_dir / "__standalone__-solo-skill.instructions.md").exists()


def test_sync_standalone_stale_cleanup_removes_instructions_not_entry(env_collapsed):
    """Stale standalone cleanup removes the instructions file but never touches the hub entry."""
    import shutil

    hub = env_collapsed["hub"]
    instr_dir = env_collapsed["instr_dir"]

    # Create and sync a standalone skill
    standalone = hub / "solo-skill"
    standalone.mkdir()
    (standalone / "SKILL.md").write_text("---\nname: solo-skill\n---\n\nBody.")
    ss.sync_skills(all_mode=True)

    instr = instr_dir / "solo-skill.instructions.md"
    assert instr.exists(), "instructions file should exist after first sync"

    # Simulate user removing the standalone skill from hub
    shutil.rmtree(str(standalone))

    # Run --all again: instructions should be cleaned up, no error from trying to unlink hub entry
    ss.sync_skills(all_mode=True)

    assert not instr.exists(), "instructions should be removed when standalone skill is gone"
