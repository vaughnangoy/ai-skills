# E2E test plan: explain-code

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`explain-code/SKILL.md`](../../explain-code/SKILL.md)
**Test status:** spec (no executable e2e harness yet — driven manually through the `/explain-code` slash command)

---

## Scenario 1 (happy) — Explain Python code with default JavaScript comparison

**Setup**
- `~/.copilot/skills/explain-code/config.json` either does not exist or has `"compareToLanguage": "javascript"`
- A Python snippet selected in the active editor, e.g.:
  ```python
  squares = [x * x for x in range(10) if x % 2 == 0]
  ```

**Steps**
1. Run `/explain-code`
2. Wait for the full response to render

**Expected**
- Response opens with `**Detected language:** Python` and `**Comparison language:** JavaScript` banners
- `## What this code does` section explains the list comprehension using JS analogies (e.g. compares to `Array.from(...).filter(...).map(...)`)
- `## Equivalent in JavaScript` section contains a fenced ` ```javascript ` block with a functionally equivalent rewrite
- `## Source language docs (Python)` section lists 3–6 links to docs.python.org
- `## Comparison language docs (JavaScript)` section lists 3–6 links to MDN
- `config.json` is created if missing, containing `{"compareToLanguage": "javascript"}`

---

## Scenario 2 (happy) — Change comparison language to Rust mid-session

**Setup**
- A Go snippet selected in the editor, e.g.:
  ```go
  func sum(nums []int) int {
      total := 0
      for _, n := range nums {
          total += n
      }
      return total
  }
  ```
- `~/.copilot/skills/explain-code/config.json` exists with any prior `compareToLanguage`

**Steps**
1. Run `/explain-code --compare-to-language rust`
2. Observe the confirmation message about the config update
3. Wait for the full response

**Expected**
- Skill prints: "Comparison language updated to `rust`. I've saved this as your default…"
- `config.json` now contains `"compareToLanguage": "rust"`
- Response uses `**Comparison language:** Rust` banner
- `## Equivalent in Rust` section contains a fenced ` ```rust ` block with idiomatic Rust (e.g. `nums.iter().sum()`)
- `## Comparison language docs (Rust)` links point to `doc.rust-lang.org`

---

## Scenario 3 (sad) — No code selected and none pasted

**Setup**
- Editor has no active selection
- Chat prompt is exactly `/explain-code` with no additional text or code block

**Steps**
1. Run `/explain-code`

**Expected**
- Skill responds with the standard "No code detected" message and instructs the user to select a snippet or paste one
- No config.json is modified
- No detected/comparison banners are emitted
- No documentation links are emitted

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Use a harness that can pre-load specific text into the active editor selection (e.g. a VS Code extension test runner with `vscode.window.activeTextEditor.edit`)
2. Snapshot `~/.copilot/skills/explain-code/config.json` before/after for assertions
3. Capture the assistant response as plain text and assert on:
   - The banner lines via regex
   - Section header presence (`## What this code does`, etc.)
   - At least one fenced code block in the expected language
   - At least 3 hyperlinks pointing to the canonical docs domains
4. For Scenario 3, simply send the chat command with no selection and no code block, then assert the response contains "No code detected"
