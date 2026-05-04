"""
NotebookLM → SecondBrain sync script.

Called by the secondbrain-notebooklm-skill.

Usage:
    python nlm_sync.py --manifest [--notebook <id>]
    python nlm_sync.py --sync [--notebook <id>] [--auto]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── Path resolution ────────────────────────────────────────────────────
# When deployed into SecondBrain/scripts/ via prereq_setup.py, ROOT points
# at the SecondBrain repo root. When run from the skill bundle directly,
# ROOT must be set via --root or the SECONDBRAIN_ROOT env variable.

import os

_env_root = os.environ.get("SECONDBRAIN_ROOT")
if _env_root:
    ROOT = Path(_env_root).expanduser().resolve()
else:
    # Assume deployed into SecondBrain/scripts/
    ROOT = Path(__file__).resolve().parent.parent

SCRIPTS_DIR = ROOT / "scripts"
RAW_DIR = ROOT / "raw"
RAW_NLM_DIR = RAW_DIR / "notebooklm"
DEDUP_DIR = RAW_DIR / "dedup-rejections"

sys.path.insert(0, str(SCRIPTS_DIR))


def _import_sb():
    """Lazy import SecondBrain helpers (requires SecondBrain on sys.path)."""
    from config import now_iso  # noqa: F401
    from utils import load_state, normalize_title, save_state, slugify  # noqa: F401
    return now_iso, load_state, normalize_title, save_state, slugify


# ── NotebookLM CLI helpers ─────────────────────────────────────────────

def run_nlm(*args: str) -> tuple[int, str]:
    result = subprocess.run(["notebooklm", *args], capture_output=True, text=True)
    return result.returncode, (result.stdout.strip() or result.stderr.strip())


def get_current_notebook() -> dict | None:
    rc, output = run_nlm("status", "--json")
    if rc != 0 or not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def list_sources(notebook_id: str) -> list[dict]:
    rc, output = run_nlm("source", "list", "--notebook", notebook_id, "--json")
    if rc != 0:
        return []
    try:
        data = json.loads(output)
        return data if isinstance(data, list) else data.get("sources", [])
    except json.JSONDecodeError:
        return []


def list_artifacts(notebook_id: str) -> list[dict]:
    rc, output = run_nlm("artifact", "list", "--notebook", notebook_id, "--json")
    if rc != 0:
        return []
    try:
        data = json.loads(output)
        return data if isinstance(data, list) else data.get("artifacts", [])
    except json.JSONDecodeError:
        return []


# ── Dedup helpers ──────────────────────────────────────────────────────

def build_dedup_index(state: dict) -> list[dict]:
    """Build lookup list from already-ingested state entries that have title_slug."""
    return [
        {
            "title_slug": v.get("title_slug", ""),
            "size_bytes": v.get("size_bytes"),
            "filename": k,
        }
        for k, v in state.get("raw_ingested", {}).items()
        if v.get("title_slug")
    ]


def find_dedup_match(
    title_slug: str,
    size_bytes: int | None,
    dedup_index: list[dict],
) -> dict | None:
    """Return first dedup index entry that matches title (+ exact size for PDFs).

    - size_bytes=None  → markdown source: title match alone is sufficient
    - size_bytes=<int> → PDF artifact: both title AND exact size must match
    """
    for entry in dedup_index:
        if entry["title_slug"] != title_slug:
            continue
        if size_bytes is None:
            return entry  # markdown: title match alone is sufficient
        if entry.get("size_bytes") is not None and entry["size_bytes"] == size_bytes:
            return entry  # PDF: title + exact size match
    return None


# ── Artifact type config ───────────────────────────────────────────────

ARTIFACT_EXT: dict[str, str | None] = {
    "audio": None,
    "video": None,
    "report": ".md",
    "slide-deck": ".pdf",
    "infographic": ".png",
    "quiz": ".md",
    "flashcards": ".md",
    "mind-map": ".md",
    "data-table": ".csv",
}

ARTIFACT_DOWNLOAD: dict[str, list[str]] = {
    "report": ["download", "report"],
    "slide-deck": ["download", "slide-deck"],
    "infographic": ["download", "infographic"],
    "quiz": ["download", "quiz", "--format", "markdown"],
    "flashcards": ["download", "flashcards", "--format", "markdown"],
    "mind-map": ["download", "mind-map"],
    "data-table": ["download", "data-table"],
}


# ── Manifest builder ───────────────────────────────────────────────────

def build_manifest(notebook_id: str, notebook_slug: str, state: dict) -> dict:
    _, _, normalize_title, _, slugify = _import_sb()
    raw_ingested = state.get("raw_ingested", {})
    dedup_index = build_dedup_index(state)

    sources_out: list[dict] = []
    artifacts_out: list[dict] = []

    for src in list_sources(notebook_id):
        sid = src.get("source_id") or src.get("id", "")
        title = src.get("title", sid)
        src_type = src.get("type", "unknown")
        status = src.get("status", "unknown")
        slug = slugify(title)
        filename = f"nlm__{notebook_slug}__source__{slug}.md"
        title_norm = normalize_title(title)

        if status not in ("ready", "complete", "processed"):
            sources_out.append({"id": sid, "title": title, "type": src_type,
                                 "action": "skip", "reason": f"not ready ({status})"})
            continue

        if filename in raw_ingested:
            sources_out.append({"id": sid, "title": title, "type": src_type,
                                 "filename": filename, "action": "skip",
                                 "reason": "already synced"})
            continue

        match = find_dedup_match(title_norm, None, dedup_index)
        if match:
            sources_out.append({"id": sid, "title": title, "type": src_type,
                                 "filename": filename, "action": "dedup_reject",
                                 "reason": "title match", "matched": match["filename"]})
            continue

        sources_out.append({"id": sid, "title": title, "type": src_type,
                             "filename": filename, "action": "sync"})

    for art in list_artifacts(notebook_id):
        aid = art.get("artifact_id") or art.get("id", "")
        art_type = art.get("type", "unknown")
        art_format = art.get("format", "")
        status = art.get("status", "unknown")

        ext = ARTIFACT_EXT.get(art_type)
        if ext is None:
            artifacts_out.append({"id": aid, "type": art_type, "format": art_format,
                                   "action": "skip", "reason": "not supported"})
            continue

        if status != "complete":
            artifacts_out.append({"id": aid, "type": art_type, "format": art_format,
                                   "action": "skip", "reason": f"not complete ({status})"})
            continue

        type_slug = slugify(f"{art_type}-{art_format}" if art_format else art_type)
        filename = f"nlm__{notebook_slug}__artifact__{type_slug}{ext}"

        if filename in raw_ingested:
            artifacts_out.append({"id": aid, "type": art_type, "format": art_format,
                                   "filename": filename, "ext": ext,
                                   "action": "skip", "reason": "already synced"})
            continue

        artifacts_out.append({"id": aid, "type": art_type, "format": art_format,
                               "filename": filename, "ext": ext, "action": "sync"})

    all_items = sources_out + artifacts_out
    return {
        "notebook_id": notebook_id,
        "notebook_slug": notebook_slug,
        "sources": sources_out,
        "artifacts": artifacts_out,
        "summary": {
            "new": sum(1 for x in all_items if x["action"] == "sync"),
            "skipped": sum(1 for x in all_items if x["action"] == "skip"),
            "dedup_rejected": sum(1 for x in all_items if x["action"] == "dedup_reject"),
        },
    }


def print_manifest(manifest: dict) -> None:
    s = manifest["summary"]
    print(f"\n📓  Notebook: {manifest['notebook_slug']}")
    print(f"    🆕 {s['new']} to sync  |  ⏭️  {s['skipped']} already synced  |  🚫 {s['dedup_rejected']} dedup rejected\n")
    if manifest["sources"]:
        print("Sources:")
        for src in manifest["sources"]:
            icon = {"sync": "🆕", "skip": "⏭️ ", "dedup_reject": "🚫"}.get(src["action"], "  ")
            print(f"  {icon}  [{src['type']}] {src['title']}")
            if src["action"] == "dedup_reject":
                print(f"         → matches: {src.get('matched', '?')}")
    if manifest["artifacts"]:
        print("\nArtifacts:")
        for art in manifest["artifacts"]:
            icon = {"sync": "🆕", "skip": "⏭️ ", "dedup_reject": "🚫"}.get(art["action"], "  ")
            label = f"{art['type']}/{art['format']}" if art.get("format") else art["type"]
            print(f"  {icon}  {label}")
    print()


# ── Sync workers ───────────────────────────────────────────────────────

def sync_source_fulltext(source: dict, dest_dir: Path, notebook_id: str) -> Path | None:
    rc, output = run_nlm("source", "fulltext", source["id"], "--notebook", notebook_id, "--json")
    if rc != 0:
        print(f"    ⚠️  Fulltext fetch failed for '{source['title']}': {output[:200]}")
        return None
    try:
        data = json.loads(output)
        content = data.get("content", "")
        title = data.get("title", source["title"])
        char_count = data.get("char_count", len(content))
    except json.JSONDecodeError:
        content, title, char_count = output, source["title"], len(output)

    if not content.strip():
        print(f"    ⚠️  Empty fulltext for '{source['title']}'")
        return None

    dest = dest_dir / source["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f"# {title}\n\n"
        f"**Source type:** {source['type']}\n"
        f"**Source ID:** {source['id']}\n"
        f"**Characters:** {char_count}\n\n"
        f"---\n\n{content}",
        encoding="utf-8",
    )
    return dest


def mind_map_to_markdown(node: dict, depth: int = 0) -> str:
    label = node.get("label") or node.get("name") or node.get("text", "")
    children = node.get("children", [])
    lines = [f"# {label}\n"] if depth == 0 else ["  " * (depth - 1) + f"- {label}"]
    for child in children:
        lines.append(mind_map_to_markdown(child, depth + 1))
    return "\n".join(lines)


def sync_artifact(artifact: dict, dest_dir: Path, notebook_id: str) -> Path | None:
    art_type = artifact["type"]
    dest = dest_dir / artifact["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    download_args = ARTIFACT_DOWNLOAD.get(art_type)
    if not download_args:
        return None

    if art_type == "mind-map":
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        rc, output = run_nlm(*download_args, str(tmp_path), "-n", artifact["id"])
        if rc != 0 or not tmp_path.exists():
            print(f"    ⚠️  Mind map download failed: {output[:200]}")
            tmp_path.unlink(missing_ok=True)
            return None
        try:
            md = mind_map_to_markdown(json.loads(tmp_path.read_text()))
            dest.write_text(md, encoding="utf-8")
            tmp_path.unlink()
            return dest
        except Exception as e:
            print(f"    ⚠️  Mind map conversion failed: {e}")
            tmp_path.unlink(missing_ok=True)
            return None
    else:
        rc, output = run_nlm(*download_args, str(dest), "-n", artifact["id"])
        if rc != 0 or not dest.exists():
            print(f"    ⚠️  {art_type} download failed: {output[:200]}")
            return None
        return dest


def move_to_dedup_rejections(path: Path, reason: str, matched: str, state: dict) -> None:
    now_iso, _, _, save_state, _ = _import_sb()
    DEDUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H-%M-%S")
    dest = DEDUP_DIR / f"{ts}__{path.name}"
    path.rename(dest)
    state.setdefault("dedup_rejections", []).append({
        "filename": path.name,
        "rejected_at": now_iso(),
        "reason": reason,
        "matched_against": matched,
        "moved_to": str(dest.name),
    })
    print(f"    🚫 Dedup rejected → {dest.name}")


def do_sync(manifest: dict, notebook_id: str, state: dict) -> int:
    now_iso, _, normalize_title, save_state, _ = _import_sb()
    notebook_slug = manifest["notebook_slug"]
    dest_dir = RAW_NLM_DIR / notebook_slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dedup_index = build_dedup_index(state)
    synced = 0

    for src in manifest["sources"]:
        if src["action"] == "dedup_reject":
            state.setdefault("dedup_rejections", []).append({
                "filename": src["filename"],
                "rejected_at": now_iso(),
                "reason": src["reason"],
                "matched_against": src.get("matched", ""),
                "moved_to": None,
            })
            print(f"  🚫 Source '{src['title']}' — {src['reason']}")
            continue
        if src["action"] != "sync":
            continue
        print(f"  ↓  Source: {src['title']}")
        path = sync_source_fulltext(src, dest_dir, notebook_id)
        if path:
            synced += 1
            print(f"     ✅ {path.name}")

    for art in manifest["artifacts"]:
        if art["action"] != "sync":
            continue
        label = f"{art['type']}/{art['format']}" if art.get("format") else art["type"]
        print(f"  ↓  Artifact: {label}")
        path = sync_artifact(art, dest_dir, notebook_id)
        if not path:
            continue
        if path.suffix.lower() == ".pdf":
            title_norm = normalize_title(path.stem)
            match = find_dedup_match(title_norm, path.stat().st_size, dedup_index)
            if match:
                move_to_dedup_rejections(path, "title+size match", match["filename"], state)
                save_state(state)
                continue
        synced += 1
        print(f"     ✅ {path.name}")

    save_state(state)
    return synced


def trigger_ingest() -> None:
    print("\n🔄 Triggering ingest pipeline...")
    result = subprocess.run(
        ["uv", "run", "--directory", str(ROOT), "python",
         str(SCRIPTS_DIR / "ingest.py"), "--pending"],
        capture_output=False,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("  ⚠️  ingest.py exited with an error — check logs")


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync NotebookLM content to SecondBrain")
    parser.add_argument("--notebook", "-n", help="Notebook ID (default: current context)")
    parser.add_argument("--manifest", action="store_true", help="Show manifest only")
    parser.add_argument("--sync", action="store_true", help="Run sync")
    parser.add_argument("--auto", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--root", help="Override SecondBrain root path")
    args = parser.parse_args()

    if args.root:
        global ROOT, SCRIPTS_DIR, RAW_DIR, RAW_NLM_DIR, DEDUP_DIR
        ROOT = Path(args.root).expanduser().resolve()
        SCRIPTS_DIR = ROOT / "scripts"
        RAW_DIR = ROOT / "raw"
        RAW_NLM_DIR = RAW_DIR / "notebooklm"
        DEDUP_DIR = RAW_DIR / "dedup-rejections"
        sys.path.insert(0, str(SCRIPTS_DIR))

    if not args.manifest and not args.sync:
        args.manifest = True

    now_iso, load_state, _, save_state, slugify = _import_sb()

    notebook_id = args.notebook
    notebook_title = None
    if not notebook_id:
        nb = get_current_notebook()
        if not nb:
            print("❌ No active notebook. Run: notebooklm use <notebook_id>")
            sys.exit(1)
        notebook_id = nb.get("notebook_id") or nb.get("id", "")
        notebook_title = nb.get("title", notebook_id)

    if not notebook_id:
        print("❌ Could not determine notebook ID.")
        sys.exit(1)

    notebook_slug = slugify(notebook_title or notebook_id[:12])
    state = load_state()
    manifest = build_manifest(notebook_id, notebook_slug, state)
    print_manifest(manifest)

    if args.manifest and not args.sync:
        return

    if manifest["summary"]["new"] == 0:
        print("✅ Nothing new to sync.")
        return

    if not args.auto:
        answer = input(f"Sync {manifest['summary']['new']} item(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    synced = do_sync(manifest, notebook_id, state)
    if synced > 0:
        trigger_ingest()
        print(f"\n✅ Synced {synced} item(s) to raw/notebooklm/{notebook_slug}/")
    else:
        print("\n⚠️  Nothing was synced (all items skipped or rejected).")


if __name__ == "__main__":
    main()
