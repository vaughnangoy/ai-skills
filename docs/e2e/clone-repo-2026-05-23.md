# E2E test plan: clone-repo

**Created:** 2026-05-23 (retrospective — backfilled during the `feature/feature-creator-skill` worktree-strategy adoption)
**Feature branch:** `feature/feature-creator-skill`
**Source of truth:** [`clone-repo/SKILL.md`](../../clone-repo/SKILL.md)
**Test status:** spec (no executable e2e harness yet — driven manually through the `/clone-repo` slash command in VS Code Copilot Chat or Claude Code)

---

## Scenario 1 (happy) — Clone a public repo over SSH with shorthand

**Setup**
- `~/.copilot/skills/clone-repo/config.json` exists with `basePath` set to a writeable absolute path (e.g. `/tmp/clone-repo-e2e`)
- SSH key registered with the GitHub account that has read access to `octocat/Hello-World`
- `ssh -T git@github.com` returns `Hi <user>!`

**Steps**
1. In a Copilot Chat session run `/clone-repo octocat/Hello-World`
2. When the SSH connectivity check passes, the skill presents the confirmation table — reply `yes`
3. Wait for the clone to finish and the success summary to render
4. When asked "Would you like to open `Hello-World` in a new window?" reply `no`

**Expected**
- The directory `<basePath>/octocat/Hello-World/` exists and contains a valid `.git` directory
- Confirmation summary shows `Auth method: SSH ✅` and the rendered URL is `git@github.com:octocat/Hello-World.git`
- Temp files `/tmp/.clone_repo_ssh_check`, `/tmp/.clone_repo_https_check`, `/tmp/.clone_repo_clone_out` are deleted
- `config.json` was not modified

---

## Scenario 2 (happy) — Update the base path with `--set-base-path`

**Setup**
- `~/.copilot/skills/clone-repo/config.json` exists with some prior `basePath` value

**Steps**
1. Run `/clone-repo --set-base-path /tmp/clone-repo-e2e-new`
2. Observe the skill's confirmation message

**Expected**
- `config.json` now contains `"basePath": "/tmp/clone-repo-e2e-new"`
- No clone is performed (no new directories created under the new path)
- No SSH or HTTPS connectivity check runs

---

## Scenario 3 (sad) — Cancel HTTPS PAT prompt when SSH is unavailable

**Setup**
- `~/.copilot/skills/clone-repo/config.json` has `basePath` set and `httpsPat` empty
- SSH is intentionally broken (e.g. unset `SSH_AUTH_SOCK` and remove identities) so that `ssh -Tn git@github.com` fails with `Permission denied`

**Steps**
1. Run `/clone-repo octocat/Hello-World`
2. The skill's SSH check fails → the skill walks through the HTTPS PAT setup guidance
3. When prompted to paste a PAT, reply `cancel`

**Expected**
- The skill prints the cancellation message and stops
- No directory is created under `<basePath>`
- `config.json` is not modified (no PAT is written)
- Temp files `/tmp/.clone_repo_ssh_check`, `/tmp/.clone_repo_https_check`, `/tmp/.clone_repo_clone_out` are cleaned up before the skill exits

---

## How to execute

These scenarios are **spec-only** today. To execute them as automated e2e:

1. Build a harness that scripts a Copilot Chat (or Claude Code) session — feasible options include the `claude-code` CLI driving non-interactive sessions, or a recorded `expect(1)` script around the slash command surface
2. Sandbox SSH agent state per scenario so Scenario 3 can deterministically fail SSH
3. Use a disposable `basePath` per run (`mktemp -d`) and assert on the resulting filesystem state with `test -d <path>/.git`
4. For Scenario 2, snapshot `config.json` before/after and diff
