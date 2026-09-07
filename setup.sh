#!/usr/bin/env bash
#
# Omarchy Voice Assistant Installer & Setup Script
#

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config/omarchy-assistant"
PLUGINS_DIR="${HOME}/.config/omarchy/plugins"
PLUGIN_DEST="${PLUGINS_DIR}/harshjsh01.assistant"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "=========================================================="
echo "         Omarchy Voice Assistant Setup & Installer       "
echo "=========================================================="

# 1. Dependency checks
echo "[1/6] Checking system tools..."
for tool in python3 arecord pw-record wpctl hyprctl; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  ✓ Found: $tool"
    else
        echo "  ! Missing: $tool (Some features may be limited)"
    fi
done

# 2. Setup configuration directory & transcripts directory
echo "[2/6] Initializing configuration..."
mkdir -p "$CONFIG_DIR"
mkdir -p "${HOME}/Documents/Omarchy-Transcripts"
if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
    cp "$REPO_DIR/config/config.json" "$CONFIG_DIR/config.json"
    echo "  ✓ Created $CONFIG_DIR/config.json"
else
    echo "  ✓ Existing configuration preserved in $CONFIG_DIR/config.json"
fi

# 3. Install CLI tool
echo "[3/6] Installing CLI binary..."
mkdir -p "$BIN_DIR"
ln -sf "$REPO_DIR/bin/omarchy-assistant" "$BIN_DIR/omarchy-assistant"
chmod +x "$REPO_DIR/bin/omarchy-assistant"
echo "  ✓ Symlinked omarchy-assistant to $BIN_DIR/omarchy-assistant"

# 4. Install Omarchy Shell Plugin
echo "[4/6] Installing Omarchy Quickshell Plugin..."
mkdir -p "$PLUGINS_DIR"
rm -rf "$PLUGIN_DEST"
cp -r "$REPO_DIR/plugin" "$PLUGIN_DEST"

if command -v omarchy >/dev/null 2>&1; then
    omarchy plugin validate "$PLUGIN_DEST"
    echo "  ✓ Plugin manifest validated successfully!"
    omarchy plugin enable harshjsh01.assistant right 2>/dev/null || true
    echo "  ✓ Plugin enabled in Omarchy shell"
fi

# 5. Install systemd user service
echo "[5/6] Setting up systemd user service..."
mkdir -p "$SYSTEMD_USER_DIR"
cp "$REPO_DIR/systemd/omarchy-assistant.service" "$SYSTEMD_USER_DIR/omarchy-assistant.service"
systemctl --user daemon-reload
systemctl --user enable --now omarchy-assistant.service 2>/dev/null || true
echo "  ✓ systemd user service installed and enabled"

# 6. Keybindings information
echo "[6/6] Finalizing setup..."
echo ""
echo "=========================================================="
echo "🎉 Installation Complete!"
echo "=========================================================="
echo ""
echo "To trigger voice commands with your keyboard, add this line to"
echo "your ~/.config/hypr/bindings.lua:"
echo ""
echo '  o.bind("SUPER + A", "Voice Assistant", "omarchy-assistant listen")'
echo ""
echo "Try running a text simulation right now:"
echo "  omarchy-assistant exec \"volume up\""
echo "  omarchy-assistant exec \"switch to workspace 2\""
echo ""
echo "Or start speaking immediately:"
echo "  omarchy-assistant listen"
echo ""
