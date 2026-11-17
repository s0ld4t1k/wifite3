#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reusable presentation helpers for the Wifite3 TUI."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rich.text import Text
from textual.widgets import DataTable

from ..model.target import WPSState

ENC_STYLES = {
    "WPA3": "bold magenta",
    "WPA2": "bold cyan",
    "WPA": "bold green",
    "WEP": "bold red",
    "OWE": "bold yellow",
    "OPEN": "dim white",
    "WPA2/WPA3": "bold magenta",
}

AUTH_STYLES = {
    "SAE": "magenta",
    "PSK": "cyan",
    "MGT": "red",
    "OWE": "yellow",
}

COLUMNS: list[tuple[str, str, int | None]] = [
    ("sel", "", 2),
    ("ssid", "SSID", 22),
    ("bssid", "BSSID", 17),
    ("ch", "CH", 3),
    ("band", "BAND", 4),
    ("enc", "ENCR", 8),
    ("auth", "AUTH", 6),
    ("pwr", "PWR", 5),
    ("wps", "WPS", 4),
    ("cli", "CLI", 3),
]


def power_dbm(target: Any) -> str:
    power = getattr(target, "power", 0) or 0
    if power <= 0:
        return "--"
    return f"-{max(0, 100 - int(power))}"


def signal_bar(target: Any) -> str:
    power = getattr(target, "power", 0) or 0
    if power >= 75:
        return "[bold green]▂▄▆█[/]"
    if power >= 50:
        return "[green]▂▄▆[/]"
    if power >= 25:
        return "[yellow]▂▄[/]"
    if power > 0:
        return "[red]▂[/]"
    return "[dim]·[/]"


def wps_label(target: Any) -> str:
    state = getattr(target, "wps", WPSState.NONE)
    return {
        WPSState.UNLOCKED: "[bold green]open[/]",
        WPSState.LOCKED: "[yellow]lock[/]",
        WPSState.UNKNOWN: "[dim]?[/]",
        WPSState.NONE: "[dim]—[/]",
    }.get(state, "[dim]—[/]")


def band_label(target: Any) -> str:
    frequency = getattr(target, "frequency", None)
    if frequency:
        if 2400 <= frequency < 2500:
            return "2.4"
        if 5150 <= frequency < 5925:
            return "5"
        if 5925 <= frequency <= 7125:
            return "6"
    channel = getattr(target, "channel", -1)
    if 1 <= channel <= 14:
        return "2.4"
    if 32 <= channel <= 177:
        return "5"
    if channel > 177:
        return "6"
    return "?"


def ssid_text(target: Any) -> Text:
    essid = getattr(target, "essid", None)
    known = getattr(target, "essid_known", False)
    if known and essid:
        text = Text(essid[:26], style="bold white")
        if getattr(target, "decloaked", False):
            text.append(" *", style="magenta")
        return text
    text = Text(f"({getattr(target, 'bssid', 'hidden')})", style="dim italic")
    if getattr(target, "decloaked", False):
        text.append(" *", style="magenta")
    return text


def encryption_text(target: Any) -> Text:
    enc = getattr(target, "primary_encryption", None) or getattr(target, "encryption", "") or "?"
    style = ENC_STYLES.get(enc, "white")
    if getattr(target, "wpa3_info", None) is not None and enc in {"WPA2", "WPA"}:
        style = "magenta"
    return Text(enc, style=style)


def auth_text(target: Any) -> Text:
    auth = getattr(target, "primary_authentication", None) or getattr(target, "authentication", "") or "—"
    return Text(auth, style=AUTH_STYLES.get(auth, "dim"))


def vendor_for(bssid: str) -> str:
    try:
        from ..config import Configuration

        Configuration.load_manufacturers()
        oui = bssid.replace(":", "").upper()[:6]
        return (Configuration.manufacturers or {}).get(oui, "") or "unknown"
    except Exception:
        return "unknown"


