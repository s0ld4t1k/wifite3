#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`wifite3 --doctor`: explain exactly what is missing and how to fix it."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field

from . import system
from .system import (
    CORE_TOOLS,
    OPTIONAL_TOOLS,
    PACKAGES,
    Adapter,
    command_exists,
    detect_distro,
    install_command,
    is_linux,
    is_root,
    list_adapters,
)


@dataclass
class Check:
    title: str
    status: str  # ok | warn | fail | info
    detail: str = ""
    hint: str = ""
    group: str = "System"

    @property
    def icon(self) -> str:
        return {"ok": "✔", "warn": "!", "fail": "✘", "info": "•"}.get(self.status, "•")


@dataclass
class Report:
    distro: system.Distro
    checks: list[Check] = field(default_factory=list)
    adapters: list[Adapter] = field(default_factory=list)
    install_cmd: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == "fail"]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == "warn"]

    @property
    def ready(self) -> bool:
        return not self.failures


def _python_dependency(name: str, package: str) -> Check:
    try:
        importlib.import_module(name)
        return Check(f"Python: {package}", "ok", group="Python", detail=f"import {name}")
    except Exception as exc:  # pragma: no cover - depends on environment
        return Check(
            f"Python: {package}",
            "fail",
            group="Python",
            detail=str(exc),
            hint=f"pip install {package}",
        )


def collect_report(deep: bool = False) -> Report:
    distro = detect_distro()
    report = Report(distro=distro)

    # OS / privileges -----------------------------------------------------
    report.checks.append(
        Check(
            "Linux host",
            "ok" if is_linux() else "fail",
            detail=distro.name or sys.platform,
            hint="Wifite3 needs Linux wireless stack (mac80211/cfg80211)." if not is_linux() else "",
            group="System",
        )
    )
    report.checks.append(
        Check(
            "Root privileges",
            "ok" if is_root() else "warn",
            detail="running as root" if is_root() else "monitor mode, packet injection and interface changes require root",
            hint="sudo wifite3" if not is_root() else "",
            group="System",
        )
    )
    report.checks.append(
        Check(
            "Distribution",
            "info",
            detail=f"{distro.name} (family: {distro.family})",
            group="System",
        )
    )

    # Core tools ----------------------------------------------------------
    missing_core: list[str] = []
    for tool in CORE_TOOLS:
        path = shutil.which(tool)
        if path:
            report.checks.append(Check(tool, "ok", group="Core tools", detail=path))
        else:
            missing_core.append(tool)
            report.checks.append(
                Check(
                    tool,
                    "fail",
                    group="Core tools",
                    detail="not found in PATH",
                    hint="install the aircrack-ng suite + iw + iproute2",
                )
            )

    # Optional tools ------------------------------------------------------
    missing_optional: list[str] = []
    for tool, purpose in OPTIONAL_TOOLS.items():
        path = shutil.which(tool)
        if path:
            report.checks.append(Check(tool, "ok", group="Optional tools", detail=f"{path} — {purpose}"))
        else:
            missing_optional.append(tool)
            report.checks.append(
                Check(
                    tool,
                    "info",
                    group="Optional tools",
                    detail=f"missing — {purpose}",
                    hint=f"optional; install `{tool}` to unlock this feature",
                )
            )

    # Python packages -----------------------------------------------------
    for module, package in (
        ("textual", "textual"),
        ("rich", "rich"),
        ("scapy", "scapy"),
        ("chardet", "chardet"),
        ("requests", "requests"),
    ):
        report.checks.append(_python_dependency(module, package))

    # Adapters ------------------------------------------------------------
    adapters = list_adapters()
    report.adapters = adapters
    if not is_linux():
        report.checks.append(
            Check(
                "Wireless adapters",
                "info",
                group="Adapters",
                detail="adapter discovery is only available on Linux",
            )
        )
    elif not adapters:
        report.checks.append(
            Check(
                "Wireless adapters",
                "fail",
                group="Adapters",
                detail="no wireless interface found in /sys/class/net",
                hint="plug in a USB Wi-Fi adapter and check `ip link` / `iw dev`",
            )
        )
    else:
        for adapter in adapters:
            detail = f"{adapter.driver or 'driver?'} · {adapter.mode} · {adapter.capability_text}"
            status = "ok" if adapter.supports_monitor is not False else "warn"
            hint = "" if adapter.supports_monitor is not False else "this radio may not support monitor mode"
            report.checks.append(Check(f"Adapter {adapter.name}", status, group="Adapters", detail=detail, hint=hint))

    # Radio sanity --------------------------------------------------------
    if is_linux():
        blocked = system.rfkill_blocked()
        report.checks.append(
            Check(
                "rfkill",
                "warn" if blocked else "ok",
                group="Radio",
                detail="Wi-Fi is blocked by rfkill" if blocked else "Wi-Fi is not rfkill-blocked",
                hint="sudo rfkill unblock wifi" if blocked else "",
            )
        )
        if system.network_manager_running():
            report.checks.append(
                Check(
                    "NetworkManager / wpa_supplicant",
                    "warn",
                    group="Radio",
                    detail="running — they may fight monitor mode or reconnect the card",
                    hint="Wifite3 stops conflicting processes when needed; `--kill` forces it",
                )
            )

    # Data files ----------------------------------------------------------
    from .util.paths import find_data_file, wordlist_paths

    if find_data_file("ieee-oui.txt"):
        report.checks.append(Check("OUI database", "ok", group="Data", detail="ieee-oui.txt available"))
    else:
        report.checks.append(
            Check("OUI database", "warn", group="Data", detail="ieee-oui.txt not found", hint="sudo wifite3 --update-db")
        )

    wordlists = wordlist_paths()
    if wordlists:
        report.checks.append(
            Check("Wordlist", "ok", group="Data", detail=f"{len(wordlists)} wordlist(s); first: {wordlists[0]}")
        )
    else:
        report.checks.append(
            Check("Wordlist", "warn", group="Data", detail="no wordlist found", hint="pass --wordlist /path/to/list.txt")
        )

    # Install command -----------------------------------------------------
    if missing_core:
        report.install_cmd = install_command(distro.family, include_optional=False)
    elif missing_optional:
        report.install_cmd = install_command(distro.family, include_optional=True)

    if deep and is_linux() and adapters:
        adapter = adapters[0]
        tool = shutil.which("aireplay-ng")
        if tool:
            code, output = system.run_command(["aireplay-ng", "--test", adapter.name], timeout=20)
            report.checks.append(
                Check(
                    "Injection self-test",
                    "ok" if code == 0 else "warn",
                    group="Deep check",
                    detail=(output or "").strip().splitlines()[-1] if output else "no output",
                    hint="" if code == 0 else f"run manually: sudo aireplay-ng --test {adapter.name}",
                )
            )

    return report


