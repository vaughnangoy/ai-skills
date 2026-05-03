---
name: clone-repo
description: "Clone a git repository to a configurable base path. Organises clones as <base>/<git-username>/<repo-name>/. Use for /clone-repo, 'clone this repo', 'clone that repo', or any request to clone a GitHub or git repository to a local path. Checks SSH and HTTPS connectivity before cloning. Asks to confirm the repo, destination, and auth method before proceeding. Use this skill whenever the user wants to clone a repo, even if they don't say /clone-repo explicitly."
argument-hint: "[<repo-url>] — optional repository URL or GitHub shorthand (e.g. owner/repo)"
---

# Clone Repo Skill

Clones a git repository into a structured directory: `<basePath>/<git-username>/<repo-name>/`.

The base path and optional HTTPS PAT are configurable and persisted in `~/.copilot/skills/clone-repo/config.json`. SSH is the preferred auth method. Connectivity is verified before the user is asked to confirm, so the confirmation always reflects a working method.

---

## Configuration

Config is stored at `~/.copilot/skills/clone-repo/config.json`.

```json
{
  "basePath": "/path/to/your/base",
  "httpsPat": ""
}
```

- `basePath` — root directory under which all repos are cloned as `<basePath>/<gitUsername>/<repoName>/`
- `httpsPat` — optional GitHub Personal Access Token used for HTTPS clones (stored locally; never displayed in full)

Update either value at any time:
- `/clone-repo --set-base-path <path>`
- `/clone-repo --set-pat` (interactive — prompts securely in chat)

---

## Procedure

Follow these steps **exactly** when `/clone-repo` is invoked or the user asks to clone a repository.

---

### Step 0 — Handle admin flags

#### `--set-base-path <path>`
1. Validate: must be an absolute path starting with `/`.
2. Write `basePath` to `~/.copilot/skills/clone-repo/config.json`.
3. Confirm to the user and stop — do not clone.

#### `--set-pat`
1. Ask the user to paste their GitHub Personal Access Token (fine-grained or classic with `repo` scope).
2. Write `httpsPat` to config.
3. Confirm and stop — do not clone.

---

### Step 1 — Resolve the base path

Read `~/.copilot/skills/clone-repo/config.json`.

- If `basePath` is set → use it.
- If missing or empty → ask the user for an absolute path, validate it (must start with `/`), write to config, and confirm before continuing.

---

### Step 2 — Identify the repository

Check in this order:

1. **Argument** — URL or `owner/repo` shorthand passed directly after `/clone-repo`.
2. **Current workspace** — if VS Code has a git remote, suggest it as the default.
3. **Ask** — if neither is available:

> **Which repository would you like to clone?**
> Paste a full git URL or GitHub shorthand like `owner/repo`.

Accept:
- Full HTTPS: `https://github.com/owner/repo[.git]`
- Full SSH: `git@github.com:owner/repo[.git]`
- Shorthand: `owner/repo` → expand to `git@github.com:owner/repo.git`

---

### Step 3 — Check connectivity

Verify which auth methods are available **before** presenting the confirmation. Run checks silently and use the results to set `<authMethod>` and `<resolvedUrl>` for Step 4.

> **Important — avoid stalls in new sessions**: Shell initialisation (nvm, prompt themes etc.) adds latency when the terminal tool opens a fresh session. Combined with the SSH connection time, the tool can appear to hang. To avoid this, write SSH output directly to a temp file rather than capturing it in a subshell — a `$()` subshell waits for every child process to fully exit, which can stall even after the auth message appears. Reading from a file instead sidesteps this entirely. Always end with `; echo "---DONE---"` so the terminal tool has a clean signal to stop waiting.

**After running each check command: read the output, find `---DONE---`, and proceed immediately. Do NOT wait for the shell prompt to re-render — the zsh prompt (git status, nvm, etc.) continues generating output after the command finishes, which will stall the terminal tool indefinitely if you wait for it.**

#### 3a — Test SSH

Run the SSH check via terminal:

```bash
ssh -Tn git@github.com -o BatchMode=yes -o ConnectTimeout=5 > /tmp/.clone_repo_ssh_check 2>&1 || true; echo "---DONE---"
```

