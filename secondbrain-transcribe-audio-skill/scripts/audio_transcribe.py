"""
Audio download and transcription script for secondbrain-transcribe-audio-skill.

Downloads NotebookLM audio artifacts and transcribes them with faster-whisper,
producing enriched Markdown transcripts with YAML frontmatter for SecondBrain.

Usage:
    # Download only
    python audio_transcribe.py --download-only \
        --notebook <notebook_id> --artifact <artifact_id> \
        --out-dir <path>

    # Transcribe a downloaded file
    python audio_transcribe.py --transcribe \
        --audio <path/to/audio.mp3> \
        --notebook-slug <slug> \
        --notebook-title "My Notebook" \
        --artifact-id <artifact_id>

    # Download + transcribe in one step (default when neither flag given)
    python audio_transcribe.py \
        --notebook <notebook_id> --artifact <artifact_id> \
        --notebook-slug <slug> --notebook-title "My Notebook" \
        --out-dir <path>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Resolve uv venv python for faster-whisper ─────────────────────────

UV_ENV_DIR = Path("~/.copilot/skills/secondbrain-transcribe-audio-skill/venv").expanduser()
_UV_PYTHON = UV_ENV_DIR / "bin" / "python"
_WHISPER_PYTHON = str(_UV_PYTHON) if _UV_PYTHON.exists() else sys.executable

# ── Colour helpers ─────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✅{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}❌{RESET}  {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"     {msg}")


# ── Slugify ────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


# ── NotebookLM CLI helpers ─────────────────────────────────────────────

def run_nlm(*args: str) -> tuple[int, str]:
    result = subprocess.run(["notebooklm", *args], capture_output=True, text=True)
    return result.returncode, (result.stdout.strip() or result.stderr.strip())


def list_audio_artifacts(notebook_id: str) -> list[dict]:
    rc, output = run_nlm("artifact", "list", "--notebook", notebook_id,
                          "--type", "audio", "--json")
    if rc != 0:
        return []
    try:
        data = json.loads(output)
        return data if isinstance(data, list) else data.get("artifacts", [])
    except json.JSONDecodeError:
        return []


# ── Download ───────────────────────────────────────────────────────────

def download_audio(
    notebook_id: str,
    artifact_id: str,
    out_dir: Path,
    notebook_slug: str,
) -> Path | None:
    """Download audio artifact to out_dir, named nlm__<slug>__artifact__audio.mp3."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"nlm__{notebook_slug}__artifact__audio.mp3"

    print(f"\n⬇️   Downloading audio → {dest}")
    rc, output = run_nlm(
        "download", "audio",
        str(dest),
        "--notebook", notebook_id,
        "--artifact", artifact_id,
        "--force",
    )
    if rc != 0 or not dest.exists():
        fail(f"Download failed: {output[:300]}")
        return None

    size_mb = dest.stat().st_size / (1024 * 1024)
    ok(f"Downloaded {size_mb:.1f} MB → {dest.name}")
    return dest


# ── Transcription ──────────────────────────────────────────────────────

