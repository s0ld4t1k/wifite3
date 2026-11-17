#!/usr/bin/env bash
# Remove a Wifite3 venv installation. System packages are left alone.
set -euo pipefail

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null; then
        SUDO="sudo"
    else
        warn "sudo not found; /opt/wifite3 and /usr/local/bin may need manual removal."
    fi
fi

# Also remove legacy pipx installs created by earlier installer versions.
if command -v pipx >/dev/null && pipx list 2>/dev/null | grep -q 'package wifite3'; then
    say "Uninstalling legacy pipx package wifite3…"
    pipx uninstall wifite3
fi

if [ -d /opt/wifite3 ]; then
    say "Removing /opt/wifite3…"
    $SUDO rm -rf /opt/wifite3
fi

if [ -L /usr/local/bin/wifite3 ]; then
    say "Removing /usr/local/bin/wifite3 symlink…"
    $SUDO rm -f /usr/local/bin/wifite3
fi

warn "Kept: user data in ~/.wifite3 (sessions, logs, OUI updates)."
warn "Kept: system packages (aircrack-ng, hashcat, …)."
