#!/usr/bin/env bash
# Brainiac — one-line installer for Linux
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/uesleinasch/brainiac/main/scripts/install.sh | bash
#
# Environment overrides:
#   BRAINIAC_REPO         Git URL to clone from (default: https://github.com/uesleinasch/brainiac.git)
#   BRAINIAC_INSTALL_DIR  Where to clone the code (default: ~/.local/share/brainiac)
#   BRAINIAC_ROOT         Where your notes live (default: ~/brainiac)
#   BRAINIAC_REF          Branch/tag/commit to install (default: main)

set -euo pipefail

REPO_URL="${BRAINIAC_REPO:-https://github.com/uesleinasch/brainiac.git}"
INSTALL_DIR="${BRAINIAC_INSTALL_DIR:-$HOME/.local/share/brainiac}"
ROOT_DIR="${BRAINIAC_ROOT:-$HOME/brainiac}"
REF="${BRAINIAC_REF:-main}"
SKILLS_DIR="$HOME/.claude/skills"

# --- pretty output ---
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

# --- 1. prerequisites ---
log "Checking prerequisites"

command -v git >/dev/null 2>&1 || err "git not found — please install git first"

# Ubuntu 22.04 ships python3 → 3.10 by default but users often install 3.11 alongside;
# prefer the highest versioned interpreter that satisfies requires-python = ">=3.11".
PYTHON=""
PY_VER=""
for candidate in python3.13 python3.12 python3.11 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    ver=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null) || continue
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
        PYTHON="$candidate"
        PY_VER="$ver"
        break
    fi
done

[ -n "$PYTHON" ] || err "Python 3.11+ not found — install with: sudo apt install python3.11 python3.11-venv"
log "Using $PYTHON ($PY_VER)"

if ! "$PYTHON" -c 'import venv' 2>/dev/null; then
    err "venv module missing — try: sudo apt install ${PYTHON}-venv (Debian/Ubuntu)"
fi

# --- 2. clone (or refuse if exists) ---
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "brainiac already installed at $INSTALL_DIR"
    warn "  use ${BOLD}bash $INSTALL_DIR/scripts/update.sh${NC} to update"
    exit 1
fi

log "Cloning brainiac to $INSTALL_DIR (ref: $REF)"
mkdir -p "$(dirname "$INSTALL_DIR")"
git clone --depth=1 --branch "$REF" "$REPO_URL" "$INSTALL_DIR"

# --- 3. venv + install ---
log "Creating Python venv + installing brainiac"
cd "$INSTALL_DIR/tools/brainiac"
"$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .

BRAINIAC_BIN="$INSTALL_DIR/tools/brainiac/.venv/bin/brainiac"
[ -x "$BRAINIAC_BIN" ] || err "install failed: $BRAINIAC_BIN not found"

# --- 4. memory root ---
if [ -d "$ROOT_DIR" ] && [ "$(ls -A "$ROOT_DIR" 2>/dev/null)" ]; then
    warn "Memory root $ROOT_DIR exists and is not empty — preserving as-is"
else
    log "Creating memory root at $ROOT_DIR"
    mkdir -p "$ROOT_DIR/longMemory/episodic" \
             "$ROOT_DIR/shortMemory" \
             "$ROOT_DIR/semanticMemory" \
             "$ROOT_DIR/memoryTransfer"
fi

# --- 5. initialize index ---
log "Initializing SQLite index"
BRAINIAC_ROOT="$ROOT_DIR" "$BRAINIAC_BIN" reindex >/dev/null

# --- 6. install skills globally ---
log "Installing skills to $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
for skill_src in "$INSTALL_DIR/.claude/skills"/brainiac-*; do
    [ -d "$skill_src" ] || continue
    skill_name=$(basename "$skill_src")
    cp -rf "$skill_src" "$SKILLS_DIR/$skill_name"
done

# --- 7. register MCP server ---
if command -v claude >/dev/null 2>&1; then
    log "Registering MCP server with claude CLI"
    if claude mcp list 2>/dev/null | grep -q '^brainiac\s'; then
        warn "MCP server 'brainiac' already registered; skipping (use 'claude mcp remove brainiac' to reset)"
    else
        claude mcp add brainiac \
            --scope user \
            --env "BRAINIAC_ROOT=$ROOT_DIR" \
            -- "$BRAINIAC_BIN" mcp \
            || warn "claude mcp add failed — register manually (see below)"
    fi
else
    warn "claude CLI not found — install it to use the MCP server in Claude Code"
    warn "  Then run:"
    printf '    %sclaude mcp add brainiac --scope user --env BRAINIAC_ROOT=%s -- %s mcp%s\n' \
        "$BOLD" "$ROOT_DIR" "$BRAINIAC_BIN" "$NC"
fi

# --- done ---
echo
log "${BOLD}brainiac installed${NC}"
echo
echo "  Code:         $INSTALL_DIR"
echo "  Memory root:  $ROOT_DIR"
echo "  Skills:       $SKILLS_DIR/brainiac-*"
echo "  CLI:          $BRAINIAC_BIN"
echo
echo "  Try:"
echo "    BRAINIAC_ROOT=$ROOT_DIR $BRAINIAC_BIN stats"
echo
echo "  Update later:"
echo "    bash $INSTALL_DIR/scripts/update.sh"
echo