The `-n` flag redirects SSH stdin from `/dev/null` (prevents SSH waiting for input). The `|| true` ensures a non-zero exit code doesn't halt the chain. **Do not try to read the SSH result from terminal output** — the terminal tool may return before `---DONE---` appears. Instead, once the command has been submitted, **use the file reading tool to read `/tmp/.clone_repo_ssh_check`** to get the result.

Determine the result from the file contents:

- **Passes** if file contains `Hi ` (e.g. `Hi VaughnAngoyNewsUK!`)
- **Fails** if file contains `Permission denied`, `Connection timed out`, or is empty

If SSH passes → `authMethod = ssh`, `resolvedUrl = git@github.com:<gitUsername>/<repoName>.git`. Skip to Step 4.

#### 3b — Test HTTPS (only if SSH failed)

Read `httpsPat` from config.

**If a PAT is present in config**, test it by running via terminal:

```bash
git ls-remote https://<PAT>@github.com/<gitUsername>/<repoName>.git HEAD > /tmp/.clone_repo_https_check 2>&1 || true; echo "---DONE---"
```

Then **use the file reading tool to read `/tmp/.clone_repo_https_check`** for the result. Do not rely on terminal output.

- If this succeeds → `authMethod = https`. Continue to Step 4.
- If this fails (bad credentials, no access) → treat PAT as invalid. Inform the user and ask them to paste a new PAT. Write it to config and re-run from the start of Step 3b.

**If no PAT in config**, inform the user:

> **SSH is unavailable and no HTTPS token is configured.**
>
> To clone via HTTPS you need a GitHub Personal Access Token with `repo` scope.
>
> **To create one:**
> 1. Go to **GitHub → Settings → Developer settings → Personal access tokens**
> 2. Generate a new token with `repo` (or `contents: read`) scope
> 3. Copy the token and paste it here when prompted
>
> Please paste your PAT now, or type **cancel** to abort.

- If the user pastes a PAT → write it to config, re-run the HTTPS check.
- If `cancel` → stop and confirm cancellation.

#### 3c — Both methods unavailable

If both SSH and HTTPS checks fail:

> **❌ Cannot connect to GitHub via SSH or HTTPS.**
>
> Check your network connection and try again, or run `/clone-repo --set-pat` to configure HTTPS access.

Stop here.

---

### Step 4 — Parse username and repo name

From the input in Step 2, extract:

- **`gitUsername`** — the repository owner
- **`repoName`** — the repository name (strip `.git` suffix if present)

Build the full clone destination:

```
<basePath>/<gitUsername>/<repoName>
```

---

### Step 5 — Confirmation

Present a full summary before cloning. The `authMethod` and `resolvedUrl` come from Step 3.

> **Ready to clone**
>
> | | |
> |---|---|
> | **Repository** | `<resolvedUrl>` |
> | **GitHub user** | `<gitUsername>` |
> | **Destination** | `<fullClonePath>` |
> | **Auth method** | SSH ✅ *(preferred)* |
>
> **Options:**
> — **yes** to proceed
> — **path** to use a different destination
> — **repo** to use a different repository
> — **ssh** to switch to SSH *(with setup guidance if not currently available)*
> — **https** to switch to HTTPS *(PAT required; guidance provided if not configured)*
> — **cancel** to abort

Adjust the auth method row and available switch options based on what Step 3 found. Only offer switching to a method that isn't already active.

#### If `path`:
Ask for a new absolute path. Return to Step 5 with the updated destination.

#### If `repo`:
Ask for a new URL or shorthand. Return to Step 2.

#### If `ssh` (switching to SSH when not currently available):

> **To set up SSH for GitHub:**
> 1. Generate a key: `ssh-keygen -t ed25519 -C "your@email.com"`
> 2. Add to agent: `ssh-add ~/.ssh/id_ed25519`
> 3. Copy public key: `cat ~/.ssh/id_ed25519.pub`
> 4. Add it to **GitHub → Settings → SSH and GPG keys**
>
> Type **done** when complete and I'll recheck your SSH connection.

Re-run Step 3a. If SSH now passes, return to Step 5 with `authMethod = ssh`.

#### If `https` (switching to HTTPS when not currently available):
Re-run Step 3b (PAT flow). If HTTPS passes, return to Step 5 with `authMethod = https`.

