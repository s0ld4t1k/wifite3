#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Host, adapter and dependency discovery for Wifite3.

This module is intentionally dependency-free (stdlib only) so the TUI and the
doctor keep working even when the attack toolchain is incomplete.  Every
external command is optional and failures are reported, never raised.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Basic environment
# --------------------------------------------------------------------------- #


def is_linux() -> bool:
    return platform.system().lower() == "linux"


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def is_tty() -> bool:
    try:
        return os.isatty(0) and os.isatty(1)
    except OSError:
        return False


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(argv: list[str], timeout: float = 5.0) -> tuple[int, str]:
    """Run a command quietly and return (returncode, output)."""
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            errors="replace",
        )
        return proc.returncode, proc.stdout or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


@dataclass(frozen=True)
class Distro:
    id: str
    name: str
    family: str  # fedora, debian, arch, suse, alpine, unknown
    version: str = ""

    @property
    def package_manager(self) -> str | None:
        return {
            "fedora": "dnf",
            "debian": "apt",
            "arch": "pacman",
            "suse": "zypper",
            "alpine": "apk",
        }.get(self.family)


def detect_distro() -> Distro:
    data: dict[str, str] = {}
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        try:
            for line in os_release.read_text(errors="replace").splitlines():
                if "=" not in line or line.startswith("#"):
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip().strip('"').strip("'")
        except OSError:
            pass

    distro_id = (data.get("ID") or platform.system()).lower()
    name = data.get("PRETTY_NAME") or distro_id
    version = data.get("VERSION_ID", "")
    like = (data.get("ID_LIKE") or "").lower().split()

    family = "unknown"
    if distro_id in {"fedora", "rhel", "centos", "rocky", "almalinux", "nobara"} or "fedora" in like or "rhel" in like:
        family = "fedora"
    elif distro_id in {"debian", "ubuntu", "linuxmint", "pop", "kali", "parrot", "raspbian"} or "debian" in like or "ubuntu" in like:
        family = "debian"
    elif distro_id in {"arch", "manjaro", "endeavouros", "garuda"} or "arch" in like:
        family = "arch"
    elif distro_id in {"opensuse", "opensuse-leap", "opensuse-tumbleweed", "sles"} or "suse" in like:
        family = "suse"
    elif distro_id == "alpine" or "alpine" in like:
        family = "alpine"

    if family == "unknown":
        # Last-resort sniffing for package managers.
        for family_name, manager in (
            ("fedora", "dnf"),
            ("debian", "apt"),
            ("arch", "pacman"),
            ("suse", "zypper"),
            ("alpine", "apk"),
        ):
            if shutil.which(manager):
                family = family_name
                break

    return Distro(id=distro_id, name=name, family=family, version=version)


# --------------------------------------------------------------------------- #
# Packages per distro
# --------------------------------------------------------------------------- #

CORE_TOOLS = [
    "airmon-ng",
    "airodump-ng",
    "aireplay-ng",
    "aircrack-ng",
    "iw",
    "ip",
]

OPTIONAL_TOOLS = {
    "reaver": "WPS Pixie-Dust / PIN attacks",
    "bully": "alternative WPS engine",
    "wash": "WPS discovery",
    "hashcat": "GPU/CPU hash cracking",
    "hcxdumptool": "PMKID capture",
    "hcxpcapngtool": "PMKID/hash conversion",
    "tshark": "handshake validation",
    "macchanger": "MAC randomisation",
    "hostapd": "Evil Twin AP",
    "dnsmasq": "Evil Twin DHCP/DNS",
    "cowpatty": "WPA handshake cracking",
    "john": "WPA handshake cracking",
    "wlancap2wpasec": "upload captures to wpa-sec",
    "bettercap": "advanced MITM / Evil Twin",
}

