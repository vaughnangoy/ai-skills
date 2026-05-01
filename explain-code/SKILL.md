---
name: explain-code
description: "Explains a selected block of code to a JavaScript engineer. Detects the source language, describes what the code does in JS-friendly terms, provides a like-for-like JavaScript (or configured language) equivalent, and links to official documentation for both the source and comparison languages. Triggered by /explain-code. Use --compare-to-language <lang> to set or override the comparison language."
argument-hint: "[--compare-to-language <language>] — optional flag to set the comparison language (e.g. --compare-to-language python)"
---

# Explain Code Skill

Explains a selected code snippet to a **JavaScript engineer**. Detects the source language, translates the concepts into JS-familiar terms, provides a side-by-side equivalent, and surfaces official documentation links for both languages.

---

## Configuration

Config is stored at `~/.copilot/skills/explain-code/config.json`.

Default config:

```json
{
  "compareToLanguage": "javascript"
}
```

`compareToLanguage` controls which language is used for the "like-for-like" equivalent example. Defaults to `javascript` if not set or if the config file is absent.

---

## Procedure

Follow these steps **exactly** when `/explain-code` is invoked.

---

### Step 0 — Resolve comparison language

#### 0a — Check for `--compare-to-language` flag

If the invocation includes `--compare-to-language <lang>` (e.g. `/explain-code --compare-to-language python`):

1. Read the config file at `~/.copilot/skills/explain-code/config.json`.
2. Set `compareToLanguage` to the provided `<lang>`.
3. Write the updated value back to the config file.
4. Output this friendly message to the chat window **before continuing**:

> **Comparison language updated to `<lang>`.**
> I've saved this as your default for all future `/explain-code` calls. You can change it at any time by running `/explain-code --compare-to-language <language>`.
> Continuing with your explanation now…

#### 0b — No flag provided — read from config

Read `~/.copilot/skills/explain-code/config.json`.

- If `compareToLanguage` is set → use that value as the comparison language.
- If the config file is missing or `compareToLanguage` is absent or empty:
  1. Default to `javascript`.
  2. Write `{ "compareToLanguage": "javascript" }` to the config file.
  3. Output this friendly message to the chat window **before continuing**:

> **No comparison language configured — defaulting to JavaScript.**
> I've saved `javascript` as your default comparison language in `~/.copilot/skills/explain-code/config.json`. Run `/explain-code --compare-to-language <language>` at any time to change it.
> Continuing with your explanation now…

---

### Step 1 — Identify the selected code

Use the code currently selected in the editor, or the code block provided in the message.

If no code is selected and none is pasted, respond:

> **No code detected.** Please select a code snippet in the editor or paste one into the chat, then run `/explain-code` again.

---

### Step 2 — Detect the source language

Identify the programming language of the selected code. Be explicit — state the detected language at the top of your response.

If the source language matches the comparison language, note that and skip the translation section (Step 4), instead providing a pure explanation with documentation links only.

---

### Step 3 — Explain the code

Provide a clear explanation of what the code does, written **for a JavaScript engineer**.

Your explanation must:
- Use JavaScript terminology and analogies where helpful (e.g. "this is similar to `Array.prototype.map`", "think of this like a `Promise`")
- Describe the intent, not just the syntax
- Call out any patterns, idioms, or language-specific behaviours that differ from JavaScript (e.g. memory management, type systems, immutability, concurrency models)
- Be concise — avoid restating the code line-by-line unless the logic is complex

Format:

```
## What this code does

<explanation>
```

---

### Step 4 — Like-for-like equivalent in the comparison language

Rewrite the selected code as a **functionally equivalent** snippet in the comparison language (from Step 0), as a JavaScript engineer would naturally write it.

Rules:
- Use idiomatic style for the comparison language (e.g. `const`, arrow functions, `async/await` for JavaScript)
- Preserve the same logic and intent — do not simplify or embellish
- Add brief inline comments only where a concept has no direct JavaScript equivalent
- If the comparison language is the same as the source language, skip this section

Format:

````
## Equivalent in <ComparisonLanguage>

```<comparison-language>
<code>
```
````

---

### Step 5 — Documentation links for the source language

Provide a curated list of links to **official documentation** relevant to the selected code — for the **source language**.

Focus on:
- The language's standard library or built-in functions used
- Relevant language features or patterns demonstrated
- Official API references (not blog posts or third-party tutorials)

Format:

```
## Source language docs (<SourceLanguage>)

- [<Topic>](<url>) — <one-line description>
- [<Topic>](<url>) — <one-line description>
```

Provide 3–6 links. If a canonical documentation URL cannot be determined with confidence, omit that entry rather than guessing.

---

### Step 6 — Documentation links for the comparison language

Provide a curated list of links to **official documentation** relevant to the **comparison language** equivalent.

Focus on:
- The comparison-language equivalents of what was used in the source code
- Key APIs, methods, or patterns referenced in Step 4

Format:

```
## Comparison language docs (<ComparisonLanguage>)

- [<Topic>](<url>) — <one-line description>
- [<Topic>](<url>) — <one-line description>
```

Provide 3–6 links. Same rule applies — omit uncertain links rather than guessing.

---

### Step 7 — Assemble the full response

Output the complete response in this order:

1. Detected language banner (e.g. `**Detected language:** Python`)
2. Comparison language banner (e.g. `**Comparison language:** JavaScript`)
3. `## What this code does`
4. `## Equivalent in <ComparisonLanguage>` *(skip if same language)*
5. `## Source language docs (<SourceLanguage>)`
6. `## Comparison language docs (<ComparisonLanguage>)` *(skip if same language)*

---

## Examples of valid invocations

| Invocation | Behaviour |
|---|---|
| `/explain-code` | Uses `compareToLanguage` from config (default: `javascript`) |
| `/explain-code --compare-to-language rust` | Updates config to `rust`, explains using Rust as the comparison |
| `/explain-code --compare-to-language python` | Updates config to `python`, explains using Python as the comparison |
