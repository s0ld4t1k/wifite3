#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Modal screens and the live attack screen for Wifite3."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

from ..bridge import AttackRunner, TAP, InputBridge, install_output_tap
from .widgets import power_dbm, ssid_text, target_details, timestamp


# --------------------------------------------------------------------------- #
# Small modals
# --------------------------------------------------------------------------- #


class InputScreen(ModalScreen[str | None]):
    """Used for engine prompts coming from a worker thread."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, default: str = "") -> None:
        super().__init__()
        self.prompt = prompt or "Input required"
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="input-dialog"):
            yield Label(escape(self.prompt), id="input-label")
            yield Input(value=self.default, id="input-field", select_on_focus=True)
            with Horizontal(classes="dialog-buttons"):
                yield Button("OK", variant="primary", id="input-ok")
                yield Button("Cancel", id="input-cancel")

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "input-ok":
            self.dismiss(self.query_one("#input-field", Input).value)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "no", "No")]

    def __init__(self, question: str, yes: str = "Yes", no: str = "No") -> None:
        super().__init__()
        self.question = question
        self.yes = yes
        self.no = no

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self.question, id="confirm-label")
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.yes, variant="error", id="confirm-yes")
                yield Button(self.no, variant="default", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_no(self) -> None:
        self.dismiss(False)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close"), ("?", "close", "Close")]

    TEXT = """
[bold cyan]Wifite3 — quick keys[/bold cyan]

[bold]Scanning[/bold]
  [cyan]s[/cyan]      start / stop scan          [cyan]r[/cyan]      refresh adapters
  [cyan]f[/cyan]      filter targets             [cyan]esc[/cyan]    clear filter
  [cyan]space[/cyan]  select / deselect target   [cyan]a[/cyan]      select all visible
  [cyan]n[/cyan]      clear selection            [cyan]enter[/cyan]  attack selected
  [cyan]d[/cyan]      target details             [cyan]?[/cyan]      this help
  [cyan]ctrl+p[/cyan] command palette            [cyan]q[/cyan]      quit

[bold]Attack screen[/bold]
  [cyan]s[/cyan]      stop attack                [cyan]esc[/cyan]    back (asks to stop)

[bold]Columns[/bold]
  Click a table header to sort. Selected target is marked with ●.

[bold]Notes[/bold]
  Use [cyan]--demo[/cyan] to explore the interface without a Wi-Fi card.
  Run [cyan]sudo wifite3 --doctor[/cyan] if something is missing.