PACKAGES: dict[str, dict[str, list[str]]] = {
    "fedora": {
        "core": [
            "aircrack-ng",
            "iw",
            "iproute",
            "wireless-regdb",
            "usbutils",
            "pciutils",
            "rfkill",
            "wpa_supplicant",
        ],
        "optional": [
            "reaver",
            "bully",
            "hashcat",
            "hcxdumptool",
            "hcxtools",
            "wireshark-cli",
            "macchanger",
            "hostapd",
            "dnsmasq",
            "cowpatty",
            "john",
        ],
        "note": "Some WPS/Evil Twin packages live in RPM Fusion on Fedora.",
    },
    "debian": {
        "core": [
            "aircrack-ng",
            "iw",
            "iproute2",
            "wireless-regdb",
            "usbutils",
            "pciutils",
            "rfkill",
            "wpasupplicant",
        ],
        "optional": [
            "reaver",
            "bully",
            "hashcat",
            "hcxdumptool",
            "hcxtools",
            "tshark",
            "macchanger",
            "hostapd",
            "dnsmasq",
            "cowpatty",
            "john",
            "bettercap",
        ],
        "note": "Run `sudo apt update` first.",
    },
    "arch": {
        "core": [
            "aircrack-ng",
            "iw",
            "iproute2",
            "wireless-regdb",
            "usbutils",
            "pciutils",
            "rfkill",
            "wpa_supplicant",
        ],
        "optional": [
            "reaver",
            "bully",
            "hashcat",
            "hcxdumptool",
            "hcxtools",
            "wireshark-cli",
            "macchanger",
            "hostapd",
            "dnsmasq",
            "cowpatty",
            "john",
            "bettercap",
        ],
        "note": "Install optional tools from the AUR if a package is unavailable.",
    },
    "suse": {
        "core": [
            "aircrack-ng",
            "iw",
            "iproute2",
            "wireless-regdb",
            "usbutils",
            "pciutils",
            "rfkill",
            "wpa_supplicant",
        ],
        "optional": [
            "reaver",
            "bully",
            "hashcat",
            "hcxdumptool",
            "hcxtools",
            "wireshark",
            "macchanger",
            "hostapd",
            "dnsmasq",
            "cowpatty",
            "john",
        ],
        "note": "Enable the Packman repository for some wireless tools.",
    },
    "alpine": {
        "core": [
            "aircrack-ng",
            "iw",
            "iproute2",
            "wireless-regdb",
            "usbutils",
            "pciutils",
            "rfkill",
            "wpa_supplicant",
        ],
        "optional": [
            "reaver",
            "bully",
            "hashcat",
            "hcxdumptool",
            "hcxtools",
            "tshark",
            "macchanger",
            "hostapd",
            "dnsmasq",
            "cowpatty",
            "john",
        ],
        "note": "Enable the community repository (or edge/testing) for optional tools.",
    },
    "unknown": {"core": [], "optional": [], "note": "Unknown distribution; install the tools with your package manager."},
}


def install_command(family: str, include_optional: bool = True) -> list[str]:
    packages = PACKAGES.get(family, PACKAGES["unknown"])
    names = list(packages["core"])
    if include_optional:
        names += packages["optional"]
    if not names:
        return []
    if family == "fedora":
        return ["sudo", "dnf", "install", "-y"] + names
    if family == "debian":
        return ["sudo", "apt", "install", "-y"] + names
    if family == "arch":
        return ["sudo", "pacman", "-S", "--needed"] + names
    if family == "suse":
        return ["sudo", "zypper", "install", "-y"] + names
    if family == "alpine":
        return ["sudo", "apk", "add"] + names
    return []


# --------------------------------------------------------------------------- #
# Adapters
# --------------------------------------------------------------------------- #


@dataclass
class Adapter:
    name: str
    driver: str = ""
    chipset: str = ""
    phy: str = ""
    mode: str = "unknown"
    channel: str = ""
    connected_ssid: str = ""
    mac: str = ""
    state: str = "unknown"
    supports_monitor: bool | None = None
    supports_ap: bool | None = None
    bands: list[str] = field(default_factory=list)

    @property
    def is_monitor(self) -> bool:
        return self.mode.lower() in {"monitor", "monitormode"}

    @property
    def label(self) -> str:
        bits = [self.name]
        if self.driver:
            bits.append(self.driver)
        if self.phy:
            bits.append(f"phy{self.phy}")
        return "  ".join(bits)

    @property
    def capability_text(self) -> str:
        caps: list[str] = []
        if self.supports_monitor:
            caps.append("monitor")
        if self.supports_ap:
            caps.append("AP")
        if self.bands:
            caps.append("/".join(self.bands) + " GHz")
        return ", ".join(caps) or "unknown"


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def _phy_index(name: str) -> str:
    try:
        target = os.readlink(f"/sys/class/net/{name}/phy80211")
        match = re.search(r"phy(\d+)$", target)
        if match:
            return match.group(1)
    except OSError:
        pass
    for entry in Path("/sys/class/net").glob(f"{name}/phy80211"):
        match = re.search(r"phy(\d+)$", str(entry.resolve()))
        if match:
            return match.group(1)
    return ""


