#!/usr/bin/env bash
# install.sh — Meshtasticd Configuration Tool installer
#
# Usage (stable, from the main branch):
#   curl -fsSL <GITHUB_RAW_URL>/install.sh | bash
#
# Usage (beta branch, for testing changes before they reach main):
#   curl -fsSL <GITHUB_RAW_URL>/install.sh | bash -s -- --beta
#
# When piping to bash, arguments must come after "bash -s --"; anything typed
# after the URL would be handed to curl instead. Alternatively:
#   curl -fsSL <GITHUB_RAW_URL>/install.sh | MESHADV_BRANCH=beta bash
#
# Options:
#   --beta            install from the "beta" branch
#   --branch <name>   install from any branch
#


set -e

REPO_URL="https://github.com/chrismyers2000/Meshtasticd-Configuration-Tool"
BRANCH="${MESHADV_BRANCH:-main}"
INSTALL_DIR="$HOME/meshadv-config"
APP_NAME="meshadv-config.py"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

# ---- Parse arguments ----
while [ $# -gt 0 ]; do
    case "$1" in
        --beta)
            BRANCH="beta"
            ;;
        --branch)
            [ -n "${2:-}" ] || error "--branch requires a branch name."
            BRANCH="$2"
            shift
            ;;
        --branch=*)
            BRANCH="${1#--branch=}"
            ;;
        -h|--help)
            sed -n '2,17p' "$0" 2>/dev/null || echo "Options: --beta, --branch <name>"
            exit 0
            ;;
        *)
            error "Unknown option: $1 (valid: --beta, --branch <name>)"
            ;;
    esac
    shift
done

RAW_URL="https://raw.githubusercontent.com/chrismyers2000/Meshtasticd-Configuration-Tool/$BRANCH"

echo ""
echo "========================================"
echo "  Meshtasticd Configuration Tool"
echo "  by Frequency Labs"
echo "========================================"
echo ""
if [ "$BRANCH" != "main" ]; then
    warn "Installing from the '$BRANCH' branch (pre-release / testing build)."
else
    info "Installing from the main branch."
fi

# ---- Check Python 3 ----
info "Checking Python 3..."
if ! command -v python3 &>/dev/null; then
    warn "Python 3 not found. Installing..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 || error "Failed to install Python 3."
fi
PYTHON_VER=$(python3 -V 2>&1)
info "Found: $PYTHON_VER"

# ---- Check pip3 ----
info "Checking pip3..."
if ! command -v pip3 &>/dev/null; then
    warn "pip3 not found. Installing..."
    sudo apt-get install -y python3-pip || error "Failed to install pip3."
fi
info "pip3 OK."

# ---- Install Python dependencies ----
info "Installing Python dependencies (customtkinter, textual)..."
pip3 install --upgrade customtkinter textual 2>&1 || {
    warn "pip3 install failed, trying with --break-system-packages..."
    pip3 install --upgrade customtkinter textual --break-system-packages 2>&1 || \
    error "Failed to install Python dependencies."
}
info "Dependencies installed."

# ---- Download application files ----
info "Downloading Meshtasticd Configuration Tool to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/core" "$INSTALL_DIR/gui" "$INSTALL_DIR/tui"

FILES=(
    "meshadv-config.py"
    "core/__init__.py"
    "core/utils.py"
    "core/hardware.py"
    "core/config_editor.py"
    "core/actions.py"
    "core/installer.py"
    "gui/__init__.py"
    "gui/app.py"
    "tui/__init__.py"
    "tui/app.py"
)

for file in "${FILES[@]}"; do
    dest="$INSTALL_DIR/$file"
    mkdir -p "$(dirname "$dest")"
    curl -fsSL "$RAW_URL/$file" -o "$dest" || error "Failed to download $file from branch '$BRANCH'"
done

echo "$BRANCH" > "$INSTALL_DIR/.branch"
info "All files downloaded (branch: $BRANCH)."

# ---- Make executable ----
chmod +x "$INSTALL_DIR/$APP_NAME"
info "Made $APP_NAME executable."

# ---- Optional: desktop shortcut ----
DESKTOP_DIR="$HOME/.local/share/applications"
if [ -d "$DESKTOP_DIR" ]; then
    cat > "$DESKTOP_DIR/meshadv-config.desktop" << EOF
[Desktop Entry]
Name=Meshtasticd Config Tool
Comment=Configure meshtasticd for MeshAdv Pi Hat
Exec=python3 $INSTALL_DIR/$APP_NAME
Terminal=false
Type=Application
Categories=Utility;
# TODO: Add Icon= line once an icon asset is created (see ToDo.md item #8)
EOF
    info "Desktop shortcut created."
fi

# ---- Done ----
echo ""
echo "========================================"
info "Installation complete!"
echo ""
echo "  Run with:  python3 $INSTALL_DIR/$APP_NAME"
echo "  GUI mode:  python3 $INSTALL_DIR/$APP_NAME --gui"
echo "  TUI mode:  python3 $INSTALL_DIR/$APP_NAME --tui"
echo ""
echo "========================================"
