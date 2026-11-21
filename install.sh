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

# Authenticate once up front: package-manager output is captured below, so a
# late password prompt would otherwise interleave with the progress bar.
NEEDS_SUDO=1
if [ "$DEV" -eq 1 ] && [ "$NO_DEPS" -eq 1 ]; then
    NEEDS_SUDO=0
fi
if [ -n "$SUDO" ] && [ "$NEEDS_SUDO" -eq 1 ]; then
    say "Requesting sudo privileges…"
    $SUDO -v || die "sudo authentication failed."
fi

# ------------------------------------------------------------- progress ----
STEP=0
TOTAL=0
BAR_WIDTH=28
STEP_LOG="$(mktemp "${TMPDIR:-/tmp}/wifite3-install.XXXXXX.log")"
cleanup() { rm -f "$STEP_LOG"; }
trap cleanup EXIT

# progress <label> — advance the bar and draw it on the current line.
progress() {
    STEP=$((STEP + 1))
    local pct=$(( STEP * 100 / TOTAL ))
    local filled=$(( STEP * BAR_WIDTH / TOTAL ))
    local empty=$(( BAR_WIDTH - filled ))
    local bar="" i
    for ((i = 0; i < filled; i++)); do bar+="█"; done
    for ((i = 0; i < empty; i++)); do bar+="░"; done
    if [ -t 1 ]; then
        printf '\r\033[K\033[1;36m[%s]\033[0m %3d%% (%d/%d) %s' \
            "$bar" "$pct" "$STEP" "$TOTAL" "$*"
    else
        printf '[%s] %3d%% (%d/%d) %s\n' "$bar" "$pct" "$STEP" "$TOTAL" "$*"
    fi
}

# Run a step quietly; its output is replayed only if it fails.
run_step() {
    local label="$1"
    shift
    progress "$label"
    : >"$STEP_LOG"
    if "$@" >>"$STEP_LOG" 2>&1; then
        return 0
    fi
    local rc=$?
    if [ -t 1 ]; then printf '\n'; fi
    warn "Step failed: $label"
    tail -n 40 "$STEP_LOG" >&2
    return "$rc"
}

# Optional packages are allowed to be unavailable; stay silent about details.
run_optional() {
    local label="$1"
    shift
    progress "$label"
    : >"$STEP_LOG"
    if "$@" >>"$STEP_LOG" 2>&1; then
        return 0
    fi
    if [ -t 1 ]; then printf '\n'; fi
    return 1
}

finish_progress() {
    if [ -t 1 ] && [ "$STEP" -gt 0 ]; then
        printf '\n'
    fi
}

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

CORE=()
OPTIONAL=()
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
            ;;
    esac
fi

# Count every step up front so the bar can show a real percentage.
TOTAL=0
if [ "$NO_DEPS" -eq 0 ]; then
    if [ "${#CORE[@]}" -gt 0 ]; then TOTAL=$((TOTAL + 1)); fi
    TOTAL=$((TOTAL + ${#OPTIONAL[@]}))
fi
if [ "$DEV" -eq 1 ]; then
    TOTAL=$((TOTAL + 3))
else
    TOTAL=$((TOTAL + 4))
fi
if [ "$TOTAL" -lt 1 ]; then TOTAL=1; fi

if [ "${#CORE[@]}" -gt 0 ]; then
    run_step "Installing core wireless toolchain" install_pkgs "${CORE[@]}" \
        || die "Core package installation failed. Install: ${CORE[*]}"
fi

for pkg in "${OPTIONAL[@]}"; do
    run_optional "Optional package: $pkg" install_pkgs "$pkg" \
        || warn "optional package not available: $pkg"
done

# ----------------------------------------------------------- python app ----
if [ "$DEV" -eq 1 ]; then
    run_step "Creating .venv" python3 -m venv "$HERE/.venv" \
        || die "Could not create the virtual environment."
    run_step "Upgrading pip" "$HERE/.venv/bin/python" -m pip install --upgrade pip \
        || die "Could not upgrade pip."
    run_step "Installing Wifite3 (editable)" "$HERE/.venv/bin/pip" install -e "$HERE" \
        || die "Could not install Wifite3."
    finish_progress
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
run_step "Creating /opt/wifite3/venv" $SUDO python3 -m venv /opt/wifite3/venv \
    || die "Could not create /opt/wifite3/venv."
run_step "Upgrading pip" $SUDO /opt/wifite3/venv/bin/python -m pip install --upgrade pip \
    || die "Could not upgrade pip."
run_step "Installing Wifite3" $SUDO /opt/wifite3/venv/bin/pip install --force-reinstall "$HERE" \
    || die "Could not install Wifite3."
run_step "Linking /usr/local/bin/wifite3" $SUDO ln -sf /opt/wifite3/venv/bin/wifite3 /usr/local/bin/wifite3 \
    || die "Could not create the wifite3 symlink."
finish_progress
BIN=/usr/local/bin/wifite3

say "Running the system doctor…"
"$BIN" --doctor || true

printf '\n\033[1;32mWifite3 installed.\033[0m\n'
printf '  TUI:      sudo wifite3\n'
printf '  Demo:     wifite3 --demo\n'
printf '  Doctor:   sudo wifite3 --doctor --deep\n'
printf '  Classic:  sudo wifite3 --classic --help\n'
