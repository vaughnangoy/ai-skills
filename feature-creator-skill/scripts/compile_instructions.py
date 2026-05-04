#!/usr/bin/env python3
"""
compile_instructions.py

Compiles feature-creator-skill/SKILL.md into the Copilot .instructions.md
format and writes it to the target instructions directory.

Usage:
  python3 compile_instructions.py <instructions_dir>
  python3 compile_instructions.py <instructions_dir> --check   # check only, no write
"""

import re
import sys
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"
OUTPUT_FILENAME = "vaughnangoy-ai-skills-feature-creator-skill.instructions.md"


def compile_skill(skill_path: Path) -> str:
    content = skill_path.read_text(encoding="utf-8")

    fm_match = re.match(r"^---\n(.+?)\n---\n", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"No YAML frontmatter found in {skill_path}")

    fm = fm_match.group(1)
    name_match = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    desc_match = re.search(r'^description:\s*"(.+)"$', fm, re.MULTILINE | re.DOTALL)

    if not name_match:
        raise ValueError("Missing 'name' in frontmatter")
    if not desc_match:
        raise ValueError("Missing 'description' in frontmatter")

    name = name_match.group(1).strip()
    desc = desc_match.group(1).strip()
    body = content[fm_match.end():].strip()

    return f"""---
applyTo: "**"
---
# Skill: {name}

> {desc}

{body}
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <instructions_dir> [--check]", file=sys.stderr)
        return 1

    instructions_dir = Path(sys.argv[1]).expanduser()
    check_only = "--check" in sys.argv

    if not SKILL_MD.exists():
        print(f"  ✗  SKILL.md not found at {SKILL_MD}", file=sys.stderr)
        return 1

    compiled = compile_skill(SKILL_MD)
    out_path = instructions_dir / OUTPUT_FILENAME

    if check_only:
        if out_path.exists():
            current = out_path.read_text(encoding="utf-8")
            if current == compiled:
                print(f"  ✓  {OUTPUT_FILENAME} is up to date")
                return 0
            else:
                print(f"  ⚠  {OUTPUT_FILENAME} exists but is out of date")
                return 1
        else:
            print(f"  ✗  {OUTPUT_FILENAME} not found in {instructions_dir}")
            return 1

    if not instructions_dir.exists():
        instructions_dir.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        current = out_path.read_text(encoding="utf-8")
        if current == compiled:
            print(f"  ·  Copilot instructions already up to date — skipping")
            return 0

    out_path.write_text(compiled, encoding="utf-8")
    print(f"  ✓  Written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