def target_details(target: Any, selected: bool) -> Text:
    """Rich text for the detail pane."""
    essid = target.essid if getattr(target, "essid_known", False) else "(hidden SSID)"
    vendor = vendor_for(target.bssid)
    clients = getattr(target, "clients", []) or []
    lines = Text()
    lines.append("  " + (essid or "(hidden)") + "\n", style="bold white")
    lines.append(f"  {target.bssid}", style="cyan")
    lines.append(f"   vendor: {vendor}\n", style="dim")
    lines.append(
        f"  ch {target.channel} · {band_label(target)} GHz · {power_dbm(target)} dBm · "
        f"{getattr(target, 'beacons', 0)} beacons\n",
        style="white",
    )
    enc = getattr(target, "primary_encryption", target.encryption)
    auth = getattr(target, "primary_authentication", target.authentication)
    lines.append(f"  security: {enc} / {auth}", style=ENC_STYLES.get(enc, "white"))
    if getattr(target, "wpa3_info", None) is not None:
        pmf = getattr(target.wpa3_info, "pmf_status", "?")
        transition = " transition" if getattr(target.wpa3_info, "is_transition", False) else ""
        lines.append(f" · PMF {pmf}{transition}", style="magenta")
    lines.append("\n")
    lines.append(f"  WPS: {Text.from_markup(wps_label(target)).plain} · clients: {len(clients)}", style="white")
    if selected:
        lines.append("  ·  SELECTED FOR ATTACK", style="bold green")
    lines.append("\n")
    if clients:
        names = ", ".join(getattr(client, "station", "?") for client in clients[:6])
        if len(clients) > 6:
            names += f" +{len(clients) - 6}"
        lines.append(f"  {names}\n", style="dim")
    if getattr(target, "honeypot_score", 0):
        lines.append(f"  ⚠ honeypot score {target.honeypot_score}: ", style="yellow")
        lines.append(", ".join(getattr(target, "honeypot_reasons", [])), style="dim")
        lines.append("\n")
    if selected:
        lines.append("  [space] deselect · [enter] attack · [d] full details", style="dim")
    else:
        lines.append("  [space] select · [enter] attack · [d] full details", style="dim")
    return lines


def sort_targets(
    targets: list[Any], column: str, reverse: bool = False, query: str = ""
) -> list[Any]:
    query = query.strip().lower()
    if query:
        targets = [
            target
            for target in targets
            if query in (getattr(target, "essid", "") or "").lower()
            or query in getattr(target, "bssid", "").lower()
            or query in vendor_for(getattr(target, "bssid", "")).lower()
        ]

    def key(target: Any):
        if column == "ssid":
            return (getattr(target, "essid", "") or "~").lower()
        if column == "bssid":
            return getattr(target, "bssid", "")
        if column == "ch":
            return getattr(target, "channel", 0)
        if column == "band":
            return band_label(target)
        if column == "enc":
            return getattr(target, "primary_encryption", "")
        if column == "auth":
            return getattr(target, "primary_authentication", "")
        if column == "pwr":
            return getattr(target, "power", 0)
        if column == "wps":
            return 1 if getattr(target, "wps", 0) == WPSState.UNLOCKED else 0
        if column == "cli":
            return len(getattr(target, "clients", []) or [])
        return getattr(target, "power", 0)

    return sorted(targets, key=key, reverse=reverse)


def short_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def add_target_row(table: DataTable, target: Any, selected: bool) -> None:
    marker = Text("●", style="bold green") if selected else Text("○", style="dim")
    table.add_row(
        marker,
        ssid_text(target),
        Text(target.bssid, style="dim"),
        Text(str(target.channel), style="cyan" if target.channel > 14 else "white"),
        Text(band_label(target), style="magenta" if band_label(target) == "6" else "dim"),
        encryption_text(target),
        auth_text(target),
        Text(power_dbm(target), style="white"),
        Text.from_markup(wps_label(target)),
        Text(str(len(getattr(target, "clients", []) or [])), style="green" if getattr(target, "clients", None) else "dim"),
        key=target.bssid,
    )