#### If `cancel`:
> **Cloning cancelled.** Nothing was changed.

Stop here.

#### If `yes` / any affirmative:
Continue to Step 6.

---

### Step 6 — Clone the repository

Construct the final command based on the confirmed auth method. Write output to a temp file so the terminal tool doesn't stall — then use the file reading tool to read `/tmp/.clone_repo_clone_out` for the result once the command completes.

**SSH:**
```bash
git clone git@github.com:<gitUsername>/<repoName>.git <fullClonePath> > /tmp/.clone_repo_clone_out 2>&1; echo "---DONE---"
```

**HTTPS with PAT** (PAT is read from config — never echoed in chat):
```bash
git clone https://<PAT>@github.com/<gitUsername>/<repoName>.git <fullClonePath> > /tmp/.clone_repo_clone_out 2>&1; echo "---DONE---"
```

After submitting the command, **use the file reading tool to read `/tmp/.clone_repo_clone_out`** — do not rely on terminal output. A zero-byte file or a file containing `fatal:` or `error:` indicates failure.

---

### Step 7 — Summary

**Success:**

> **✅ Repository cloned successfully**
>
> | | |
> |---|---|
> | **Repository** | `<resolvedUrl (PAT masked if HTTPS)>` |
> | **GitHub user** | `<gitUsername>` |
> | **Cloned to** | `<fullClonePath>` |
> | **Auth method** | SSH / HTTPS |

**Failure:**

> **❌ Clone failed**
>
> **Error:** `<git error output>`

Diagnose from the error and suggest a specific fix:

| Error pattern | Suggested fix |
|---|---|
| `Permission denied (publickey)` | SSH key not added to GitHub or agent — see SSH setup guidance above |
| `Authentication failed` | PAT may be expired or missing `repo` scope — run `/clone-repo --set-pat` |
| `already exists and is not empty` | Choose a different destination path |
| `Could not resolve host` | Check network connection |

On failure, skip Steps 8 and 9 — do not clean up or offer to open the repo.

---

### Step 8 — Clean up temp files

Remove all temp files written during this session:

```bash
rm -f /tmp/.clone_repo_ssh_check /tmp/.clone_repo_https_check /tmp/.clone_repo_clone_out; echo "---DONE---"
```

Confirm in chat:

> 🧹 **Temp files cleaned up.**

---

### Step 9 — Offer to open the repo

Ask the user:

> **Would you like to open `<repoName>` in a new window?**
> — **yes** to open / **no** to finish

If **no** → stop here.

If **yes**:

#### Detect the IDE

Check for VS Code first — it's the most common and has a reliable environment variable:

```bash
echo "${TERM_PROGRAM:-unknown}"; echo "---DONE---"
```

Read the result via file reading tool isn't needed here — this is a simple echo, use terminal output directly.

| `TERM_PROGRAM` value | IDE |
|---|---|
| `vscode` | VS Code |
| `iTerm.app` | iTerm2 (no project open command) |
| anything else / unknown | Ask the user |

**If VS Code detected:**

```bash
code "<fullClonePath>"; echo "---DONE---"
```

Confirm in chat:

> **✅ Opened `<repoName>` in a new VS Code window.**

**If not VS Code** — ask the user:

> **Which IDE are you using?**
> — Type the name (e.g. `Cursor`, `Zed`, `WebStorm`, `IntelliJ`, `PyCharm`, `Windsurf`) or **cancel** to skip.

Use the CLI command for the detected IDE:

| IDE | CLI command |
|---|---|
| Cursor | `cursor "<fullClonePath>"` |
| Zed | `zed "<fullClonePath>"` |
| WebStorm | `webstorm "<fullClonePath>"` |
| IntelliJ IDEA | `idea "<fullClonePath>"` |
| PyCharm | `pycharm "<fullClonePath>"` |
| Windsurf | `windsurf "<fullClonePath>"` |

Run the appropriate command, then confirm in chat:

> **✅ Opened `<repoName>` in `<IDE name>`.**

If the command fails (not found on PATH), inform the user:

> **⚠️ Could not open automatically** — `<command>` not found on PATH.
> Open the repo manually at: `<fullClonePath>`