"""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-dialog"):
            yield Static(self.TEXT, id="help-text")
            yield Button("Close", variant="primary", id="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


@dataclass
class DoctorRow:
    icon: str
    status: str
    group: str
    check: str
    detail: str
    hint: str


class DoctorScreen(Screen[None]):
    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def __init__(self, deep: bool = False) -> None:
        super().__init__()
        self.deep = deep
        self.report = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="doctor-wrap"):
            yield Static("System doctor", id="doctor-title")
            yield Static("Checking host, tools and adapters…", id="doctor-summary")
            yield DataTable(id="doctor-table", zebra_stripes=True)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Re-check", id="doctor-refresh")
                yield Button("Deep check", id="doctor-deep")
                yield Button("Close", variant="primary", id="doctor-close")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.add_columns(" ", "Group", "Check", "Detail", "Fix")
        table.cursor_type = "row"
        self.run_checks()

    def _post(self, callback, *args) -> None:
        try:
            self.app.call_from_thread(callback, *args)
        except Exception:
            pass

    @work(thread=True, exclusive=True, group="doctor")
    def run_checks(self) -> None:
        from ..doctor import collect_report

        report = collect_report(deep=self.deep)
        self._post(self.show_report, report)

    def show_report(self, report) -> None:
        self.report = report
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        styles = {"ok": "green", "warn": "yellow", "fail": "red", "info": "dim"}
        for check in report.checks:
            table.add_row(
                Text(check.icon, style=styles.get(check.status, "white")),
                Text(check.group, style="dim"),
                Text(check.title, style="white"),
                Text(check.detail or "", style="dim"),
                Text(check.hint or "", style="cyan"),
            )
        if report.ready:
            summary = (
                f"[bold green]✔ ready[/]  ·  {report.distro.name}  ·  "
                f"{len(report.adapters)} adapter(s)"
            )
        else:
            summary = (
                f"[bold red]✘ {len(report.failures)} blocking issue(s)[/]  ·  "
                f"{report.distro.name}"
            )
        if report.warnings:
            summary += f"  ·  [yellow]{len(report.warnings)} warning(s)[/]"
        self.query_one("#doctor-summary", Static).update(summary)
        if report.install_cmd:
            self.query_one("#doctor-summary", Static).update(
                summary
                + "\n[dim]Install:[/] [bold green]"
                + " ".join(report.install_cmd)
                + "[/bold green]"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "doctor-close":
            self.dismiss(None)
        elif event.button.id == "doctor-refresh":
            self.deep = False
            self.run_checks()
        elif event.button.id == "doctor-deep":
            self.deep = True
            self.run_checks()

    def action_close(self) -> None:
        self.dismiss(None)


class DetailsScreen(ModalScreen[None]):
    """Full target inspection, including every associated client."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("d", "close", "Close"),
    ]

    def __init__(self, target: object, selected: bool = False) -> None:
        super().__init__()
        self.target = target
        self.selected = selected

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="details-dialog"):
            yield Static(target_details(self.target, self.selected), id="details-text")
            yield Static("Associated clients", classes="section-title")
            yield DataTable(id="details-clients", zebra_stripes=True)
            yield Button("Close", variant="primary", id="details-close")

    def on_mount(self) -> None:
        table = self.query_one("#details-clients", DataTable)
        table.add_columns("Station", "Power", "Packets", "BSSID")
        table.cursor_type = "row"
        clients = getattr(self.target, "clients", []) or []
        for client in clients:
            table.add_row(
                Text(getattr(client, "station", "?"), style="cyan"),
                Text(f"{getattr(client, 'power', 0)} dBm", style="white"),
                Text(str(getattr(client, "packets", 0)), style="dim"),
                Text(getattr(client, "bssid", "?"), style="dim"),
            )
        if not clients:
            table.add_row(Text("no associated clients seen", style="dim"), "", "", "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


# --------------------------------------------------------------------------- #
# Attack screen
# --------------------------------------------------------------------------- #


@dataclass
class TargetProgress:
    bssid: str
    essid: str
    status: str = "queued"
    phase: str = "waiting"
    note: str = ""


class AttackScreen(Screen[None]):
    BINDINGS = [
        Binding("s", "stop", "Stop attack"),
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back", show=False),
        # Shadow dashboard bindings so the footer stays relevant here.
        Binding("space", "noop", "", show=False),
        Binding("a", "noop", "", show=False),
        Binding("n", "noop", "", show=False),
        Binding("f", "noop", "", show=False),
        Binding("d", "noop", "", show=False),
        Binding("r", "noop", "", show=False),
        Binding("enter", "noop", "", show=False),
        Binding("question_mark", "noop", "", show=False),
    ]

    def __init__(self, targets: list, demo: bool = False, options=None) -> None:
        super().__init__()
        self.targets = targets
        self.demo = demo
        self.options = options
        self.runner: AttackRunner | None = None
        self.stop_event = threading.Event()
        self.finished = False
        self.rows: dict[str, TargetProgress] = {}
        self._line_count = 0

    # -- layout ----------------------------------------------------------- #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="attack-wrap"):
            with Vertical(id="attack-head"):
                yield Static("ATTACK IN PROGRESS", id="attack-title")
                yield Static("", id="attack-subtitle")
                yield ProgressBar(total=max(1, len(self.targets)), show_eta=False, id="attack-progress")
            with Horizontal(id="attack-middle"):
                with Vertical(id="attack-targets-wrap"):
                    yield Static("Targets", classes="section-title")
                    yield DataTable(id="attack-targets", zebra_stripes=True)
                with Vertical(id="attack-log-wrap"):
                    yield Static("Live engine output", classes="section-title")
                    yield RichLog(id="attack-log", max_lines=3000, wrap=True, markup=False)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Stop attack", variant="error", id="attack-stop")
                yield Button("Back", variant="primary", id="attack-back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#attack-targets", DataTable)
        table.add_column("Status", key="status")
        table.add_column("Target", key="target")
        table.add_column("Phase", key="phase")
        table.add_column("Note", key="note")
        table.cursor_type = "row"
        for target in self.targets:
            essid = target.essid if getattr(target, "essid_known", False) else "(hidden)"
            progress = TargetProgress(
                bssid=target.bssid,
                essid=essid or "(hidden)",
            )
            self.rows[target.bssid] = progress
            table.add_row(
                Text("…", style="dim"),
                ssid_text(target),
                Text("waiting", style="dim"),
                Text("", style="dim"),
                key=target.bssid,
            )
        mode = "demo simulation" if self.demo else "engine"
        self.query_one("#attack-subtitle", Static).update(
            f"[dim]{len(self.targets)} target(s) · {mode} · "
            "press [bold]s[/bold] to stop[/dim]"
        )
        install_output_tap()
        self.query_one("#attack-log", RichLog).write(Text(f"[{timestamp()}] attack session started", style="dim"))
        if self.demo:
            self.run_demo()
        else:
            self.run_real_attack()

    def on_unmount(self) -> None:
        self.stop_event.set()
        if self.runner:
            self.runner.stop()

    def _post(self, callback, *args) -> None:
        """call_from_thread that is safe after the screen/app is gone."""
        try:
            self.app.call_from_thread(callback, *args)
        except Exception:
            pass

    # -- real engine ------------------------------------------------------ #

    @work(thread=True, exclusive=True, group="attack")
    def run_real_attack(self) -> None:
        def on_line(line: str) -> None:
            self._post(self.log_line, line)

        def on_finished(ok: bool, message: str) -> None:
            self._post(self.finish, ok, message)

        runner = AttackRunner(
            self.targets,
            on_line=on_line,
            on_finished=on_finished,
            stop_event=self.stop_event,
            options=self.options,
        )
        self.runner = runner
        runner.run()

    def log_line(self, line: str) -> None:
        if not self.is_attached:
            return
        self._line_count += 1
        log = self.query_one("#attack-log", RichLog)
        log.write(Text(line, style=self._line_style(line)))
        self._track_target(line)

    @staticmethod
    def _line_style(line: str) -> str:
        low = line.lower()
        if "error" in low or "failed" in low or "unable" in low:
            return "red"
        if "cracked" in low or "key found" in low or "password" in low and "found" in low:
            return "bold green"
        if "handshake" in low and ("captur" in low or "found" in low):
            return "bold cyan"
        if line.strip().startswith("["):
            return "dim"
        return "white"

    def _track_target(self, line: str) -> None:
        bssid_match = re.search(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", line)
        matched = None
        for bssid, progress in self.rows.items():
            if bssid_match and bssid_match.group(0).lower() == bssid.lower():
                matched = progress
                break
            if progress.essid and progress.essid.lower() in line.lower() and len(progress.essid) > 3:
                matched = progress
                break
        if not matched:
            return
        low = line.lower()
        if "starting attacks against" in low:
            matched.status, matched.phase = "running", "starting"
        elif "pmkid" in low and ("captur" in low or "attack" in low):
            matched.status, matched.phase = "running", "PMKID"
        elif "deauth" in low:
            matched.status, matched.phase = "running", "deauth"
        elif "handshake" in low and ("captur" in low or "found" in low):
            matched.status, matched.phase = "running", "handshake ✓"
        elif "crack" in low or "wordlist" in low:
            matched.status, matched.phase = "running", "cracking"
        elif "key found" in low or "cracked" in low:
            matched.status, matched.phase = "done", "cracked ✓"
            matched.note = "KEY FOUND"
        elif "failed" in low or "unable" in low:
            matched.status, matched.phase = "failed", "failed"
        matched.note = line[:90]
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        table = self.query_one("#attack-targets", DataTable)
        icons = {
            "queued": ("…", "dim"),
            "running": ("▶", "cyan"),
            "done": ("✔", "green"),
            "failed": ("✘", "red"),
        }
        for bssid, progress in self.rows.items():
            icon, style = icons.get(progress.status, ("…", "dim"))
            try:
                table.update_cell(bssid, "status", Text(icon, style=style))
                table.update_cell(bssid, "phase", Text(progress.phase, style=style))
                table.update_cell(bssid, "note", Text(progress.note, style="dim"))
            except Exception:
                pass

    def finish(self, ok: bool, message: str) -> None:
        self.finished = True
        self.stop_event.set()
        if not self.is_attached:
            return
        log = self.query_one("#attack-log", RichLog)
        log.write(Text(f"[{timestamp()}] {message}", style="bold green" if ok else "bold yellow"))
        self.query_one("#attack-title", Static).update(
            "[bold green]ATTACK FINISHED[/]" if ok else "[bold yellow]ATTACK STOPPED[/]"
        )
        self.query_one("#attack-stop", Button).disabled = True

    # -- demo engine ------------------------------------------------------ #

    @work(thread=True, exclusive=True, group="attack-demo")
    def run_demo(self) -> None:
        phases = [
            ("PMKID", "requesting PMKID from RSN information element"),
            ("deauth", "sending deauth burst to force reassociation"),
            ("handshake", "EAPOL 4-way handshake captured"),
            ("cracking", "hashcat / aircrack-ng against wordlist"),
        ]
        for index, target in enumerate(self.targets, start=1):
            if self.stop_event.is_set():
                break
            progress = self.rows[target.bssid]
            self._post(self._demo_mark, target.bssid, "running", "starting", "attack start")
            for phase, message in phases:
                if self.stop_event.is_set():
                    break
                self._post(
                    self.log_line,
                    f"[+] {target.bssid} ({progress.essid}) {phase}: {message}",
                )
                if phase == "PMKID":
                    self._post(self._demo_mark, target.bssid, "running", "PMKID", message)
                elif phase == "deauth":
                    self._post(self._demo_mark, target.bssid, "running", "deauth", message)
                elif phase == "handshake":
                    self._post(
                        self._demo_mark, target.bssid, "running", "handshake ✓", message
                    )
                else:
                    self._post(self._demo_mark, target.bssid, "running", "cracking", message)
                self.stop_event.wait(0.55)
            if self.stop_event.is_set():
                break
            cracked = index % 3 == 1
            if cracked:
                password = ["sunshine", "12345678", "qwerty2024"][index % 3]
                self._post(
                    self.log_line,
                    f"[+] KEY FOUND! {target.bssid} ({progress.essid}) password: {password}",
                )
                self._post(
                    self._demo_mark, target.bssid, "done", "cracked ✓", f"password: {password}"
                )
            else:
                self._post(
                    self.log_line,
                    f"[-] {target.bssid} ({progress.essid}) no password in wordlist — handshake saved",
                )
                self._post(
                    self._demo_mark, target.bssid, "failed", "no match", "handshake saved to hs/"
                )
            self._post(self._advance_progress, 1)
        if self.stop_event.is_set():
            self._post(self.finish, False, "Stopped by user")
        else:
            self._post(self.finish, True, "Demo attack finished")

    def _demo_mark(self, bssid: str, status: str, phase: str, note: str) -> None:
        if bssid in self.rows:
            self.rows[bssid].status = status
            self.rows[bssid].phase = phase
            self.rows[bssid].note = note
            self._refresh_rows()

    def _advance_progress(self, amount: int) -> None:
        try:
            self.query_one("#attack-progress", ProgressBar).advance(amount)
        except Exception:
            pass

    # -- actions ---------------------------------------------------------- #

    def action_noop(self) -> None:
        pass

    def action_stop(self) -> None:
        if self.finished:
            return
        self.stop_event.set()
        if self.runner:
            self.runner.stop()
        self.query_one("#attack-title", Static).update("[bold yellow]STOPPING…[/]")
        self.query_one("#attack-stop", Button).disabled = True

    def action_back(self) -> None:
        if not self.finished and not self.stop_event.is_set():
            self.app.push_screen(
                ConfirmScreen("Stop the attack and go back?", yes="Stop & back"),
                callback=self._confirm_back,
            )
        else:
            self.dismiss(None)

    def _confirm_back(self, confirmed: bool | None) -> None:
        if confirmed:
            self.action_stop()
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "attack-stop":
            self.action_stop()
        elif event.button.id == "attack-back":
            self.action_back()
