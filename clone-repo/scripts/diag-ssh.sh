#!/usr/bin/env bash
# clone-repo SSH diagnostics
# Run this in a fresh terminal and paste the output back into Copilot chat
# Usage: bash ~/.claude/skills/vaughnangoy-ai-skills/clone-repo/scripts/diag-ssh.sh

echo "=== clone-repo SSH diagnostics ==="
echo "Date: $(date)"
echo "Shell: $SHELL ($($SHELL --version 2>&1 | head -1))"
echo "User: $(whoami)"
echo ""

# --- 1. SSH agent ---
echo "--- SSH agent ---"
if [ -z "$SSH_AUTH_SOCK" ]; then
  echo "SSH_AUTH_SOCK: not set (agent may not be running)"
else
  echo "SSH_AUTH_SOCK: $SSH_AUTH_SOCK"
  ssh-add -l 2>&1 && echo "(keys listed above)" || echo "(no keys loaded or agent unreachable)"
fi
echo ""

# --- 2. SSH config ---
echo "--- SSH keys in ~/.ssh ---"
ls -1 ~/.ssh/*.pub 2>/dev/null || echo "(no public keys found in ~/.ssh)"
echo ""

# macOS-compatible millisecond timer
ms() { python3 -c "import time; print(int(time.time()*1000))"; }

# --- 3. Raw SSH test WITHOUT || true ---
echo "--- Test 1: without || true ---"
START=$(ms)
RAW_OUT=$(ssh -T git@github.com -o BatchMode=yes -o ConnectTimeout=5 2>&1)
RAW_EXIT=$?
END=$(ms)
echo "exit code : $RAW_EXIT"
echo "duration  : $((END - START))ms"
echo "output    : $RAW_OUT"
echo ""

# --- 4. SSH test WITH || true ---
echo "--- Test 2: with || true ---"
START=$(ms)
SAFE_OUT=$(ssh -T git@github.com -o BatchMode=yes -o ConnectTimeout=5 2>&1 || true)
SAFE_EXIT=$?
END=$(ms)
echo "exit code : $SAFE_EXIT"
echo "duration  : $((END - START))ms"
echo "output    : $SAFE_OUT"
echo ""

# --- 5. Verdict ---
echo "--- Verdict ---"
if echo "$SAFE_OUT" | grep -q "^Hi "; then
  echo "SSH: PASS (authenticated as: $(echo "$SAFE_OUT" | grep -o 'Hi [^!]*'))"
elif echo "$SAFE_OUT" | grep -qi "permission denied"; then
  echo "SSH: FAIL (permission denied — key not accepted by GitHub)"
elif [ -z "$SAFE_OUT" ]; then
  echo "SSH: FAIL (no output — likely timed out or agent unreachable)"
else
  echo "SSH: UNKNOWN — output did not match expected patterns"
fi

echo ""
echo "=== end diagnostics ==="
