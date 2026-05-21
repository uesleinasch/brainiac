#!/usr/bin/env bash
# Brainiac — update to latest version
#
# Usage:
#   bash ~/.local/share/brainiac/scripts/update.sh
#
# Environment overrides:
#   BRAINIAC_INSTALL_DIR  Where brainiac is installed (default: ~/.local/share/brainiac)

set -euo pipefail

INSTALL_DIR="${BRAINIAC_INSTALL_DIR:-$HOME/.local/share/brainiac}"
SKILLS_DIR="$HOME/.claude/skills"

if [ -t 1 ]; then
    GREEN=$'\033[0;32m'
    YELLOW=$'\033[0;33m'
    RED=$'\033[0;31m'
    BOLD=$'\033[1m'
    NC=$'\033[0m'
else
    GREEN="" YELLOW="" RED="" BOLD="" NC=""
fi

log()  { printf '%s==>%s %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%s!!%s %s\n' "$YELLOW" "$NC" "$*"; }
err()  { printf '%sxx%s %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

# --- sanity ---
[ -d "$INSTALL_DIR/.git" ] || err "brainiac not installed at $INSTALL_DIR — run install.sh first"

# --- 1. git pull ---
log "Pulling latest from origin"
cd "$INSTALL_DIR"
BEFORE=$(git rev-parse HEAD)
git fetch --quiet origin
git pull --ff-only --quiet
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    log "Already up to date ($(git rev-parse --short HEAD))"
else
    log "Updated $(echo $BEFORE | cut -c1-7) → $(echo $AFTER | cut -c1-7)"
fi

# --- 2. upgrade Python package ---
log "Upgrading Python package"
cd "$INSTALL_DIR/tools/brainiac"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet --upgrade -e .

# --- 3. re-sync skills ---
log "Re-syncing skills to $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
for skill_src in "$INSTALL_DIR/.claude/skills"/brainiac-*; do
    [ -d "$skill_src" ] || continue
    skill_name=$(basename "$skill_src")
    cp -rf "$skill_src" "$SKILLS_DIR/$skill_name"
done

# --- 4. reindex (schema migrations are idempotent in connect()) ---
ROOT_DIR="${BRAINIAC_ROOT:-$HOME/brainiac}"
if [ -d "$ROOT_DIR/memoryTransfer" ]; then
    log "Reindexing $ROOT_DIR (applies schema migrations)"
    BRAINIAC_ROOT="$ROOT_DIR" "$INSTALL_DIR/tools/brainiac/.venv/bin/brainiac" reindex >/dev/null
fi

echo
log "${BOLD}brainiac updated${NC} ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"
echo
