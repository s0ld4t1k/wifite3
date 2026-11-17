#!/usr/bin/env bash
# Wifite3 installer for Linux.
#
#   ./install.sh            install system tools + wifite3 (/opt venv)
#   ./install.sh --no-deps  only install the Python app
#   ./install.sh --dev      editable install into ./.venv
#
# The script never runs `pip install` into the system Python. Fedora 38+,
# Ubuntu 23.04+, Debian 12+ and Arch all mark it externally managed, which is
# exactly the class of "installation error" Wifite3 is meant to avoid.

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
NO_DEPS=0
DEV=0

for arg in "$@"; do
    case "$arg" in
        --no-deps) NO_DEPS=1 ;;
        --dev) DEV=1 ;;
        -h|--help)
            sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "Wifite3 runs on Linux. Use 'wifite3 --demo' on other systems."
command -v python3 >/dev/null || die "python3 is required."

PYVER="$(python3 - <<'PY'
import sys
print('%d.%d' % sys.version_info[:2])
PY
)"
say "Python $PYVER detected"

# ---------------------------------------------------------------- distro ----
FAMILY="unknown"
if [ -r /etc/os-release ]; then
    . /etc/os-release
    case "${ID:-}${ID_LIKE:-}" in
        *fedora*|*rhel*|*centos*) FAMILY="fedora" ;;
        *debian*|*ubuntu*|*kali*|*mint*) FAMILY="debian" ;;
        *arch*|*manjaro*|*endeavour*) FAMILY="arch" ;;
        *suse*|*opensuse*) FAMILY="suse" ;;
        *alpine*) FAMILY="alpine" ;;
    esac
fi
say "Distribution family: $FAMILY"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null || die "sudo is required (or run as root)."
    SUDO="sudo"
fi

install_pkgs() {
    [ "$#" -gt 0 ] || return 0
    case "$FAMILY" in
        fedora)  $SUDO dnf install -y "$@" ;;
        debian)  $SUDO apt-get update -qq && $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
        arch)    $SUDO pacman -S --needed --noconfirm "$@" ;;
        suse)    $SUDO zypper --non-interactive install "$@" ;;
        alpine)  $SUDO apk add "$@" ;;
        *)       return 1 ;;
    esac
}

if [ "$NO_DEPS" -eq 0 ]; then
    # Keep the hard requirements separate: if an optional package name differs
    # on a derivative distro, the core tools still get installed.
    case "$FAMILY" in
        fedora)
            CORE=(aircrack-ng iw iproute wireless-regdb usbutils pciutils rfkill wpa_supplicant)
            OPTIONAL=(reaver bully hashcat hcxdumptool hcxtools wireshark-cli macchanger hostapd dnsmasq cowpatty john)
            ;;
        debian)
            CORE=(aircrack-ng iw iproute2 wireless-regdb usbutils pciutils rfkill wpasupplicant python3-venv)
            OPTIONAL=(reaver bully hashcat hcxdumptool hcxtools tshark macchanger hostapd dnsmasq cowpatty john bettercap)
            ;;
        arch)
            CORE=(aircrack-ng iw iproute2 wireless-regdb usbutils pciutils rfkill wpa_supplicant)
            OPTIONAL=(reaver bully hashcat hcxdumptool hcxtools wireshark-cli macchanger hostapd dnsmasq cowpatty john bettercap)
            ;;
        suse)
            CORE=(aircrack-ng iw iproute2 wireless-regdb usbutils pciutils rfkill wpa_supplicant)
            OPTIONAL=(reaver bully hashcat hcxdumptool hcxtools wireshark macchanger hostapd dnsmasq cowpatty john)
            ;;
        alpine)
            CORE=(aircrack-ng iw iproute2 wireless-regdb usbutils pciutils rfkill wpa_supplicant)
            OPTIONAL=(reaver bully hashcat hcxdumptool hcxtools tshark macchanger hostapd dnsmasq cowpatty john)
            ;;
        *)
            warn "Unknown distribution: install aircrack-ng, iw, iproute2 and wireless-regdb manually."
            CORE=(); OPTIONAL=()
            ;;
    esac

    if [ "${#CORE[@]}" -gt 0 ]; then
        say "Installing core wireless toolchain…"
        install_pkgs "${CORE[@]}" || die "Core package installation failed. Install: ${CORE[*]}"
    fi

    if [ "${#OPTIONAL[@]}" -gt 0 ]; then
        say "Installing optional attack tools (WPS, PMKID, Evil Twin, cracking)…"
        for pkg in "${OPTIONAL[@]}"; do
            install_pkgs "$pkg" >/dev/null 2>&1 || warn "optional package not available: $pkg"
        done
    fi
fi

# ----------------------------------------------------------- python app ----
if [ "$DEV" -eq 1 ]; then
    say "Creating .venv and installing Wifite3 in editable mode…"
    python3 -m venv "$HERE/.venv"
    "$HERE/.venv/bin/python" -m pip install --upgrade pip
    "$HERE/.venv/bin/pip" install -e "$HERE"
    cat <<EOF

Done. Run:
  sudo $HERE/.venv/bin/wifite3
  $HERE/.venv/bin/wifite3 --demo
EOF
    exit 0
fi

# Install to a root-owned location. Wifite3 needs elevated privileges to manage
# wireless interfaces, so pointing sudo at a user-writable pipx environment
# would let that user replace code which is later run as root.
say "Installing Wifite3 into an isolated venv at /opt/wifite3…"
$SUDO python3 -m venv /opt/wifite3/venv
$SUDO /opt/wifite3/venv/bin/python -m pip install --upgrade pip
$SUDO /opt/wifite3/venv/bin/pip install --force-reinstall "$HERE"
$SUDO ln -sf /opt/wifite3/venv/bin/wifite3 /usr/local/bin/wifite3
BIN=/usr/local/bin/wifite3

say "Running the system doctor…"
"$BIN" --doctor || true

cat <<EOF

\033[1;32mWifite3 installed.\033[0m
  TUI:      sudo wifite3
  Demo:     wifite3 --demo
  Doctor:   sudo wifite3 --doctor --deep
  Classic:  sudo wifite3 --classic --help
EOF