def transcribe_audio(audio_path: Path) -> dict | None:
    """
    Transcribe audio_path using faster-whisper (medium model, device=auto).
    Returns dict with keys: text, segments, duration_seconds, language.
    Runs in the uv venv if available.
    """
    # Delegate to a subprocess so we isolate the import from the calling env
    script = """
import sys, json
from pathlib import Path
try:
    from faster_whisper import WhisperModel
except ImportError:
    print(json.dumps({"error": "faster-whisper not installed"}))
    sys.exit(1)

audio_path = Path(sys.argv[1])
model = WhisperModel("medium", device="auto", compute_type="auto")
segments_iter, info = model.transcribe(str(audio_path), beam_size=5)

segments = []
full_text = []
for seg in segments_iter:
    segments.append({
        "start": round(seg.start, 2),
        "end": round(seg.end, 2),
        "text": seg.text.strip(),
    })
    full_text.append(seg.text.strip())

print(json.dumps({
    "text": " ".join(full_text),
    "segments": segments,
    "duration_seconds": round(info.duration, 1) if info.duration else None,
    "language": info.language,
}))
"""
    result = subprocess.run(
        [_WHISPER_PYTHON, "-c", script, str(audio_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"Transcription failed:\n{result.stderr[:500]}")
        return None
    try:
        data = json.loads(result.stdout)
        if "error" in data:
            fail(data["error"])
            return None
        return data
    except json.JSONDecodeError:
        fail(f"Could not parse transcription output: {result.stdout[:300]}")
        return None


# ── Tag / category extraction ──────────────────────────────────────────

# Common domain keywords → category mapping
_DOMAIN_MAP: list[tuple[list[str], str]] = [
    (["machine learning", "deep learning", "neural", "model", "training", "dataset",
      "transformer", "llm", "embedding"], "AI/ML"),
    (["research", "study", "experiment", "hypothesis", "literature"], "Research Notes"),
    (["product", "roadmap", "sprint", "backlog", "feature", "ux", "user story"], "Product"),
    (["code", "programming", "software", "api", "function", "class", "deploy",
      "architecture", "database"], "Engineering"),
    (["finance", "revenue", "cost", "budget", "growth", "market", "startup"], "Business"),
    (["health", "medical", "clinical", "patient", "therapy", "diagnosis"], "Health"),
    (["history", "politics", "society", "culture", "economics"], "Social Science"),
    (["philosophy", "ethics", "logic", "argument", "theory"], "Philosophy"),
]

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "that", "this", "it", "its", "we", "i",
    "you", "he", "she", "they", "so", "if", "as", "by", "from", "about",
    "into", "through", "also", "than", "then", "when", "which", "who",
    "what", "there", "their", "they", "not", "all", "more", "very",
}


def extract_tags(text: str, notebook_title: str) -> list[str]:
    """Extract meaningful keyword tags from transcript text."""
    lower = text.lower()
    words = re.findall(r"\b[a-z][a-z\-]{3,}\b", lower)
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1

    # Top 10 by frequency, min 3 occurrences
    top = sorted(
        [(w, c) for w, c in freq.items() if c >= 3],
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    tags = [w for w, _ in top]

    # Always include standard tags
    tags = ["notebooklm", "audio-overview"] + [t for t in tags if t not in
            ("notebooklm", "audio", "overview")]

    return tags


def extract_categories(text: str, notebook_title: str, tags: list[str]) -> list[str]:
    """Map tags and text to high-level SecondBrain categories."""
    lower = (text + " " + notebook_title).lower()
    categories = []
    for keywords, category in _DOMAIN_MAP:
        if any(kw in lower for kw in keywords):
            categories.append(category)
    if not categories:
        categories = ["General"]
    return categories


# ── Markdown writer ────────────────────────────────────────────────────

def write_transcript_md(
    audio_path: Path,
    transcript: dict,
    notebook_slug: str,
    notebook_title: str,
    artifact_id: str,
) -> Path:
    """Write enriched Markdown transcript alongside the audio file."""
    dest = audio_path.parent / audio_path.name.replace(
        "__artifact__audio.mp3", "__artifact__audio-transcript.md"
    )

    text = transcript.get("text", "")
    duration = transcript.get("duration_seconds")
    language = transcript.get("language", "en")
    segments = transcript.get("segments", [])
    word_count = len(text.split())

    tags = extract_tags(text, notebook_title)
    categories = extract_categories(text, notebook_title, tags)
    transcribed_at = datetime.now(timezone.utc).astimezone().isoformat()

    # Build YAML frontmatter
    tags_yaml = "\n".join(f"  - {t}" for t in tags)
    cats_yaml = "\n".join(f"  - {c}" for c in categories)
    duration_str = f"{int(duration)}" if duration else "unknown"

    frontmatter = (
        f"---\n"
        f"title: \"Audio Overview: {notebook_title}\"\n"
        f"notebook: {notebook_slug}\n"
        f"artifact_id: {artifact_id}\n"
        f"source_type: notebooklm-audio\n"
        f"language: {language}\n"
        f"transcribed_at: {transcribed_at}\n"
        f"duration_seconds: {duration_str}\n"
        f"word_count: {word_count}\n"
        f"tags:\n{tags_yaml}\n"
        f"categories:\n{cats_yaml}\n"
        f"---\n\n"
    )

    # Build body
    body_lines = [
        f"# Audio Overview: {notebook_title}\n",
        f"> **Notebook:** {notebook_slug}  \n"
        f"> **Transcribed:** {transcribed_at}  \n"
        f"> **Duration:** {duration_str}s  |  **Words:** {word_count}  |  **Language:** {language}\n",
        "---\n",
        "## Transcript\n",
        text,
    ]

    if segments:
        body_lines += [
            "\n---\n",
            "## Timestamped Segments\n",
        ]
        for seg in segments:
            start = seg["start"]
            end = seg["end"]
            body_lines.append(f"**[{_fmt_time(start)} → {_fmt_time(end)}]** {seg['text']}\n")

    dest.write_text(frontmatter + "\n".join(body_lines), encoding="utf-8")
    return dest


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── CLI entry point ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and/or transcribe NotebookLM audio for SecondBrain"
    )
    parser.add_argument("--download-only", action="store_true",
                        help="Download audio only — do not transcribe")
    parser.add_argument("--transcribe", action="store_true",
                        help="Transcribe an already-downloaded audio file")
    parser.add_argument("--audio", help="Path to .mp3 file (for --transcribe)")
    parser.add_argument("--notebook", "-n", help="Notebook ID")
    parser.add_argument("--artifact", "-a", help="Artifact ID")
    parser.add_argument("--notebook-slug", default="notebook",
                        help="Slug for output filenames")
    parser.add_argument("--notebook-title", default="Notebook",
                        help="Human-readable notebook title")
    parser.add_argument("--out-dir", help="Output directory for audio")
    args = parser.parse_args()

    # ── Transcribe-only mode ──────────────────────────────────────────
    if args.transcribe:
        if not args.audio:
            fail("--audio <path> is required with --transcribe")
            sys.exit(1)
        audio_path = Path(args.audio)
        if not audio_path.exists():
            fail(f"Audio file not found: {audio_path}")
            sys.exit(1)

        print(f"\n🎙️  Transcribing {audio_path.name} ...")
        transcript = transcribe_audio(audio_path)
        if not transcript:
            sys.exit(1)

        artifact_id = args.artifact or "unknown"
        md_path = write_transcript_md(
            audio_path,
            transcript,
            args.notebook_slug,
            args.notebook_title,
            artifact_id,
        )
        ok(f"Transcript → {md_path.name}")
        ok(f"Words: {transcript.get('text','').count(' ') + 1}  |  "
           f"Duration: {transcript.get('duration_seconds', '?')}s")
        return

    # ── Download (+ optional transcribe) mode ─────────────────────────
    if not args.notebook:
        fail("--notebook <id> is required")
        sys.exit(1)
    if not args.artifact:
        fail("--artifact <id> is required")
        sys.exit(1)
    if not args.out_dir:
        fail("--out-dir <path> is required")
        sys.exit(1)

    out_dir = Path(args.out_dir).expanduser()
    audio_path = download_audio(
        args.notebook,
        args.artifact,
        out_dir,
        args.notebook_slug,
    )
    if not audio_path:
        sys.exit(1)

    if args.download_only:
        return

    # Proceed to transcribe
    print(f"\n🎙️  Transcribing ...")
    transcript = transcribe_audio(audio_path)
    if not transcript:
        print(f"\n{YELLOW}⚠️  Transcription failed — audio saved but not transcribed.{RESET}")
        print(f"   Retry later: python audio_transcribe.py --transcribe --audio {audio_path} "
              f"--notebook-slug {args.notebook_slug} "
              f"--notebook-title \"{args.notebook_title}\" "
              f"--artifact-id {args.artifact}")
        sys.exit(0)

    md_path = write_transcript_md(
        audio_path,
        transcript,
        args.notebook_slug,
        args.notebook_title,
        args.artifact,
    )
    ok(f"Transcript → {md_path.name}")
    info(f"Words: {transcript.get('text','').count(' ') + 1}  |  "
         f"Duration: {transcript.get('duration_seconds', '?')}s")
    print(f"\n✅ Ready to ingest:")
    print(f"   {audio_path}")
    print(f"   {md_path}")


if __name__ == "__main__":
    main()