def print_report(report: Report) -> None:
    """Pretty-print the report without depending on Textual."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console(highlight=False)
    console.print(
        Panel.fit(
            "[bold cyan]Wifite3 system doctor[/bold cyan]\n"
            f"[dim]host:[/dim] {report.distro.name}   "
            f"[dim]kernel:[/dim] {system.kernel_version()}   "
            f"[dim]python:[/dim] {system.python_version()}",
            border_style="cyan",
        )
    )

    groups: dict[str, list[Check]] = {}
    for check in report.checks:
        groups.setdefault(check.group, []).append(check)

    styles = {"ok": "green", "warn": "yellow", "fail": "red", "info": "dim"}
    for group, checks in groups.items():
        table = Table(title=group, title_style="bold white", box=None, pad_edge=False)
        table.add_column("", width=2)
        table.add_column("Check", style="white", no_wrap=True)
        table.add_column("Detail", style="dim")
        table.add_column("Fix", style="cyan")
        for check in checks:
            table.add_row(
                f"[{styles.get(check.status, 'white')}]{check.icon}[/]",
                check.title,
                check.detail,
                check.hint,
            )
        console.print(table)

    if report.install_cmd:
        console.print()
        console.print("[bold]Install missing packages:[/bold]")
        console.print("  [bold green]" + " ".join(report.install_cmd) + "[/bold green]")
        note = PACKAGES.get(report.distro.family, {}).get("note")
        if note:
            console.print(f"  [dim]{note}[/dim]")

    console.print()
    if report.ready:
        console.print("[bold green]✔ System is ready for Wifite3.[/bold green] Run [bold]sudo wifite3[/bold].")
    else:
        console.print(
            "[bold red]✘ Missing required components.[/bold red] "
            "Use the install command above, then run [bold]wifite3 --doctor[/bold] again."
        )
    console.print("[dim]Optional tools only unlock extra attacks; they do not block scanning.[/dim]")


def main(deep: bool = False) -> int:
    report = collect_report(deep=deep)
    print_report(report)
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main(deep="--deep" in sys.argv))