def _driver(name: str) -> str:
    for candidate in (
        f"/sys/class/net/{name}/device/driver",
        f"/sys/class/net/{name}/device/driver/module",
    ):
        try:
            return os.path.basename(os.path.realpath(candidate))
        except OSError:
            continue
    return ""


def _is_wireless(name: str) -> bool:
    base = Path(f"/sys/class/net/{name}")
    if (base / "wireless").exists() or (base / "phy80211").exists():
        return True
    # USB/PCI wireless devices may not expose a wireless/ directory on some
    # drivers; fall back to the typical interface name prefixes.
    return bool(re.match(r"^(wl|wlan|wlp|wlan|ath|ra|rtw)", name))


def _phy_caps(phy: str) -> tuple[bool | None, bool | None, list[str]]:
    if not phy or not command_exists("iw"):
        return None, None, []
    code, output = run_command(["iw", f"phy{phy}", "info"])
    if code != 0:
        return None, None, []
    lower = output.lower()
    monitor = bool(re.search(r"\*\s*monitor", lower))
    ap = bool(re.search(r"\*\s*ap\b", lower))
    bands: list[str] = []
    if re.search(r"24\d\d\s*mhz", lower):
        bands.append("2.4")
    if re.search(r"5\d\d\d\s*mhz", lower):
        bands.append("5")
    if re.search(r"59\d\d\s*mhz|6\d\d\d\s*mhz", lower):
        bands.append("6")
    return monitor, ap, bands


def list_adapters() -> list[Adapter]:
    """Return wireless interfaces (Linux) without touching monitor mode."""
    if not is_linux():
        return []
    net_dir = Path("/sys/class/net")
    if not net_dir.is_dir():
        return []

    adapters: list[Adapter] = []
    for entry in sorted(net_dir.iterdir()):
        name = entry.name
        if name == "lo" or not _is_wireless(name):
            continue
        adapter = Adapter(
            name=name,
            driver=_driver(name),
            phy=_phy_index(name),
            mac=_read_text(f"/sys/class/net/{name}/address"),
            state=_read_text(f"/sys/class/net/{name}/operstate"),
        )

        if command_exists("iw"):
            code, output = run_command(["iw", "dev", name, "info"])
            if code == 0:
                match = re.search(r"type\s+(\S+)", output)
                if match:
                    adapter.mode = match.group(1)
                match = re.search(r"channel\s+([\d.]+)\s*MHz", output)
                if match:
                    adapter.channel = match.group(1)
                if "ssid" in output:
                    match = re.search(r"ssid\s+(.+)", output)
                    if match:
                        adapter.connected_ssid = match.group(1).strip()

        if command_exists("iwconfig") and adapter.mode == "unknown":
            code, output = run_command(["iwconfig", name])
            if code == 0:
                match = re.search(r"Mode:(\S+)", output)
                if match:
                    adapter.mode = match.group(1)

        monitor, ap, bands = _phy_caps(adapter.phy)
        adapter.supports_monitor = monitor
        adapter.supports_ap = ap
        adapter.bands = bands
        adapters.append(adapter)
    return adapters


def interface_names() -> list[str]:
    return [adapter.name for adapter in list_adapters()]


def rfkill_blocked() -> bool:
    if not is_linux() or not command_exists("rfkill"):
        return False
    code, output = run_command(["rfkill", "list", "wifi"])
    return code == 0 and ("Soft blocked: yes" in output or "Hard blocked: yes" in output)


def network_manager_running() -> bool:
    return command_exists("systemctl") and any(
        run_command(["systemctl", "is-active", "--quiet", service])[0] == 0
        for service in ("NetworkManager", "wpa_supplicant")
    )


def kernel_version() -> str:
    return platform.release()


def python_version() -> str:
    return platform.python_version()
